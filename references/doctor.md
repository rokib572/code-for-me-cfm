# cfm doctor — reference

The doctor converts config promises into facts: ten checks (0-9) that read
`.cfm-workflow.yml`, the files it names, `.claude/settings.json`, the agent
files and the state ledger, run the lint-class command slots, and print one
report. The plugin ships no script for this. Claude runs every check by hand
with Read, Glob, Grep and short shell commands, in order, and prints the
report in the shape below. A check never edits a file: it reports, the user
or the owning skill fixes, the doctor runs again.

**Used by:** `/cfm:doctor` (the full run), `/cfm:init` (until green),
`/cfm:configure`, `/cfm:mode`, `/cfm:add-agent`, `/cfm:connect-tracker`
(automatic run after every applied diff), `/cfm:upgrade` (baseline and
final run, compared).

## Ground rules

- Order is fixed: 0 → 9. Check 0 failing on the environment gate STOPS the
  run; nothing else is checked.
- Config unavailable (check 1 could not parse the file) → checks 2-9 are
  SKIP, not FAIL.
- Status per check: any failure → FAIL; else any warning → WARN; else PASS;
  a check that could not run → SKIP.
- Never read a file that matches a `secret_globs` entry, in any check. The
  secrets check inspects names, `.gitignore` lines and `.env.example` only.
- Never run `verify_full`, `test_scoped`, or a `migrate_*` slot. Human-only
  and mutating slots are never executed by the doctor; templates cannot run
  without arguments.
- Never edit `.cfm-workflow.yml` or any project file to "fix" a finding.
  Propose the fix, let the user apply or approve it, then re-run.
- Hard invariants (Claude Code only, secret globs never shrinkable, rules
  need teeth, no direct push to main) are not fixable by relaxing config —
  if the user asks to disable one, decline and explain it is
  non-configurable.

## Output contract

Print exactly this shape, one check per block, in check order:

```
cfm doctor
[PASS] #0 environment
    · running inside Claude Code
    · cfm 1.0.5 satisfies min_version 1.0.0
[FAIL] #2 paths
    ✘ layers.api: path does not exist: apps/api
    ⚠ progress_log: docs/progress.md does not exist yet (created by the workflow)
...
verdict: healthy
```

- Header line `cfm doctor`.
- One status line per check: `[STATUS] #<n> <name>` with STATUS one of
  PASS, WARN, FAIL, SKIP and the names in the table below.
- Under it, in this order: every failure as `    ✘ <message>`, every warning
  as `    ⚠ <message>`, every note as `    · <message>`. A SKIP line has no
  children.
- Last line: `verdict: healthy` when no check is FAIL, otherwise
  `verdict: UNHEALTHY — fix the failures above`.
- The skill's closing line is separate: **healthy** or
  **unhealthy (N failures)** with N the total failure count.

| # | name |
|---|---|
| 0 | environment |
| 1 | schema & invariants |
| 2 | paths |
| 3 | commands |
| 4 | roster coherence |
| 5 | models |
| 6 | rules have teeth |
| 7 | secrets hygiene |
| 8 | pipeline wiring |
| 9 | state |

Message wording below is exact: quote it, substituting the `<...>` parts.

## Check 0 — environment

The gate script is gone; the test stays as a Bash one-liner.

1. Run `test "$CLAUDECODE" = "1"`. Non-zero → failure:
   `cfm runs only in Claude Code (terminal, IDE, or the Desktop Code tab).`
   then STOP the whole run; print the verdict as UNHEALTHY.
   Zero → note `running inside Claude Code`.
2. Config unavailable → warning
   `config unavailable — min_version not checked`; done.
3. Read `cfm.requires.min_version` from the config and `version` from
   `${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json`. Compare as numeric
   tuples (`1.0.5` → 1,0,5). Installed lower → failure
   `config requires cfm >= <min_version>, installed plugin is <version> — update cfm`.
   Otherwise note `cfm <version> satisfies min_version <min_version>`.
   Either value absent → nothing to report.

## Check 1 — schema & invariants

Read `.cfm-workflow.yml` and, if present, `.cfm-workflow.local.yml`.
Validate schema v2 and the hard invariants as `references/config.md` defines
them. Every loader error is a failure, every loader warning a warning,
verbatim. No errors → note
`config parses; schema v2 valid; hard invariants intact`.

The invariants the loader enforces, so the by-hand pass does not miss them:

