#!/usr/bin/env bash
# cfm status line (opt-in; wired by gen_settings.py --statusline --write).
# Reads Claude Code's status-line JSON on stdin and prints one line:
#   cfm ▸ enforced ▸ phase 2 in-flight @ api ▸ gate: run-verify_full ▸ [Model]
# Outside a cfm project it prints "[Model] <dir>".

set -u
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
if ! command -v python3 >/dev/null 2>&1; then
  while IFS= read -r _; do :; done
  echo "cfm"
  exit 0
fi
exec python3 "$PLUGIN_ROOT/scripts/session_context.py" --event StatusLine
