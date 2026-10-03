---
name: diagnose
description: Diagnoses a bug or performance regression through a gated loop — builds a feedback loop that goes red on THIS bug, minimises the repro, ranks falsifiable hypotheses, instruments one variable at a time, then reports the confirmed root cause and asks whether to plan a fix. It never applies one. Use when the user reports something broken, throwing, failing, or slow, or asks for it to be debugged.
compatibility: Requires Claude Code (terminal, IDE extension, or Desktop Code tab)
---

# cfm:diagnose

You are the ORCHESTRATOR. You hold the phase discipline, dispatch
subagents, and keep the ledgers. Every loop script and probe comes from a
dispatched agent — there is no "one-line change" exception, and in cfm mode
(`mode: enforced`, the default) the guard refuses the write; a refusal
means dispatch.

This skill ends at the finding. It never applies a fix and never asks an
agent to: the fix is a feature like any other and goes through `/cfm:plan`
and `/cfm:implement-phase`, where it earns its regression test and the
review gates. What this skill owns is everything that comes before that
code — the loop, the repro, the confirmed cause, and the seam the fix's
test should observe from.

## Output order — the one rule

**Your first substantive output is a command and what it printed.** The
cause comes after that, or not at all this turn. Recognizing the bug class
on sight is the moment the rule binds hardest, not a reason to skip it.

Naming a cause before showing a command that ran is a wrong answer even
when the cause turns out to be right: a plausible-on-sight diagnosis is
exactly what this discipline exists to resist, and being right by luck
trains the habit that loses the next bug. If you catch yourself typing
"the problem is", stop and go build the loop.

## Step 0 — environment gate

Run: `bash "${CLAUDE_PLUGIN_ROOT}/scripts/require-claude-code.sh"`
If it exits non-zero, STOP and show its stderr verbatim.

## Step 1 — load config and state

1. Config: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/cfm_config.py" --project-dir "$(pwd)" --json`
   — no config → send the user to `/cfm:init` and STOP; validation errors →
   send them to `/cfm:doctor` and STOP.
2. State: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state.py" --project-dir "$(pwd)" show` (a pure read). The ledger is written only
   through that script; the schema and command table are in
   `${CLAUDE_PLUGIN_ROOT}/skills/implement-phase/references/state-and-resume.md`.
   A diagnosis is recorded as a phase whose id is `diagnose-<slug>`, so a
   dead session resumes from the ledger exactly like an implementation
   phase does.
3. Resolve `$CLAUDE_PLUGIN_ROOT` once (`echo "$CLAUDE_PLUGIN_ROOT"`) and
   keep the absolute path. Dispatch briefs are text: an unexpanded
   `${CLAUDE_PLUGIN_ROOT}` reaches a subagent literally and its Read fails.

**A phase already in flight?** Say so with its id and progress, and let the
user choose: finish it first, or record the diagnosis as its own phase
(the implementation phase stays in-flight, and the interruption goes into
its carried-forward list).

## Step 2 — capture the symptom

Get the user's exact symptom in their words, before any code is read: what
they did, what happened, what they expected. That sentence is the thing the
loop in step 3 has to be able to detect, and every later phase checks back
against it. Wrong symptom means right loop for the wrong bug.

Open the phase with that sentence as its description:
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state.py" --project-dir "$(pwd)" init --id diagnose-<slug> --description "<the symptom, verbatim>" --layers <layers the bug touches>`.

## Showing commands and output

Everything this skill surfaces — a loop invocation, its output, a captured
trace, a probe's log line — goes through redaction first:

```bash
<command producing the text> 2>&1 | python3 "${CLAUDE_PLUGIN_ROOT}/scripts/redact.py"
```

Show the pipe's OUTPUT and nothing else. `scripts/redact.py` is the single
source of redaction patterns; carry no pattern list of your own. If the
pipe fails, show nothing — fail closed. Build loops against environment
variables so credentials stay in the environment rather than in the text.
If redacted output is genuinely not enough to diagnose the bug, say so and
ask the user rather than widening what you print.

