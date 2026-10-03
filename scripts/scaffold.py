#!/usr/bin/env python3
"""cfm scaffold — render the workflow-level scaffold from a VALID config.

Everything deterministic renders here, straight from .cfm-workflow.yml,
so config↔scaffold drift is structurally impossible. Everything
stack-specific (the buildable skeleton, the typed config module) is
dispatched to the coder agent — see skills/init/references/scaffold.md.
Nothing in this script names a package manager, framework, or language.

Existing files are NEVER clobbered: they are left untouched and reported
as "kept" (no --force flag, by design). The one exception is .gitignore,
which is append-only: existing lines are never removed or reordered.

Usage: python3 scaffold.py [--project-dir DIR] [--dry-run] [--date YYYY-MM-DD]
Exit code: 0 rendered (warnings allowed), 1 config invalid or bad flags.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cfm_config

PROVENANCE = (
    "<!-- rendered from .cfm-workflow.yml by cfm scaffold — change the "
    "config, not just this file -->"
)

RULES_SEED = """# Project Rules

Every rule declares its enforcement mechanism — the doctor rejects
toothless rules (hard invariant 3).

## R1. Environment access via the typed config module

Product code reads environment values only through the project's typed
config module — never scattered raw env access, never literals.

**Enforcement:** {r1_enforcement}

## R2. Feature code lives in feature roots

New feature files go under the configured `feature_roots` path for their
layer, nowhere else.

**Enforcement:** {r2_enforcement}
"""


def _enforcement_owner(config, preferred):
    """First ENABLED agent from `preferred`, else the first enabled
    judgment-tier agent, else the first enabled agent, else None.

    Doctor check #6 rejects reviewer(<name>) enforcement whose agent is
    missing or disabled — seeded rules must name a live owner."""
    agents = {
        name: agent
        for name, agent in (config.get("agents") or {}).items()
        if isinstance(agent, dict) and agent.get("enabled") is True
    }
    for name in preferred:
        if name in agents:
            return name
    for name, agent in agents.items():
        if agent.get("tier") == "judgment":
            return name
    return next(iter(agents), None)


def render_rules(config):
    r1 = _enforcement_owner(config, ["security-check", "code-reviewer"])
    r2 = _enforcement_owner(config, ["code-reviewer", "security-check"])
    # no enabled agents at all: fall back to non-reviewer teeth — the guard
    # hook for env access, the lint_arch slot (when configured) for layout
    r1_enforcement = f"reviewer({r1})" if r1 else "hook(guard.sh)"
    if r2:
        r2_enforcement = f"reviewer({r2})"
    elif "lint_arch" in (config.get("commands") or {}):
        r2_enforcement = "lint(lint_arch)"
    else:
        r2_enforcement = "hook(guard.sh)"
    return RULES_SEED.format(
        r1_enforcement=r1_enforcement, r2_enforcement=r2_enforcement
    )

ENV_EXAMPLE = """# .env.example — variable names only, values stay empty — cfm doctor enforces this.
# Add a `NAME=` line in the same change that introduces the variable.
"""

# The project glossary. Every dispatched agent starts cold, so a shared
# vocabulary is what stops each one re-deriving the project's jargon from
# prose. A glossary and nothing else: no implementation detail, no spec.
CONTEXT_SEED = """# Project context

The shared language of this project. Agents read it before they name
anything, so terms here decide what variables, functions, files, and review
findings are called.

Entries are earned: add a term when it is resolved, not in advance. Keep
implementation detail, specs, and scratch notes out — this is a glossary.
Terms crystallize during `/cfm:brainstorm`, `/cfm:plan`, and any session
that resolves what something is actually called.

## Language

<!-- One entry per term:

**Term**:
What it means, in one or two sentences, in terms a domain expert would use.
_Avoid_: the near-synonyms this term replaces, so they stop reappearing.

-->

## Relationships

<!-- How the terms above relate, e.g. "An Order holds many Line Items". -->

## Flagged ambiguities

