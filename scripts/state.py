#!/usr/bin/env python3
"""cfm state — the workflow ledger, written by a script instead of by hand.

The state file (config `state_file`, default .cfm/state.json) is what
`/cfm:implement-phase` resumes from in a fresh session. Its schema is v1,
documented in skills/implement-phase/references/state-and-resume.md; this
module is the single writer skills call at every boundary, so the file is
always schema-valid, always written atomically, and unknown fields survive
every rewrite. Doctor check 9 validates with the same function.

Usage: python3 state.py [--project-dir DIR] <command> [options]

  show                          print the state JSON (pure read)
  validate                      exit 1 with errors when the state is malformed
  init      --id ID --description TEXT --layers L... [--plan PATH]
  dispatch  --agent A [--layer L]
  record    --agent A --purpose TEXT --model M [--layer L] [--total N]
            [--input N] [--output N] [--duration-ms N] [--usage BLOCK] [--files F...]
            [--tests-written T...] [--tests-passed T...]
  gate      --agent A --verdict pass|fail [--layer L]
  rollback  --layer L --to coder-pending|tests-pending
  carry     ITEM...
  question  --ask TEXT --asked-by CMD | --resolve --asked-by CMD --outcome accepted|declined
  tracker   [--provider P] [--last-sync TEXT] [--bind KEY=VALUE...]
  note      --key K --value TEXT   free-form phase notes (diagnose's red
                                   command, hypotheses, debug marker)
  complete  [--gates G...]      mark the phase complete, set the human gates
                                (default: the implementation gates; diagnose
                                passes `plan-fix`, since it leaves no diff)
  abandon                       mark the phase abandoned
  report                        the phase-gate token chart (stacked bars), as markdown

Every mutating command exits 1 and writes nothing when the resulting state
would fail validation.
"""

from __future__ import annotations

import argparse
import copy
import datetime
import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cfm_config

VERSION = 1
PHASE_STATUSES = (None, "in-flight", "complete", "abandoned")
CODER_STATES = ("pending", "dispatched", "done")
GATE_STATES = ("pending", "pass", "fail")
QUESTION_OUTCOMES = (None, "accepted", "declined")
HUMAN_GATES = ["run-verify_full", "git-per-level", "next-phase-approval"]

SEED = {
    "version": VERSION,
    "phase": {"id": None, "status": None},
    "deferred_questions": [],
    "carried_forward": [],
}


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- load / save -----------------------------------------------------------

def state_path(project_dir, config):
    rel = (config or {}).get("state_file") or cfm_config.DEFAULTS["state_file"]
    return os.path.join(project_dir, rel)


def load_state(path):
    """(state, error). A missing file is the seed; an unreadable one is an
    error, never silently replaced."""
    if not os.path.exists(path):
        return copy.deepcopy(SEED), None
    try:
        with open(path, encoding="utf-8") as fh:
            state = json.load(fh)
    except json.JSONDecodeError as exc:
        return None, (f"invalid JSON at line {exc.lineno} column {exc.colno}: "
                      f"{exc.msg}")
    except OSError as exc:
        return None, f"unreadable: {exc}"
    if not isinstance(state, dict):
        return None, f"top level must be a JSON object, got {type(state).__name__}"
    return state, None


def save_state(path, state):
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".state-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


# --- validation ------------------------------------------------------------

