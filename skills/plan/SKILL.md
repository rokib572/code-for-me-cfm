---
name: plan
description: Turns a feature into a phased integration plan grounded in the real codebase — docs/plans/<feature-slug>.md with independently shippable phases sized for one implement-phase run, each declaring its test seams. Use when the user wants a feature broken down into implementable phases.
compatibility: Requires Claude Code (terminal, IDE extension, or Desktop Code tab)
---

# cfm:plan

Produce a plan grounded in the actual codebase, not guesses. The output is
a markdown plan file that `/cfm:implement-phase` executes phase by phase.
The plan file is canonical; any tracker is a projection of it.

## Step 0 — environment gate

Run: `bash "${CLAUDE_PLUGIN_ROOT}/scripts/require-claude-code.sh"`
If it exits non-zero, STOP and show its stderr verbatim.

## Step 1 — load config

Run: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/cfm_config.py" --project-dir "$(pwd)" --json`

- No config → send the user to `/cfm:init` and STOP.
- Validation errors → send them to `/cfm:doctor` and STOP (never plan on a
  broken config).

## Step 2 — enter plan mode

Call the `EnterPlanMode` tool NOW, before any grounding or drafting.
Planning is read-only thinking, and the user must approve the plan through
the plan-mode approval gate — not an informal "looks good?". If the
`EnterPlanMode` tool is not available in this session, continue with the
draft-show-approve flow described below and say nothing about it
(graceful degradation, no error).

## Step 3 — resolve the feature

- The argument, or the conversation so far, names the feature.
- If a feature brief exists (`docs/briefs/<slug>.md` matching the feature),
  read it — its acceptance criteria and non-goals seed the plan.
- If a product brief `docs/brief.md` exists, read it for context on where
  the feature fits.
- If the argument is `fix-<slug>` (a `/cfm:diagnose` hand-off, in this
  session or a fresh one), run
  `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state.py" --project-dir "$(pwd)" show`
  and, when the ledger holds a completed phase `diagnose-<slug>`, treat its
  `notes` as the brief: `root_cause` is the problem statement, `fix_scope`
  seeds the first phase's scope, `regression_seam` is its `seams` line, and
  `red_command` is its first test expectation (the loop that goes red must
  go green). Diagnose never applied a fix — the plan is where one starts.
- No recognizable feature → ask the user which feature to plan, in one
  question, and wait. Clarifying questions via `AskUserQuestion` are fine
  in plan mode.

## Step 4 — ground in the real code

This step and the next happen INSIDE plan mode — they are read-only.

BEFORE writing a single phase, read the code the feature will touch:

- the config's `layers` the feature crosses, in order;
- the `feature_roots` locations — and at least one neighboring feature that
  already lives there, to learn the actual conventions (naming, module
  layout, test placement);
- anything the brief names explicitly.

Plans reference real files, real modules, and real conventions. If you
have not read it, you may not cite it. If the repo is an empty skeleton,
say so and ground in the scaffold structure instead.

## Step 5 — draft the plan and present it through the approval gate

Draft the plan for `docs/plans/<feature-slug>.md` (kebab-case slug) —
draft only, no file yet:

- **Header**: feature name, link to the feature brief (if any), date,
  `status: draft`.