- `cfm.requires.surface` must be `claude-code` (hard invariant 4).
- `secret_globs` is extendable, never shrinkable: the default glob list is
  always unioned in. A file that lists a subset gets them back with the
  warning `secret_globs: re-added default globs the file omits (extendable,
  never shrinkable — hard invariant): [<omitted>]`.
- `.cfm-workflow.local.yml` may override only `agents.*.model`,
  `agents.*.autonomy`, `implement.plan_gate`, `token_reporting`. Any other
  key → error `.cfm-workflow.local.yml: override of '<path>' is not
  permitted (local overrides are limited to: <allowlist>)` and the whole
  local file is ignored.
- `mode: off` is read by YAML 1.1 as `false`; treat `false` as `off`.
- Agents with `enabled: false` are dropped from the merged config along
  with their review gates; later checks never see them.
- `profile`, `mode`, `layers` (non-empty, relative paths, unique names),
  `project_context` (non-empty), `commands` slot names, `agents.*` fields,
  `review`, `git.level`, `rules_file`, `state_file` and the rest, as the
  schema lists them.

## Check 2 — paths

All paths relative to the project root; `test -e <path>`.

- Each `layers[].path` missing → failure
  `layers.<name>: path does not exist: <path>`.
- Each `claude_md.files[]` missing → failure
  `claude_md.files: routing target missing: <file>`.
- `rules_file` missing → failure `rules_file: does not exist: <path>`.
- `progress_log` or `state_file` missing → warning
  `<field>: <path> does not exist yet (created by the workflow)`.
- `context_file` missing → warning
  `context_file: <path> does not exist — dispatched agents have no shared
  vocabulary; /cfm:init scaffolds it` (a glossary is earned term by term;
  absence is not a failure).
- Each `feature_roots.<name>` template containing `{feature}`: take the text
  before `{feature}`, strip the trailing `/`; if non-empty and missing →
  warning `feature_roots.<name>: base directory missing: <prefix>`.

## Check 3 — commands

A slot value is one string or a list of strings; check each command.

Slot policy:

| slot | policy |
|---|---|
| lint, lint_arch, typecheck | run |
| test_scoped | template — never run |
| verify_full | exists — contractually the human's command, never run |
| migrate_generate, migrate_apply | resolve — mutating, resolve the binary only |
| any custom slot | resolve |

1. `commands.verify_full` absent or empty → failure
   `commands.verify_full: must be defined — it is the human's command
   (agents are banned from running it, but it has to exist)`.
2. For every command in every slot except `verify_full`, resolve the binary:
   the first shell word. Absolute path → must be executable. Contains a
   `/` → executable relative to the project root. Otherwise `command -v
   <word>`. Unresolved → failure
   `commands.<slot>: binary not found for: <command>`; skip the rest for
   that command.
3. `test_scoped`: no `{files}` → failure
   `commands.<slot>: template must contain {files}: <command>`.
   Has `{files}` but no `{pkg}` → warning
   `commands.<slot>: no {pkg} placeholder — fine for single-package repos`.
4. `lint`, `lint_arch`, `typecheck`: run the command verbatim through the
   shell from the project root with a 120-second timeout. Exactly as
   configured, nothing added, nothing substituted; these are the project's
   own read-only checks and the only slots the doctor ever executes.
   Timeout → failure
   `commands.<slot>: timed out after 120s: <command>`.
   Non-zero exit → failure
   `commands.<slot>: exited <code>: <command> — <detail>` where detail is
   the last three lines of stderr (stdout if stderr is empty) joined with
   ` | `, or `no output`.
   Zero → note `commands.<slot>: green (<command>)`.
5. Standard slots not in `commands` at all (`lint`, `lint_arch`,
   `typecheck`, `test_scoped`, `verify_full`, `migrate_generate`,
   `migrate_apply`) → one note
   `absent slots (capability deactivated): <a, b, c>`.

## Check 4 — roster coherence

Only `enabled: true` agents count; a disabled agent runs nothing. Shipped
agents are the files in `${CLAUDE_PLUGIN_ROOT}/agents/*.md`; any other
agent name is custom and lives in `.claude/agents/<name>.md`.

1. Layers: an enabled agent whose `layers` list contains no configured
   layer name → failure
   `agents.<name>: enabled but none of its layers exist — it can never activate`.
2. Ownership: for each enabled agent, each `owns_commands` entry. Entry is
   `verify_full` → failure
   `agents.<name>: owns_commands lists verify_full — verify_full is the
   human's command — no agent may own it`. Collect owners per slot.
