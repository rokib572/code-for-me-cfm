---
name: configure
description: Views or changes any cfm configuration value — profile, agents, models, autonomy, review pipeline, git level, command slots, coding conventions, tracker — always as a diff applied only on explicit approval, followed by an automatic doctor run. Use when the user wants a workflow setting or a project coding rule adjusted; this is the sanctioned path, so reach for it rather than hand-editing .cfm-workflow.yml.
compatibility: Requires Claude Code (terminal, IDE extension, or Desktop Code tab)
---

# cfm:configure

Change configuration safely: current value → proposed YAML diff → explicit
apply → automatic doctor. Config is the single source of truth — this skill
is the only sanctioned way to change it besides hand-editing plus doctor.

## Step 0 — environment gate

Run: `bash "${CLAUDE_PLUGIN_ROOT}/scripts/require-claude-code.sh"`
If it exits non-zero, STOP and show its stderr verbatim.

## Step 1 — load

Run: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/cfm_config.py" --project-dir "$(pwd)" --json`

- No config → tell the user to run `/cfm:init` first and STOP.
- Validation errors → show them, recommend fixing via this skill or
  `/cfm:doctor`, and continue only for the domains the errors don't touch.

## Step 2 — route to a domain

If the user named a domain or a concrete change, go straight there.
Otherwise show the menu once: **agents** (roster, models, autonomy, custom
agents) · **review** (gate order, trigger, scope) · **implement** (phase
plan gate) · **git** (level, branch prefixes) · **commands** (slots) ·
**profile** · **claude_md** (layout, files) · **conventions** (coding
rules, feature structure) · **secrets** (extend globs) · **tracker** ·
**mode** (cfm mode: enforced / advisory / off).

Domain notes:

- **agents / models**: present a live-fetched model list (check what models
  currently exist — never offer a hardcoded list) with a free-text escape
  hatch. Keep tier discipline visible: judgment/implementation/mechanical.
- **agents / custom agent**: follow the add-agent skill flow
  (`/cfm:add-agent`), which owns the questions, defaults, and
  single-owner conflict handling.
- **mode**: follow the mode skill flow (`/cfm:mode`), which owns the
  table of what each value does and the one-line diff. It is a team
  setting: never route it to `.cfm-workflow.local.yml`.
- **tracker**: follow the connect-tracker skill flow
  (`/cfm:connect-tracker`), which owns the provider menu (Jira, ClickUp,
  Trello, Custom), the MCP server connection, sync flags, and disconnect.
- **conventions**: follow the conventions round
  (`${CLAUDE_PLUGIN_ROOT}/skills/init/references/conventions-round.md`),
  which owns the categories, the rule format, and enforcement assignment.
  Read its "Re-run" section first — a re-run is a TARGETED change to one
  category or one rule, never the full init sweep. The change lands in
  `rules_file` and the CLAUDE.md `## Feature structure` sections, not in
  `.cfm-workflow.yml`, so step 4's diff is a markdown diff.
  Moving a rule TO `lint(...)` runs that file's "Prove the lint teeth"
  phase for that one rule — measured, wired, or demoted, same as at init.
  If the wiring needs a new or split lint slot, that is a `commands`
  change: a second, sequential diff under the one-domain limit below.
- **implement**: `implement.plan_gate` (default true) decides whether
  `/cfm:implement-phase` presents the phase's full dispatch plan through
  the plan-mode approval gate, or only a one-line scope confirmation.
  Either way the phase is entered through that gate, so the developer can
  approve with auto-accept edits; turning it off skips the reading, not
  the gate. Per-agent `autonomy` is unaffected.
- **profile**: switching profile rewrites the bundled values (git.level,
  autonomy, review.trigger) — show ALL of them in the diff, not just the
  profile name.
- **git level**: L0 read-only · L1 commit-local · L2 push-branches ·
  L3 open-PRs. The level itself decides what the guard forbids
  (`cfm_config.GIT_LEVEL_GRANTS`); `forbidden_ops` in config only EXTENDS
  that list and never needs regenerating. Show what the new level grants
  in the diff's consequence lines. Pushes landing on the default branch,
  force or delete pushes, branch deletes, git aliases, `git config`
  writes, and `gh pr merge` stay blocked at every level.
- **review**: `review_gates` order, `review.trigger`, `review.auto_scope`,
  and `review.scope` — `phase` (default) runs the reviewers once over the
  whole phase diff, `layer` runs them after every layer.
- **secrets**: `secret_globs` is additive — the defaults are always in
  force and the file lists only extras. A subset in the file is not a
  shrink; the loader re-adds the defaults and warns.
- **model/autonomy/plan-gate changes for one developer**: offer to write
  them to `.cfm-workflow.local.yml` (gitignored, personal) instead of the
  team file. Only `agents.*.model`, `agents.*.autonomy`,
  `implement.plan_gate`, and `token_reporting` may live there — the parser
  rejects anything else.

## Step 3 — refuse invariant changes

Decline, with one sentence of why, any request to: change
`cfm.requires.surface`, remove or narrow `secret_globs` entries (extending
is fine), allow direct push to the default branch, or keep a rule with no
enforcement. These are hard invariants; no profile or argument unlocks them.

## Step 4 — diff, apply, doctor

1. Show the exact change as a unified diff (only the changed lines, with 2
   lines of context) — YAML for `.cfm-workflow.yml`, markdown for the
   conventions domain's `rules_file` and CLAUDE.md edits. Below it, one
   sentence per behavioral consequence ("coder dispatches will now wait
   for your approval").
2. Apply ONLY on explicit approval. Edit the target file surgically —
   never rewrite untouched sections, never reformat, keep the user's
   comments.
3. Validate: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/cfm_config.py" --project-dir "$(pwd)"`
   — if it errors on what you wrote, fix your edit (not the user's other
   config) until clean. The conventions domain touches no config value, so
   this step is a no-op there; step 4 below is its real check.
4. Auto-run the doctor: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/doctor.py" --project-dir "$(pwd)"`
   and show the report. A change that turns the doctor red gets flagged
   immediately with the offer to revert the diff.
5. If check 7 reports deny entries missing from or **stale** in
   `.claude/settings.json` (a git-level or secrets change alters the
   required set — a raised level must RETRACT the old `git push:*`-style
   denies or the change is silently ineffective at the permission layer;
   a project initialized before the denies existed has none), offer to
   regenerate them: run
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/gen_settings.py" --project-dir "$(pwd)"`,
   show the diff against the current file (cfm's own recorded rules are
   retracted; everything the user wrote is kept in place), and on explicit
   approval re-run with `--write`, then re-run the doctor. This is a
   second, sequential diff under the one-domain limit below. If the
   sandbox is on (check 7 says so) add `--sandbox` to both runs so its
   entries follow the config too; if it is off, mention once that
   `--sandbox` adds the OS-level layer and leave the choice to the user.
   The same applies to the cfm status line (check 8 says whether it is
   on): `--statusline` writes a `statusLine` entry that shows the cfm
   mode and the phase in flight in Claude Code's status bar, replacing a
   personal status line inside this project only; `--remove-statusline`
   retracts cfm's and never the user's own. Offer it once when it is off.

## Hard limits

- Never apply without showing the diff and getting approval — even for
  "obviously safe" changes.
- Never touch git.
- One domain change per apply; batch requests become sequential diffs.
