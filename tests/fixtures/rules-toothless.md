# Project Rules

## R1. No raw environment access
Product code reads configuration through the typed config module only.

**Enforcement:** lint(no-process-env)

## R2. Write good code
Code should be good, not bad. Everyone just has to remember this one.

## R3. Feature code lives in feature roots
New feature files go under the configured `feature_roots` path.