def _is_str_list(value):
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def validate_state(state, config=None):
    """(errors, warnings) for a schema v1 state. `config` (when given)
    lets layer and agent names be checked against the roster."""
    errors, warnings = [], []
    if not isinstance(state, dict):
        return [f"top level must be a JSON object, got {type(state).__name__}"], []
    if "version" not in state:
        errors.append("version: missing (expected 1)")
    elif state["version"] != VERSION:
        warnings.append(f"version {state['version']!r} != 1 — written by a different cfm?")

    layer_names = agent_names = None
    if isinstance(config, dict):
        layer_names = {l.get("name") for l in config.get("layers") or []
                       if isinstance(l, dict)}
        agent_names = set((config.get("agents") or {}).keys())

    phase = state.get("phase")
    if not isinstance(phase, dict):
        errors.append("phase: must be an object")
        phase = {}
    status = phase.get("status")
    if status not in PHASE_STATUSES:
        errors.append(f"phase.status: {status!r} is not one of "
                      f"{[s for s in PHASE_STATUSES if s]} or null")
    if status is not None:
        if not isinstance(phase.get("id"), str) or not phase["id"]:
            errors.append("phase.id: must be a non-empty string when a phase exists")
        if not isinstance(phase.get("started"), str):
            errors.append("phase.started: must be an ISO timestamp when a phase exists")
    if status in ("complete", "abandoned") and not isinstance(phase.get("completed"), str):
        errors.append(f"phase.completed: must be set when status is {status}")

    cursor = state.get("cursor")
    if cursor is not None:
        if not isinstance(cursor, dict):
            errors.append("cursor: must be an object")
            cursor = {}
        layers = cursor.get("layers")
        if layers is not None and not isinstance(layers, dict):
            errors.append("cursor.layers: must be an object")
            layers = {}
        for name, layer in (layers or {}).items():
            prefix = f"cursor.layers.{name}"
            if layer_names is not None and name not in layer_names:
                errors.append(f"{prefix}: no layer named '{name}' in config")
            if not isinstance(layer, dict):
                errors.append(f"{prefix}: must be an object")
                continue
            if layer.get("coder") not in CODER_STATES:
                errors.append(f"{prefix}.coder: {layer.get('coder')!r} is not one "
                              f"of {list(CODER_STATES)}")
            tests = layer.get("tests")
            if not isinstance(tests, dict) or not _is_str_list(tests.get("written")) \
                    or not _is_str_list(tests.get("passed")):
                errors.append(f"{prefix}.tests: must be {{written: [..], passed: [..]}}")
            _validate_gates(f"{prefix}.gates", layer.get("gates"), agent_names, errors)
        current = cursor.get("current_layer")
        if current is not None and layers is not None and current not in layers:
            errors.append(f"cursor.current_layer: '{current}' is not in cursor.layers")
        _validate_gates("cursor.phase_gates", cursor.get("phase_gates"), agent_names, errors)

    for field in ("files_touched", "open_questions", "carried_forward", "pending_gates"):
        if field in state and not _is_str_list(state[field]):
            errors.append(f"{field}: must be a list of strings")

    questions = state.get("deferred_questions")
    if questions is not None:
        if not isinstance(questions, list):
            errors.append("deferred_questions: must be a list")
        else:
            for i, entry in enumerate(questions):
                if not isinstance(entry, dict) or not isinstance(entry.get("question"), str) \
                        or not isinstance(entry.get("asked_by"), str):
                    errors.append(f"deferred_questions[{i}]: must be "
                                  f"{{question, asked_by, outcome}}")
                elif entry.get("outcome") not in QUESTION_OUTCOMES:
                    errors.append(f"deferred_questions[{i}].outcome: "
                                  f"{entry.get('outcome')!r} is not accepted/declined/null")

    tokens = state.get("tokens")
    if tokens is not None:
        if not isinstance(tokens, dict):
            errors.append("tokens: must be an object")
        else:
            if not isinstance(tokens.get("phase_total"), int):
                errors.append("tokens.phase_total: must be an integer")
            dispatches = tokens.get("dispatches")
            if not isinstance(dispatches, list):
                errors.append("tokens.dispatches: must be a list")
            else:
                for i, d in enumerate(dispatches):
                    if not isinstance(d, dict) or not isinstance(d.get("agent"), str):
                        errors.append(f"tokens.dispatches[{i}]: must name an agent")
                        continue
                    for field in ("input_tokens", "output_tokens", "total_tokens",
                                  "duration_ms"):
                        if d.get(field) is not None and not isinstance(d[field], int):
                            errors.append(f"tokens.dispatches[{i}].{field}: "
                                          f"must be an integer or null")

    notes = state.get("notes")
    if notes is not None and (not isinstance(notes, dict)
                              or not all(isinstance(v, str) for v in notes.values())):
        errors.append("notes: must be an object of strings")

    tracker = state.get("tracker")
    if tracker is not None:
        if not isinstance(tracker, dict):
            errors.append("tracker: must be an object")
        elif tracker.get("tasks") is not None and not isinstance(tracker["tasks"], dict):
            errors.append("tracker.tasks: must be an object")
    return errors, warnings