The secrets policy applies unchanged: agents never read `secret_globs`
files, even to diagnose one.

## Phase 1 — build a feedback loop

**This is the skill.** Everything after it is mechanical. With a tight
pass/fail signal that goes red on *this* bug, bisection, hypothesis
testing, and instrumentation all just consume it. Without one, reading code
produces theories that feel right and are not.

Spend disproportionate effort here. Be aggressive, be creative, and keep
going: this is the phase to over-invest in.

Dispatch the **coder** to construct the loop. Ways to build one, in roughly
this order:

1. **Failing test** at whatever seam reaches the bug.
2. **HTTP script** (any request client) against a locally running dev server.
3. **CLI invocation** with a fixture input, diffed against known-good
   output.
4. **Headless browser script** driving the UI and asserting on DOM,
   console, or network.
5. **Replay a captured trace** — a real request, payload, or event log
   saved to disk and pushed through the code path in isolation.
6. **Throwaway harness** — a minimal subset of the system (one service,
   mocked dependencies) that reaches the bug in a single call.
7. **Property or fuzz loop** — for "sometimes wrong output", run many
   random inputs and watch for the failure mode.
8. **Bisection harness** — the bug appeared between two known states, so
   automate "boot at state X, check, repeat".
9. **Differential loop** — same input through two versions or configs,
   diff the outputs.

Then **tighten** it. Treat the loop as the product of this phase: make it
faster (cache setup, skip unrelated init), sharper (assert the specific
symptom rather than "did not crash"), and more deterministic (pin time,
seed the RNG, isolate the filesystem, freeze the network). A 30-second
flaky loop is barely a loop; a 2-second deterministic one is a superpower.

**Non-deterministic bugs** want a higher reproduction rate rather than a
clean repro: loop the trigger, parallelise, add stress, narrow timing
windows, inject sleeps. A 50%-flake bug is debuggable; keep raising the
rate until it is.

### Gate: a tight loop that goes red

Phase 1 completes when ONE named command — a script path, a test
invocation, an HTTP call — has **already been run at least once**, with its
invocation and redacted output shown, and is:

- **Red-capable**: it drives the real bug code path and asserts the user's
  exact symptom from step 2, so it goes red now and green once fixed.
  "Runs without erroring" does not qualify.
- **Deterministic**: same verdict every run (or a pinned, high reproduction
  rate for a flaky bug).
- **Fast**: seconds.
- **Agent-runnable**: it runs unattended.

Record the command: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state.py" --project-dir "$(pwd)" note --key red_command --value "<the exact invocation>"`.
**No red command, no phase 2.** Reading code
to build a theory before this command exists is the exact failure this
skill prevents — if you catch yourself doing it, stop and return to
building the loop.

**Genuinely cannot build one?** Stop and say so, listing what was tried.
Ask the user for one of: access to an environment that reproduces it, a
redacted captured artifact (HAR, log dump, core dump, timestamped
recording), or permission to add temporary instrumentation to a running
environment. Do not proceed to hypothesise.

## Phase 2 — reproduce and minimise

Run the loop and watch it go red.

Confirm all three:

- The failure is the one the **user** described, not a different failure
  living nearby.
- It reproduces across runs (or at the pinned rate).
- The exact symptom is captured — error text, wrong value, measured timing
  — so the fix's regression test can later prove it addressed it.

Then **minimise**: shrink to the smallest scenario that still goes red. Cut
inputs, callers, config, data, and steps **one at a time**, re-running the
loop after each cut, keeping only what is load-bearing. Done when removing
any remaining element turns the loop green.

Minimising pays twice: it shrinks the hypothesis space in phase 3, and it
is the regression test the fix's plan will name.

## Phase 3 — hypothesise

