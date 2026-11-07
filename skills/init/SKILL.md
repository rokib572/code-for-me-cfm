---
name: init
description: Sets up the cfm workflow in any project — detects whether the repo is greenfield, existing, scaffolded, or has a prior Claude setup to adopt, then interviews the user, writes .cfm-workflow.yml, dispatches the scaffold, and runs the doctor until green. Use when the user wants to start using cfm in a project or onboard a repo.
compatibility: Requires Claude Code (terminal, IDE extension, or Desktop Code tab)
---

# cfm:init

Produce a valid, doctor-green `.cfm-workflow.yml` for this project. You
are the orchestrator: interview, propose, and write config — never write
product code or scaffold files yourself. Once the config exists the
doctrine block rendered into CLAUDE.md holds you to that in every later
session (cfm mode, `mode: enforced`) — nothing refuses a write at
runtime; the rule holds because you follow it. During init itself the
stack skeleton goes to the coder for the same reason.

## Step 0 — environment gate

Run with Bash: `test "$CLAUDECODE" = "1"`
If it exits non-zero, STOP and show exactly: "cfm runs only in Claude
Code (terminal, IDE, or the Desktop Code tab). Your project config and
brief are untouched — open this repo in Claude Code to continue."

## Step 1 — scan and classify

Run the init scan by hand per the **Init scan** section of
`${CLAUDE_PLUGIN_ROOT}/references/scans.md`: collect every signal in
order, apply the decision rules, and report `scenario`, `scenario_note`
and `signals` with exactly the keys it names.

The `scenario` field routes you:

| scenario | action |
|---|---|
| `already-initialized` | Say config already exists and name the cfm mode in force (`mode` from the merged config, `enforced` by default) in one line; offer `/cfm:configure` to change any setting, `/cfm:mode` to inspect or change the mode, `/cfm:doctor` to check health. STOP. |
| `adoption` | Follow **Adoption** in `references/scenarios.md` |
| `greenfield` | Follow **Greenfield** in `references/scenarios.md` |
| `scaffolded` / `existing` | The split is a heuristic — state what the scan found (source file count, manifests) and ask the user which it is, then follow that playbook in `references/scenarios.md` |

Read `references/scenarios.md` for the chosen playbook before proceeding.

## Step 2 — the progressive interview

Rules that apply to every scenario:

- Ask each question exactly ONCE, at the moment its answer first matters.
  Do not front-load; a question whose answer only matters later is
  DEFERRED: record it in the state ledger with the
  `question` operation (ask `<the question>`, `asked_by` = the command
  that will ask it) per `${CLAUDE_PLUGIN_ROOT}/references/state.md` —
  that command resolves the entry in place when it asks (the ask rule
  never writes a duplicate).
- Questions init must resolve now:
  1. **project_context** — draft one paragraph from the scan/brief, ask the
     user to confirm or correct it.
  2. **layers** — propose from the directory structure (or stack answers),
     ordered by build sequence; confirm.
  3. **profile** — supervised (default) / collaborative / autonomous, with
     one line on what each changes (git level, dispatch confirmation).
  4. **claude_md.layout** — `single` or `router` (root CLAUDE.md routing to
     per-layer files). Default `single` for one-layer projects.
  5. **commands** — derive per `references/command-derivation.md`.
  6. **existing ledgers** — when the scan's `doc_candidates` has entries,
     ask (AskUserQuestion) which listed file is the project's
     progress/status ledger → `progress_log`, and which (if any) holds
     the coding rules → `rules_file`; "none of these / use cfm defaults"
     is always an option. NEVER silently assume the defaults while
     candidates exist, and never adopt a candidate without asking.
- Coding conventions (naming, structure, style, testing) are NOT asked
  here — they are resolved in step 4, once a rules file exists to hold
  them. Do not front-load them into this round.
- Never ask what the scan already proved. Evidence beats questions.
- Exception to the rule above: the roster / models / autonomy round in
  step 3 (3a–3c) is NEVER skipped or answered on the user's behalf —
  auto-configuring it is a bug, not efficiency. Existing-project scans may
  PRE-FILL the proposals, but never skip the questions.

## Step 3 — config genesis (interactive round)