3. Agent files. Config `tools` is a promise; the file's frontmatter is what
   Claude Code enforces. Mutating tools: Write, Edit, MultiEdit,
   NotebookEdit, Bash.
   - Shipped agent: read the plugin file's frontmatter `tools`. File grants
     tools the config omits: any of them mutating → failure
     `agents.<name>.tools omits [<extra>], but the shipped agent file grants
     them — Claude Code enforces the file, so the config understates what
     this agent can do; list the file's tools [<file tools>] or add a custom
     agent instead`; all read-only → warning
     `agents.<name>.tools omits read-only [<extra>] that the shipped agent
     file grants — align the config`. Config lists tools the file lacks →
     warning `agents.<name>.tools lists [<missing>] that the shipped agent
     file does not grant — the file wins at dispatch`. Config model alias
     (fable/opus/sonnet/haiku, by substring) differs from the file's →
     note `agents.<name>.model resolves to '<cfg alias>'; the orchestrator
     passes that alias at dispatch (the shipped file's '<file alias>' is
     only the fallback)`.
   - Custom agent: `.claude/agents/<name>.md` absent or unreadable →
     failure `agents.<name>: custom agent has no .claude/agents/<name>.md —
     without it the agent is dispatched with EVERY tool and its config tools
     are unenforced; /cfm:add-agent or /cfm:upgrade writes it`. Present but
     frontmatter `name` differs or the tool set differs → failure
     `agents.<name>: .claude/agents/<name>.md frontmatter (name '<fm
     name>', tools [<file tools>]) drifted from config (tools [<cfg
     tools>]) — /cfm:upgrade re-renders it`.
4. Shared ownership: each slot with two or more owners. Slot listed in
   `shared_commands_ack` → warning
   `shared ownership of <slot> acknowledged — the doctor will keep nagging
   (owners: <a, b>)`; otherwise failure
   `commands.<slot>: shared ownership (<a, b>) violates the single-owner
   matrix — reassign, or acknowledge via shared_commands_ack: [<slot>]`.
5. Stale references to disabled agents (names with `enabled: false` in the
   raw file): grep each name as a whole word (not adjacent to `[A-Za-z0-9_-]`)
   in `CLAUDE.md`, `.cfm-workflow.local.yml`, every `claude_md.files` entry,
   `rules_file`, `context_file`, and every file under `.claude/` except
   `settings.json` and `settings.local.json`. A disabled CUSTOM agent's own
   `.claude/agents/<name>.md` is a whole-file hit. Each hit → warning
   `<path>:<line> still names disabled agent '<name>' — remove the
   reference (/cfm:upgrade or /cfm:configure sweeps them)` (no `:<line>`
   for a whole-file hit).
6. No failures and no warnings → note
   `layers resolve, single-owner matrix clean`.

## Check 5 — models

For each enabled agent with a string `model`. WARN, not FAIL: model is
free text by design.

- Empty or whitespace → warning `agents.<name>.model: empty string`.
- Not matching `claude-[A-Za-z0-9][A-Za-z0-9.-]*` → warning
  `agents.<name>.model: '<model>' does not look like an Anthropic model id
  (expected claude-*)`.
- No alias substring (`fable`, `opus`, `sonnet`, `haiku`) → warning
  `agents.<name>.model: '<model>' has no dispatch alias
  (fable/opus/sonnet/haiku) — the Agent tool's model parameter takes an
  alias, so this agent will run on its file's default model`.
- Always note `live model-list verification is done by the doctor skill`.

The live part is Claude's: verify each configured id against the models
known to exist today, flag any that no longer resolves, suggest
`/cfm:configure agents`.

## Check 6 — rules have teeth

`rules_file` missing → SKIP (check 2 owns that failure). Otherwise read it.

- Rules are `## R<n>` headings (`## R1. Title`). None → warning
  `<rules_file>: no rules found (expected '## R<n>. <title>' headings)`;
  done.
- Each rule block (heading to next heading) needs a
  `**Enforcement:** <text>` line. Absent → failure
  `R<n>: no '**Enforcement:**' declared — rules without teeth are rejected
  (hard invariant 3)`.
- Enforcement text that is exactly `reviewer(<name>)`: `<name>` must be an
  enabled agent, else failure
  `R<n>: enforcement names reviewer '<name>' which is not an enabled agent
  — teeth require a live owner`. Other forms (`lint(...)`, `hook(...)`,
  `ci(...)`, `doctor(...)`, free text) are accepted.
- Enforcement mentions `lint(` while neither `commands.lint` nor
  `commands.lint_arch` is configured: collect, then one warning
  `R<a>, R<b>: enforcement claims lint(...) but neither the 'lint' nor the
  'lint_arch' command slot is configured — nothing runs it; assign a
  reviewer instead`.
