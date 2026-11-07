---
name: upgrade
description: Upgrades a project's cfm setup to the installed plugin version and the repo as it is now — a thorough sweep of config schema, retired and newly defaulted keys, roster agents added since init, model ids, packages and scripts the config never heard of, a full re-render of every CLAUDE.md guide, settings denies, scaffold files, and custom agent files, each proposed as a diff applied only on explicit approval, ending in a doctor run compared against the starting one. Use after updating the cfm plugin, or when the user wants the repo's cfm config brought up to date.
compatibility: Requires Claude Code (terminal, IDE extension, or Desktop Code tab)
---

# cfm:upgrade

Bring an existing cfm setup up to the installed plugin: measure first,
propose every change as a diff, apply only what the user approves, prove
it with the doctor. Every value the user chose stays as it is. Upgrading
fills gaps and retires dead keys, and never re-decides a setting.

## Step 0 — environment gate

Run: `bash "${CLAUDE_PLUGIN_ROOT}/scripts/require-claude-code.sh"`
If it exits non-zero, STOP and show its stderr verbatim.

## Step 1 — baseline

1. `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/upgrade.py" --project-dir "$(pwd)" --json`
   - Exit 1 with "not found" → tell the user to run `/cfm:init` and STOP.
   - `schema.file` above `schema.latest` → the config is newer than this
     plugin: tell the user to update cfm and STOP.
   - `schema.file` below `schema.latest` → this plugin ships no
     migration for that schema: say so and STOP. Never send the user to
     `/cfm:init`: it refuses a repo that already has a config.
2. `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/doctor.py" --project-dir "$(pwd)" --json`.
   Keep this report. It is the baseline step 5 compares against.
3. The generators, as dry runs (nothing is written yet):
   - `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/gen_settings.py" --project-dir "$(pwd)" --check`
     (add `--sandbox` if doctor check 7 says the sandbox is on)
   - `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/scaffold.py" --project-dir "$(pwd)" --dry-run`
   - **CLAUDE.md re-render.** For every `kept` line in that dry run
     whose path ends in `CLAUDE.md`, diff the file on disk against its
     rendering from config:
     `diff -u <path> <(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/scaffold.py" --project-dir "$(pwd)" --print <path>)`.
     Any difference is a finding. Before the diff, list every `## `
     section the re-render would DROP by its heading.
   - `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/agent_file.py" --project-dir "$(pwd)" --all`.
     Compare each rendering with the file on disk. A frontmatter that
     differs is drift.
4. **Models, live.** For every id in the report's `models`, check it
   against the models that exist now. Never use a hardcoded list. Flag
   an id that no longer resolves, and an id with a newer model in the
   same family and tier (e.g. an older haiku on a mechanical agent). The
   proposal keeps the family and tier: haiku stays haiku. The report
   lists only enabled agents. A disabled agent is never proposed, checked,
   or re-added.

## Step 2 — the findings table

Render one table, one row per finding, grouped by domain in this order.
The plan in step 3 follows the same order.

| # | domain | finding | proposed change |
|---|---|---|---|

- **config / retired**: each `unknown_keys` entry. The proposal is
  removal. A key the user may still need (a typo of a real key, a custom
  note) is proposed as a rename or a comment instead.
- **config / defaults**: the `defaulted_keys` entries, as ONE row. The
  proposal writes them explicitly with their default values, so the file
  shows every setting the plugin reads. Offer this, never push it.
- **config / stamp**: when `stamp_behind` is true, set
  `cfm.requires.min_version` to `plugin_version`. Warn that it makes
  every teammate's doctor fail until they update cfm. It is a team
  decision, so say so.
- **agents / new**: each `new_agents` entry, with its roster entry as the
  proposal. The `layers` are already narrowed to this project's.
  Models get the step 1.4 live check before they go in a diff. An agent
  the user removed on purpose stays removed. If the user says so, drop
  the row.
- **agents / models**: each id flagged in step 1.4.
- **repo / layers**: each `repo.unlayered_packages` entry. A package no
  layer covers. Propose a layer (name, path, position in build order)
  plus its `feature_roots` entry and, under `router`, its
  `claude_md.files` entry. Read the package's manifest first, so the
  name and position come from evidence. A package that is tooling, not
  product (a config package, a script folder), is a row the user drops.