def _validate_gates(prefix, gates, agent_names, errors):
    if gates is None:
        return
    if not isinstance(gates, dict):
        errors.append(f"{prefix}: must be an object")
        return
    for agent, verdict in gates.items():
        if agent_names is not None and agent not in agent_names:
            errors.append(f"{prefix}.{agent}: no agent named '{agent}' in config")
        if verdict not in GATE_STATES:
            errors.append(f"{prefix}.{agent}: {verdict!r} is not one of {list(GATE_STATES)}")


# --- mutations -------------------------------------------------------------

def _layer(state, name):
    cursor = state.setdefault("cursor", {})
    layers = cursor.setdefault("layers", {})
    return layers.setdefault(name, {
        "coder": "pending", "tests": {"written": [], "passed": []}, "gates": {},
    })


def _reset_gates(state):
    cursor = state.setdefault("cursor", {})
    for agent in cursor.get("phase_gates") or {}:
        cursor["phase_gates"][agent] = "pending"
    for layer in (cursor.get("layers") or {}).values():
        for agent in layer.get("gates") or {}:
            layer["gates"][agent] = "pending"


def _extend_unique(target, items):
    for item in items:
        if item not in target:
            target.append(item)


def cmd_init(state, args, config):
    phase = state.get("phase") or {}
    if phase.get("status") == "in-flight":
        raise SystemExit(
            f"error: phase '{phase.get('id')}' is in flight — resume it with "
            f"/cfm:implement-phase, or `state.py abandon` it first"
        )
    state["phase"] = {
        "id": args.id, "description": args.description, "plan": args.plan,
        "status": "in-flight", "started": now(), "completed": None,
    }
    state["cursor"] = {
        "current_layer": args.layers[0],
        "layers": {}, "phase_gates": {},
    }
    for name in args.layers:
        _layer(state, name)
    state["files_touched"] = []
    state["open_questions"] = []
    state["tokens"] = {"phase_total": 0, "dispatches": []}
    state["pending_gates"] = []
    state.setdefault("carried_forward", [])
    state.setdefault("deferred_questions", [])
    state.setdefault("tracker", {"provider": None, "last_sync": None, "tasks": {}})


def _require_phase(state):
    if (state.get("phase") or {}).get("status") != "in-flight":
        raise SystemExit("error: no phase in flight — run `state.py init` first")


def cmd_dispatch(state, args, config):
    _require_phase(state)
    if args.layer:
        state["cursor"]["current_layer"] = args.layer
        if args.agent == "coder":
            _layer(state, args.layer)["coder"] = "dispatched"


def _usage_tag(text, *tags):
    for tag in tags:
        m = re.search(rf"<{tag}>\s*(\d+)\s*</{tag}>", text or "")
        if m:
            return int(m.group(1))
    return None


def cmd_record(state, args, config):
    _require_phase(state)
    # a background agent's usage arrives in its task-notification <usage>
    # block; explicit flags win over what it carries
    if args.usage:
        if args.total is None:
            args.total = _usage_tag(args.usage, "subagent_tokens", "total_tokens")
        if args.duration_ms is None:
            args.duration_ms = _usage_tag(args.usage, "duration_ms")
    if args.layer:
        layer = _layer(state, args.layer)
        state["cursor"]["current_layer"] = args.layer
        if args.agent == "coder":
            layer["coder"] = "done"
        _extend_unique(layer["tests"]["written"], args.tests_written or [])
        _extend_unique(layer["tests"]["passed"], args.tests_passed or [])
    _extend_unique(state.setdefault("files_touched", []), args.files or [])
    tokens = state.setdefault("tokens", {"phase_total": 0, "dispatches": []})
    tokens["dispatches"].append({
        "agent": args.agent, "model": args.model, "layer": args.layer,
        "purpose": args.purpose, "input_tokens": args.input,
        "output_tokens": args.output, "total_tokens": args.total,
        "duration_ms": args.duration_ms, "finished": args.finished or now(),
    })
    if args.total is not None:
        tokens["phase_total"] = tokens.get("phase_total", 0) + args.total