- No failures → note `<count> rules, all with declared enforcement`.

## Check 7 — secrets hygiene

Keep a `verified` list of what actually ran so the success note never
overclaims. `is_repo` = `.git` exists. `env_files` = top-level entries
starting with `.env` (`ls -A | grep '^\.env'`).

### .gitignore env-family coverage

Applies when `is_repo` or `env_files` is non-empty; otherwise note
`.gitignore rule deferred — applies once the project is a git repo or a
.env* file exists`.

- No `.gitignore` → failure `.gitignore missing — the .env glob family is uncovered`.
- Compare stripped lines exactly. No `.env*` line: a bare `.env` line →
  failure `.gitignore: bare '.env' leaves the rest of the env family
  committable (.env.local etc — use '.env*', and '!.env.example')`;
  otherwise failure `.gitignore does not cover the env family — add
  '.env*' (and '!.env.example')`.
- `.env*` present, no `!.env.example` → warning `.gitignore: no
  '!.env.example' negation — the sanctioned example file gets ignored too`.
- Both present: later rules win, so the last `!.env.example` must come
  after the last line starting with `.env`. If not → warning
  `.gitignore: '!.env.example' appears before the env ignore lines — the
  negation is overridden by later rules — move '!.env.example' last`.
- Add `.gitignore env coverage checked` to verified.

### .env.example NAME= form

Absent → note `.env.example absent — nothing to verify`. Present: read it
(it is the one env-family file that is safe to open). Skip blank and `#`
lines. For each other line, split on the first `=`:

- No `=` → failure `.env.example:<lineno>: line is not NAME= form (content
  not shown)`. Never echo any part of the line; it could be a pasted token.
- Non-blank value → failure `.env.example:<lineno>: '<NAME>' must be
  'NAME=' with a blank value (value not shown)`. The name alone locates it.
- Add `.env.example values blank` to verified.

### Tracked secrets

`is_repo` only. `git ls-files`; match each path and its basename against
the merged `secret_globs` (config list plus the defaults — the set never
shrinks; a `**/` prefix also matches at the root). Each match → failure
`tracked file '<path>' matches secret glob '<glob>' (critical) — a secret
that touched git history is burned — rotate it`. Add `no tracked secrets`
to verified. Then `.git/hooks/pre-commit`: absent → warning `no pre-commit
hook installed — install it via /cfm:code-review's trigger section`;
present without the text `gitleaks` → warning `.git/hooks/pre-commit does
not mention gitleaks — staged-content secret scan is missing`. Either
warning also adds the closing note `the pre-commit hook stays WARN, not
FAIL — it protects the human's commits, not the agents' tool calls`.

### Settings denies

Read `.claude/settings.json` (absent = `{}`). Not a JSON object, or
`permissions` / `sandbox` present but not objects → warning
`.claude/settings.json: unreadable (<reason>)` and skip the rest of this
section. Otherwise compute per `references/settings-denies.md`: the
required deny set for this config, the cfm-owned set (the
`.claude/cfm-denies.json` sidecar plus every level-independent cfm shape),
and from them `missing` (required, absent from `permissions.deny`) and
`stale` (present, cfm-owned, no longer required).

- `stale` non-empty and check 1 had no errors → failure
  `<n> stale deny entries in .claude/settings.json from an earlier config
  (<first three>, …) — the permission layer contradicts the config;
  regenerate the denies to retract them`.
- `missing` non-empty and check 1 had errors → warning `<n> deny entries
  missing from .claude/settings.json — not failed because the config has
  schema errors; fix those, then regenerate the denies`.
- `missing` non-empty otherwise → failure `<n> deny entries missing from
  .claude/settings.json — the permission layer is the enforcement; regenerate
  the denies (cfm:init does this; /cfm:configure re-offers it)`.
- Else add `settings denies present` to verified.
- `sandbox.enabled` is true: compare `sandbox.filesystem.denyRead` /
  `denyWrite` with the cfm entries settings-denies.md lists. Gaps →
  warning `sandbox is enabled but <n> cfm filesystem entries are missing
  (<first>, …) — regenerate the sandbox block; verify the resolved paths in
  /sandbox → Config`; none → add `sandbox OS-level denies present` to
  verified. Sandbox off → note `Bash sandbox off: the secret and
  policy-file rules are enforced on command TEXT only (settings denies);
  the sandbox block adds the OS-level layer that closes the interpreter,
  variable and script-file evasions`.
