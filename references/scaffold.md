# Workflow scaffold — rendered by hand from `.cfm-workflow.yml`

The workflow scaffold is the set of files cfm owns in a project: the
CLAUDE.md guides, the rules seed, the glossary, `.env.example`, the
`.gitignore` entries, the progress log, and the initial state file. Every
one of them is a deterministic render FROM the validated config, so config
and scaffold cannot drift. This edition ships no scripts and no hooks, so
Claude renders them itself with Read, Glob, Edit and Write, following this
document exactly. The orchestrator doctrine that the SessionStart and
UserPromptSubmit hooks used to inject now lives inside CLAUDE.md, which
Claude Code loads every session. Nothing here names a package manager,
framework, or language: the stack skeleton is always dispatched to the
coder agent (`skills/init/references/scaffold.md`).

**Used by:** `/cfm:init` (first render), `/cfm:upgrade` (dry run, diff,
re-render of CLAUDE.md guides), `/cfm:doctor` (locates the cfm-owned
region of CLAUDE.md), `/cfm:mode` (re-renders the doctrine after a mode
change).

## Placeholders

- `{{name}}` — a config value, substituted verbatim.
- `{{for each X}} … {{end}}` — the block repeats once per item, in config
  order. Inside it, `{{X.field}}` is that item's field.
- `{{if COND}} … {{else}} … {{end}}` — render one branch.
- `{{today}}` — today's date as `YYYY-MM-DD`, unless the skill names one.

Every placeholder is replaced in the rendered file. A `{{` left in a
written file is a scaffold bug.

## Inputs

Read `.cfm-workflow.yml` at the project root. Scaffold only from a config
the doctor's schema check accepts; if it is invalid, fix the config first
and never hand-write the files the scaffold would have rendered. Apply
these defaults for absent keys:

| key | default |
|---|---|
| `mode` | `enforced` |
| `claude_md.layout` | `single` (`router` is the other value) |
| `claude_md.files` | `["CLAUDE.md"]` |
| `rules_file` | `.claude/rules/rules.md` |
| `context_file` | `CONTEXT.md` |
| `progress_log` | `docs/PROGRESS.md` |
| `state_file` | `.cfm/state.json` |
| `git.level` | `L0` |
| `human_gates` | `full-test-suite`, `git-per-level`, `next-phase-start`, `feature-scope-confirm` |
| `secret_globs` | the config list UNIONED with the defaults: `.env*`, `*.env`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, `*.jks`, `*.keystore`, `id_rsa*`, `id_dsa*`, `id_ecdsa*`, `id_ed25519*`, `.npmrc`, `.pypirc`, `.netrc`, `.git-credentials`, `.htpasswd`, `.pgpass`, `**/credentials`, `service-account*.json`, `secrets.json`, `secrets.yml`, `secrets.yaml`, `secrets.toml`, `kubeconfig*`, `*.tfstate`, `*.tfvars` |

A layer counts only when it is a mapping with a string `path`. A command
slot's value is one string or a list of strings; display a list joined
with ` ; `. An agent counts as enabled only when `enabled: true` — a
disabled agent owns no slot, enforces no rule, and is never listed.

## What the scaffold writes

In this order. Paths are relative to the project root; normalize them
(`./a/../b` → `b`, forward slashes).

| # | path | content | reason line |
|---|---|---|---|
| 1 | `CLAUDE.md` | root guide (template below) | `root workflow guide` |
| 2 | `<layer.path>/CLAUDE.md`, per layer, ONLY under `layout: router` | layer guide | `layer guide (<layer.name>)` |
| 3 | each `claude_md.files` entry not already planned | a layer guide when the path equals `<layer.path>/CLAUDE.md`; otherwise a stub, plus the warning `claude_md.files: '<entry>' does not correspond to the root or a configured layer — rendered as a stub; fix via /cfm:configure` | `layer guide (<name>)` / `stub — listed in claude_md.files, no matching layer` |
| 4 | `{{rules_file}}` | rules seed | `rules seed (2 starter rules, enforcement declared)` |
| 5 | `{{context_file}}` | glossary seed | `project glossary (empty — terms are earned, not guessed)` |
| 6 | `.env.example` | names-only header | `variable names only, no values` |
| 7 | `{{progress_log}}` | progress ledger | `progress ledger (newest first, Carried forward)` |
| 8 | `{{state_file}}` | initial state | `workflow state, schema v1, no phase in flight` |
| 9 | `.gitignore` | append-only entries | `appended N line(s): <lines>` |

