# cfm upgrade sweep — where a project's config lags the installed plugin

A pure read that produces findings; `/cfm:upgrade` turns each into a diff
the user approves. It covers only what the doctor does not already check:
keys the plugin no longer knows, settings the file leaves on a default,
roster agents added since init, the schema and `min_version` stamp, model
ids, and repo packages and scripts the config never heard of; then the
generated surfaces (settings denies, scaffold files, custom agent files,
CLAUDE.md guides) compared against their rendering from the final config.
Every step below ends in a proposed diff or "no finding". Nothing is
written here.

**Used by:** `cfm:upgrade` step 1 (baseline) and step 2 (findings table).

## Step 0 — read the raw file

Read `.cfm-workflow.yml` RAW (not merged: defaults and the local override
must not mask what the file says). Missing: tell the user to run
`/cfm:init` and stop. Unparseable, empty, or not a mapping: show the
error and stop. Read the plugin version from
`${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json` `version`.

## Step 1 — schema

- `schema.file` = `cfm.schema_version` in the file; `schema.latest` = 2
  (the only supported version).
- Above latest: the config is newer than this plugin; tell the user to
  update cfm and stop. Below: this plugin ships no migration; say so and
  stop. Never send the user to `/cfm:init` for an initialised repo.

## Step 2 — version stamp

`min_version` = `cfm.requires.min_version`. Compare as tuples of the
integers found in each string. `stamp_behind` is true when the stamp is
unset or lower than the plugin version. Finding (domain config / stamp):
set `cfm.requires.min_version` to the plugin version, with the warning
that every teammate's doctor fails until they update cfm.

## Step 3 — retired keys (config / retired)

Walk the file against the known schema; a key not in the schema at its
level is `unknown`, reported as a dotted path. Walk INTO a section only
when its known keys are fixed by cfm:

- top level: `profile mode feature_roots claude_md commands agents
  review_gates review implement git forbidden_ops secret_globs tenancy
  human_gates done_criteria shared_commands_ack token_reporting tracker
  rules_file context_file progress_log state_file cfm layers
  project_context`
- `cfm`: `schema_version requires`; `cfm.requires`: `surface min_version`
- `claude_md`: `layout files`
- `review`: `trigger auto_scope scope`
- `implement`: `plan_gate`
- `git`: `level branch_prefixes`
- `tenancy`: `scope_field`
- `tracker`: `provider sync`; `tracker.sync`: `create_tasks
  transition_status post_notes fetch_tasks`
- do NOT walk `feature_roots`, `commands`, `agents`, `layers`: their keys
  are user-named.

Then the agent fields: for every `agents.<name>` entry that is a mapping
and not `enabled: false`, any field outside `enabled purpose model tier
autonomy tools owns_commands layers` is `agents.<name>.<field>`, appended
to the same list. A disabled agent is the user's choice and is never
inspected.

Proposal per entry: remove it. A key that is a typo of a real key or a
deliberate note is proposed as a rename or a comment instead.

## Step 4 — newly defaulted keys (config / defaults)

For each scalar leaf of the plugin defaults, follow its dotted path into
the file; when any segment is absent or the value is null, the key is
defaulted. The scalar leaves and their defaults:

```
profile: supervised          mode: enforced
claude_md.layout: single     review.trigger: phase-gate
review.auto_scope: full      review.scope: phase
implement.plan_gate: true    git.level: L0
tenancy.scope_field: null    token_reporting: true
tracker.provider: null       tracker.sync.create_tasks: true
tracker.sync.transition_status: true
tracker.sync.post_notes: true
tracker.sync.fetch_tasks: true
rules_file: .claude/rules/rules.md
context_file: CONTEXT.md     progress_log: docs/PROGRESS.md
state_file: .cfm/state.json
```

List and mapping leaves (`claude_md.files`, `git.branch_prefixes`,
`human_gates`, `done_criteria`, `shared_commands_ack`, `forbidden_ops`,
`secret_globs`, `feature_roots`, `commands`, `agents`, `review_gates`)
are never reported. Finding: ONE row proposing to write them explicitly
with their default values. Offer, never push. A value the file sets is
never re-decided, even when the plugin's default changed.

