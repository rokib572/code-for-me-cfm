---
name: code-review
description: Runs the configured review pipeline over a diff, path, staged changes, all uncommitted work, or a plain-English scope — dispatches the reviewers in config order and reports findings by severity with file:line. Use when the user asks to review changes, names a scope to review ("the auth module, watch for race conditions"), or an automatic trigger (phase-gate, on-stop, pre-commit) demands one.
compatibility: Requires Claude Code (terminal, IDE extension, or Desktop Code tab)
---

# cfm:code-review

You are the ORCHESTRATOR of the review pipeline. You resolve the target,
dispatch the configured reviewers, and report their verdicts. You never
review code yourself — reviewers do — and you never modify the code.

## Step 0 — environment gate

Run: `bash "${CLAUDE_PLUGIN_ROOT}/scripts/require-claude-code.sh"`
If it exits non-zero, STOP and show its stderr verbatim.

## Step 1 — load config

Run: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/cfm_config.py" --project-dir "$(pwd)" --json`

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

Scope on automatic triggers: when this skill fires from a phase-gate,
on-stop, or pre-commit context (not a direct user request), honor config
`review.auto_scope` — `fast` = dispatch code-reviewer only; `full` = the
whole pipeline.

## Step 3 — run the pipeline

Dispatch the agents exactly in the config's `review_gates` order — a
nested list is one parallel step (dispatch those agents concurrently);
the order is the config's, never your own. Model per agent from config
`agents.<name>.model`, passed to the Agent tool as its alias (`fable` /
`opus` / `sonnet` / `haiku` — the alias word inside the id). Custom agents
dispatch by their project agent file (`.claude/agents/<name>.md`), never
as a general subagent.

Every brief contains: `project_context` verbatim, the config's
`context_file` path (the project glossary), the file/diff scope, the
step-2 focus directive verbatim if there was one, and — for reviewers —
the plan section if a phase is in flight (read it with
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state.py" --project-dir "$(pwd)" show`).

Gate semantics in a review context:

- **e2e-test** = re-run EXISTING test files covering the touched files,
  via `commands.test_scoped`. If no such test files exist, skip the gate
  with a note — review never writes new tests.
- **mechanical-gate** = run its configured slots as-is, PASS/FAIL only.
- Never run `verify_full`; never mutate git.

## Step 4 — report

- Verdict per gate (PASS/FAIL).
- Findings ordered by severity, each with `file:line`.
- Token usage per dispatch when config `token_reporting` is true.

## Step 5 — mark reviewed

Only a review of the FULL uncommitted set (the no-argument case) marks the
tree reviewed. A path-, ref-, `staged`-, or prompt-scoped run covered part
of the work, so it must NOT write the loop-breaker — say in one line that
the tree is still unreviewed and skip to the trigger modes. Claiming
otherwise would silence the on-stop hook for everything the focus left out.

Write the loop-breaker file — at the PROJECT ROOT (the directory
containing `.cfm-workflow.yml`), which is the same anchor the Stop
hook uses (its `CLAUDE_PROJECT_DIR`), so run the recipe and the write
from there:

```bash
mkdir -p .cfm
sha256sum <(git status --porcelain; git diff; git ls-files -z --others --exclude-standard -- ':!.cfm' | sort -z | xargs -0 -r cat 2>/dev/null) | awk '{print $1}' > .cfm/last-review.sha
```

`scripts/on_stop_review.sh` computes the same hash (status, tracked diff,
and untracked file content outside `.cfm/` — so rewriting an untracked
file after review changes it, while the sha file itself never does) and
compares it against this file to decide whether the working tree has been
reviewed — this is what stops the on-stop trigger from looping. The hash
recipe here MUST stay byte-identical to that script's; if one changes,
change both (tests/run-tests.sh asserts the match).

## Trigger modes

- **manual** — this command, run by the user on demand. Always available
  regardless of `review.trigger`.
- **phase-gate** — `/cfm:implement-phase` runs the gates itself as part of
  each layer's pipeline; no separate invocation.
- **on-stop** — the Stop hook (`scripts/on_stop_review.sh`) blocks
  finishing while unreviewed changes exist, until Step 5's file matches.
- **pre-commit** — offer to install the hook by COPYING
  `${CLAUDE_PLUGIN_ROOT}/templates/pre-commit.sh` to
  `.git/hooks/pre-commit` (keep it executable). Only with the user's
  explicit approval — it is their repo; never install unasked.
- **settings generation** — offer to run
  `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/gen_settings.py" --project-dir "$(pwd)"`
  (add `--sandbox` when the user wants the OS-level layer, or when the
  sandbox is already on so its entries follow the config), show the
  proposed settings as a diff against the current `.claude/settings.json`
  — cfm's recorded rules that the config no longer requires are retracted,
  the user's own rules are kept — and on explicit approval re-run with
  `--write`. Then suggest `/cfm:doctor` to confirm coherence.

## Hard limits

- Read-only on the repo — the ONLY file this skill writes is
  `.cfm/last-review.sha` (plus the two installs above, each gated on
  explicit approval).
- Never mutate git; never run `verify_full` — both are the human's.
- The orchestrator never reviews code itself — reviewers do.
- Never read `secret_globs` files, even to review them.
