#!/usr/bin/env python3
"""cfm references — where the project still names a disabled agent.

The loader already drops a disabled agent from the flow. This finds the
files that still name it — CLAUDE.md guides, the rules file, the glossary,
the local override file, everything under .claude/ — so the reference can
be removed there too. A disabled custom agent's own file is reported whole.

A PURE READ. History (progress log, plans, state) is never scanned: it
records what happened, not what runs. Settings files are gen_settings.py's.

Usage: python3 references.py [--project-dir DIR] [--json]
Exit code: 0 report rendered (even with hits), 1 config missing or unparseable.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent_file
import cfm_config

SKIP_FILES = {"settings.json", "settings.local.json"}


def disabled_agents(raw):
    agents = raw.get("agents") if isinstance(raw.get("agents"), dict) else {}
    return sorted(name for name, agent in agents.items()
                  if isinstance(agent, dict) and agent.get("enabled") is False)


def _scan_paths(project_dir, raw):
    paths = ["CLAUDE.md", cfm_config.LOCAL_CONFIG_FILE]
    paths += [p for p in (raw.get("claude_md") or {}).get("files") or []
              if isinstance(p, str)]
    for field in ("rules_file", "context_file"):
        value = raw.get(field, cfm_config.DEFAULTS[field])
        if isinstance(value, str):
            paths.append(value)
    for current, dirs, files in os.walk(os.path.join(project_dir, ".claude")):
        dirs.sort()
        for name in sorted(files):
            if name not in SKIP_FILES:
                paths.append(os.path.relpath(os.path.join(current, name), project_dir))
    return list(dict.fromkeys(os.path.normpath(p).replace(os.sep, "/") for p in paths))


def stale_references(project_dir, raw):
    """[{agent, path, line, text}] — line None means the whole file."""
    names = disabled_agents(raw)
    if not names:
        return []
    shipped = agent_file.shipped_agents()
    own_files = {os.path.join(agent_file.AGENTS_REL, f"{n}.md").replace(os.sep, "/"): n
                 for n in names if n not in shipped}
    patterns = {n: re.compile(rf"(?<![\w-]){re.escape(n)}(?![\w-])") for n in names}
    hits = []
    for rel in _scan_paths(project_dir, raw):
        path = os.path.join(project_dir, rel)
        if os.path.islink(path) or not os.path.isfile(path):
            continue
        if rel in own_files:
            hits.append({"agent": own_files[rel], "path": rel, "line": None,
                         "text": "the disabled custom agent's own file"})
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                lines = fh.read().splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for number, text in enumerate(lines, 1):
            for name, pattern in patterns.items():
                if pattern.search(text):
                    hits.append({"agent": name, "path": rel, "line": number,
                                 "text": text.strip()})
    return hits


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="cfm — find project files that still name a disabled agent"
    )
    parser.add_argument("--project-dir", default=".", help="project root (default: .)")
    parser.add_argument("--json", action="store_true", help="print the hits as JSON")
    args = parser.parse_args(argv)

    project_dir = os.path.abspath(args.project_dir)
    errors = []
    path = os.path.join(project_dir, cfm_config.CONFIG_FILE)
    raw = cfm_config._read_yaml(path, errors) if os.path.exists(path) else None
    if raw is None:
        for error in errors or [f"{cfm_config.CONFIG_FILE} not found — run /cfm:init"]:
            print(f"error: {error}", file=sys.stderr)
        return 1
    hits = stale_references(project_dir, raw)
    if args.json:
        json.dump({"disabled": disabled_agents(raw), "references": hits},
                  sys.stdout, indent=2)
        print()
        return 0
    for hit in hits:
        where = hit["path"] + (f":{hit['line']}" if hit["line"] else "")
        print(f"{where}: {hit['agent']} — {hit['text']}")
    if not hits:
        print("no references to disabled agents")
    return 0


if __name__ == "__main__":
    sys.exit(main())
