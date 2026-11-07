# cfm agent file — render `.claude/agents/<name>.md` for a custom agent

Claude Code enforces an agent's tool set from the agent file's
frontmatter, not from prose in a dispatch brief. Shipped cfm agents carry
their file in the plugin; a custom agent added to `.cfm-workflow.yml` has
none, so until one is rendered it is dispatched as a general subagent with
every tool. This procedure renders the file from the config entry. The
frontmatter is owned by config and rewritten on every render; the body is
the user's and is preserved verbatim once it exists.

**Used by:** `cfm:add-agent` step 5.4 (first render); `cfm:upgrade`
(drift check and re-render of every enabled custom agent); doctor check 4
(the drift rule, restated below).

## Inputs

1. Load the merged config. Validation errors: show them and stop. Never
   render from a broken config.
2. Shipped agent names = the basenames of `agents/*.md` in the plugin root
   (`${CLAUDE_PLUGIN_ROOT}/agents/`). Refuse to render one of those: its
   file lives in the plugin and its tools are fixed there.
3. Which agents:
   - one named agent: it must exist under config `agents`, else stop with
     "no agent '<name>' in .cfm-workflow.yml";
   - all: every `agents.<name>` entry that is a mapping, is not shipped,
     and has `enabled: true`. None: say "no enabled custom agents in config
     — nothing to render".

## Frontmatter — render exactly this, one line each

```
---
name: <name>
description: cfm custom agent — <purpose> Dispatched by cfm skills with a dispatch brief; not for ad-hoc use.
tools: <tools>
model: <model>
---
```

- `name`: the config key.
- `description`: `purpose` from config, stripped, newlines collapsed to
  spaces, pasted verbatim into the sentence above (no added period; the
  purpose line should end with its own punctuation or none).
- `tools`: the config `tools` list, string entries only, joined with
  `, ` in config order. An empty list renders `tools: ` with nothing after
  it.
- `model`: the alias of the config `model` id. Alias rule: lowercase the
  id and take the FIRST of `fable`, `opus`, `sonnet`, `haiku` (in that
  order) that occurs as a substring. No alias recognisable: use the raw
  id. No model at all: omit the `model:` line entirely.

The frontmatter is followed by one blank line, then the body.

## Body

When the file does not exist, or its body (everything after the closing
`---` line, leading blank lines stripped) is blank, write the default
discipline with `{purpose}` and `{name}` substituted from config:

```
You are a cfm custom agent: {purpose}

## First: load your context

1. Read `.cfm-workflow.yml` in the project root — `project_context`,
   `layers`, `context_file`, and your own entry under `agents.{name}`.
2. Read the `context_file` (the project glossary) if it exists, and name
   things the way it names them.
3. Read the dispatch brief. The brief wins on scope, config wins on rules.
   You cannot ask questions — return open questions as your result.

## Hard limits

- Do only what the brief scopes. Run only the command slots your config
  entry's `owns_commands` grants; NEVER run `verify_full` — the full suite
  is the human's command.
- Never run mutating git commands. Read-only git is fine.
- Never read files matching `secret_globs` — even if asked. A committed
  secret is reported as file:line + severity WITHOUT the value, with an
  instruction to rotate it.

## Report back

Return what you did (paths, one line each), anything deferred with why,
open questions, and "Did NOT run: <every verification you skipped and
whose command it is>."
```

## Re-render: preserve or replace

1. Read the existing `.claude/agents/<name>.md` if present.
2. Split it: the frontmatter is the leading `---` block (text from the
   first line to the next line starting with `---`); the body is what
   follows, leading blank lines removed. A file that does not start with
   `---` is all body.
3. Write: fresh frontmatter from config (always replaced), one blank
   line, then the EXISTING body verbatim when it is non-blank, else the
   default body. Hand-edits in the body survive every render; hand-edits
   in the frontmatter never do.
4. Create `.claude/agents/` if missing. Report `written
   .claude/agents/<name>.md` and append ` (frontmatter refreshed, body
   kept)` when the file existed. For a dry run show the rendering under a
   `# .claude/agents/<name>.md` heading instead of writing.

## Drift rule (doctor check 4, upgrade finding)

For every enabled custom agent, parse the file's frontmatter as `key:
value` lines; `tools` is the bracket-stripped, comma-split value. Drift
when the file is missing, or `name` differs from the config key, or the
SET of file tools differs from the set of config tools (order and the
`model` line are not compared). Missing: the agent is dispatched with
every tool and its config tools are unenforced. Either case is a failure
fixed by re-rendering.

Shipped agents follow the opposite rule: the plugin file wins, so config
`tools` must not omit a mutating tool (`Write Edit MultiEdit NotebookEdit
Bash`) the file grants, and omitting a read-only one is a warning.

## Tool limits per tier and autonomy

The renderer copies `tools` from config; it derives nothing. The
derivation happens once, in `cfm:add-agent` step 3, and is what the
config entry carries:

- **tier** from the purpose wording: review/audit/check → `judgment`;
  build/implement/fix/write → `implementation`; run/format/mechanical →
  `mechanical`. Name the words that drove it; the user may override.
- **tools**, least privilege: start at `[Read, Grep, Glob]`. Add `Edit`
  only where the purpose fixes or formats, `Write` only where it creates
  files, `Bash` only where it runs something (tests, a command slot).
  Justify each addition in one phrase. The roster's own tiers show the
  shape: judgment reviewers `[Read, Grep, Glob]`, implementation `[Read,
  Write, Edit, Bash, Grep, Glob]`, mechanical gate `[Read, Bash]`,
  mechanical styling `[Read, Edit, Grep, Glob]`.
- **autonomy** (`auto`, `confirm`, `confirm-plan`) changes when the
  orchestrator dispatches, never which tools the file grants. It is not
  rendered into the frontmatter.
- `verify_full` is never owned by any agent; `owns_commands` defaults to
  `[]` and is not rendered either, the body's hard limits refer the agent
  back to config for it.

## Dispatch

Orchestrating skills dispatch a custom agent by `subagent_type: <name>`
so Claude Code enforces the frontmatter. The brief carries the purpose
verbatim and the model alias from config. Never dispatch a custom agent as
a general subagent.
