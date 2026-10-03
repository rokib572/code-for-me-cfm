#!/bin/sh
# cfm pre-commit hook — installed by copying to .git/hooks/pre-commit.
# Enforcement layer for the secrets policy (plan §11) that catches the
# human too: blocks staged secret files, scans staged content with
# gitleaks when available, and runs the config's lint slot.
# POSIX sh; runs from the repo root (git's hook cwd).

set -u

# --- staged secret files -------------------------------------------------
# --diff-filter=d: deletions unstage a secret, never add one
staged="$(git diff --cached --name-only --diff-filter=d)"

matches=""
if [ -n "$staged" ]; then
  if command -v python3 >/dev/null 2>&1; then
    matches="$(printf '%s\n' "$staged" | python3 -c '
import fnmatch, os, sys

# mirrors cfm_config.DEFAULT_SECRET_GLOBS — keep in sync
globs = [
    ".env*", "*.env", "*.pem", "*.key", "*.p12", "*.pfx", "*.jks",
    "*.keystore", "id_rsa*", "id_dsa*", "id_ecdsa*", "id_ed25519*",
    ".npmrc", ".pypirc", ".netrc", ".git-credentials", ".htpasswd",
    ".pgpass", "**/credentials", "service-account*.json", "secrets.json",
    "secrets.yml", "secrets.yaml", "secrets.toml", "kubeconfig*",
    "*.tfstate", "*.tfvars",
]
# the hook runs from the repo root: read the config there directly —
# never via cfm_config, which does not import from .git/hooks/
try:
    import yaml
    with open(".cfm-workflow.yml", encoding="utf-8") as fh:
        config = yaml.safe_load(fh)
    if isinstance(config, dict):
        extra = config.get("secret_globs")
        if isinstance(extra, list):
            globs.extend(g for g in extra if isinstance(g, str) and g not in globs)
except Exception:
    pass  # unreadable config never shrinks the default glob set

for path in sys.stdin.read().splitlines():
    if not path:
        continue
    base = os.path.basename(path)
    if base == ".env.example":  # the only sanctioned env file
        continue
    if any(fnmatch.fnmatch(base, g) or fnmatch.fnmatch(path, g) for g in globs):
        print(path)
')"
  else
    # no python3 — basename match against the default globs
    # (mirrors cfm_config.DEFAULT_SECRET_GLOBS — keep in sync)
    matches="$(printf '%s\n' "$staged" | while IFS= read -r f; do
      base="${f##*/}"
      [ "$base" = ".env.example" ] && continue
      case "$base" in
        .env*|*.env|*.pem|*.key|*.p12|*.pfx|*.jks|*.keystore|id_rsa*|id_dsa*|id_ecdsa*|id_ed25519*|.npmrc|.pypirc|.netrc|.git-credentials|.htpasswd|.pgpass|credentials|service-account*.json|secrets.json|secrets.yml|secrets.yaml|secrets.toml|kubeconfig*|*.tfstate|*.tfvars)
          printf '%s\n' "$f" ;;
      esac
    done)"
  fi
fi

if [ -n "$matches" ]; then
  printf '%s\n' "$matches" >&2
  echo "cfm pre-commit: refusing to commit secret file(s) listed above." >&2
  echo "cfm pre-commit: .env.example (names only, blank values) is the only sanctioned env file." >&2
  exit 1
fi

# --- staged secret content ----------------------------------------------
if command -v gitleaks >/dev/null 2>&1; then
  gitleaks protect --staged --no-banner --redact || exit 1
else
  echo "cfm pre-commit: gitleaks not found — install it for staged secret-content scanning." >&2
fi

# --- lint slot -----------------------------------------------------------
# Absent config, PyYAML, or lint slot → skip silently.
if [ -f .cfm-workflow.yml ] && command -v python3 >/dev/null 2>&1; then
  lint_cmds="$(python3 -c '
import sys

# the hook runs from the repo root: read the config there directly —
# never via cfm_config, which does not import from .git/hooks/
try:
    import yaml
    with open(".cfm-workflow.yml", encoding="utf-8") as fh:
        config = yaml.safe_load(fh)
except Exception:
    sys.exit(0)
if not isinstance(config, dict):
    sys.exit(0)
commands = config.get("commands")
value = commands.get("lint") if isinstance(commands, dict) else None
if isinstance(value, str):
    value = [value]
if isinstance(value, list):
    for cmd in value:
        if isinstance(cmd, str) and cmd.strip():
            print(cmd)
' 2>/dev/null)" || lint_cmds=""
  if [ -n "$lint_cmds" ]; then
    printf '%s\n' "$lint_cmds" | while IFS= read -r cmd; do
      [ -n "$cmd" ] || continue
      sh -c "$cmd" </dev/null || exit 1
    done || exit 1
  fi
fi

exit 0