def cmd_gate(state, args, config):
    _require_phase(state)
    scope = ((config or {}).get("review") or {}).get("scope") or "phase"
    if scope == "layer":
        if not args.layer:
            raise SystemExit("error: review.scope is 'layer' — gate needs --layer")
        _layer(state, args.layer).setdefault("gates", {})[args.agent] = args.verdict
    else:
        state["cursor"].setdefault("phase_gates", {})[args.agent] = args.verdict


def cmd_rollback(state, args, config):
    _require_phase(state)
    layer = _layer(state, args.layer)
    if args.to == "coder-pending":
        layer["coder"] = "pending"
        layer["tests"] = {"written": [], "passed": []}
    else:
        layer["tests"]["passed"] = []
    state["cursor"]["current_layer"] = args.layer
    # a verdict on a diff that has since changed is not a verdict
    _reset_gates(state)


def cmd_carry(state, args, config):
    _extend_unique(state.setdefault("carried_forward", []), args.items)


def cmd_question(state, args, config):
    questions = state.setdefault("deferred_questions", [])
    if args.ask:
        for entry in questions:
            if entry.get("asked_by") == args.asked_by and entry.get("outcome") is None:
                return  # one entry per question, never a duplicate
        questions.append({"question": args.ask, "asked_by": args.asked_by,
                          "outcome": None})
        return
    for entry in questions:
        if entry.get("asked_by") == args.asked_by:
            entry["outcome"] = args.outcome
            return
    raise SystemExit(f"error: no deferred question asked_by '{args.asked_by}'")


def cmd_tracker(state, args, config):
    tracker = state.setdefault("tracker", {"provider": None, "last_sync": None,
                                           "tasks": {}})
    if args.provider is not None:
        tracker["provider"] = args.provider or None
    if args.last_sync is not None:
        tracker["last_sync"] = {"outcome": args.last_sync, "at": now()}
    for binding in args.bind or []:
        key, sep, value = binding.partition("=")
        if not sep:
            raise SystemExit(f"error: --bind takes '<plan>#<phase>=<provider>:<key>', got {binding!r}")
        tracker.setdefault("tasks", {})[key] = value


def cmd_note(state, args, config):
    _require_phase(state)
    state.setdefault("notes", {})[args.key] = args.value


def cmd_complete(state, args, config):
    _require_phase(state)
    state["phase"]["status"] = "complete"
    state["phase"]["completed"] = now()
    state["pending_gates"] = list(args.gates) if args.gates else list(HUMAN_GATES)


def cmd_abandon(state, args, config):
    _require_phase(state)
    state["phase"]["status"] = "abandoned"
    state["phase"]["completed"] = now()


# --- report ----------------------------------------------------------------

def _human(n):
    if n is None:
        return "—"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def _duration(ms):
    if ms is None:
        return "—"
    seconds = int(round(ms / 1000))
    minutes, seconds = divmod(seconds, 60)
    return f"{minutes}m {seconds}s" if minutes else f"{seconds}s"


def _parse_ts(value):
    try:
        return datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return None


BAR_WIDTH = 20
IN_BLOCK, OUT_BLOCK, UNKNOWN_BLOCK = "\U0001F7E6", "\U0001F7E7", "\u2B1C"


