# cfm config — schema v2 reference

The shape of `.cfm-workflow.yml`: how the team file and the personal local
file merge into one effective config, every key with its type, default and
allowed values, the hard invariants, and the exact validation wording. Read
the YAML yourself (Read tool); never guess a value from memory — the file
and this document together are the source of truth. Everything a skill
needs from the config comes through the procedures in the last section.

Used by: `/cfm:init`, `/cfm:configure`, `/cfm:mode`, `/cfm:add-agent`,
`/cfm:upgrade`, `/cfm:doctor` (check 1),
`/cfm:plan`, `/cfm:implement-phase`, `/cfm:code-review`,
`/cfm:create-task`, `/cfm:diagnose`, and `/cfm:status` (mode line).

## 1. Files and merge order

| file | role |
|---|---|
| `.cfm-workflow.yml` | team config, committed. Required. |
| `.cfm-workflow.local.yml` | one developer's overrides, gitignored. Optional. |

Precedence, lowest to highest: **built-in defaults ← team file ← local
file**. Merge rule: mappings merge key by key, recursively; a scalar or a
**list** in the higher layer **replaces** the lower one outright (lists are
not unioned — `git: {level: L1}` keeps the default `branch_prefixes`, but
`human_gates: [x]` replaces all four defaults). The one exception is
`secret_globs`, which is unioned with the defaults after the merge
(section 4).

The local file may set ONLY these dotted keys (glob match on each leaf):

```
agents.*.model
agents.*.autonomy
implement.plan_gate
token_reporting
```

Any other leaf anywhere in the local file is a violation. One violation
rejects the **whole** local file — the team config stays in force, every
offending path is reported as an error (wording in section 5), and the run
counts as failed validation. `mode` is a team setting and never lives here.

## 2. Keys

Required = the team file must set it (no default). Paths marked *rel* must
be relative and contain no `..` segment.

### Top level

| key | type | default | allowed / meaning |
|---|---|---|---|
| `cfm.schema_version` | int | required | must be `2` |
| `cfm.requires.surface` | str | required | must be `claude-code` (hard invariant 4) |
| `cfm.requires.min_version` | str | optional | minimum plugin version |
| `profile` | str | `supervised` | `supervised` · `collaborative` · `autonomous`. A bundle name: switching it rewrites `git.level`, agent `autonomy`, `review.trigger` |
| `mode` | str | `enforced` | `enforced` (the doctrine block rendered into CLAUDE.md forbids main-session writes to product code and expects dispatch) · `advisory` (same doctrine, as a preference) · `off` (a one-line notice only). The settings denies apply in every mode; no runtime guard exists in this edition |
| `project_context` | str | required | one non-empty paragraph, passed verbatim in every dispatch brief |
| `layers` | list | required | ≥1 entries of `{name: <str>, path: <str rel>}`; names unique; order = build/dispatch order |
| `feature_roots` | map | `{}` | `<layer name>: <template str rel>`; template must contain `{feature}`; key must name a layer |
| `claude_md.layout` | str | `single` | `single` · `router` (root CLAUDE.md routes to per-layer files) |
| `claude_md.files` | list | `[CLAUDE.md]` | ≥1 paths (*rel*) |
| `commands` | map | `{}` | command slots, section 2.1 |
| `agents` | map | `{}` | agent roster, section 2.2 |
| `review_gates` | list | `[]` | pipeline order, section 2.3 |
| `review.trigger` | str | `phase-gate` | `manual` · `phase-gate` · `pre-commit` — `on-stop` is retired (it needed a Stop hook this edition cannot ship): load it as `phase-gate` with the warning `review.trigger: 'on-stop' is retired — using phase-gate; set manual, phase-gate or pre-commit` |
| `review.auto_scope` | str | `full` | `fast` (code-reviewer only, or the first gate) · `full` (whole pipeline) — on automatic triggers only |
| `review.scope` | str | `phase` | `phase` (one pass over the whole phase diff) · `layer` (a pass after every layer) |
| `implement.plan_gate` | bool | `true` | `true` = full dispatch plan through the plan-mode gate; `false` = one-line scope confirmation (still gated) |
| `git.level` | str | `L0` | `L0` · `L1` · `L2` · `L3`, section 2.4 |
| `git.branch_prefixes` | list | `[feature/, project/, hotfix/, chore/]` | strings, each ending in `/` |
| `forbidden_ops` | list | `[]` | extra command strings the settings denies forbid; extends the level's list, never shrinks it |
| `secret_globs` | list | `[]` | extra secret-file globs; always unioned with the defaults (section 4) |
| `tenancy.scope_field` | str or null | `null` | the tenant field reviewers check scoping against; not validated |
| `human_gates` | list | `[full-test-suite, git-per-level, next-phase-start, feature-scope-confirm]` | not validated |
| `done_criteria` | list | `[tests-green-scoped, gates-pass, progress-log-updated]` | not validated |
| `shared_commands_ack` | list | `[]` | command-slot names whose shared ownership the user acknowledged; strings |
| `token_reporting` | bool | `true` | per-phase token usage reporting |
| `rules_file` | str rel | `.claude/rules/rules.md` | coding rules with `**Enforcement:**` lines |
| `context_file` | str rel | `CONTEXT.md` | project glossary |
| `progress_log` | str rel | `docs/PROGRESS.md` | phase ledger |
| `state_file` | str rel | `.cfm/state.json` | workflow state |