<!-- A word used for two different things, and how it was resolved. -->
"""

# Schema v1 (see skills/implement-phase/references/state-and-resume.md);
# no in-flight phase, so doctor check 9 stays green.
STATE_SEED = {
    "version": 1,
    "phase": {"id": None, "status": None},
    "deferred_questions": [],
    "carried_forward": [],
}


def _norm(rel):
    return os.path.normpath(rel).replace(os.sep, "/")


def _contained(project_dir, path):
    """True when path (fully symlink-resolved) stays inside project_dir."""
    root = os.path.realpath(project_dir)
    target = os.path.realpath(path)
    try:
        return os.path.commonpath([root, target]) == root
    except ValueError:  # different drives / mixed abs-rel
        return False


def _write_new(path, content):
    """Exclusive create — never follows a pre-existing path or symlink."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(content)


def _layers(config):
    return [
        layer for layer in config.get("layers") or []
        if isinstance(layer, dict) and isinstance(layer.get("path"), str)
    ]


def _command_matrix(config):
    owners = {}
    for name, agent in (config.get("agents") or {}).items():
        if not isinstance(agent, dict):
            continue
        # disabled agents run nothing — matching doctor check 4, they own
        # no slots (the slot falls back to "(unassigned)")
        if agent.get("enabled") is not True:
            continue
        for slot in agent.get("owns_commands") or []:
            if isinstance(slot, str):
                owners.setdefault(slot, []).append(name)
    lines = [
        "## Command matrix",
        "",
        "Single-owner matrix: each slot is run only by its owner agent.",
        "",
        "| Slot | Command | Owner |",
        "|---|---|---|",
    ]
    for slot in config.get("commands") or {}:
        commands = cfm_config.slot_commands(config, slot)
        display = " ; ".join(commands)
        if slot == "verify_full":
            owner = "**HUMAN-ONLY** — agents are banned from running it"
        else:
            owner = ", ".join(owners.get(slot, [])) or "(unassigned)"
        lines.append(f"| {slot} | `{display}` | {owner} |")
    return lines


def _shared_sections(config):
    lines = _command_matrix(config)
    lines += ["", "## Human gates", ""]
    lines += [f"- {gate}" for gate in config.get("human_gates") or []]
    lines += [
        "",
        "## Workflow files",
        "",
        f"- Rules: `{config['rules_file']}`",
        f"- Glossary: `{config['context_file']}` — the project's shared "
        f"language; name things the way it names them",
        f"- Progress log: `{config['progress_log']}` (newest entries first)",
        f"- Workflow state: managed by `/cfm:implement-phase` "
        f"(`{config['state_file']}`)",
    ]
    return lines


def render_root(config):
    layers = _layers(config)
    lines = [
        "# CLAUDE.md",
        "",
        PROVENANCE,
        "",
        "## Project",
        "",
        str(config.get("project_context", "")).strip(),
        "",
    ]
    if (config.get("claude_md") or {}).get("layout") == "router":
        lines += ["## Routing", "", "| Working in | Read first |", "|---|---|"]
        for layer in layers:
            target = _norm(os.path.join(layer["path"], "CLAUDE.md"))
            lines.append(f"| `{layer['path']}` | `{target}` |")
        lines.append("")
    lines += ["## Layers (build order)", ""]
    for i, layer in enumerate(layers, 1):
        lines.append(f"{i}. **{layer.get('name')}** — `{layer['path']}`")
    lines.append("")
    lines += _shared_sections(config)
    return "\n".join(lines) + "\n"


def render_layer(config, layer):
    root_rel = _norm(os.path.relpath("CLAUDE.md", layer["path"]))
    feature_root = (config.get("feature_roots") or {}).get(layer.get("name"))
    lines = [
        f"# {layer.get('name')} — layer guide",
        "",
        PROVENANCE,
        "",
        f"- Layer: **{layer.get('name')}**",
        f"- Path: `{layer['path']}`",
    ]
    if isinstance(feature_root, str):
        lines.append(f"- Feature root: `{feature_root}`")
    lines += [
        "",
        "Project context, the command matrix, and human gates live in the "
        f"root guide: `{root_rel}`. Read it first.",
    ]
    return "\n".join(lines) + "\n"


