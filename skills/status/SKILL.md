---
name: status
description: Shows where the cfm workflow stands — active phase, pipeline cursor, pending human gates, carried-forward debts, deferred config questions, and tracker sync state. A pure read that changes nothing. Use when the user asks what is in flight or what to do next, or picks work back up in a fresh session.
compatibility: Requires Claude Code (terminal, IDE extension, or Desktop Code tab)
---

# cfm:status

Render the workflow state. This is a PURE READ — never modify state, config,
or any project file while executing this skill.

## Step 0 — environment gate

Run: `bash "${CLAUDE_PLUGIN_ROOT}/scripts/require-claude-code.sh"`

If it exits non-zero, STOP and show its stderr message verbatim.

## Step 1 — locate state

1. Read `.cfm-workflow.yml` at the project root. If it does not exist,
   report: "No cfm configuration here yet — run `/cfm:init` to set up the
   workflow." and stop.
2. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state.py" --project-dir "$(pwd)" show`. If the config's `state_file` (default
   `.cfm/state.json`) does not exist, the output is the empty seed
   (no phase): report "cfm is configured but no phase has started —
   `/cfm:plan` to plan a feature or `/cfm:implement-phase <description>`
   to start one." and stop. If the command exits 1, the file is
   unreadable: show its error and recommend `/cfm:doctor` — never repair
   it here.

## Step 2 — render

From the `show` output, present, in this order, skipping empty sections:

0. **Mode** — one line: the cfm mode from the merged config (`enforced`
   unless the file says otherwise) and what it means for this session —
   `enforced`: the guard refuses main-session writes to product code;
   `advisory`: the doctrine is injected, the guard is silent; `off`: no
   cfm context. `/cfm:mode` changes it.
1. **Current phase** — id, description, and the plan file it references.
2. **Pipeline cursor** — per layer: coder done? tests written/run (which
   files)? Then the review gates and their PASS/FAIL — from
   `cursor.phase_gates` when config `review.scope` is `phase` (the
   default), from each layer's `gates` when it is `layer`.
3. **Pending human gates** — anything waiting on the user (full test suite,
   git actions per level, next-phase approval).
4. **Carried forward** — every deferred obligation from state, verbatim,
   then the code-anchored half of the same ledger. Run
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/debt_scan.py" --project-dir "$(pwd)"`
   (pure read) and add one line: `<total> cfm-debt markers, <no_trigger>
   with no upgrade trigger`. List the `no_trigger` ones as
   `file:line — <ceiling>` — a shortcut naming a ceiling but no trigger to
   revisit it is the one that rots into "later means never". Zero markers
   renders nothing; the section keeps skipping when empty.
5. **Deferred config questions** — progressive-interview questions not yet
   asked, and which command will trigger each.
6. **Tracker sync** — provider and last sync result, or "offline (markdown
   plan is canonical)". When the current phase's plan is known, add one
   line for the binding: the phase's task key from its `- **tracker**:`
   line in the plan file, and the count of phases in that plan still
   unbound (those get tasks on the next sync). The plan file is the
   authority here, not state's `tracker.tasks` cache. Reading is all this
   step does — never call the tracker from `/cfm:status`.

The full state schema lives in the implement-phase skill's
`references/state-and-resume.md`. Render whatever fields exist and do not
invent missing ones; resume itself belongs to `/cfm:implement-phase`, not
to this skill.