- **Phases** — for each phase:
  - **id**: kebab-case, unique in the plan (this is what
    `/cfm:implement-phase <id>` targets);
  - **goal**: one line;
  - **layers**: the layers touched, listed in the config's layer order;
  - **scope**: concrete files/modules to create or change, by path;
  - **acceptance criteria**: testable statements — a reviewer can answer
    pass/fail to each;
  - **seams**: the public boundaries this phase's tests observe behavior
    from, by name or path (e.g. "the `OrderIntake` module's public
    interface", "the `POST /orders` route"). One line; a seam per behavior
    worth locking down. The discipline behind the choice is
    `skills/testing/SKILL.md` — read it before drafting this line;
  - **test expectations**: what the e2e-test agent should prove at those
    seams, scoped;
  - **non-goals**: what this phase explicitly does NOT do.

Seams are drafted here so the human approves them at the same gate as the
scope. `/cfm:implement-phase` copies them verbatim into the e2e-test
dispatch brief, which is what keeps testing effort on the critical paths
instead of spread evenly over every edge case. A phase whose behavior has
no correct seam still gets the line — say so, and name it as a design
question for the architect rather than leaving the field blank.

Phase sizing rules: each phase must be independently shippable (the repo
is coherent and green after it) and sized for ONE `/cfm:implement-phase`
run. Too big → split; a phase that cannot ship alone → merge or reorder.

**YAGNI pass — do this before presenting.** The plan gate is the only place
speculative scope can be cut, because the human is here and the coder is
not: a dispatched agent works from an approved plan and builds what it
says. So read the draft back once, hunting for work that exists for an
imagined future rather than a stated need — a phase nothing downstream
consumes, an acceptance criterion no user story reaches, an abstraction
sized for a second case that does not exist, configurability nobody asked
for. Name each one in a line under the phase ("AC-3 is speculative: nothing
calls this path yet") and recommend cutting or deferring it. The user
decides at the gate. The discipline behind the call is
`skills/simplicity/SKILL.md`. Finding nothing is a fine outcome; say so in
one line rather than inventing a cut.

Present the finished plan by calling `ExitPlanMode` — the plan-mode
approval gate IS the approval. Never ask "is this plan okay?" as text.
The plan passed to `ExitPlanMode` must be the full phased plan — the same
content that will land in `docs/plans/<feature-slug>.md`. If the user
rejects it, revise inside plan mode and present again. Without plan mode
(fallback): show the full draft, iterate, and proceed only on the user's
explicit approval.

## Step 6 — write the plan file (after approval only)

Plan mode has exited; writes are allowed now. Write the approved plan to
`docs/plans/<feature-slug>.md` exactly as presented. Never overwrite an
existing plan for the same slug without showing a diff and getting
explicit approval.

**Amending an existing plan** — when the slug already exists, you are
amending, and step 7 has to bring the tracker along. Before writing,
record from the on-disk version: every phase id, its `tracker` binding
line if it has one, and enough of its content (goal, acceptance criteria,
layers, scope, non-goals) to tell changed from merely moved. Carry every
existing binding line into the amended plan for phases that survive — a
dropped binding line orphans a live task. This is the delta step 7's
reconcile consumes; without it, an amendment silently duplicates tasks.

## Step 7 — tracker (greenfield-gated question)

Check config `tracker.provider` and the `deferred_questions` in
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state.py" --project-dir "$(pwd)" show`.

- **Provider is null AND `deferred_questions` holds the tracker-question
  entry with `"outcome": null`** — recorded ONLY by greenfield
  `/cfm:init` — → the first plan is now approved and written, so ask
  exactly once: "Want to connect a project tracker (Jira, ClickUp,
  Trello, or your own MCP server)? The markdown plan stays canonical
  either way."
  - **yes** → run the connect-tracker flow: steps 3–6 of
    `${CLAUDE_PLUGIN_ROOT}/skills/connect-tracker/SKILL.md` — follow it
    by reference, do NOT duplicate it here. That flow offers the four
    providers, connects the MCP server, asks the sync flags, applies the
    YAML diff with explicit approval and an auto-doctor run, and sets the
    deferred-question entry's `"outcome": "accepted"`. If the user backs
    out before the config diff is approved, leave the entry's `outcome`
    null and tell the user plainly that this question will come back on
    the next `/cfm:plan` — that re-ask is intentional. Either way, the
    sub-flow's STOP ends only the tracker step, never the plan: ALWAYS
    continue to step 8.
  - **no** → `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state.py" --project-dir "$(pwd)" question --resolve --asked-by cfm:plan --outcome declined`
    — the entry is updated in place, so no cfm command ever auto-asks
    again.
- **No such pending entry** (existing/scaffolded/adopted repos, or the
  question was already answered) → do NOT ask. If no tracker is
  connected, end the tracker step with exactly ONE informational line:
  "No tracker connected — run /cfm:connect-tracker to integrate one."
  Nothing else.
- **Provider IS connected** → if a deferred tracker entry still has
  `"outcome": null` (e.g. the provider was hand-edited into config),
  close it (`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state.py" --project-dir "$(pwd)" question --resolve --asked-by cfm:plan --outcome accepted`)
  so `/cfm:status` stops listing it as pending. Then sync, gated on `tracker.sync.create_tasks`,
  following the adapter contract in `${CLAUDE_PLUGIN_ROOT}/CONNECTORS.md`
  Part 2:

  - **New plan** → run **create_tasks**: the container if the provider
    has one, then ONE TASK PER PHASE for every phase in the plan — not
    just the first. Each task carries the phase id, goal, acceptance
    criteria, layers, and a pointer to the plan file. Write each returned
    key back as that phase's `- **tracker**:` binding line (Part 2, "The
    binding"). Transition NOTHING — no phase has started.
  - **Amended plan** → run **create_tasks (reconcile after an
    amendment)** with step 6's delta: changed phases updated in place,
    new phases created and bound, unchanged/moved phases left alone, and
    phases dropped from the plan commented + closed, never deleted.
    Show the user the reconcile summary (`updated N, created M, closed
    K`) before the calls, then run it.

  Pipe every outbound payload through
  `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/redact.py"` (the single
  redaction source — never reimplement or inline its patterns), sending
  only the pipe's OUTPUT. When unsure whether a string is a credential,
  drop it and note `[redacted]`. A ticket is the most public place in the
  system.

  Adding the binding lines is bookkeeping on a plan the user just
  approved: apply it, mention it in one line, do not re-open the approval
  gate. Cache the bindings and the outcome in one call:
  `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state.py" --project-dir "$(pwd)" tracker --provider <provider> --last-sync "ok" --bind "<plan path>#<phase id>=<provider>:<key>" ...`
  (`--last-sync "failed: <reason>"` on failure).

Tracker failure of any kind (connector down, auth error, API rejection)
degrades to a one-line warning and continues — the plan file is written,
canonical, and complete. Offline must work fully.

## Step 8 — hand off

Point the user at the next command:
`/cfm:implement-phase <first phase id>`. NEVER start it yourself —
starting a phase is a human gate.

## Hard limits

- No product code, no scaffold — this skill plans; coders implement.
- Never mutate git; never run `verify_full`.
- No file writes while in plan mode; the plan file is written only after
  the plan-mode approval.
- The only writes: the plan file (including the `tracker` binding lines
  step 7 writes back), state through `scripts/state.py` only
  (deferred-question and tracker bookkeeping), and the approved config
  diff of Step 7. Nothing else.
- A tracker task is never deleted on an amendment — dropped phases get a
  comment and a close, so history survives.
