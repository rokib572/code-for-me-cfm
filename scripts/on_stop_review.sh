#!/usr/bin/env bash
# cfm Stop hook: enforces review.trigger: on-stop.
# Blocks the stop (exit 2) while there are unreviewed working-tree changes.
# /cfm:code-review writes .cfm/last-review.sha with the current work hash;
# a matching hash lets the stop through — this is what prevents a stop-loop.

set -u

# hook event JSON arrives on stdin (may be empty); a re-fired stop must
# never loop, so stop_hook_active always lets the stop through
event="$(cat 2>/dev/null || true)"
if printf '%s' "$event" | grep -Eq '"stop_hook_active"[[:space:]]*:[[:space:]]*true'; then
  exit 0
fi

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"

[ -f "$PROJECT_DIR/.cfm-workflow.yml" ] || exit 0
command -v python3 >/dev/null 2>&1 || exit 0

# a config with validation errors prints no trigger: /cfm:code-review refuses
# to run on a broken config, so nagging here would be an unbreakable loop
trigger="$(python3 "$PLUGIN_ROOT/scripts/cfm_config.py" --project-dir "$PROJECT_DIR" --get review.trigger 2>/dev/null)" || exit 0
[ "$trigger" = "on-stop" ] || exit 0

git -C "$PROJECT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

status="$(git -C "$PROJECT_DIR" status --porcelain 2>/dev/null)"
diff="$(git -C "$PROJECT_DIR" diff 2>/dev/null)"
[ -n "$status" ] || [ -n "$diff" ] || exit 0

# the hash recipe (between `&&` and `| awk`) MUST stay byte-identical to skills/code-review/SKILL.md step 5 —
# if one changes, change both (tests/run-tests.sh asserts the match)
hash="$(cd "$PROJECT_DIR" && sha256sum <(git status --porcelain; git diff; git ls-files -z --others --exclude-standard -- ':!.cfm' | sort -z | xargs -0 -r cat 2>/dev/null) | awk '{print $1}')"
if [ -f "$PROJECT_DIR/.cfm/last-review.sha" ]; then
  last="$(awk '{print $1; exit}' "$PROJECT_DIR/.cfm/last-review.sha")"
  [ "$last" = "$hash" ] && exit 0
fi

echo "cfm: review.trigger is on-stop and there are unreviewed changes — run /cfm:code-review before finishing." >&2
exit 2
