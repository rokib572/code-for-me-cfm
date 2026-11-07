# Greenfield scaffold playbook (after config genesis)

Two kinds of scaffold, two executors — the split IS the design:

- **Workflow files** (CLAUDE.md, rules seed, glossary, .gitignore,
  .env.example, progress log, initial state) are deterministic renders
  FROM config, following the templates in
  `${CLAUDE_PLUGIN_ROOT}/references/scaffold.md` exactly, so
  config↔scaffold drift is structurally impossible. The orchestrator
  renders them itself — they are workflow files, never product code.
- **The stack skeleton** (manifests, build config, the typed config
  module, layer directory contents) is stack-specific. It is ALWAYS
  dispatched to the coder agent — never written in the main session.

## Step 1 — render the workflow scaffold (by hand)

Follow the render procedure in
`${CLAUDE_PLUGIN_ROOT}/references/scaffold.md`: from the validated
config, CLAUDE.md (per `claude_md.layout`, with the command matrix,
human gates and the cfm doctrine block between `<!-- cfm:begin -->` and
`<!-- cfm:end -->`), the rules seed at `rules_file`, the glossary seed at
`context_file`, `.gitignore` (append-only: `.env*` family, secret globs,
`.cfm/`), `.env.example` (names only), the progress log, and the initial
state. Existing files are kept, never clobbered. Do a dry run first
(render in memory, show the `would-write`/`kept` summary), then write
and show the written/kept summary. If the config fails validation
(`references/config.md`), fix that first — do not hand-write the files
the render would have produced. If the rules seed finds no enabled
reviewer and no `lint_arch` slot, stop and send the user to
`/cfm:configure agents`; a toothless rule is never seeded.

## Step 1.5 — run the conventions round

The rules seed now exists, so the project's coding conventions can be
resolved and appended to it. Follow `conventions-round.md` — the
interview, the rules, and the `## Feature structure` sections only. Do
this BEFORE the coder dispatch: the skeleton must be built to the
conventions, not retrofitted to them.

STOP at that file's "Prove the lint teeth" phase and resume it at step
2.5 — proving a lint rule needs a linter, and the linter needs the
manifest the skeleton has not created yet.

## Step 2 — dispatch the coder for the stack skeleton

Dispatch ONE coder subagent. Include in the brief: the confirmed
`project_context`, the stack decisions from the architecture round, the
ordered layer list with paths and feature roots, and the configured
command slots verbatim, plus the `rules_file` path and, per layer, its
CLAUDE.md `## Feature structure` section. The brief MUST demand:

- the stack's minimal buildable skeleton for every configured layer, at
  that layer's path;
- conformance to every rule in `rules_file` and to each layer's
  `## Feature structure` layout — naming, file layout, and declaration
  style come from there, not from the coder's preferences;
- a TYPED CONFIG MODULE (zod env schema, or the stack's equivalent) as
  the ONLY environment access path — product code reads `config.x`,
  never scattered raw env access, never literals;
- every configured command slot exiting green on the empty skeleton;
- a `NAME=` entry appended to `.env.example` for every env var the
  skeleton introduces — names only, values stay empty;
- no secrets anywhere: not in code, not in fixtures, not in examples;
- nothing beyond the skeleton — no features, no speculative structure.

## Step 2.5 — prove the lint teeth

The skeleton exists, so the linter does too. Resume `conventions-round.md`
at its "Prove the lint teeth" phase: every `lint(...)` enforcement is
measured against a deliberate violation, wired if it does not bite, and
demoted to a reviewer if it still does not. Fixtures are deleted in that
phase's last stage — step 3's doctor run is what proves the tree is clean
again.

## Step 3 — settings denies, then doctor must be fully green

First render the permission-layer denies (SKILL.md step 5 — propose,
diff, approve, write per `${CLAUDE_PLUGIN_ROOT}/references/settings-denies.md`);
check 7 fails without them. Then run every doctor check by hand per
`${CLAUDE_PLUGIN_ROOT}/references/doctor.md`.

All checks (0–9) must pass on the empty skeleton BEFORE init ends —
every configured command running green against zero product code.

- Command-slot failures → re-dispatch the coder with the doctor's raw
  output for that slot.
- A slot the stack genuinely lacks → with the user's explicit approval,
  remove the slot (absent slots deactivate capabilities). Never fake a
  green command.
