---
name: create-task
description: Captures a description or the current discussion as a tracked task file — docs/tasks/<slug>.md with title, acceptance criteria, affected layers, and size, mirrored to a connected tracker through a redaction pass. Use when the user wants work written down and tracked without planning it yet.
compatibility: Requires Claude Code (terminal, IDE extension, or Desktop Code tab)
---

# cfm:create-task

Capture one piece of work as a canonical markdown task file. Works fully
offline; a connected tracker only mirrors the file.

## Step 0 — environment gate

Run: `bash "${CLAUDE_PLUGIN_ROOT}/scripts/require-claude-code.sh"`
If it exits non-zero, STOP and show its stderr verbatim.

## Step 1 — load config

Run: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/cfm_config.py" --project-dir "$(pwd)" --json`

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

This file is canonical — whatever any tracker says later, this is the
task.

## Step 4 — tracker mirror (optional, never blocking)

- **Connected** (config `tracker.provider` set, `tracker.sync.create_tasks`
  true): mirror the task — title, description, acceptance criteria, a
  pointer to the task file. Follow the adapter contract in
  `${CLAUDE_PLUGIN_ROOT}/CONNECTORS.md`, and pipe
  every outbound payload through
  `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/redact.py"` (the single
  redaction source — never reimplement or inline its patterns), sending
  only the pipe's OUTPUT.

  Then write the returned key back into the task file as its binding line
  — `- **tracker**: <provider>:<key> — <url>`, the format in Part 2 —
  so `/cfm:implement-phase` and any later sync resolve the same task
  instead of creating a second one. A mirror whose key was not written
  back is a duplicate waiting to happen.

  When unsure whether a string is a credential, drop it and note
  `[redacted]`. Record the attempt either way:
  `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state.py" --project-dir "$(pwd)" tracker --last-sync "ok" --bind "docs/tasks/<slug>.md=<provider>:<key>"`
  (or `--last-sync "failed: <reason>"`). Sync failure of any kind →
  one-line warning and done; the file remains canonical.
- **Not connected**: never ask about connecting one here — that is
  `/cfm:connect-tracker`'s job (greenfield projects get asked once by
  `/cfm:plan` after the first plan). Just note the task is local-only,
  e.g. "local-only — run /cfm:connect-tracker to mirror tasks".

## Hard limits

- No product code, no scaffold, no plan phases — capture only.
- Never mutate git; never run `verify_full`.
- The only writes: the task file (including its tracker binding line) and,
  after a sync attempt, the tracker bookkeeping through
  `scripts/state.py`. Nothing else.