Config genesis is the moment the roster, model, and autonomy answers first
matter — so this is where the user chooses them. Sub-steps 3a–3c each use
the AskUserQuestion tool (Claude Code's structured question UI), never
free-text prose questions, and never a single take-it-or-leave-it YAML
dump. Run them in order:

1. Derive the candidate roster: `cat "${CLAUDE_PLUGIN_ROOT}/templates/roster.yml"`.
   Include an agent only if its `layers` gate matches (`[any]` = always; a
   named list activates only when such a layer exists). Replace `[any]` with
   the project's actual layer names in the written config.
2. **3a — roster toggle.** One AskUserQuestion with `multiSelect: true`:
   one option per candidate agent — label = agent name, description = its
   one-line purpose + tier. Note in the question text that the full listed
   set is the recommended default, with security-check and mechanical-gate
   strongly recommended. The user's selection IS the enabled set. If the
   user deselects security-check, warn once (it is the mandatory-per-phase
   security gate) — then respect the choice. Then one AskUserQuestion:
   "Add any custom agents of your own?" If yes, run the add-agent flow
   (steps 2–4 of `${CLAUDE_PLUGIN_ROOT}/skills/add-agent/SKILL.md` —
   follow it by reference, do NOT duplicate its questions here) once per
   custom agent; custom agents then join 3b/3c like roster agents,
   skipping anything the flow already answered.
3. **3b — models.** First confirm model ids against the live model list
   (check what models are currently available; never trust the template's
   defaults blindly). Then one AskUserQuestion: "Use the recommended model
   tiering, or customize?" Options:
   - **Recommended** — architect → strongest available, reviewers → next,
     implementation → mid, mechanical → cheapest; name the concrete live
     model ids you verified in the description.
   - **Customize per tier** — one model each for judgment /
     implementation / mechanical.
   - **Customize per agent** — one model for each enabled agent.
   If customizing: present the live-fetched model list per tier/agent —
   never a hardcoded list — with a free-text escape hatch via the Other
   option (same discipline as `cfm:configure` agents/models).
4. **3c — autonomy.** One AskUserQuestion: "How should agents dispatch?"
   Options, each with one line on what the user will experience:
   - **All automatic** — profile default for supervised; agents dispatch
     freely, you see results at phase gates.
   - **Confirm each implementation dispatch** — coder, e2e-test, and
     ui-design show a dispatch brief and wait for your OK (`confirm`);
     reviewers stay automatic.
   - **Confirm the phase plan once** — approve the phase's whole dispatch
     plan up front (`confirm-plan` for implementation agents), then it runs
     unattended.
   - **Customize per agent** — set auto / confirm / confirm-plan agent by
     agent.
5. **3d — assemble and approve.** Build the full config from the 3a–3c
   answers. Fields and defaults are defined by
   `${CLAUDE_PLUGIN_ROOT}/references/config.md` — match its schema exactly
   (schema_version 2, `cfm.requires.surface: claude-code`) and validate
   the assembled YAML against its section 5 before showing it. Set
   `review_gates` to the default pipeline:
   `[e2e-test, [code-reviewer, security-check, simplicity-check], mechanical-gate]`,
   dropping entries whose agent the user did not enable in 3a. The three
   reviewers share one parallel step deliberately — they answer different
   questions (is it right / is it safe / is it more code than the job
   needs), and merging them into one ranked report lets a finding on one
   axis mask a finding on another. Running them in parallel costs no extra
   wall-clock. `review.trigger` is `manual`, `phase-gate` (default) or
   `pre-commit` — `on-stop` is retired and never written. Write
   `implement: {plan_gate: true}` explicitly, the same way `review:` is
   written — do NOT add an interview question for it; 3c already covers
   dispatch autonomy, and `/cfm:configure` owns the change later. Write
   `mode: enforced` explicitly too, with a one-line comment (`# cfm mode:
   the main session orchestrates; product code is written by dispatched
   agents — /cfm:mode to change`) — no interview question either; the
   default is the doctrine, and `/cfm:mode` owns the change. Show the
   COMPLETE proposed YAML and get explicit approval — this final look
   checks the assembly; it is not a substitute for 3a–3c.
6. Write `.cfm-workflow.yml`. If the rules file does not exist yet,
   create the config's `rules_file` from the rules-seed template in
   `${CLAUDE_PLUGIN_ROOT}/references/scaffold.md` (`## R<n>. <title>` +
   `**Enforcement:**` line; owners picked from the ENABLED roster, or
   `lint(lint_arch)` when that slot exists). With no enabled reviewer and
   no lint slot, stop and send the user to `/cfm:configure agents` —
   never seed a rule whose enforcement names nothing live. Greenfield:
   skip this — the render in `references/scaffold.md` produces the seed.

## Step 4 — conventions round

Resolve the project's coding conventions — naming, feature structure,
layer boundaries, style, types, errors, testing. Follow
`references/conventions-round.md` and run it by reference; do NOT restate
its categories or questions here.

The round appends to the rules file, so it runs only once that file is on
disk:

- **Greenfield** — the rules file does not exist until the workflow
  scaffold is rendered, and the linter does not exist until the skeleton
  does. Follow
  `references/scaffold.md`: render the workflow files (its step 1), run
  the interview and rules (step 1.5), dispatch the coder for the stack
  skeleton (step 2) so it is built to the conventions, then prove the lint
  teeth (step 2.5).
- **Existing / scaffolded / adoption** — the seeded or adopted rules file
  from step 3 is already on disk and the toolchain already exists; run the
  round straight through, proof phase included.

## Step 4.5 — seed the glossary

The scaffold wrote an empty glossary at the config's `context_file`. Seed
it with the terms this project already has, so the first dispatch inherits
a shared language instead of deriving one.

Sources, in order: `docs/brief.md` if `/cfm:brainstorm` produced one, the
answers given during this interview, and the domain nouns already visible
in an existing codebase's directory and model names.

Propose **3 to 8 terms** — the ones that carry the project's meaning, not
every noun — each with its definition and the near-synonyms it replaces.
Show them to the user, take their corrections, and write only what they
confirm. An entry nobody confirmed is a guess that every future agent will
treat as settled.

Fewer than three real terms is a fine outcome on a thin brief: leave the
glossary near-empty and say so. Terms are earned as they resolve, and
`skills/domain-modeling/SKILL.md` is the discipline for adding them later.

## Step 5 — settings denies, then validate

Greenfield: the scaffold and coder dispatch happen in step 4 via
`references/scaffold.md`. The doctor must be fully green on the empty
skeleton before init ends.

**Settings denies first.** The generated `.claude/settings.json` deny
rules are the permission layer — the one enforcement no missing
interpreter can switch off — and the doctor FAILS check 7 without them.
Derive the required set per
`${CLAUDE_PLUGIN_ROOT}/references/settings-denies.md`, show the proposed
document as a unified diff against the current `.claude/settings.json`
(cfm's rules are recorded in `.claude/cfm-denies.json` so a later config
change can retract them; every entry the user wrote is kept in place),
and write the pair ONLY on the user's explicit approval. Adoption repos
with a hand-written settings file get the same merge — nothing of theirs
is removed. If the user declines, say in one line that the doctor will
stay red on check 7 until the denies exist.

Then offer, once, the OS-level layer: the sandbox block from the same
reference enables Claude Code's Bash sandbox in the project settings with
`denyRead` on every secret glob and `denyWrite` on the config pair and
sidecar, which closes the interpreter, variable and script-file evasions
the text rules cannot see. It needs macOS, Linux or WSL2 (Linux:
`bubblewrap`; the `/sandbox` panel lists what is missing) and adds
network prompts of its own, so it is the user's call — show the block as
part of the same diff if they say yes, and tell them to verify the
resolved paths in `/sandbox` → Config afterwards.

Then recommend, once, that the user install their own staged-secret scan
(for example gitleaks) as `.git/hooks/pre-commit`: cfm ships no script
for it and never writes one; the doctor warns on check 7 while that file
is absent, and the warning never turns the verdict red.

Run the doctor: every check 0–9 by hand per
`${CLAUDE_PLUGIN_ROOT}/references/doctor.md`, printed in its output
contract.

- Doctor failures caused by init's own output are yours to fix: adjust the
  config or seed files and re-run until green (command slots that fail
  because the project genuinely lacks the tool → remove the slot: absent
  slots deactivate capabilities; never fake a green command).
- Show the final doctor report. End by telling the user their next command:
  `/cfm:plan` for a feature, or `/cfm:configure` to tune anything —
  including `/cfm:configure` → conventions to revise the coding rules and
  feature structure settled in step 4.

## Hard limits

- Never scaffold product code in this skill. Rendering the workflow
  scaffold per `${CLAUDE_PLUGIN_ROOT}/references/scaffold.md` is allowed
  — it writes WORKFLOW files from config; the STACK SKELETON is always
  dispatched to the coder agent (see `references/scaffold.md`).
- Never overwrite an existing CLAUDE.md, agent file, or settings file
  (adoption absorbs; it does not clobber). The conventions round APPENDS a
  `## Feature structure` section to CLAUDE.md — appending a new section is
  not overwriting; rewriting or reordering what is already there is.
- Never touch git.
- The conventions round writes rules and CLAUDE.md sections itself; linter
  configuration is DISPATCHED to the coder and verified by the
  mechanical-gate, never written in this session. A `lint(...)`
  enforcement that cannot be measured biting is demoted to a reviewer, not
  left standing — an unproven claim is a fake green.
- Hard invariants are not interview questions: surface, secrets policy,
  rules-need-teeth, and no-push-to-main are fixed.
