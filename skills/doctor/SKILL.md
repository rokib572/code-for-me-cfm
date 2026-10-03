---
name: doctor
description: Validates that cfm config and reality still agree — environment, schema and invariants, paths, commands, agent roster, models, rule teeth, secrets hygiene, pipeline wiring, and state (checks 0-9). Use when the user wants the setup checked, after any change to .cfm-workflow.yml, or when behavior seems to contradict the configuration.
compatibility: Requires Claude Code (terminal, IDE extension, or Desktop Code tab)
---

# cfm:doctor

Validate that the cfm configuration and the repository still agree. Config
values are promises; the doctor converts them to facts.

## Step 0 — environment gate

Run: `bash "${CLAUDE_PLUGIN_ROOT}/scripts/require-claude-code.sh"`

If it exits non-zero, STOP immediately and show its stderr message verbatim.
Do not attempt any other step.

## Step 1 — run the doctor engine

Run: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/doctor.py" --project-dir "$(pwd)" --json`

- If `python3` is missing, tell the user cfm's doctor needs Python 3 and stop.
- If the output mentions PyYAML, tell the user to run `pip install pyyaml` and stop.
- Never reimplement the checks yourself; the engine is the single source of truth.

## Step 2 — render the report

Present a compact table: one row per check with its PASS / WARN / FAIL / SKIP
status:

| # | check |
|---|---|
| 0 | environment |
| 1 | schema & invariants |
| 2 | paths |
| 3 | commands |
| 4 | roster coherence (incl. agent files vs config tools) |
| 5 | models |
| 6 | rules have teeth |
| 7 | secrets hygiene (incl. settings denies present and none stale; sandbox status) |
| 8 | pipeline wiring (incl. guard self-test and whether a real subagent event has been observed) |
| 9 | state |

For check #5 the engine only validates the id shape mechanically; you do the
live part: verify each configured `agents.*.model` id against the models you
know currently exist, flag any id that no longer resolves, and suggest
`/cfm:configure agents` to update it.

Then, for every failure, explain in one or two sentences:
- what is broken, quoting the exact failure message,
- the most likely fix (edit `.cfm-workflow.yml`, create the missing file,
  fix the failing command, add an `**Enforcement:**` line to a rule).

## Step 3 — verdict and follow-up

- End with one line: **healthy** or **unhealthy (N failures)**.
- NEVER edit `.cfm-workflow.yml` or any project file to "fix" a finding
  yourself. Propose the fix and let the user apply it (or approve it
  explicitly), then re-run the doctor to confirm.
- Hard invariants (Claude Code only, secret globs never shrinkable, rules
  need teeth, no direct push to main) are not fixable by relaxing config —
  if the user asks to disable one, decline and explain it is non-configurable.
