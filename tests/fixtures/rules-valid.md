# Project Rules

## R1. No raw environment access
Product code reads configuration through the typed config module only —
never `process.env` / `os.environ` scattered through the codebase.

**Enforcement:** lint(no-process-env)

## R2. Feature code lives in feature roots
New feature files go under the configured `feature_roots` path for their
layer, nowhere else.

**Enforcement:** reviewer(code-reviewer)
