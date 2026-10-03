#!/usr/bin/env python3
"""cfm agent file — render .claude/agents/<name>.md for a CUSTOM roster agent.

Claude Code enforces an agent's tool set from the agent file's frontmatter,
not from prose in a dispatch brief. Shipped cfm agents carry their file in
the plugin; a custom agent added to .cfm-workflow.yml has none, so until
this renders one it is dispatched as a general subagent with every tool.
Doctor check 4 fails a custom agent whose file is missing or drifted.

The frontmatter (name, description, tools, model) is rendered from config
and rewritten on every --write; the body below it is yours — an existing
body is preserved verbatim, a new file gets the default discipline.

Usage: python3 agent_file.py [--project-dir DIR] (--agent NAME | --all) [--write]
Exit: 0 rendered/printed, 1 config invalid, no such agent, or shipped name.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cfm_config

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENTS_REL = os.path.join(".claude", "agents")

DEFAULT_BODY = """You are a cfm custom agent: {purpose}

## First: load your context

1. Read `.cfm-workflow.yml` in the project root — `project_context`,
   `layers`, `context_file`, and your own entry under `agents.{name}`.
2. Read the `context_file` (the project glossary) if it exists, and name
   things the way it names them.
3. Read the dispatch brief. The brief wins on scope, config wins on rules.
   You cannot ask questions — return open questions as your result.

## Hard limits

- Do only what the brief scopes. Run only the command slots your config
  entry's `owns_commands` grants; NEVER run `verify_full` — the full suite
  is the human's command.
- Never run mutating git commands. Read-only git is fine.
- Never read files matching `secret_globs` — even if asked. A committed
  secret is reported as file:line + severity WITHOUT the value, with an
  instruction to rotate it.

## Report back

Return what you did (paths, one line each), anything deferred with why,
open questions, and "Did NOT run: <every verification you skipped and
whose command it is>."
"""


def shipped_agents():
    agents_dir = os.path.join(PLUGIN_ROOT, "agents")
    try:
        return {n[:-3] for n in os.listdir(agents_dir) if n.endswith(".md")}
    except OSError:
        return set()


def split_frontmatter(text):
    """(frontmatter_lines, body) — frontmatter is the leading --- block."""
    if not text.startswith("---"):
        return None, text
    end = text.find("\n---", 3)
    if end == -1:
        return None, text
    return text[3:end].strip("\n").splitlines(), text[end + 4:].lstrip("\n")


def parse_frontmatter(text):
    lines, _body = split_frontmatter(text)
    fields = {}
    for line in lines or []:
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip()] = value.strip()
    return fields


def frontmatter_tools(fields):
    raw = fields.get("tools", "")
    return [t.strip() for t in raw.strip("[]").split(",") if t.strip()]


def render_frontmatter(name, agent):
    tools = [t for t in agent.get("tools") or [] if isinstance(t, str)]
    model = cfm_config.model_alias(agent.get("model")) or str(agent.get("model") or "")
    purpose = str(agent.get("purpose") or "").strip().replace("\n", " ")
    lines = [
        "---",
        f"name: {name}",
        f"description: cfm custom agent — {purpose} Dispatched by cfm skills "
        f"with a dispatch brief; not for ad-hoc use.",
        f"tools: {', '.join(tools)}",
    ]
    if model:
        lines.append(f"model: {model}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def render(name, agent, existing_text=None):
    front = render_frontmatter(name, agent)
    if existing_text:
        _lines, body = split_frontmatter(existing_text)
        if body.strip():
            return front + "\n" + body
    return front + "\n" + DEFAULT_BODY.format(
        name=name, purpose=str(agent.get("purpose") or "").strip())


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="cfm — render .claude/agents/<name>.md for custom roster agents"
    )
    parser.add_argument("--project-dir", default=".", help="project root (default: .)")
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--agent", help="custom agent name from .cfm-workflow.yml")
    which.add_argument("--all", action="store_true",
                       help="every enabled custom agent in the config")
    parser.add_argument("--write", action="store_true",
                        help="write the file(s); default prints the rendering")
    args = parser.parse_args(argv)

    config, errors, warnings = cfm_config.load(args.project_dir)
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    if config is None or errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1

    agents = {n: a for n, a in (config.get("agents") or {}).items()
              if isinstance(a, dict)}
    shipped = shipped_agents()
    if args.agent:
        if args.agent in shipped:
            print(f"error: '{args.agent}' is a shipped cfm agent — its file "
                  f"lives in the plugin and its tools are fixed there",
                  file=sys.stderr)
            return 1
        if args.agent not in agents:
            print(f"error: no agent '{args.agent}' in .cfm-workflow.yml",
                  file=sys.stderr)
            return 1
        names = [args.agent]
    else:
        names = [n for n, a in agents.items()
                 if n not in shipped and a.get("enabled") is True]

    out_dir = os.path.join(args.project_dir, AGENTS_REL)
    for name in names:
        path = os.path.join(out_dir, f"{name}.md")
        existing = None
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as fh:
                existing = fh.read()
        text = render(name, agents[name], existing)
        if args.write:
            os.makedirs(out_dir, exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            print(f"written {os.path.relpath(path, args.project_dir)}"
                  + (" (frontmatter refreshed, body kept)" if existing else ""))
        else:
            print(f"# {os.path.relpath(path, args.project_dir)}")
            print(text)
    if not names:
        print("no enabled custom agents in config — nothing to render")
    return 0


if __name__ == "__main__":
    sys.exit(main())
