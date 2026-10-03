---
name: mode
description: Shows or changes cfm mode — enforced (the guard refuses main-session writes to product code and the session hooks inject the orchestrator doctrine), advisory (doctrine injected, guard silent), or off — as a one-line config diff applied only on explicit approval, followed by an automatic doctor run. Use when the user asks what mode the session is in, wants to relax or restore cfm's orchestrator-only rule, or asks why an edit was refused as "product code".
compatibility: Requires Claude Code (terminal, IDE extension, or Desktop Code tab)
---

# cfm:mode

cfm mode is the layer cfm adds on top of whichever Claude Code permission
mode is active. Whenever a repository carries `.cfm-workflow.yml`, every
session in it enters cfm mode: the main session orchestrates, work goes
through the `/cfm:*` skills, and product code is written only by
dispatched agents. This skill reads or changes the `mode` value and
nothing else.

| mode | session context (start / resume / compact / each prompt) | guard: main-session product writes | every other guard rule |
|---|---|---|---|
| `enforced` (default) | injected | refused | unchanged |
| `advisory` | injected | allowed | unchanged |
| `off` | none | allowed | unchanged |

"Product" is everything inside the project that is not a workflow file:
the config pair, `.claude/`, `.cfm/`, `.git/`, `docs/`, `CLAUDE.md` and
the `claude_md.files` entries, and the configured `rules_file`,
`context_file`, `progress_log` and `state_file` (plus `.gitignore` and
`.env.example`) stay writable from the main session in every mode.

## Step 0 — environment gate

Run: `bash "${CLAUDE_PLUGIN_ROOT}/scripts/require-claude-code.sh"`

If it exits non-zero, STOP and show its stderr message verbatim.

## Step 1 — load

Read `.cfm-workflow.yml` at the project root. If it does not exist, report
"No cfm configuration here — cfm mode applies only to initialized
projects; run `/cfm:init`." and stop. Run
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/cfm_config.py" --project-dir "$(pwd)" --json`
and read `mode` from the merged config (absent in the file means the
default, `enforced`).

## Step 2 — show

With no argument, or an argument that is not one of `enforced`,
`advisory`, `off`: print the current mode, one line on what it means (the
table row above), and the fact that it is a team setting — it lives in
`.cfm-workflow.yml`, never in `.cfm-workflow.local.yml`, because "the
orchestrator never writes code" is a promise the whole repository makes,
not one developer's comfort setting. Then stop.

If the user asked because a tool call was just refused with "is product
code; in cfm mode the main session orchestrates", say what the refusal
means before offering anything: the change belongs to a dispatched coder
(`/cfm:implement-phase` for phase work; a bug starts at `/cfm:diagnose`,
which hands its findings to `/cfm:plan`), and
lowering the mode is the exception, not the fix.

## Step 3 — change

With `enforced`, `advisory` or `off` as the argument (a value equal to
the current mode is a no-op — say so and stop):

1. Show the diff — the single `mode:` line of `.cfm-workflow.yml`, added
   when absent, changed in place when present, with two lines of context —
   and one sentence per consequence, from the table: what the guard will
   do with the main session's product writes, and whether the session
   context still arrives. Lowering to `off` also says that the next
   session in this repository will receive no cfm context at all.
2. Apply ONLY on explicit approval. Edit the file surgically; write the
   value quoted (`mode: "off"`) so YAML never reads it as a boolean.
3. Validate: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/cfm_config.py" --project-dir "$(pwd)"`.
4. Auto-run the doctor: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/doctor.py" --project-dir "$(pwd)"`
   and show the report; check 8 re-runs the guard self-test with the new
   mode's expected verdicts and re-probes the session-context hook.
5. Say that the change takes effect on the next tool call for the guard
   and on the next session start (or `/clear`) for the session context,
   and that `git diff .cfm-workflow.yml` shows it to the team.

## Hard limits

- This skill edits the `mode` line of `.cfm-workflow.yml` and nothing
  else — no other key, no other file, never the local override file.
- Never apply without showing the diff and getting approval.
- Never touch git.
- Never lower the mode on your own initiative: a refused write is a
  dispatch waiting to happen, and only the human decides otherwise.
