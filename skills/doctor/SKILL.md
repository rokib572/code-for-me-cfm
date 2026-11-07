---
name: doctor
description: Validates that cfm config and reality still agree — environment, schema and invariants, paths, commands, agent roster, models, rule teeth, secrets hygiene, pipeline wiring, and state (checks 0-9). Use when the user wants the setup checked, after any change to .cfm-workflow.yml, or when behavior seems to contradict the configuration.
compatibility: Requires Claude Code (terminal, IDE extension, or Desktop Code tab)
---

# cfm:doctor

Validate that the cfm configuration and the repository still agree. Config
values are promises; the doctor converts them to facts.

## Step 0 — environment gate

Run `test "$CLAUDECODE" = "1"` with Bash. If it fails, STOP immediately
and show exactly: "cfm runs only in Claude Code (terminal, IDE, or the
Desktop Code tab). Your project config and brief are untouched — open this
repo in Claude Code to continue." Do not attempt any other step.

## Step 1 — run the checks

Run checks 0-9 by hand, in order, exactly as
`${CLAUDE_PLUGIN_ROOT}/references/doctor.md` specifies them — Read, Glob,
Grep and short shell commands, quoting its message wording verbatim.

- That document is the single source of truth for what each check does;
  never invent a check or skip one. Config that fails check 1 makes
  checks 2-9 SKIP, not FAIL.
- Never run `verify_full`, `test_scoped`, or a `migrate_*` slot; only
  `lint`, `lint_arch` and `typecheck` are ever executed.
- Never read a file matching a `secret_globs` entry — names, `.gitignore`
  lines and `.env.example` only.

## Step 2 — render the report

Print the report in doctor.md's output contract: the `cfm doctor` header,
one `[PASS|WARN|FAIL|SKIP] #<n> <name>` line per check with its failures,
warnings and notes beneath, then the verdict line.

| # | check |
|---|---|
| 0 | environment |
| 1 | schema & invariants |
| 2 | paths |
| 3 | commands |
| 4 | roster coherence (incl. agent files vs config tools; project files still naming a disabled agent) |
| 5 | models |
| 6 | rules have teeth |
| 7 | secrets hygiene (incl. settings denies present and none stale; sandbox status) |
| 8 | pipeline wiring (settings deny layer, CLAUDE.md doctrine block matches the mode, pre-commit trigger has teeth) |
| 9 | state |

For check #5 the written rules only validate the id shape; you do the
live part: verify each configured `agents.*.model` id against the models
you know currently exist, flag any id that no longer resolves, and suggest
`/cfm:configure agents` to update it.

Then, for every failure, explain in one or two sentences:
- what is broken, quoting the exact failure message,
- the most likely fix (edit `.cfm-workflow.yml`, create the missing file,
  fix the failing command, add an `**Enforcement:**` line to a rule,
  regenerate the settings denies, re-render the CLAUDE.md doctrine block).

## Step 3 — verdict and follow-up

- End with one line: **healthy** or **unhealthy (N failures)**.
- NEVER edit `.cfm-workflow.yml` or any project file to "fix" a finding
  yourself. Propose the fix and let the user apply it (or approve it
  explicitly), then re-run the doctor to confirm.
- Hard invariants (Claude Code only, secret globs never shrinkable, rules
  need teeth, no direct push to main) are not fixable by relaxing config —
  if the user asks to disable one, decline and explain it is non-configurable.
