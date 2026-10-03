---
name: add-agent
description: Adds a custom agent to the cfm roster through a guided flow — name, purpose, model, autonomy, then smart defaults for tier, tools, and layers — ending in a YAML diff applied only on explicit approval. Use when the user wants their own agent or a specialist reviewer added to the workflow.
compatibility: Requires Claude Code (terminal, IDE extension, or Desktop Code tab)
---

# cfm:add-agent

Add ONE custom agent to `.cfm-workflow.yml`: four core questions, smart
defaults for the rest, then the standard diff → approval → doctor
discipline. This skill owns the custom-agent flow — `cfm:init` and
`cfm:configure` route here instead of duplicating it.

## Step 0 — environment gate

Run: `bash "${CLAUDE_PLUGIN_ROOT}/scripts/require-claude-code.sh"`
If it exits non-zero, STOP and show its stderr verbatim.

## Step 1 — load config

Run: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/cfm_config.py" --project-dir "$(pwd)" --json`

- No config → tell the user to run `/cfm:init` first and STOP.
- Validation errors → show them, send the user to `/cfm:doctor`, and STOP
  (never add an agent to a broken config).

## Step 2 — the four core questions

Ask one at a time, each via the AskUserQuestion tool:

1. **name** — kebab-case identifier. Reject anything that collides with an
   existing agent in config (roster or custom) and re-ask.
2. **purpose** — one line. This exact sentence is shown in dispatch briefs,
   so it must say what the agent does, not what it is.
3. **model** — present a live-fetched model list (check what models
   currently exist — never offer a hardcoded list) with a free-text escape
   hatch via the Other option.
4. **autonomy** — one AskUserQuestion, options with what the user will
   experience:
   - **auto** — dispatches freely, you see results at gates.
   - **confirm** — shows a dispatch brief and waits, every time.
   - **confirm-plan** — you approve its part of the phase plan once, then
     it runs.

## Step 3 — smart defaults

Infer the remaining fields from the purpose, then ONE AskUserQuestion:
"use these defaults or customize?" — stating each inference:

- **tier** — purpose reads like review/audit/check → `judgment`;
  build/implement/fix/write → `implementation`; run/format/mechanical →
  `mechanical`. State which words drove the inference; the user can
  override.
- **tools** — least privilege: default `[Read, Grep, Glob]`. Add Write,
  Edit, or Bash ONLY where the purpose individually justifies it (an agent
  that "fixes" needs Edit; one that "runs tests" needs Bash) — name the
  justification for every addition.
- **layers** — default: all project layers. When customizing, offer the
  choices from the config's existing layer names and validate against
  them — never free text (the validator rejects unknown layers).
- **owns_commands** — default `[]`.

If the user customizes, ask only about the fields they want changed.

## Step 4 — reviewers and command ownership (conditional)

- **If the agent reviews** (judgment tier, purpose is review-shaped): ask
  where it sits in `review_gates` — which step, and whether it runs in
  parallel with an existing gate (a nested list is one parallel step).
- **If the user wants it to own a command slot another agent owns**:
  surface the single-owner conflict with exactly three exits:
  **report-only** (recommended — the agent reads results, owns nothing),
  **transfer ownership**, or **shared ownership** (allowed, but the doctor
  will nag about it forever; the diff must ALSO append the slot to the
  top-level `shared_commands_ack` list — that acknowledgment is what
  downgrades doctor check 4 from a failure to the standing nag).
- **REFUSE `verify_full` ownership outright** — the full suite is the
  human's command; doctor check 4 rejects any agent owning it. No
  exception.

## Step 5 — diff, apply, doctor

1. Show the exact change as a unified YAML diff: the new `agents.<name>`
   entry plus any `review_gates` or ownership edits (including the
   `shared_commands_ack` append when shared ownership was chosen), with 2
   lines of context. The written entry ALWAYS carries `enabled: true`
   alongside the collected fields — the schema requires it.
2. Apply ONLY on explicit approval. Edit `.cfm-workflow.yml` surgically —
   never rewrite untouched sections, never reformat, keep the user's
   comments.
3. Validate: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/cfm_config.py" --project-dir "$(pwd)"`
   — if it errors on what you wrote, fix your edit (not the user's other
   config) until clean.
4. **Render the agent file** — the thing that actually enforces the tool
   limits:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/agent_file.py" --project-dir "$(pwd)" --agent <name> --write
   ```

   It writes `.claude/agents/<name>.md` with frontmatter (name,
   description, tools, model alias) rendered from the config entry and a
   default discipline body. Show the file. The body is the user's to edit
   afterwards; a later `--write` refreshes only the frontmatter.
5. Auto-run the doctor: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/doctor.py" --project-dir "$(pwd)"`
   and show the report. Check 4 fails a custom agent whose file is missing
   or whose frontmatter drifted from config. A change that turns the doctor
   red gets flagged immediately with the offer to revert the diff.

## Dispatch

Orchestrating skills dispatch a custom agent by its project agent file
(`subagent_type: <name>`), so Claude Code enforces the tool set from the
frontmatter. The brief carries the purpose verbatim and the model alias
from config. A custom agent is never dispatched as a general subagent —
that would hand it every tool.

## Hard limits

- Never touch git.
- One agent per run; a second request becomes a second run.
- Never write without showing the diff and getting explicit approval.