def render_stub(rel):
    parent = os.path.dirname(rel)
    root_rel = _norm(os.path.relpath("CLAUDE.md", parent or "."))
    return (
        f"# {rel}\n\n{PROVENANCE}\n\n"
        "Listed in claude_md.files, but no configured layer lives at this "
        "path — fix the config via /cfm:configure.\n\n"
        f"Root workflow guide: `{root_rel}`.\n"
    )


def render_progress(date):
    return (
        "# Progress\n\n"
        "<!-- newest entries first — prepend new entries, never append -->\n\n"
        f"## {date} — scaffold rendered [complete]\n\n"
        "- Workflow scaffold rendered from .cfm-workflow.yml by cfm "
        "scaffold.\n\n"
        "### Carried forward\n"
        "- (none)\n"
    )


def plan(config, date, warnings):
    """Ordered list of (relpath, content, reason). .gitignore is separate."""
    items = [("CLAUDE.md", render_root(config), "root workflow guide")]
    planned = {"CLAUDE.md"}

    layers = _layers(config)
    layer_targets = {
        _norm(os.path.join(layer["path"], "CLAUDE.md")): layer
        for layer in layers
    }
    if (config.get("claude_md") or {}).get("layout") == "router":
        for target, layer in layer_targets.items():
            items.append((target, render_layer(config, layer),
                          f"layer guide ({layer.get('name')})"))
            planned.add(target)

    for listed in (config.get("claude_md") or {}).get("files") or []:
        if not isinstance(listed, str):
            continue
        rel = _norm(listed)
        if rel in planned:
            continue
        if rel in layer_targets:  # listed layer file under single layout
            items.append((rel, render_layer(config, layer_targets[rel]),
                          f"layer guide ({layer_targets[rel].get('name')})"))
        else:
            warnings.append(
                f"claude_md.files: '{listed}' does not correspond to the root "
                f"or a configured layer — rendered as a stub; fix via "
                f"/cfm:configure"
            )
            items.append((rel, render_stub(rel),
                          "stub — listed in claude_md.files, no matching layer"))
        planned.add(rel)

    items += [
        (config["rules_file"], render_rules(config),
         "rules seed (2 starter rules, enforcement declared)"),
        (config["context_file"], CONTEXT_SEED,
         "project glossary (empty — terms are earned, not guessed)"),
        (".env.example", ENV_EXAMPLE, "variable names only, no values"),
        (config["progress_log"], render_progress(date),
         "progress ledger (newest first, Carried forward)"),
        (config["state_file"], json.dumps(STATE_SEED, indent=2) + "\n",
         "workflow state, schema v1, no phase in flight"),
    ]
    return items