- Every `permissions.allow` entry: starts with `mcp__` and contains `*` →
  warning `.claude/settings.json: allow '<rule>' is a wildcard over a whole
  MCP server — replace it with the exact tool names sync uses`; starts with
  `Bash(claude mcp add` → warning `.claude/settings.json: allow '<rule>'
  lets an agent register any MCP server — including a stdio server, which
  is an arbitrary command — without a prompt; remove it`.

No failures and verified non-empty → note the verified items joined by
`, `.

## Check 8 — pipeline wiring

The plugin ships no hooks, so the former hook-wiring and guard self-test
parts are replaced (said inline below); the status-line, on-stop and
subagent-observed parts are dropped. Enforcement now rests on the settings
denies, the doctrine rendered into CLAUDE.md, and the agent files' tool
limits (check 4).

Mode = `mode` from the merged config (`enforced` by default).

1. Settings deny layer (replaces the guard self-test). Reuse check 7's
   deny result; do not recompute. Denies present and none stale → note
   `settings deny rules present and not stale (check 7)`. Otherwise
   failure `settings deny rules missing or stale — the only enforcement
   layer is absent; see check 7`.
2. CLAUDE.md doctrine block (replaces the session-context hook test).
   `references/scaffold.md` defines the render; the doctor detects the
   block as the region between `<!-- cfm:begin -->` and `<!-- cfm:end -->`
   in the root `CLAUDE.md`, which carries a heading `## cfm mode: <MODE>`
   with MODE upper-case. Zero or two begin markers, or an end marker
   before the begin marker, is the same as an absent block.
   - Mode `enforced` or `advisory`: block absent → failure
     `CLAUDE.md carries no cfm doctrine block (no <!-- cfm:begin --> …
     <!-- cfm:end --> region) — the orchestrator doctrine never reaches
     the session; /cfm:init or /cfm:upgrade renders it`. Present but the mode line is missing or names another mode →
     failure `CLAUDE.md doctrine block does not announce cfm mode '<mode>'
     — re-render it (/cfm:mode)`. Correct → note `cfm mode: <mode> —
     doctrine rendered into CLAUDE.md, routing through /cfm:* skills`, with
     `; the orchestrator rule is advisory` appended when mode is advisory.
   - Mode `off`: block absent, or present announcing `OFF` → note
     `cfm mode: off — no doctrine block required`. Present announcing
     another mode → failure `cfm mode is off but CLAUDE.md still carries an
     '<MODE>' doctrine block — re-render it (/cfm:mode)`.
3. `review.trigger` is `pre-commit` and `.git/hooks/pre-commit` is absent
   → failure `review.trigger is 'pre-commit' but .git/hooks/pre-commit is
   not installed — the configured trigger has no teeth`.

## Check 9 — state

`state_file` absent from config or not a string → nothing to report (a
typing error is check 1's). File missing → note
`<state_file> absent — no phase started yet`.

Otherwise read it and validate against the schema in `references/state.md`
(the same rules every writer applies before a save, so a failure here means
the file was hand-edited or written by something else). Unparseable →
failure `<state_file>: <error>`. Each schema error → failure
`<state_file>: <error>`; each schema warning → warning
`<state_file>: <warning>`. `phase.status` is `in-flight` and
`phase.plan` names a path that does not exist → failure
`orphaned in-flight phase references missing plan <plan>`. No failures →
note `<state_file> is schema-valid (v1); no orphaned in-flight phase`.

## After a config change: automatic run and baseline comparison

Every skill that applies a diff to `.cfm-workflow.yml`, the rules file,
CLAUDE.md, the agent files or the settings denies runs the doctor
automatically right after the apply and shows the full report. A change
that turns the doctor red is flagged immediately with an offer to revert
that diff. When check 7 reports denies missing or stale, the skill offers
to regenerate them per `references/settings-denies.md` (a second,
sequential diff) and runs the doctor again.

`/cfm:upgrade` keeps the report from its first run as the baseline. After
its last apply it runs the doctor again and shows the two side by side,
per check:

- **fixed**: FAIL or WARN in the baseline, PASS now;
- **still failing**: the same FAIL (or WARN) in both, with its messages;
- **worse**: PASS → WARN, PASS → FAIL, WARN → FAIL, or a new failure
  message on a check that already failed.

Compare by check number and by failure/warning message text, not by
count. A check that got worse is flagged immediately with an offer to
revert that domain's change. End with one line: **healthy** or
**unhealthy (N failures)**.