def _bar(inp, out, total, scale):
    """A stacked bar: input blocks, then output blocks, then blocks for the
    part of the total whose split was not reported. Length is proportional
    to `total / scale`; any non-zero segment gets at least one block."""
    if not total or not scale:
        return ""
    length = max(1, round(total / scale * BAR_WIDTH))
    segments = [inp or 0, out or 0]
    segments.append(max(0, total - sum(segments)))
    blocks = [round(v / total * length) if v else 0 for v in segments]
    blocks = [max(1, b) if v else 0 for b, v in zip(blocks, segments)]
    while sum(blocks) > length and max(blocks) > 1:
        blocks[blocks.index(max(blocks))] -= 1
    while sum(blocks) < length:
        blocks[blocks.index(max(blocks))] += 1
    return IN_BLOCK * blocks[0] + OUT_BLOCK * blocks[1] + UNKNOWN_BLOCK * blocks[2]


def _padded_bar(*args):
    """`_bar` padded to the full width (each block is two columns wide), so
    the numbers after it line up."""
    bar = _bar(*args)
    return bar + "  " * (BAR_WIDTH - len(bar))


def render_report(state):
    """The phase-gate token chart, in a fenced block: one stacked bar per
    dispatch (input, output, unknown split), scaled to the largest dispatch,
    then a Totals bar over the non-null values ('+' marks a sum with a null
    somewhere) and the phase wall-clock time."""
    dispatches = (state.get("tokens") or {}).get("dispatches") or []
    sums = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    partial = {k: False for k in sums}
    for d in dispatches:
        for key in sums:
            if d.get(key) is None:
                partial[key] = True
            else:
                sums[key] += d[key]
    labels = [f"{d.get('agent', '—')} · {d.get('layer') or d.get('purpose') or '—'}"
              for d in dispatches]
    pad = max([len(label) for label in labels] + [len("Totals")])
    scale = max([d.get("total_tokens") or 0 for d in dispatches] + [0])

    def detail(inp, out, total, marks=("", "", "")):
        return (f"{_human(total)}{marks[2]}  "
                f"(in {_human(inp)}{marks[0]} · out {_human(out)}{marks[1]})")

    lines = ["```", f"{IN_BLOCK} input   {OUT_BLOCK} output   {UNKNOWN_BLOCK} split not reported", ""]
    for label, d in zip(labels, dispatches):
        inp, out, total = d.get("input_tokens"), d.get("output_tokens"), d.get("total_tokens")
        info = detail(inp, out, total) if total is not None else "no token data"
        info += f"  {d.get('model') or '—'} · {_duration(d.get('duration_ms'))}"
        lines.append(f"{label.ljust(pad)}  {_padded_bar(inp, out, total, scale)}  {info}")
    phase = state.get("phase") or {}
    started, completed = _parse_ts(phase.get("started")), _parse_ts(phase.get("completed"))
    if started and completed:
        wall = _duration(int((completed - started).total_seconds() * 1000))
    else:
        wall = "—"
    marks = tuple("+" if partial[k] else ""
                  for k in ("input_tokens", "output_tokens", "total_tokens"))
    total_bar = _padded_bar(sums["input_tokens"], sums["output_tokens"],
                            sums["total_tokens"], sums["total_tokens"])
    lines.append("")
    lines.append(f"{'Totals'.ljust(pad)}  {total_bar}  "
                 f"{detail(sums['input_tokens'], sums['output_tokens'], sums['total_tokens'], marks)}"
                 f"  {len(dispatches)} dispatches · {wall}")
    lines.append("```")
    return "\n".join(lines)


# --- cli -------------------------------------------------------------------

COMMANDS = {
    "init": cmd_init, "dispatch": cmd_dispatch, "record": cmd_record,
    "gate": cmd_gate, "rollback": cmd_rollback, "carry": cmd_carry,
    "question": cmd_question, "tracker": cmd_tracker, "note": cmd_note,
    "complete": cmd_complete, "abandon": cmd_abandon,
}