## Step 5 — roster agents added since init (agents / new)

Read `${CLAUDE_PLUGIN_ROOT}/templates/roster.yml`. For each roster agent
whose name is NOT a key under the file's `agents`:

1. Take the project's layer names from `layers[].name`.
2. If the roster entry's `layers` contains `any`, matched = all project
   layer names; else matched = the intersection, sorted.
3. Matched empty (e.g. `ui-design` with no `web/frontend/ui/app` layer):
   no finding. Otherwise the proposal is the roster entry with `layers`
   replaced by the matched list.

An agent present in the file with `enabled: false` is in `agents` and so
is never proposed, checked, or re-added. The model id in the proposal
gets the step 6 live check before it enters a diff.

## Step 6 — model ids (agents / models)

`models` = `{name: model}` for every agent entry that is a mapping and
not `enabled: false`. Check each id against the models that exist now;
never a hardcoded list. Flag an id that no longer resolves, and an id
with a newer model in the same family and tier. The proposal keeps family
and tier: haiku stays haiku. A personal override in
`.cfm-workflow.local.yml` that pins an outdated model is listed in step 4
of the skill, not proposed; it is the developer's to edit.

## Step 7 — repo packages and scripts (repo / layers, repo / commands)

- `unlayered_packages`: Glob each manifest name from the init scan's
  list (`package.json pyproject.toml setup.py requirements.txt go.mod
  Cargo.toml composer.json Gemfile pom.xml build.gradle build.gradle.kts
  mix.exs pubspec.yaml Makefile justfile Taskfile.yml`) at depth one
  (`*/<manifest>`) and depth two (`*/*/<manifest>`). Skip a directory
  with an ignored dir or a dot-dir in its path. Report its directory,
  sorted, when it is not equal to or under any `layers[].path`. Proposal:
  a layer (name, path, position) plus its `feature_roots` entry and, under
  the `router` layout, its `claude_md.files` entry, from the manifest's
  evidence. Tooling packages are rows the user drops.
- `unused_scripts`: every root `package.json` script name that does not
  occur as a whole token (not adjacent to a word character, `:` or `-`)
  in the concatenation of every command slot's commands. Propose only one
  that fits an empty or differently-filled slot (`lint typecheck
  test_scoped verify_full migrate_*`); show its body. Never propose a
  script just because it exists.

## Step 8 — settings denies

Follow `references/settings-denies.md` as a check (nothing written):
missing or stale cfm denies and allows are the finding, one row. Apply
after the config is final, with the same sandbox choice as the check.

## Step 9 — scaffold files

Follow `references/scaffold.md` as a dry run. Every file the scaffold
would create because it is missing, and every required `.gitignore` line
absent, is a `would-write` finding. An existing file is `kept` and never
touched.

## Step 10 — custom agent files

Follow `references/agent-file.md` for every enabled custom agent as a dry
run and compare the rendered frontmatter with the file on disk: a missing
file, a different `name`, or a different tool set is drift, one row each.
Apply by re-rendering, which refreshes the frontmatter and keeps the
body.

## Step 11 — CLAUDE.md re-render

Follow the re-render procedure in `references/scaffold.md` for every
`kept` CLAUDE.md guide: render it from config and diff against disk. Any
difference is a finding; name every `## ` section the re-render drops.
`## Feature structure` is carried over after the replace; other dropped
hand-written text is gone, and the row says so. This runs LAST at apply
time so it renders the final config, and the diff is redone when step 3
or 4 changed the config.

## Step 12 — disabled-agent references

Follow the reference sweep in `references/scans.md`. Each hit is a row
handled exactly as `/cfm:configure` step 5 says. A guide being replaced
in step 11 needs only the hits the re-render does not already remove.

## Report shape

Carry these fields into the findings table, in this order: `schema`
(`file`, `latest`), `plugin_version`, `min_version`, `stamp_behind`,
`unknown_keys` (step 3, both halves), `defaulted_keys` (`key`,
`default`), `new_agents` (`agent`, `entry`), `models`, `repo`
(`unlayered_packages`, `unused_scripts`), then the generated-surface
findings of steps 8 to 12. No findings at all: "cfm is up to date with
plugin <version>", show the doctor verdict, stop.