- **repo / commands**: `repo.unused_scripts` that fit a command slot
  (`lint`, `typecheck`, `test_scoped`, `verify_full`, `migrate_*`) and
  whose slot is empty or runs something else. Show the script's body
  from `package.json`. Never propose a script just because it exists.
- **doctor**: every baseline FAIL and WARN not covered above. Name the
  fix and the command that owns it (`/cfm:configure <domain>`,
  `/cfm:add-agent`, `/cfm:connect-tracker`). These are fixed through
  those flows and never edited from here.
- **settings**: missing or stale denies and allows from `--check`.
- **scaffold**: every `would-write` line (missing workflow files and
  `.gitignore` lines). Existing files are never touched.
- **custom agent files**: every frontmatter drift from step 1.3.
- **disabled-agent references**: every hit from
  `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/references.py" --project-dir "$(pwd)" --json`.
  Handle each exactly as `/cfm:configure` step 5 says: prose deleted, a
  rule's enforcement reassigned (never deleted), local override blocks
  dropped, a disabled custom agent's file deleted. A CLAUDE.md guide that
  is also being re-rendered needs only the hits the re-render does not
  already remove.
- **CLAUDE.md**: one row per guide that differs. The proposal is a full
  replacement with the rendering. Name the dropped sections in the row.
  A `## Feature structure` section is written by the conventions round,
  not by the renderer. It is carried over after the replace (step 3.4)
  unless the user says otherwise. Any other dropped hand-written text is
  gone once applied, so say that in the row.

No findings at all → say "cfm is up to date with plugin <version>",
show the doctor verdict, and STOP.

## Step 3 — choose, then apply one domain at a time

1. Show every config and agents change as a unified diff of
   `.cfm-workflow.yml` (only changed lines, 2 lines of context). Each
   diff gets one consequence sentence per behavioral change.
2. One AskUserQuestion, `multiSelect: true`, one option per row group:
   which upgrades to apply. Nothing unselected is applied.
3. Apply the selected groups in table order. Each is its own surgical
   edit: never rewrite untouched sections, never reformat, keep the
   user's comments. After each config edit, validate:
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/cfm_config.py" --project-dir "$(pwd)"`.
   An error on what you wrote is yours to fix before moving on. Never
   fix it by changing the user's other config.
4. The generators run after the config is final, because the config feeds
   them. For each one selected:
   - settings: `gen_settings.py --project-dir "$(pwd)" --write` (with
     the same `--sandbox` choice as the check)
   - scaffold: `scaffold.py --project-dir "$(pwd)"`
   - custom agent files: `agent_file.py --project-dir "$(pwd)" --all --write`
     (refreshes frontmatter and keeps the body)
   - CLAUDE.md, LAST, so it renders the final config:
     `scaffold.py --project-dir "$(pwd)" --replace <each selected path>`.
     Then re-append each carried-over `## Feature structure` section to
     its file verbatim, with the Edit tool. If the config changed in step
     3.3, re-run the step 1.3 diff first. The user approved the old one,
     so show what moved before replacing.

## Step 4 — what the upgrade does not decide

The skill names these and leaves them to the user, one line each:

- New behavior the plugin added that changes what agents do (a new mode
  value, a new review scope): point to `/cfm:configure <domain>`.
- Rules in `rules_file` without teeth: point to the conventions round
  via `/cfm:configure conventions`.
- `.cfm-workflow.local.yml` overrides that pin an outdated model: list
  them. They are personal, so the developer edits them.

## Step 5 — prove it

Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/doctor.py" --project-dir "$(pwd)"`
and show the report next to the baseline: checks fixed, checks still
failing, and any check that got WORSE. A check that got worse is
flagged immediately, with an offer to revert that domain's change. End
with one line: **upgraded to cfm <version>** (applied N of M) or
**unhealthy (N failures)**.

## Hard limits

- Never apply without showing the diff and getting approval.
- The only existing files the upgrade overwrites are the CLAUDE.md guides
  the user selected, via `scaffold.py --replace`. Everything else is a
  surgical edit or a create-if-missing.
- Never re-decide a user's value: profile, git level, autonomy, review
  order, mode, and commands stay as written. A changed default in the
  plugin does not change a value the file sets.
- Refuse invariant changes exactly as `/cfm:configure` step 3 does.
- Never touch git, never run `verify_full`, never read `secret_globs`
  files, never write product code.
- The state file is untouched. Its schema is owned by `scripts/state.py`,
  and the doctor's check 9 validates it.