def build_parser():
    parser = argparse.ArgumentParser(description="cfm state — the workflow ledger")
    parser.add_argument("--project-dir", default=".", help="project root (default: .)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("show", help="print the state JSON")
    sub.add_parser("validate", help="exit 1 with errors when the state is malformed")
    p = sub.add_parser("complete", help="mark the phase complete")
    p.add_argument("--gates", nargs="+", metavar="GATE",
                   help="pending human gates to set (default: the implementation gates)")
    sub.add_parser("abandon", help="mark the phase abandoned")
    sub.add_parser("report", help="the phase-gate token chart (stacked bars) as markdown")

    p = sub.add_parser("init", help="start a phase")
    p.add_argument("--id", required=True)
    p.add_argument("--description", required=True)
    p.add_argument("--plan", default=None)
    p.add_argument("--layers", nargs="+", required=True)

    p = sub.add_parser("dispatch", help="mark a dispatch sent")
    p.add_argument("--agent", required=True)
    p.add_argument("--layer", default=None)

    p = sub.add_parser("record", help="record a dispatch result")
    p.add_argument("--agent", required=True)
    p.add_argument("--layer", default=None)
    p.add_argument("--purpose", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--input", type=int, default=None)
    p.add_argument("--output", type=int, default=None)
    p.add_argument("--total", type=int, default=None)
    p.add_argument("--duration-ms", type=int, default=None)
    p.add_argument("--usage", default=None,
                   help="the <usage> block from the agent's task-notification, verbatim")
    p.add_argument("--finished", default=None)
    p.add_argument("--files", nargs="*", default=[])
    p.add_argument("--tests-written", nargs="*", default=[])
    p.add_argument("--tests-passed", nargs="*", default=[])

    p = sub.add_parser("gate", help="record a review gate verdict")
    p.add_argument("--agent", required=True)
    p.add_argument("--verdict", choices=("pass", "fail"), required=True)
    p.add_argument("--layer", default=None)

    p = sub.add_parser("rollback", help="move the cursor back after reconciliation")
    p.add_argument("--layer", required=True)
    p.add_argument("--to", choices=("coder-pending", "tests-pending"), required=True)

    p = sub.add_parser("carry", help="append carried-forward obligations")
    p.add_argument("items", nargs="+")

    p = sub.add_parser("question", help="defer a question, or resolve one in place")
    p.add_argument("--ask", default=None)
    p.add_argument("--resolve", action="store_true")
    p.add_argument("--asked-by", required=True)
    p.add_argument("--outcome", choices=("accepted", "declined"), default=None)

    p = sub.add_parser("tracker", help="record tracker bookkeeping")
    p.add_argument("--provider", default=None)
    p.add_argument("--last-sync", default=None)
    p.add_argument("--bind", nargs="*", default=[])

    p = sub.add_parser("note", help="record a free-form note on the phase")
    p.add_argument("--key", required=True)
    p.add_argument("--value", required=True)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command == "question":
        if bool(args.ask) == args.resolve:
            print("error: question takes --ask TEXT or --resolve, not both/neither",
                  file=sys.stderr)
            return 1
        if args.resolve and not args.outcome:
            print("error: --resolve needs --outcome accepted|declined", file=sys.stderr)
            return 1

    project_dir = os.path.abspath(args.project_dir)
    config, _errors, _warnings = cfm_config.load(project_dir)
    if not isinstance(config, dict):
        config = None  # a broken config still gets a valid ledger
    path = state_path(project_dir, config)
    state, error = load_state(path)
    rel = os.path.relpath(path, project_dir)
    if error:
        print(f"error: {rel}: {error}", file=sys.stderr)
        return 1

    if args.command == "show":
        json.dump(state, sys.stdout, indent=2)
        print()
        return 0
    if args.command == "validate":
        errors, warnings = validate_state(state, config)
        for w in warnings:
            print(f"warning: {rel}: {w}", file=sys.stderr)
        for e in errors:
            print(f"error: {rel}: {e}", file=sys.stderr)
        return 1 if errors else 0
    if args.command == "report":
        print(render_report(state))
        return 0

    before = copy.deepcopy(state)
    try:
        COMMANDS[args.command](state, args, config)
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        return 1
    errors, _warnings = validate_state(state, config)
    if errors:
        for e in errors:
            print(f"error: refusing to write {rel}: {e}", file=sys.stderr)
        return 1
    if state != before:
        save_state(path, state)
    print(f"{rel}: {args.command} recorded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