Generate **3 to 5 ranked hypotheses before testing any of them**. Testing
as you go anchors the whole diagnosis on the first plausible idea.

Each one states its prediction, so it can be wrong:

> If `<X>` is the cause, then `<changing Y>` makes the bug disappear, and
> `<changing Z>` makes it worse.

A hypothesis with no stated prediction is a vibe: sharpen it or drop it.

**Show the ranked list to the user before testing.** They re-rank instantly
when they hold context you do not ("we deployed a change to #3 on
Tuesday"), and they know what has already been ruled out. Cheap
checkpoint, large payoff. Proceed with your own ranking if they are away —
this informs, it does not block.

Record the list (`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state.py" --project-dir "$(pwd)" note --key hypotheses --value "<the ranked list>"`)
so a resumed session inherits the ranking.

## Phase 4 — instrument

Every probe maps to a specific prediction from phase 3, and you **change
one variable at a time**.

Tool order:

1. **Debugger or REPL inspection** where the environment supports it. One
   breakpoint beats ten log lines.
2. **Targeted logs** at the boundaries that distinguish two hypotheses.
3. Logging broadly and grepping afterwards produces noise, not signal.

**Tag every debug line** with a unique marker — `[DEBUG-a4f2]` — chosen
once per diagnosis and recorded
(`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state.py" --project-dir "$(pwd)" note --key debug_marker --value "[DEBUG-a4f2]"`). Cleanup in phase 6 is then a
single grep, and untagged instrumentation is what survives into main.

**Performance regressions take a different branch.** Logs mislead on
timing. Establish a baseline measurement first (a timing harness, a
profiler, a query plan), then bisect against it. Measure first, theorise
second.

## Phase 5 — confirm the cause and name the seam

Confirm the surviving hypothesis before calling it the root cause. The
phase 4 evidence has to show the prediction the hypothesis made in phase 3:
the one-variable change made the bug disappear, or worse, exactly as
stated. Re-run the red command with that change in place and show its
redacted output. A hypothesis whose prediction did not land is not
confirmed — go back to phase 3 or 4 rather than forward.

Then name two things the fix's plan will need. Neither is code.

**The regression seam.** A correct seam exercises the real bug pattern as
it occurs at the call site. A seam too shallow to reproduce the conditions
— a single-caller test where the bug needs several, a unit test that cannot
replicate the chain that triggered it — produces a green test and false
confidence. The seam vocabulary and the rules for choosing one are in
`${CLAUDE_PLUGIN_ROOT}/skills/testing/SKILL.md`; read it, name the seam by
path or public boundary, and do not dispatch e2e-test — the test is written
when the fix is implemented, not here.

**No correct seam exists? That is a finding.** The architecture is
preventing this bug from being locked down, which is a design question for
the architect inside the fix's plan, not a reason to invent a test that
cannot fail. Record it as carried-forward debt in step 7.

**The fix scope.** The files and functions the confirmed hypothesis
implicates — a pointer for the plan, not a diff. Name where the fix lives;
do not describe the change, and do not dispatch anyone to make it.

Record all three so a later `/cfm:plan`, even in a fresh session, inherits
them from the ledger:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state.py" --project-dir "$(pwd)" note --key root_cause --value "<the hypothesis, and the evidence that confirmed it>"
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state.py" --project-dir "$(pwd)" note --key regression_seam --value "<the seam, or: none — <why>>"
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state.py" --project-dir "$(pwd)" note --key fix_scope --value "<files and functions implicated>"
```

## Phase 6 — cleanup gate

Every item verified before this is done:

- [ ] Instrumentation is gone: `grep -rn '\[DEBUG-' .` returns nothing for
      the marker recorded in phase 4. A non-empty result fails this gate —
      dispatch the coder to remove the remainder and check again. Reverting
      the probes this diagnosis added is not a fix; it is the only code
      change the orchestrator dispatches after phase 4.
- [ ] The red-command loop is kept as the regression seed (its invocation
      is already in the `red_command` note), or deleted because the user
      asked. Any other throwaway harness is deleted, or moved to a
      clearly-named debug location the user approved keeping.
- [ ] The bug still reproduces: re-run the red command once after cleanup
      and show its redacted output going red. Green here means a fix landed
      by accident — find it and have the coder revert it, because the fix
      belongs to a planned phase, not to this diagnosis.
- [ ] The surviving hypothesis and its evidence are in the `root_cause`
      note, so the next person to touch this code inherits the reasoning.

## Step 7 — the findings gate (always stop here)

1. Render the diagnosis report:

   **Diagnosis — `<phase id>`** and a status line, then:

   a. **Symptom** — the user's words from step 2.

   b. **Red command** — the invocation and its redacted output.

   c. **Minimised repro** — the smallest scenario that still goes red.

   d. **Root cause** — the hypothesis that survived, and the evidence from
      phases 4 and 5 that confirmed it.

   e. **Ruled out** — each other hypothesis and what disproved it.

   f. **Regression seam** — the seam the fix's test should observe from,
      or the recorded absence of a correct one.

   g. **Fix scope** — the files and functions implicated. Where, not what.

   h. **Token usage chart** — the output of `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state.py" --project-dir "$(pwd)" report`, pasted
      verbatim (fenced block included) after item 3 below has marked the phase complete.

   i. **Your next step** — the question in item 5.

2. Update `PROGRESS.md` (config `progress_log`) with a newest-first entry
   whose **Carried forward** section names every deferred obligation: a
   missing seam, a hypothesis left untested, a harness kept on purpose.
3. `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state.py" --project-dir "$(pwd)" carry "<obligation>" ...` for every
   item in the Carried-forward section, then
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state.py" --project-dir "$(pwd)" complete --gates plan-fix`.
   A diagnosis leaves no diff, so the implementation gates (`verify_full`,
   git) do not apply; the one pending gate is the user's decision below.
4. Sync the tracker if one is connected, per the adapter contract in
   `${CLAUDE_PLUGIN_ROOT}/CONNECTORS.md`, piping outbound text through
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/redact.py"` and sending only the
   pipe's output. Failure is a one-line warning, never a blocker.
5. Ask, with the `AskUserQuestion` tool, exactly one question — "Plan a
   fix for these findings now?" — with two options:
   - **Yes, plan the fix** → invoke the `cfm:plan` skill through the
     `Skill` tool with the argument `fix-<slug>`. Plan reads the
     `diagnose-<slug>` notes from the ledger and runs its own plan-mode
     approval gate; nothing is pre-approved here.
   - **Not now** → print the command for later, `/cfm:plan fix-<slug>`,
     and STOP.

   Findings are the deliverable. Never apply the fix, never dispatch one,
   never start `/cfm:implement-phase` — whether and when to fix is the
   user's call.

## Hard limits

- Never applies a fix, and never dispatches the coder, e2e-test, or any
  other agent to apply one, write a regression test, or change product
  behaviour. The only code this skill causes to exist is the loop and the
  probes, and the probes are reverted before the report.
- The orchestrator dispatches every loop and probe — it writes no code
  itself; in cfm mode the guard refuses it ("is product code").
- Phase order holds: a hypothesis without a red command, or a root cause
  without a confirmed prediction, means going back rather than forward.
- Never starts `/cfm:implement-phase`. The only skill it may invoke is
  `cfm:plan`, and only after the user answers yes in step 7.
- Never run `verify_full` — the full suite is the human's command, and the
  loop is one scoped command by design.
- Never mutate git; never read `secret_globs` files, even to diagnose them.
- One writer: only this orchestrator writes `PROGRESS.md`, and the state
  file is written only through `scripts/state.py` — never by hand.
- Every command, output, and artifact shown passes through
  `scripts/redact.py` first.
