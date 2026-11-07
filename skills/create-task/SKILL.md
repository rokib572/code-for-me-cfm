---
name: create-task
description: Captures a description or the current discussion as a tracked task file — docs/tasks/<slug>.md with title, acceptance criteria, affected layers, and size. Use when the user wants work written down and tracked without planning it yet.
compatibility: Requires Claude Code (terminal, IDE extension, or Desktop Code tab)
---

# cfm:create-task

Capture one piece of work as a canonical markdown task file. Works fully
offline.

## Step 0 — environment gate

Run `test "$CLAUDECODE" = "1"` with the Bash tool. If it fails, STOP and
show exactly: "cfm runs only in Claude Code (terminal, IDE, or the
Desktop Code tab). Your project config and brief are untouched — open
this repo in Claude Code to continue."

## Step 1 — load config

Load the effective config per
`${CLAUDE_PLUGIN_ROOT}/references/config.md` ("Load and validate the
config").

- No config → send the user to `/cfm:init` and STOP.
- Validation errors → send them to `/cfm:doctor` and STOP.

## Step 2 — build the task

Source: the argument (`/cfm:create-task "<desc>"`), or — when invoked from
a discussion ("create a task from this") — synthesize it from the
conversation. Produce:

- **title**: one line;
- **description**: one paragraph — what and why, not how;
- **acceptance criteria**: testable statements;
- **affected layers**: from the config's `layers` — only ones the task
  plausibly touches;
- **suggested size**: one phase, or multi-phase. If multi-phase, recommend
  `/cfm:plan` instead — a task file is for work one phase can carry; still
  create the task if the user wants it captured now.

Anything the source doesn't answer stays an open question in the task —
do not invent criteria the user never stated.

## Step 3 — write the task file

Draft `docs/tasks/<slug>.md` (kebab-case slug from the title) containing
the fields above plus date and `status: open`. Show the full draft,
iterate, write only on the user's approval. Never overwrite an existing
task file without showing a diff and getting explicit approval.

## Hard limits

- No product code, no scaffold, no plan phases — capture only.
- Never mutate git; never run `verify_full`.
- The only write: the task file. Nothing else.
