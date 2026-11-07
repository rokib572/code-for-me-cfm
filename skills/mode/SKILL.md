---
name: mode
description: Shows or changes cfm mode — enforced (the doctrine block rendered into CLAUDE.md forbids main-session writes to product code and expects every change to be dispatched), advisory (same doctrine, the rule stated as a preference), or off (a one-line notice) — as a one-line config diff applied only on explicit approval, followed by a CLAUDE.md doctrine re-render and an automatic doctor run. Use when the user asks what mode the session is in, wants to relax or restore cfm's orchestrator-only rule, or asks why a change was routed to a dispatch instead of an edit.
compatibility: Requires Claude Code (terminal, IDE extension, or Desktop Code tab)
---

# cfm:mode

cfm mode is the layer cfm adds on top of whichever Claude Code permission
mode is active. Whenever a repository carries `.cfm-workflow.yml`, every
session in it enters cfm mode: the main session orchestrates, work goes
through the `/cfm:*` skills, and product code is written only by
dispatched agents. The mode lives in two places that must agree: the
`mode` value in config, and the doctrine block it renders between
`<!-- cfm:begin -->` and `<!-- cfm:end -->` in the root `CLAUDE.md` (per
`${CLAUDE_PLUGIN_ROOT}/references/scaffold.md`), which Claude Code loads
every session. This skill reads or changes that pair and nothing else.

| mode | doctrine block in CLAUDE.md | main-session product writes |
|---|---|---|
| `enforced` (default) | full block, writes forbidden by instruction | forbidden — dispatch the coder |
| `advisory` | full block, rule stated as a preference | allowed, rule still stands |
| `off` | one-line notice only | allowed |

Said once, honestly: this edition ships no runtime guard — nothing refuses
a write in any mode. `enforced` is a standing instruction the orchestrator
obeys; a product edit from the main session shows up in review as a diff
with no dispatch record behind it. Settings denies and agent-file tool
limits do not depend on the mode.

"Product" is everything inside the project that is not a workflow file:
the config pair, `.claude/`, `.cfm/`, `.git/`, `docs/`, `CLAUDE.md` and
the `claude_md.files` entries, and the configured `rules_file`,
`context_file`, `progress_log` and `state_file` (plus `.gitignore` and
`.env.example`) stay writable from the main session in every mode.

## Step 0 — environment gate

Run `test "$CLAUDECODE" = "1"` with Bash. If it fails, STOP and show
exactly: "cfm runs only in Claude Code (terminal, IDE, or the Desktop Code
tab). Your project config and brief are untouched — open this repo in
Claude Code to continue."

## Step 1 — load

Read `.cfm-workflow.yml` at the project root. If it does not exist, report
"No cfm configuration here — cfm mode applies only to initialized
projects; run `/cfm:init`." and stop. Load and validate the effective
config per `${CLAUDE_PLUGIN_ROOT}/references/config.md` and read `mode`
from it (absent means the default, `enforced`; a bare `off` parses as a
boolean and means `off`). Then read the root `CLAUDE.md` and note which
mode its `## cfm mode: <MODE>` heading announces, or that the marked
region is missing.

## Step 2 — show

With no argument, or an argument that is not one of `enforced`,
`advisory`, `off`: print the current mode, one line on what it means (the
table row above), and the fact that it is a team setting — it lives in
`.cfm-workflow.yml`, never in `.cfm-workflow.local.yml`, because "the
orchestrator never writes code" is a promise the whole repository makes,
not one developer's comfort setting. If CLAUDE.md announces a different
mode, or carries no block while the mode is not `off`, say that config
and doctrine disagree and offer the re-render of step 3.4 alone. Then
stop.

If the user asked because a change was routed to a dispatch instead of
being edited directly ("a file change is a dispatch, never an edit"), say
what that means before offering anything: the change belongs to a
dispatched coder (`/cfm:implement-phase` for phase work; a bug starts at
`/cfm:diagnose`, which hands its findings to `/cfm:plan`), and lowering
the mode is the exception, not the fix.

## Step 3 — change

With `enforced`, `advisory` or `off` as the argument (a value equal to
the current mode is a no-op — say so and stop):

1. Show the diff — the single `mode:` line of `.cfm-workflow.yml`, added
   when absent, changed in place when present, with two lines of context —
   and one sentence per consequence, from the table: what the doctrine
   will say about the main session's product writes, and what the next
   session reads. Lowering to `off` also says that the next session in
   this repository will read only the one-line notice.
2. Apply ONLY on explicit approval. Edit the file surgically; write the
   value quoted (`mode: "off"`) so YAML never reads it as a boolean.
3. Validate: re-run the load of step 1 ("Validate after a write" in
   config.md) and expect zero errors.
4. Re-render the doctrine: render the root `CLAUDE.md` from the new
   config per scaffold.md, show the diff of the marked region only, and
   apply on explicit approval with its replace rule (one Edit of the
   region, markers included; nothing outside them changes; a guide
   without markers follows the no-markers rule). Until this lands, config
   and doctrine disagree and the doctor says so.
5. Auto-run the doctor: run checks 0-9 by hand per
   `${CLAUDE_PLUGIN_ROOT}/references/doctor.md` and show the report;
   check 8 compares the block's mode heading with the config.
6. Say that this session follows the new doctrine from now on, that a
   fresh session (or `/clear`) reloads CLAUDE.md, and that
   `git diff .cfm-workflow.yml CLAUDE.md` shows it to the team.

## Hard limits

- This skill edits the `mode` line of `.cfm-workflow.yml` and the
  cfm-owned region of the root CLAUDE.md, nothing else — no other key, no
  byte outside the markers, never the local override file.
- Never apply without showing the diff and getting approval.
- Never touch git.
- Never lower the mode on your own initiative: a write the doctrine
  forbids is a dispatch waiting to happen, and only the human decides
  otherwise.
