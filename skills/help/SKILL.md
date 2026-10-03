---
name: help
description: Explains where to start with cfm in a few lines and lists every cfm command with a one-line explanation in a table. A pure read that changes nothing. Use when the user asks for help with cfm, what commands exist, how to get started, or which command fits what they want to do.
compatibility: Requires Claude Code (terminal, IDE extension, or Desktop Code tab)
---

# cfm:help

A PURE READ: never modify config, state, or any project file while
executing this skill, and never start another command on the user's
behalf. Render the sections below and stop.

## Step 0 — environment gate

Run: `bash "${CLAUDE_PLUGIN_ROOT}/scripts/require-claude-code.sh"`

If it exits non-zero, STOP and show its stderr message verbatim.

## Step 1 — where to start

Check whether `.cfm-workflow.yml` exists at the project root, then render
**Where to start** as at most five short lines:

- No config yet: "This project is not set up for cfm. Start with
  `/cfm:init`. It detects whether the repo is new or existing, asks a few
  questions, and writes the config. Have only an idea so far? Run
  `/cfm:brainstorm` first; it needs no config."
- Config present: "cfm is set up here. Run `/cfm:status` to see what is in
  flight and what to do next."

Then one line with the usual flow, verbatim:

`/cfm:init` → `/cfm:brainstorm` → `/cfm:plan` → `/cfm:implement-phase` (one phase at a time; you run the full suite, review, and do git at each gate) → next phase

And one line for the side paths: something broken or slow → `/cfm:diagnose`;
review any change → `/cfm:code-review`; settings → `/cfm:configure`.

## Step 2 — the command table

Render this table verbatim under the heading **Commands**:

| Command | What it does |
|---|---|
| `/cfm:help` | This overview: where to start and every command |
| `/cfm:init` | Sets up cfm in any project: detects the scenario, interviews you, writes `.cfm-workflow.yml`, scaffolds, runs the doctor |
| `/cfm:brainstorm [scope]` | Turns a raw idea into a written brief (`docs/brief.md` or a feature brief). Needs no config |
| `/cfm:plan` | Breaks a feature into independently shippable phases in `docs/plans/<feature>.md` |
| `/cfm:implement-phase [id]` | Builds one phase through the agent pipeline and review gates, then stops at your gate. No argument resumes the phase in flight |
| `/cfm:code-review [target\|prompt]` | Runs the review pipeline over a diff, path, staged or uncommitted work, or a plain-English scope |
| `/cfm:diagnose [symptom]` | Finds the root cause of a bug or slowdown through a gated loop, then offers to plan the fix. Never applies one |
| `/cfm:create-task "<desc>"` | Captures work as `docs/tasks/<slug>.md`, mirrored to the tracker if one is connected |
| `/cfm:status` | Shows where the workflow stands: mode, phase, pending gates, carried-forward debts. Changes nothing |
| `/cfm:configure [domain]` | Views or changes any config value or coding convention, as a diff you approve, then runs the doctor |
| `/cfm:mode [enforced\|advisory\|off]` | Shows or changes cfm mode, the orchestrator-only rule for the main session |
| `/cfm:add-agent` | Adds a custom agent or specialist reviewer to the roster |
| `/cfm:connect-tracker` | Connects Jira, ClickUp, Trello, or a custom MCP server so plans and tasks are mirrored there |
| `/cfm:doctor` | Checks that config, repo, agents, models, and environment still agree (checks 0–9) |

Close with one line: "`testing`, `simplicity`, and `domain-modeling` are
reference skills that cfm reads on its own; they are not commands."