def gitignore_missing(config, path):
    required = [".env*", "!.env.example"]
    for glob in config.get("secret_globs") or []:
        if isinstance(glob, str) and glob not in required:
            required.append(glob)
    # personal overrides (model, autonomy, plan gate) never reach the team
    required.append(cfm_config.LOCAL_CONFIG_FILE)
    # .cfm/ is cfm's own local dir (review marker, default state) —
    # always ignored. A state file configured OUTSIDE it is ignored
    # by name: never ignore a whole shared directory for one file.
    required.append(".cfm/")
    state_file = config.get("state_file") or ""
    state_dir = os.path.dirname(state_file)
    if state_file and not (state_dir and _norm(state_dir) == ".cfm"):
        state_line = _norm(state_file)
        if state_line not in required:
            required.append(state_line)

    existing = []
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            existing = [line.strip() for line in fh]
    missing = [line for line in required if line not in existing]
    # later rules win in .gitignore: whenever we append, the '!.env.example'
    # negation must land LAST or the appended globs override it
    if missing:
        if "!.env.example" in missing:
            missing.remove("!.env.example")
            missing.append("!.env.example")
        elif "!.env.example" in existing:
            missing.append("!.env.example")
    return missing


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="cfm scaffold — render workflow files from .cfm-workflow.yml"
    )
    parser.add_argument("--project-dir", default=".", help="project root (default: .)")
    parser.add_argument("--dry-run", action="store_true",
                        help="list what would be written and why; write nothing")
    parser.add_argument("--date", default=None,
                        help="YYYY-MM-DD for the initial progress entry (default: today)")
    args = parser.parse_args(argv)

    if args.date:
        try:
            date = datetime.date.fromisoformat(args.date).isoformat()
        except ValueError:
            print(f"error: --date must be YYYY-MM-DD, got '{args.date}'",
                  file=sys.stderr)
            return 1
    else:
        date = datetime.date.today().isoformat()

    project_dir = os.path.abspath(args.project_dir)
    config, errors, cfg_warnings = cfm_config.load(project_dir)
    for warning in cfg_warnings:
        print(f"warning: {warning}", file=sys.stderr)
    if config is None or errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        print("error: scaffold renders only from a valid config — fix the "
              "errors above", file=sys.stderr)
        return 1

    warnings = []
    written, kept, blocked = [], [], []
    for rel, content, reason in plan(config, date, warnings):
        path = os.path.join(project_dir, rel)
        # lexists: a dangling symlink is still "a file lives here" — never
        # follow it (open() would write through it, outside the project)
        if os.path.lexists(path):
            kept.append((rel, "exists — left untouched"))
            continue
        # defense in depth on top of config validation: never write a
        # target that resolves outside the project directory
        if not _contained(project_dir, path):
            blocked.append((rel, "resolves outside the project directory"))
            continue
        if not args.dry_run:
            try:
                parent = os.path.dirname(path)
                if parent:
                    os.makedirs(parent, exist_ok=True)
                _write_new(path, content)
            except FileExistsError:
                kept.append((rel, "exists — left untouched"))
                continue
            except OSError as exc:
                blocked.append((rel, f"write failed: {exc.strerror or exc}"))
                continue
        written.append((rel, reason))

    gi_path = os.path.join(project_dir, ".gitignore")
    missing = gitignore_missing(config, gi_path)
    if not missing:
        kept.append((".gitignore", "all required lines already present"))
    elif os.path.islink(gi_path) or not _contained(project_dir, gi_path):
        # never append through a symlink — it can redirect the write
        # outside the project
        blocked.append((".gitignore",
                        "is a symlink or resolves outside the project "
                        "directory"))
    else:
        appended = True
        if not args.dry_run:
            prefix = ""
            if os.path.isfile(gi_path):
                with open(gi_path, encoding="utf-8") as fh:
                    text = fh.read()
                if text and not text.endswith("\n"):
                    prefix = "\n"
            payload = (prefix + "# cfm — secret globs + local workflow "
                                "state (append-only)\n"
                       + "".join(line + "\n" for line in missing))
            try:
                fd = os.open(gi_path,
                             os.O_WRONLY | os.O_APPEND | os.O_CREAT
                             | os.O_NOFOLLOW, 0o644)
            except OSError as exc:  # ELOOP from O_NOFOLLOW, perms, …
                blocked.append((".gitignore",
                                f"append refused: {exc.strerror or exc}"))
                appended = False
            else:
                with os.fdopen(fd, "a", encoding="utf-8") as fh:
                    fh.write(payload)
        if appended:
            written.append((".gitignore", f"appended {len(missing)} line(s): "
                                          f"{', '.join(missing)}"))

    verb = "would-write" if args.dry_run else "written"
    print("cfm scaffold — " + project_dir + (" (dry-run)" if args.dry_run else ""))
    for rel, reason in written:
        print(f"  {verb:<11} {rel} — {reason}")
    for rel, reason in kept:
        print(f"  {'kept':<11} {rel} — {reason}")
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    for rel, reason in blocked:
        print(f"error: {rel} — {reason} — not written", file=sys.stderr)
    print(f"summary: {len(written)} {verb}, {len(kept)} kept"
          + (f", {len(blocked)} blocked" if blocked else ""))
    return 1 if blocked else 0


if __name__ == "__main__":
    sys.exit(main())
