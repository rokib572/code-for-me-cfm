#!/usr/bin/env bash
# cfm PreToolUse hook entry.
# Pipeline: project check → environment gate → guard_check.py decision engine.
# Receives the hook event JSON on stdin; exit 0 allows the tool call,
# exit 2 blocks it and feeds stderr back to Claude.

set -u

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"

# not a cfm project: allow before spawning anything — this hook fires on
# every Read/Edit/Grep/Bash call in every project, so the file test comes
# first. Drain stdin with a builtin so the writer never sees a closed pipe.
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
if [ ! -f "$PROJECT_DIR/.cfm-workflow.yml" ]; then
  while IFS= read -r _; do :; done
  exit 0
fi

# environment gate (hard invariant 4 — works even if sideloaded).
"$PLUGIN_ROOT/scripts/require-claude-code.sh" || exit 2

# no python3: allow — the generated settings.json deny rules remain as backstop.
command -v python3 >/dev/null 2>&1 || exit 0

exec python3 "$PLUGIN_ROOT/scripts/guard_check.py"
