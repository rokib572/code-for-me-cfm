# Command slot derivation

The slots are the portable contract; nothing in cfm ever hardcodes a
package manager or stack tool. Fill them by this procedure, in this order:

## 1. Evidence beats proposals (existing/scaffolded repos)

- **CI config is the strongest evidence.** Whatever the CI pipeline runs to
  bless a change IS `verify_full`. Read the workflow files the scan listed.
- **Manifest scripts are second.** package.json scripts, Makefile targets,
  justfile recipes, composer scripts: map `lint`/`format:check` → `lint`,
  `typecheck`/`tsc` → `typecheck`, the test runner → `test_scoped` (as a
  template) and the full run → `verify_full` if CI didn't already decide.
- **Lockfiles pick the package manager** (pnpm-lock.yaml → pnpm, etc.).
  Never propose npm where the lockfile says pnpm.

## 2. Propose for the declared stack (greenfield, or gaps in evidence)

Propose the stack's native tooling for each slot and say why. Examples of
the *shape* (do not treat as a lookup table — reason from the actual stack
and its current ecosystem):

- TypeScript/pnpm monorepo: `pnpm -r lint`, `pnpm -r typecheck`,
  `pnpm --filter {pkg} test {files}`, verify_full = the CI-equivalent chain.
- .NET: `dotnet format --verify-no-changes`, `dotnet build -warnaserror`,
  `dotnet test --filter {files}`.
- Python/uv: `uv run ruff check .`, `uv run mypy .`,
  `uv run pytest {files}`.

## 3. Slot rules

- `test_scoped` MUST be a template containing `{files}` (and `{pkg}` for
  monorepos) — agents run tests only by explicit path.
- `verify_full` MUST exist. It is contractually the human's command; agents
  never run it, but the doctor requires it to be defined.
- `lint_arch`: propose the stack's architecture-lint tool
  (dependency-cruiser / NetArchTest / deptrac / import-linter). If the
  ecosystem has none, LEAVE THE SLOT ABSENT and assign the layering rule to
  a reviewer in the rules file instead — teeth preserved, slot empty.
- `migrate_generate` / `migrate_apply`: only if the stack has migrations.
- **Absent slots deactivate capabilities.** Never invent a command to fill
  a slot; an honest absence beats a fake green.

## 4. Confirmation, not a quiz

Present all derived slots in one table with their evidence source
(ci / manifest / proposal). The user confirms or edits once. The doctor
then executes every filled slot — derivation may be imperfect because
verification is mechanical.