Unknown top-level keys are kept, never rejected (the upgrade skill reports
retired keys such as the old `tracker` block; the loader does not).

### 2.1 Command slots (`commands.<slot>`)

Standard slots: `lint`, `lint_arch`, `typecheck`, `test_scoped`,
`verify_full`, `migrate_generate`, `migrate_apply`. A value is one
non-empty command string or a non-empty list of them; a list means "run
each, in order". Any other slot name is kept as a custom slot with a
warning. Normalising a slot: absent → `[]`; string → one-item list; list →
its string items.

### 2.2 Agents (`agents.<name>`)

Every entry is a mapping with:

| field | type | allowed |
|---|---|---|
| `enabled` | bool | required; `false` drops the agent at load (section 6) |
| `purpose` | str | required |
| `model` | str | required; a full model id. Alias = the first of `fable`, `opus`, `sonnet`, `haiku` found inside the lowercased id; none → no alias (doctor check 5 flags it) |
| `tier` | str | `judgment` · `implementation` · `mechanical` |
| `autonomy` | str | `auto` (dispatch freely) · `confirm` (approve each dispatch brief) · `confirm-plan` (approve the phase's dispatch plan once) |
| `tools` | list | tool names; duplicated in the agent file, which is what Claude Code enforces |
| `owns_commands` | list | optional; command slots only this agent runs |
| `layers` | list | required; layer names from `layers`, or `[any]` |

Model defaults come from the plugin roster, `templates/roster.yml`, not
from the loader: architect → `claude-fable-5` (fable); code-reviewer,
security-check, simplicity-check → `claude-opus-5` (opus); coder,
e2e-test, ui-design → `claude-sonnet-5` (sonnet); mechanical-gate,
code-styling → `claude-haiku-4-5-20251001` (haiku). Init confirms ids
against the live model list before writing them. At dispatch, pass the
alias to the Agent tool's `model` parameter, never the full id.

### 2.3 Review gates (`review_gates`)

A list whose entries are agent names or nested lists of agent names. A
nested list is one parallel step. Every name must be a configured
(enabled) agent. Default pipeline written by init:
`[e2e-test, [code-reviewer, security-check, simplicity-check], mechanical-gate]`.
Dispatch strictly in this order.

### 2.4 Git levels

Levels are cumulative. Grants per level:

| level | grants (added to the level below) |
|---|---|
| `L0` | nothing — read-only |
| `L1` | `git add`, `git commit`, `git stash`, `git rm`, `git mv`, `git restore`, `git cherry-pick`, `git revert`, `git am`, `git apply` |
| `L2` | `git push`, `git checkout`, `git switch`, `git pull`, `git merge`, `git rebase`, `git tag` |
| `L3` | `gh pr create`, `gh pr edit`, `gh pr comment`, `gh pr review`, `gh issue create`, `gh issue edit`, `gh issue comment` |

The full mutating set (34 ops, in this order): `git add`,
`git commit`, `git push`, `git reset`, `git rebase`, `git merge`,
`git stash`, `git tag`, `git rm`, `git mv`, `git pull`, `git checkout`,
`git switch`, `git restore`, `git clean`, `git cherry-pick`, `git revert`,
`git am`, `git apply`, `git worktree`, `git submodule`, `git remote`,
`git notes`, `git config`, `gh pr create`, `gh pr edit`, `gh pr comment`,
`gh pr close`, `gh pr review`, `gh issue create`, `gh issue edit`,
`gh issue close`, `gh issue comment`, `gh release`.

Forbidden at a level = the full set minus everything granted up to that
level. So:

- `L0` forbids all 34.
- `L1` forbids the 24 not granted by L1.
- `L2` forbids: `git reset`, `git clean`, `git worktree`, `git submodule`,
  `git remote`, `git notes`, `git config`, and every `gh` op.
- `L3` forbids: `git reset`, `git clean`, `git worktree`, `git submodule`,
  `git remote`, `git notes`, `git config`, `gh pr close`,
  `gh issue close`, `gh release` — no level ever grants these.

Effective forbidden set = level's list + the config's `forbidden_ops`
(each trimmed, blanks dropped) + the always-forbidden ops, in that order,
duplicates removed. Always forbidden, whatever the level or config:
`gh pr merge`, `gh repo delete`, `gh repo edit`, `gh secret`,
`gh variable`, `gh auth`, `git filter-branch`, `git update-ref`,
`git symbolic-ref`, `git replace`, `git reflog expire`, `git gc`.
An invalid `git.level` counts as `L0` for this computation.

## 3. Hard invariants

1. **Claude Code only** — `cfm.requires.surface` must be `claude-code`.
2. **`secret_globs` is extendable, never shrinkable** — the defaults are
   always in force; the file lists only extras.
3. **Git forbids extend, never shrink** — `forbidden_ops` adds to the
   level's list; the always-forbidden ops cannot be unlocked.
4. **Local overrides are limited** to the four allowlisted keys; one bad
   key rejects the whole local file.
5. **Paths stay inside the project** — no absolute paths, no `..`.

No profile, argument or user request unlocks any of these. Decline with
one sentence of why.

## 4. Default secret globs

Always present in the effective `secret_globs`, verbatim:

```
.env*
*.env
*.pem
*.key
*.p12
*.pfx
*.jks
*.keystore
id_rsa*
id_dsa*
id_ecdsa*
id_ed25519*
.npmrc
.pypirc
.netrc
.git-credentials
.htpasswd
.pgpass
**/credentials
service-account*.json
secrets.json
secrets.yml
secrets.yaml
secrets.toml
kubeconfig*
*.tfstate
*.tfvars
```

Effective list = the file's string entries, then every default not already
listed, duplicates removed, order kept. When the team file sets
`secret_globs` as a list that omits any default, emit a warning (not an
error) and re-add them:
`secret_globs: re-added default globs the file omits (extendable, never shrinkable — hard invariant): [<omitted globs>]`.

## 5. Validation rules and exact wording

Run every rule; collect all errors, never stop at the first. Report
warnings as `warning: <text>` and errors as `error: <text>`, one per line.
Any error = validation failed.

### File-level

| condition | error |
|---|---|
| team file missing | `.cfm-workflow.yml not found in <project dir> — run /cfm:init` |
| file cannot be read | `<file>: unreadable: <reason>` |
| file is not parseable YAML | `<file>: not valid YAML: <reason>` |
| file parses to nothing (empty, comments only) | `<file>: file is empty` |
| top level is a list or scalar | `<file>: top level must be a mapping` |
| local file sets a disallowed key | `.cfm-workflow.local.yml: override of '<dotted.path>' is not permitted (local overrides are limited to: agents.*.model, agents.*.autonomy, implement.plan_gate, token_reporting)` — one per offending path |

A missing, empty or malformed team file stops everything: there is no
effective config. A malformed local file is an error but the team config
still loads.

### Generic field checks

For a field with a required type: missing → `<key>: required field is
missing`; wrong type → `<key>: expected <type>, got <actual type>`
(type names: `int`, `str`, `bool`, `list`, `dict`; actual names as YAML
yields them: `str`, `int`, `float`, `bool`, `list`, `dict`,
`NoneType`); value outside an enum → `<key>: '<value>' is not one of
['a', 'b', 'c']` with the allowed list in the order of section 2. Bad
paths → `<key>: must be a relative path inside the project`.

### Field-specific

| key | extra error |
|---|---|
| `cfm.schema_version` | `cfm.schema_version: <n> unsupported (supported: [2])` |
| `cfm.requires.surface` | `cfm.requires.surface: must be 'claude-code' (hard invariant — cfm runs only in Claude Code), got '<value>'` |
| `project_context` | blank → `project_context: must be a non-empty paragraph` |
| `layers` | empty → `layers: at least one layer is required`; bad entry → `layers[<i>]: must be {name: <str>, path: <str>}`; repeats → `layers: duplicate layer names: ['x', 'y']` (sorted) |
| `feature_roots.<name>` | `feature_roots.<name>: no layer named '<name>'`; `feature_roots.<name>: must be a string containing {feature}` |
| `claude_md.files` | empty → `claude_md.files: must list at least one CLAUDE.md path` |
| `commands.<slot>` | non-standard → warning `commands.<slot>: not a standard slot (standard: lint, lint_arch, typecheck, test_scoped, verify_full, migrate_generate, migrate_apply) — kept as custom`; bad value → `commands.<slot>: must be a non-empty command string or list of them` |
| `agents.<name>` | not a mapping → `agents.<name>: must be a mapping`; field errors are prefixed `agents.<name>.<field>: …` (e.g. `agents.coder.tier: 'x' is not one of ['judgment', 'implementation', 'mechanical']`); unknown layer → `agents.<name>.layers: no layer named '<l>'` |
| `review_gates` | `review_gates: '<gate>' is not a configured agent` — for every entry, flat or nested, that is not an enabled agent name |
| `git.branch_prefixes` | `git.branch_prefixes: '<p>' must be a string ending in '/'` |
| `secret_globs` | `secret_globs: entries must be non-empty strings, got <repr>` |
| `forbidden_ops` | `forbidden_ops: entries must be command strings, got <repr>` |
| `shared_commands_ack` | `shared_commands_ack: entries must be command-slot strings, got <type>` |

Checks on layer names (`feature_roots`, agent `layers`) are skipped when
`layers` itself failed. Agents are validated after disabled ones are
dropped, so a disabled agent's other fields are never checked — but
`enabled` must be a real boolean; `enabled: "false"` (a string) keeps the
agent and fails with `expected bool, got str`.

## 6. Disabled agents are dropped at load

After the merge and before validation: every agent whose `enabled` is
exactly `false` is removed from `agents`, and its name is removed from
`review_gates` — from flat entries and from inside parallel groups; a
group left empty disappears. No warning is emitted. The effective config
therefore carries ONLY enabled agents: a disabled agent is never
dispatched, validated, counted, planned or reported. Its name may still
sit in project prose (CLAUDE.md, rules, glossary); that sweep belongs to
`/cfm:configure` step 5 and doctor check 4, not to loading.

The default roster (names, purposes, tools, model defaults, activating
layers — `ui-design` only joins when a layer named `web`, `frontend`, `ui`
or `app` exists) is `${CLAUDE_PLUGIN_ROOT}/templates/roster.yml`. Agents
are copied into the team file at init; custom agents added later follow
the same schema and carry `enabled: true` explicitly.

## 7. Procedures

### Load and validate the config (effective config)

1. Read `.cfm-workflow.yml` at the project root. Missing → the
   `not found` error; the skill sends the user to `/cfm:init` and stops.
2. Parse it as YAML 1.1 (section 8). Not parseable, empty, or not a
   mapping → the matching file-level error; stop — there is no config.
3. If `.cfm-workflow.local.yml` exists, parse it the same way. Collect
   every dotted leaf path it sets (descend mappings; a list or scalar is
   a leaf). Any path not matching the four allowlisted patterns →
   one `override … is not permitted` error per path, and discard the
   whole local file.
4. Build the effective config: start from the defaults in section 2,
   merge the team file over them, then the surviving local file, using
   the merge rule in section 1. A bare `off` under `mode` means `off`.
5. `secret_globs`: file entries then every missing default; warn if the
   team file listed the key and omitted a default (section 4).
6. Drop disabled agents and their gates (section 6).
7. Apply every rule in section 5, collecting errors and warnings.
8. Show warnings. If there are errors, go to "report validation errors
   and stop". Otherwise the effective config is what every later step
   reads: `layers` order, `agents` (enabled only), `review_gates`,
   `review.*`, `implement.plan_gate`, `git.level`, the four paths.

Validation never mutates either file. Only `/cfm:configure`,
`/cfm:mode`, `/cfm:add-agent`, `/cfm:upgrade`
and `/cfm:init` write config, each as a diff applied on approval.

### Read one key

Load and validate first — a key read from a config with errors is not
trustworthy and must not be used. Then walk the dotted path through the effective config:
`review.trigger`, `agents.coder.model`, `git.level`. A
missing path is "unset" (empty), not an error. Report booleans as
`true`/`false`, lists as a comma-separated line. A key absent from the
file resolves to its default (`mode` → `enforced`, `git.level` → `L0`),
never to "unset".

### Report validation errors and stop

1. Print every `warning:` line, then every `error:` line, verbatim in
   the wording of section 5 — the user searches this document and the
   doctor by those strings.
2. Say which file each error concerns (the prefix for file-level errors;
   `.cfm-workflow.yml` for schema errors unless the key is one of the
   four local-overridable ones and the local file sets it).
3. Send the user to `/cfm:doctor` (checks 1 and 2 explain each failure
   with its fix) or `/cfm:configure` for the key in question. Then STOP
   — never plan, implement, review or dispatch on a broken config, and
   never edit the config to "fix" it from a read-only skill.
4. `/cfm:configure` alone may continue, for the domains the errors do
   not touch. After any skill writes config, re-run this load; an error
   on what was just written is that skill's to fix before moving on,
   never by changing the user's other config.

### Validate after a write

Re-run "load and validate" on the edited files and expect zero errors.
Then run `/cfm:doctor` — the loader checks shape; the doctor checks that
paths exist, commands run, agent files match, and denies are current.

## 8. Reading YAML by hand

The loader used YAML 1.1 (PyYAML `safe_load`) semantics. Mirror them:

- Bare `true/false/yes/no/on/off` (any case) are booleans; bare
  `null`, `~` or an empty value is null; bare digits are integers;
  anything quoted is a string. Hence `mode: off` is the boolean `false`,
  which the loader maps back to the string `off`; write it as
  `mode: "off"` to avoid the ambiguity. `enabled: no` is a valid
  boolean `false`; `profile: on` would be `expected str, got bool`.
- Duplicate keys in one mapping are not an error: the last wins.
- `[a, b]` and the dashed block form are the same list; `{k: v}` and
  the indented block form are the same mapping.
- A file that holds only comments or blank lines parses to nothing
  (→ `file is empty`).

Treat the file as malformed — and emit `<file>: not valid YAML:
<reason>` with a one-phrase reason — when any of these holds:

- a line begins with a tab (`grep -nP '^\t' .cfm-workflow.yml`);
- a block's children are indented inconsistently, or a value sits at a
  shallower indent than its key;
- a quote, bracket or brace is opened and not closed on the same value;
- a mapping key has no `: ` separator, or a plain scalar contains `: `
  or ` #` without quoting in a position that makes the structure
  ambiguous;
- a line mixes a list item and a mapping key in a way that cannot be
  resolved to one structure.

When unsure, quote the offending line and its number in the reason, state
the structure you could not resolve, and stop; never guess a value and
continue. The fix is the user's: point them at the line, suggest quoting
the value or fixing the indent, and recommend `/cfm:doctor` afterwards.
