#!/usr/bin/env bash
# cfm SessionStart / UserPromptSubmit hook entry: `session_context.sh <event>`.
# Injects the cfm-mode context (additionalContext JSON on stdout) in projects
# that carry a .cfm-workflow.yml; silent everywhere else. Never blocks —
# the guard is the mechanism, this is the prose that arrives with it.

set -u

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
EVENT="${1:-SessionStart}"

# not a cfm project: exit before spawning anything — this fires on every
# session and every prompt in every project. Drain stdin with a builtin.
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
if [ ! -f "$PROJECT_DIR/.cfm-workflow.yml" ]; then
  while IFS= read -r _; do :; done
  exit 0
fi

# environment gate (hard invariant 4): outside Claude Code there is no
# session to inform, so stay silent rather than block
if ! "$PLUGIN_ROOT/scripts/require-claude-code.sh" 2>/dev/null; then
  while IFS= read -r _; do :; done
  exit 0
fi

# no python3: silent — the settings denies and the guard's own python test
# already cover the mechanism side
command -v python3 >/dev/null 2>&1 || exit 0

exec python3 "$PLUGIN_ROOT/scripts/session_context.py" --event "$EVENT"