**Keep, never clobber.** Before writing any of 1–8, check the path with
Glob. If anything exists there — a file, a directory, a symlink, even a
dangling one — leave it untouched and report it as `kept … exists — left
untouched`. There is no force flag, by design. Create parent directories
as needed. A target that resolves outside the project directory (a `..`
path, or a symlinked parent) is never written: report it as blocked.

**Dry run.** When the skill asks for a dry run (`/cfm:upgrade` step 1),
render everything in memory, run the same checks, and print the summary
with `would-write` in place of `written`. Write nothing.

**Replace (CLAUDE.md guides only).** The single sanctioned overwrite, run
by `/cfm:upgrade` after the user approved the diff of a named guide:

1. The path must be a CLAUDE.md guide the config renders (root, a layer
   guide, or a listed file), an existing regular file inside the project,
   not a symlink. Anything else: `error: <path> — not an existing regular
   file inside the project — not replaced`, and stop.
2. Read the file. Find `<!-- cfm:begin -->` … `<!-- cfm:end -->`. Replace
   that region, markers included, with the fresh rendering's region, with
   one Edit. Everything outside the markers (the conventions round's
   `## Feature structure`, the user's own sections) stays byte-for-byte.
3. No markers (a guide from an edition before the markers): list every
   `## ` heading the re-render would drop, show the full diff, and only on
   approval Write the fresh rendering; then re-append each dropped
   `## Feature structure` section verbatim outside the markers.
4. Report `  replaced    <path>`.

To diff a guide without writing (the old `--print`), render it in memory
and compare against the file on disk; any difference is an upgrade finding.

**Summary format.** Print exactly this shape after a render or dry run:

    cfm scaffold — <absolute project dir>[ (dry-run)]
      written     <path> — <reason>
      kept        <path> — <reason>
    warning: <text>
    error: <path> — <reason> — not written
    summary: N written, M kept[, K blocked]

`written` lines first, then `kept`, then warnings, then errors. A blocked
path makes the run a failure: say so, do not continue to the coder dispatch.

## The cfm-owned region: marker convention

Every CLAUDE.md guide the scaffold renders wraps its content in

    <!-- cfm:begin -->
    …
    <!-- cfm:end -->

exactly once, markers on their own lines. The region is cfm's: the upgrade
and the doctor re-render or compare it as a unit and never touch a byte
outside it. Content the user or the conventions round adds goes OUTSIDE the
markers (after `<!-- cfm:end -->`). `references/doctor.md` looks for this
pair; a guide with zero or two `cfm:begin` markers, or `cfm:end` before
`cfm:begin`, is a doctor finding. Keep the provenance stamp verbatim: the
doctor and the conventions round grep for it.

## Template — root `CLAUDE.md`

```markdown
<!-- cfm:begin -->
# CLAUDE.md

<!-- rendered from .cfm-workflow.yml by cfm scaffold — change the config, not just this file -->

## Project

{{project_context}}

{{if claude_md.layout == router}}
## Routing

| Working in | Read first |
|---|---|
{{for each layer}}
| `{{layer.path}}` | `{{layer.path}}/CLAUDE.md` |
{{end}}

{{end}}
## Layers (build order)

{{for each layer}}
{{layer.index}}. **{{layer.name}}** — `{{layer.path}}`
{{end}}

## Command matrix

Single-owner matrix: each slot is run only by its owner agent.

| Slot | Command | Owner |
|---|---|---|
{{for each slot in commands}}
| {{slot.name}} | `{{slot.commands joined by " ; "}}` | {{if slot.name == verify_full}}**HUMAN-ONLY** — agents are banned from running it{{else}}{{enabled agents whose owns_commands lists it, comma-joined, or "(unassigned)"}}{{end}} |
{{end}}

## Human gates

{{for each gate in human_gates}}
- {{gate}}
{{end}}

## Workflow files

- Rules: `{{rules_file}}`
- Glossary: `{{context_file}}` — the project's shared language; name things the way it names them
- Progress log: `{{progress_log}}` (newest entries first)
- Workflow state: managed by `/cfm:implement-phase` (`{{state_file}}`)

{{if mode == off}}
## cfm mode: OFF

This repository is initialized with cfm (`.cfm-workflow.yml`), with `mode: "off"`: the `/cfm:*` skills are available, no orchestrator doctrine applies, and the main session may edit product code. Restore it with `/cfm:mode enforced|advisory` — a config diff the human approves.
{{else}}
## cfm mode: {{mode, upper-case}}

This repository is initialized with cfm (`.cfm-workflow.yml`). Every session here runs in cfm mode, on top of whichever Claude Code permission mode is active (plan, auto-accept, manual).

You are the ORCHESTRATOR. You plan, dispatch the cfm agents, verify their results, and keep the ledgers. You never write product code, tests, or scaffold yourself — no "small change" exception. Every line of product code comes from a dispatched agent. An agent the config marks `enabled: false` does not exist: never dispatch it, list it, or substitute another agent for its step.

"Product code" is everything in the project that is not a workflow file. The workflow files — `.cfm-workflow.yml`, `.cfm-workflow.local.yml`, `.claude/`, `.cfm/`, `docs/`, every CLAUDE.md guide, `{{rules_file}}`, `{{context_file}}`, `{{progress_log}}`, `{{state_file}}`, `.gitignore`, `.env.example` — stay writable from this session.

{{if mode == enforced}}
Mode ENFORCED: an Edit, Write, or shell write to product code from this session is forbidden. Treat the urge to make one as the signal to dispatch the coder. This edition ships no hook, so nothing refuses the write at runtime: the rule holds because you follow it, and a product edit from this session is a workflow violation to confess in the progress log, not to work around.
{{else}}
Mode ADVISORY: a product write from this session is allowed, and the rule still stands — prefer the dispatch, and say so when you deviate. This edition ships no hook, so no runtime guard exists in either mode.
{{end}}

### Start of session

Before acting on the first request of a session — and again after `/clear` or a context compaction — read `{{state_file}}` if it exists and report one or two lines before anything else:

- `phase.status` is `in-flight`: "Phase '<id>' (<description or 'no description'>) is IN-FLIGHT, at layer '<cursor.current_layer>' — `/cfm:implement-phase` with no argument resumes it from the ledger."
- `phase.status` is `complete`: "Last phase '<id>' is complete; the next one starts only when the human names it."
- otherwise: "No phase in flight — `/cfm:plan` a feature, or `/cfm:implement-phase <description>` to start one."
- `pending_gates` non-empty: add "Pending human gates: <comma-joined>."
- `open_questions` non-empty: add "<N> open question(s) are waiting on the human."
- the file is missing or not valid JSON: "The state file is unreadable — run /cfm:doctor before any phase work."

If `.cfm-workflow.yml` fails validation, say so and run `/cfm:doctor` before any phase work.

### Routing

Route every request through the cfm skill that owns it:

- a feature or change to build → `/cfm:plan`
- implement, continue or resume a phase → `/cfm:implement-phase`
- something broken, failing, throwing or slow → `/cfm:diagnose`
- review changes → `/cfm:code-review`
- a workflow setting or a coding rule → `/cfm:configure`
- this mode itself → `/cfm:mode`
- where things stand, what to do next → `/cfm:status`
- capture work without planning it yet → `/cfm:create-task`
- an idea to think through → `/cfm:brainstorm`
- the setup looks wrong → `/cfm:doctor`

Questions, explanations, and reading code need no skill — answer them directly. A request that needs a file changed is a dispatch, never an edit.

### Human-only gates

In every profile: the full test suite (verify_full); git per the configured level; starting the next phase (git level {{git.level}}).

### Before every request

cfm mode ({{mode}}): route this through the matching /cfm:* skill — build → /cfm:plan then /cfm:implement-phase, broken → /cfm:diagnose, review → /cfm:code-review, settings → /cfm:configure, status → /cfm:status. Answer questions directly; a file change is a dispatch, never an edit ({{if mode == enforced}}enforced: product edits from this session are forbidden{{else}}advisory: the rule stands, nothing refuses the write{{end}}). A prompt that is already a `/cfm:*` command names its own skill.

Change the mode with `/cfm:mode enforced|advisory|off` — a config diff the human approves.
{{end}}
<!-- cfm:end -->
```

Rendering notes:

- Under `layout: single` the Routing section is omitted; the Layers,
  Command matrix, Human gates, and Workflow files sections render in every
  layout.
- The command matrix lists the slots in config order; `verify_full` is
  HUMAN-ONLY regardless of who claims to own it.
- The doctrine block (everything from `## cfm mode:` to the end) is what
  the hooks used to inject: it renders in every layout and re-renders on
  every `/cfm:mode` change via the replace rule above.

## Template — layer guide (`<layer.path>/CLAUDE.md`)

Rendered per layer under `layout: router`, and for any `claude_md.files`
entry that equals a layer's `<path>/CLAUDE.md` under `single`.
`{{root_rel}}` is the relative path from the layer directory to the root
`CLAUDE.md` (for example `../../CLAUDE.md`).

```markdown
<!-- cfm:begin -->
# {{layer.name}} — layer guide

<!-- rendered from .cfm-workflow.yml by cfm scaffold — change the config, not just this file -->

- Layer: **{{layer.name}}**
- Path: `{{layer.path}}`
{{if feature_roots[layer.name] is a string}}
- Feature root: `{{feature_roots[layer.name]}}`
{{end}}

Project context, the command matrix, human gates, and the cfm orchestrator doctrine live in the root guide: `{{root_rel}}`. Read it first.
<!-- cfm:end -->
```

## Template — stub (a `claude_md.files` entry with no layer)

```markdown
<!-- cfm:begin -->
# {{entry path}}

<!-- rendered from .cfm-workflow.yml by cfm scaffold — change the config, not just this file -->

Listed in claude_md.files, but no configured layer lives at this path — fix the config via /cfm:configure.

Root workflow guide: `{{root_rel}}`.
<!-- cfm:end -->
```

## Template — rules seed (`{{rules_file}}`)

Pick each rule's owner from the ENABLED agents: R1 prefers `security-check`
then `code-reviewer`; R2 prefers `code-reviewer` then `security-check`.
When neither preferred agent is enabled, take the first enabled
`tier: judgment` agent, else the first enabled agent. For R2, when no agent
is enabled at all but a `lint_arch` command slot exists, write
`lint(lint_arch)`. With no enabled agent and no `lint_arch`, no rule can be
seeded with teeth: stop and send the user to `/cfm:configure agents` before
scaffolding — never write a rule whose enforcement names nothing live,
because the doctor rejects it.

```markdown
# Project Rules

Every rule declares its enforcement mechanism — the doctor rejects
toothless rules (hard invariant 3).

## R1. Environment access via the typed config module

Product code reads environment values only through the project's typed
config module — never scattered raw env access, never literals.

**Enforcement:** reviewer({{r1_owner}})

## R2. Feature code lives in feature roots

New feature files go under the configured `feature_roots` path for their
layer, nowhere else.

**Enforcement:** {{reviewer(r2_owner) or lint(lint_arch)}}
```

The conventions round appends further rules to this file afterwards
(`skills/init/references/conventions-round.md`); the seed is never
rewritten.

## Template — glossary seed (`{{context_file}}`)

```markdown
# Project context

The shared language of this project. Agents read it before they name
anything, so terms here decide what variables, functions, files, and review
findings are called.

Entries are earned: add a term when it is resolved, not in advance. Keep
implementation detail, specs, and scratch notes out — this is a glossary.
Terms crystallize during `/cfm:brainstorm`, `/cfm:plan`, and any session
that resolves what something is actually called.

## Language

<!-- One entry per term:

**Term**:
What it means, in one or two sentences, in terms a domain expert would use.
_Avoid_: the near-synonyms this term replaces, so they stop reappearing.

-->

## Relationships

<!-- How the terms above relate, e.g. "An Order holds many Line Items". -->

## Flagged ambiguities

<!-- A word used for two different things, and how it was resolved. -->
```

## Template — `.env.example`

Variable names only, values blank, always.

```
# .env.example — variable names only, values stay empty.
# Add a `NAME=` line in the same change that introduces the variable.
```

Later additions are one `NAME=` line each, appended by whoever introduces
the variable (the coder brief demands it).

## `.gitignore` — append-only

Required lines, in this order:

1. `.env*`
2. `!.env.example`
3. every entry of the merged `secret_globs` not already in 1–2
4. `.cfm-workflow.local.yml` — personal overrides never reach the team
5. `.cfm/` — cfm's own local directory
6. `{{state_file}}` ONLY when it does not live under `.cfm/` — ignore the
   one file by name, never a whole shared directory for one file

Read the existing `.gitignore` (none counts as empty). A required line is
present when some existing line, stripped of surrounding whitespace, equals
it. Append only the missing lines, under this header, after a newline if
the file does not end with one:

```
# cfm — secret globs + local workflow state (append-only)
<missing line>
…
```

Later rules win in `.gitignore`, so `!.env.example` must land LAST: when it
is among the missing lines, move it to the end of the appended block; when
it already exists and anything else is appended, append it again at the end.
Never remove, reorder, or rewrite an existing line. Never append through a
symlink: a symlinked `.gitignore` is blocked. Nothing missing → `kept
.gitignore — all required lines already present`.

## Template — progress log (`{{progress_log}}`)

```markdown
# Progress

<!-- newest entries first — prepend new entries, never append -->

## {{today}} — scaffold rendered [complete]

- Workflow scaffold rendered from .cfm-workflow.yml by cfm scaffold.

### Carried forward
- (none)
```

## Template — initial state (`{{state_file}}`)

Schema v1, no phase in flight, so the doctor's state check stays green. The
full schema and every later transition are in `references/state.md`; the
scaffold writes only this seed and never edits the file afterwards.

```json
{
  "version": 1,
  "phase": {
    "id": null,
    "status": null
  },
  "deferred_questions": [],
  "carried_forward": []
}
```

Two-space indentation, trailing newline.

## Mode semantics (doctrine, not mechanism)

`mode` is a team setting in `.cfm-workflow.yml`, never in the local
override file. It selects which doctrine block the root CLAUDE.md carries:

| mode | doctrine in CLAUDE.md | main-session product writes |
|---|---|---|
| `enforced` (default) | full block, writes forbidden by instruction | forbidden — dispatch the coder |
| `advisory` | full block, rule stated as preference | allowed, rule still stands |
| `off` | one-line notice only | allowed |

Honesty line, carried into the rendered text: this edition ships no
PreToolUse guard and no session hooks, so nothing refuses a write at
runtime in any mode — `enforced` is a standing instruction the orchestrator
obeys, not a mechanism. The reviewers still read the ledgers, so a product
edit made from the main session shows up as a diff with no dispatch record
behind it.

A mode change (`/cfm:mode`) re-renders the cfm region of the root
CLAUDE.md with the replace rule above, so the doctrine the next session
reads matches the config. Until the file is re-rendered, the config and
the doctrine disagree, and the doctor reports it.

## Hard limits

- Render from a valid config only; never invent a value the config lacks
  beyond the defaults table.
- Never overwrite: the only overwrite is the CLAUDE.md region replace,
  after the user approved its diff.
- Never write outside the markers of an existing guide, and never write
  product code: the stack skeleton is the coder's.
- Never touch git, never run `verify_full`, never read files matched by
  `secret_globs`.
- Keep the provenance stamp and the marker pair verbatim; other documents
  grep for them.
