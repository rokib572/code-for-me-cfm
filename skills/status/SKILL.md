---
name: status
description: Shows where the cfm workflow stands — active phase, pipeline cursor, pending human gates, carried-forward debts, and deferred config questions. A pure read that changes nothing. Use when the user asks what is in flight or what to do next, or picks work back up in a fresh session.
compatibility: Requires Claude Code (terminal, IDE extension, or Desktop Code tab)
---

# cfm:status

Render the workflow state. This is a PURE READ — never modify state, config,
or any project file while executing this skill.

## Step 0 — environment gate

Run `test "$CLAUDECODE" = "1"` with Bash. If it fails, STOP and show
exactly: "cfm runs only in Claude Code (terminal, IDE, or the Desktop Code
tab). Your project config and brief are untouched — open this repo in
Claude Code to continue."

## Step 1 — locate state

1. Read `.cfm-workflow.yml` at the project root. If it does not exist,
   report: "No cfm configuration here yet — run `/cfm:init` to set up the
   workflow." and stop. Otherwise load the merged config per
   `${CLAUDE_PLUGIN_ROOT}/references/config.md` ("load and validate",
   then "read one key" for `mode`, `review.scope`, `state_file`). A
   config that fails validation still gets a status: show the errors,
   recommend `/cfm:doctor`, and continue with the defaults (`enforced`,
   `phase`, `.cfm/state.json`).
2. Read the state ledger with the `show` operation in
   `${CLAUDE_PLUGIN_ROOT}/references/state.md`. If the config's
   `state_file` (default `.cfm/state.json`) does not exist, the result is
   the empty seed (no phase): report "cfm is configured but no phase has
   started — `/cfm:plan` to plan a feature or `/cfm:implement-phase
   <description>` to start one." and stop. If the file is unreadable
   (invalid JSON, non-object top level): show the error from the
   reference and recommend `/cfm:doctor` — never repair it here.

## Step 2 — render

From the state, present, in this order, skipping empty sections:

0. **Mode** — one line: the cfm mode from the merged config (`enforced`
   unless the file says otherwise) and what it means for this session —
   `enforced`: the doctrine in CLAUDE.md forbids main-session writes to
   product code, every edit is a dispatch; `advisory`: the doctrine
   stands as a preference, a main-session write is allowed; `off`: no
   doctrine. Nothing refuses a write at runtime in any mode. `/cfm:mode`
   changes it.
1. **Current phase** — id, description, and the plan file it references.
2. **Pipeline cursor** — per layer: coder done? tests written/run (which
   files)? Then the review gates and their PASS/FAIL — from
   `cursor.phase_gates` when config `review.scope` is `phase` (the
   default), from each layer's `gates` when it is `layer`.
3. **Pending human gates** — anything waiting on the user (full test suite,
   git actions per level, next-phase approval).
4. **Carried forward** — every deferred obligation from state, verbatim,
   then the code-anchored half of the same ledger. Run the whole-repo
   debt scan in `${CLAUDE_PLUGIN_ROOT}/references/scans.md` (pure read)
   and add one line: `<total> cfm-debt markers, <no_trigger> with no
   upgrade trigger`. List the `no_trigger` ones as
   `file:line — <ceiling>` — a shortcut naming a ceiling but no trigger to
   revisit it is the one that rots into "later means never". Zero markers
   renders nothing; the section keeps skipping when empty.
5. **Deferred config questions** — progressive-interview questions not yet
   asked, and which command will trigger each.
6. **Tokens** — when `tokens.dispatches` is non-empty, the phase token
   table from section 5 of `references/state.md`, one row per dispatch,
   totals suffixed `+` where a dispatch has no usage. Never estimate a
   missing number; `—` is the honest cell.

The full state schema is `${CLAUDE_PLUGIN_ROOT}/references/state.md`.
Render whatever fields exist and do not invent missing ones; resume itself
belongs to `/cfm:implement-phase`, not to this skill.
