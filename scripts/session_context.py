#!/usr/bin/env python3
"""cfm mode — the session-side half of the orchestrator rule.

The guard (guard_check.py) is the mechanism: in `mode: enforced` it refuses
the main session's writes to product code. This script is the prose that
arrives with it, so a plain "add a null check" typed into a cfm repo is
routed through a /cfm:* skill instead of edited in place. Claude Code's
permission modes are fixed and no hook can switch them, so cfm mode is a
layer on top of whichever one is active, built from what a plugin can do:

  SessionStart      → the doctrine, the routing table, the human-only gates
                      and a one-line state summary, as additionalContext.
                      Fires on startup, resume, clear and compact, so the
                      doctrine survives compaction.
  UserPromptSubmit  → a two-line reminder for prompts that are not already
                      a slash command.
  StatusLine        → one line for Claude Code's status bar (opt-in, wired
                      by gen_settings.py --statusline).

Reads the hook event JSON on stdin; prints the hook output JSON (or the
status-line text) on stdout; exits 0 always. Nothing is printed when the
project has no config or `mode` is off. Fail-open on any internal error:
context is grace, never guarantee — the guard holds the line.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cfm_config  # noqa: E402

# request shape → the skill that owns it. Every name must exist in skills/
# (tests/test_coherence.py pins this).
ROUTES = (
    ("a feature or change to build", "plan"),
    ("implement, continue or resume a phase", "implement-phase"),
    ("something broken, failing, throwing or slow", "diagnose"),
    ("review changes", "code-review"),
    ("a workflow setting or a coding rule", "configure"),
    ("this mode itself", "mode"),
    ("where things stand, what to do next", "status"),
    ("capture work without planning it yet", "create-task"),
    ("an idea to think through", "brainstorm"),
    ("the setup looks wrong", "doctor"),
)

HUMAN_GATES = (
    "the full test suite (verify_full)",
    "git per the configured level",
    "starting the next phase",
)


def _mode(config):
    mode = (config or {}).get("mode")
    return mode if mode in cfm_config.MODES else cfm_config.DEFAULTS["mode"]


def _state_summary(project_dir, config):
    """One or two lines from the ledger, or '' when nothing is in flight."""
    import state as state_mod
    state, error = state_mod.load_state(state_mod.state_path(project_dir, config))
    if error or not isinstance(state, dict):
        return "The state file is unreadable — run /cfm:doctor before any phase work."
    phase = state.get("phase") if isinstance(state.get("phase"), dict) else {}
    lines = []
    if phase.get("status") == "in-flight":
        current = (state.get("cursor") or {}).get("current_layer")
        where = f", at layer '{current}'" if current else ""
        lines.append(
            f"Phase '{phase.get('id')}' ({phase.get('description') or 'no description'}) "
            f"is IN-FLIGHT{where} — `/cfm:implement-phase` with no argument resumes it "
            f"from the ledger.")
    elif phase.get("status") == "complete":
        lines.append(f"Last phase '{phase.get('id')}' is complete; the next one starts "
                     f"only when the human names it.")
    else:
        lines.append("No phase in flight — `/cfm:plan` a feature, or "
                     "`/cfm:implement-phase <description>` to start one.")
    pending = state.get("pending_gates")
    if isinstance(pending, list) and pending:
        lines.append("Pending human gates: " + ", ".join(str(g) for g in pending) + ".")
    questions = state.get("open_questions")
    if isinstance(questions, list) and questions:
        lines.append(f"{len(questions)} open question(s) are waiting on the human.")
    return "\n".join(lines)


def session_start_context(project_dir, config, errors):
    mode = _mode(config)
    level = ((config or {}).get("git") or {}).get("level") or cfm_config.DEFAULTS["git"]["level"]
    out = [f"# cfm mode: {mode.upper()}", ""]
    out.append(
        "This repository is initialized with cfm (`.cfm-workflow.yml`). Every "
        "session here runs in cfm mode, on top of whichever Claude Code permission "
        "mode is active (plan, auto-accept, manual).")
    out.append("")
    out.append(
        "You are the ORCHESTRATOR. You plan, dispatch the cfm agents, verify their "
        "results, and keep the ledgers. You never write product code, tests, or "
        "scaffold yourself — no \"small change\" exception. Every line of product "
        "code comes from a dispatched agent.")
    if mode == "enforced":
        out.append(
            "The PreToolUse guard enforces this: an Edit, Write, or shell write from "
            "this session is refused unless it targets a workflow file (the cfm "
            "config, .claude/, .cfm/, docs/, CLAUDE.md, the rules file, the "
            "glossary, the progress log). A refusal is not an error to work around; "
            "it means dispatch the coder.")
    else:
        out.append(
            "The mode is advisory: the guard will not refuse the write, and the rule "
            "still stands.")
    out.append("")
    out.append("Route every request through the cfm skill that owns it:")
    for shape, skill in ROUTES:
        out.append(f"- {shape} → `/cfm:{skill}`")
    out.append(
        "Questions, explanations, and reading code need no skill — answer them "
        "directly. A request that needs a file changed is a dispatch, never an edit.")
    out.append("")
    out.append("Human-only gates, in every profile: " + "; ".join(HUMAN_GATES)
               + f" (git level {level}).")
    out.append("")
    out.append(_state_summary(project_dir, config))
    if errors:
        out.append("")
        out.append(f"The config has {len(errors)} validation error(s) — the guard "
                   f"enforces its defaults meanwhile; run /cfm:doctor.")
    out.append("")
    out.append("Change the mode with `/cfm:mode enforced|advisory|off` — a config "
               "diff the human approves.")
    return "\n".join(out)


def prompt_context(config):
    mode = _mode(config)
    teeth = ("the guard refuses product edits from this session"
             if mode == "enforced" else "advisory: the rule stands, the guard is silent")
    return (
        f"cfm mode ({mode}): route this through the matching /cfm:* skill — build → "
        f"/cfm:plan then /cfm:implement-phase, broken → /cfm:diagnose, review → "
        f"/cfm:code-review, settings → /cfm:configure, status → /cfm:status. Answer "
        f"questions directly; a file change is a dispatch, never an edit ({teeth})."
    )


def status_line(event, project_dir, config):
    model = (event.get("model") or {}).get("display_name") if isinstance(
        event.get("model"), dict) else None
    tail = f"[{model}]" if model else ""
    if config is None:
        return f"{tail} {os.path.basename(project_dir.rstrip(os.sep))}".strip()
    mode = _mode(config)
    parts = [f"cfm ▸ {mode}"]
    try:
        import state as state_mod
        state, error = state_mod.load_state(state_mod.state_path(project_dir, config))
    except Exception:  # noqa: BLE001 — a status line never fails loudly
        state, error = None, "x"
    if error or not isinstance(state, dict):
        parts.append("state unreadable")
    else:
        phase = state.get("phase") if isinstance(state.get("phase"), dict) else {}
        if phase.get("status") == "in-flight":
            current = (state.get("cursor") or {}).get("current_layer")
            parts.append(f"phase {phase.get('id')} in-flight" + (f" @ {current}" if current else ""))
        elif phase.get("status") == "complete":
            parts.append(f"phase {phase.get('id')} complete")
        else:
            parts.append("no phase")
        pending = state.get("pending_gates")
        if isinstance(pending, list) and pending:
            parts.append("gate: " + ", ".join(str(g) for g in pending))
    if tail:
        parts.append(tail)
    return " ▸ ".join(parts)


def _read_event():
    try:
        raw = sys.stdin.read()
    except OSError:
        return {}
    if not raw.strip():
        return {}
    try:
        event = json.loads(raw)
    except ValueError:
        return {}
    return event if isinstance(event, dict) else {}


def _project_dir(event, explicit):
    if explicit:
        return os.path.abspath(explicit)
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return os.path.abspath(env)
    workspace = event.get("workspace") if isinstance(event.get("workspace"), dict) else {}
    for candidate in (workspace.get("project_dir"), event.get("cwd")):
        if isinstance(candidate, str) and candidate:
            return os.path.abspath(candidate)
    return os.getcwd()


def main(argv=None):
    parser = argparse.ArgumentParser(description="cfm mode — session context")
    parser.add_argument("--event", required=True,
                        choices=("SessionStart", "UserPromptSubmit", "StatusLine"))
    parser.add_argument("--project-dir", default=None)
    args = parser.parse_args(argv)
    event = _read_event()
    project_dir = _project_dir(event, args.project_dir)

    if not os.path.isfile(os.path.join(project_dir, cfm_config.CONFIG_FILE)):
        if args.event == "StatusLine":
            print(status_line(event, project_dir, None))
        return 0
    config, errors, _warnings = cfm_config.load(project_dir)
    if not isinstance(config, dict):
        config = {}
    if args.event == "StatusLine":
        print(status_line(event, project_dir, config))
        return 0
    if _mode(config) == "off":
        return 0
    if args.event == "SessionStart":
        context = session_start_context(project_dir, config, errors)
    else:
        prompt = event.get("prompt")
        if isinstance(prompt, str) and prompt.lstrip().startswith("/"):
            return 0  # a slash command already names its skill
        context = prompt_context(config)
    json.dump({"hookSpecificOutput": {"hookEventName": args.event,
                                      "additionalContext": context}}, sys.stdout)
    print()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 — context is grace, never guarantee
        print(f"cfm session context: internal error, no context injected ({exc})",
              file=sys.stderr)
        sys.exit(0)
