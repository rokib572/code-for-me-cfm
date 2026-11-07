---
name: code-review
description: Runs the configured review pipeline over a diff, path, staged changes, all uncommitted work, or a plain-English scope — dispatches the reviewers in config order and reports findings by severity with file:line. Use when the user asks to review changes, names a scope to review ("the auth module, watch for race conditions"), or an automatic trigger (phase-gate, pre-commit) demands one.
compatibility: Requires Claude Code (terminal, IDE extension, or Desktop Code tab)
---

# cfm:code-review

You are the ORCHESTRATOR of the review pipeline. You resolve the target,
dispatch the configured reviewers, and report their verdicts. You never
review code yourself — reviewers do — and you never modify the code.

## Step 0 — environment gate

Run `test "$CLAUDECODE" = "1"` with Bash. If it fails, STOP and show
exactly: "cfm runs only in Claude Code (terminal, IDE, or the Desktop Code
tab). Your project config and brief are untouched — open this repo in
Claude Code to continue."

## Step 1 — load config

Load and validate the effective config by the procedure in
`${CLAUDE_PLUGIN_ROOT}/references/config.md` (section 7).

- No config → send the user to `/cfm:init` and STOP.
- Validation errors → send them to `/cfm:doctor` and STOP (never review on
  a broken config).

## Step 2 — resolve the review target

An explicit argument wins. Try the exact forms first, in this order:

- a **path** → review those files;
- a **git ref or range** → review that diff (`git diff <ref-or-range>`,
  read-only);
- **`staged`** → review `git diff --cached`.

Anything else is a **scope prompt** in plain English ("the auth module",
"check the payment code for race conditions"). Resolve it to a concrete
file set with read-only Grep/Glob over the repo — intersected with the
uncommitted set when the prompt implies the user's own changes — restate
the resolved files in one line before dispatching, and pass the prompt
VERBATIM to every reviewer as a focus directive in its brief. A prompt
that resolves to no files: say so and STOP; never silently widen it to
the whole repo.

A focus prompt narrows attention, never responsibility: a reviewer that
sees a critical or security finding outside the focus still reports it.

No argument → all uncommitted work: `git status --porcelain` plus
`git diff` (read-only commands only). If the resolved target is empty,
say there is nothing to review and STOP.

Scope on automatic triggers: when this skill fires from a phase-gate or
pre-commit context (not a direct user request), honor config
`review.auto_scope` — `fast` = dispatch code-reviewer only (the first
gate when code-reviewer is not enabled); `full` = the whole pipeline.

## Step 3 — run the pipeline

The effective config carries only enabled agents and drops a disabled
agent's gates (config.md section 6), so a disabled reviewer never runs and
is never reported. Dispatch the agents exactly in its `review_gates`
order — a nested list is one parallel step (dispatch those agents
concurrently); the order is the config's, never your own. Model per agent
from config `agents.<name>.model`, passed to the Agent tool as its alias
(`fable` / `opus` / `sonnet` / `haiku` — the alias word inside the id).
Custom agents dispatch by their project agent file
(`.claude/agents/<name>.md`), never as a general subagent.

Every brief contains: `project_context` verbatim, the config's
`context_file` path (the project glossary), the file/diff scope, the
step-2 focus directive verbatim if there was one, and — for reviewers —
the plan section if a phase is in flight (read the ledger by the `show`
operation in `${CLAUDE_PLUGIN_ROOT}/references/state.md`).

Gate semantics in a review context:

- **e2e-test** = re-run EXISTING test files covering the touched files,
  via `commands.test_scoped`. If no such test files exist, skip the gate
  with a note — review never writes new tests.
- **mechanical-gate** = run its configured slots as-is, PASS/FAIL only.
- Never run `verify_full`; never mutate git.

## Step 4 — report

- Verdict per gate (PASS/FAIL).
- Findings ordered by severity, each with `file:line`.
- Token usage per dispatch when config `token_reporting` is true — taken
  from each reviewer's result as it lands ("tokens not reported" when none
  came back); never end the turn to wait for usage numbers.

## Step 5 — record the dispatches

When a phase is in flight, write each reviewer result into the ledger by
the `record` operation in `${CLAUDE_PLUGIN_ROOT}/references/state.md`:
`purpose: "review: <scope>"`, a null layer (the layer under
`review.scope: layer`), and only the usage numbers the result actually
carried — nulls otherwise, backfilled later with `usage`. Record as each
result lands, never while a reviewer is still running. No phase in
flight → nothing to record; say so in one line.

Only a review of the FULL uncommitted set (the no-argument case) covers
the tree. A path-, ref-, `staged`-, or prompt-scoped run covered part of
the work, so say in one line that the rest is still unreviewed.

## Trigger modes

- **manual** — this command, run by the user on demand. Always available
  regardless of `review.trigger`.
- **phase-gate** — `/cfm:implement-phase` runs the gates itself as part of
  each layer's pipeline; no separate invocation.
- **pre-commit** — the user's own `.git/hooks/pre-commit` invokes a review
  of the staged set (for example `claude -p "/cfm:code-review staged"`)
  and refuses the commit on a FAIL verdict. cfm ships no hook file and
  never writes into `.git/hooks/` — it is their repo; when asked, describe
  the shape and let the user install it.
- **`on-stop`** is retired: nothing in this edition can hold a session
  open until a review runs. A config still naming it loads as
  `phase-gate` with the warning config.md gives.
- **settings generation** — offer the propose-diff-approve-write
  procedure in `${CLAUDE_PLUGIN_ROOT}/references/settings-denies.md`
  (include its sandbox block when the user wants the OS-level layer, or
  when the sandbox is already on so its entries follow the config); show
  the proposed settings as a diff against the current
  `.claude/settings.json` — cfm's recorded rules that the config no longer
  requires are retracted, the user's own rules are kept — and write only
  on explicit approval. Then suggest `/cfm:doctor` to confirm coherence.

## Hard limits

- Read-only on the repo — the ONLY file this skill writes is the state
  ledger (Step 5), plus the settings write above, gated on explicit
  approval.
- Never mutate git; never run `verify_full` — both are the human's.
- The orchestrator never reviews code itself — reviewers do.
- Never read `secret_globs` files, even to review them.
