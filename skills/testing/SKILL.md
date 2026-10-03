---
name: testing
description: The discipline that makes a test worth keeping — seams, what a good test asserts, the three anti-patterns, and the red-before-green loop. Use when writing tests, choosing the seam a test observes from, or sharpening a plan's test expectations.
compatibility: Requires Claude Code (terminal, IDE extension, or Desktop Code tab)
---

# cfm:testing

Reference, not a workflow. There is no environment gate and nothing to run
here — read it, apply it, and carry on with whatever dispatched you.

cfm already enforces where a test may *run*: the e2e-test agent fills
`commands.test_scoped` with its own explicit file paths and widens to
nothing. That is scope hygiene, and it says nothing about whether the test
is worth keeping. This file is the other half.

## Seams

A **seam** is the public boundary a test observes behavior from without
reaching inside. Tests live at seams.

In cfm the seam is a **declared, approved artifact**, not a judgment made
mid-dispatch:

1. `/cfm:plan` names the seams per phase, alongside its test expectations.
2. The plan-mode approval gate is where the human confirms them.
3. `/cfm:implement-phase` copies them verbatim into the e2e-test dispatch
   brief.

Test at the seams the brief names. If the briefed seam turns out to be the
wrong place to observe the behavior from — the bug needs multiple callers
and the seam sees one, or the assertion can only be made by reaching past
the interface — that is a **finding to report**, not a seam to invent.
The orchestrator re-dispatches with a corrected seam, and the plan is
amended so the next phase inherits the correction.

Declaring seams up front is how testing effort lands on critical paths and
complex logic instead of spreading evenly over every edge case.

## What a good test asserts

Verify behavior through the public interface. The implementation can change
entirely and the test should not.

A good test reads like a specification: `user can checkout with a valid
cart` names a capability that exists, and it survives refactors because it
never cared about internal structure. Prefer that shape over
`checkoutService calls validateCart then chargeCard`.

Expected values come from an **independent source of truth** — a known-good
literal, a worked example from the plan, the acceptance criteria — so the
assertion can disagree with the code.

## Three anti-patterns

**Implementation-coupled.** Mocks internal collaborators, exercises private
methods, or verifies through a side channel (querying the database directly
instead of asking the interface). The tell: the test breaks under a
refactor while the behavior is unchanged. Assert through the seam instead.

**Tautological.** The assertion recomputes the expected value the same way
the code does — `expect(add(a, b)).toBe(a + b)`, a snapshot derived by hand
from the same algorithm, a constant asserted equal to itself. It passes by
construction and can never disagree with the code, so it proves nothing.
Bring the expected value from outside the implementation.

**Horizontal slicing.** Writing every test first, then every
implementation. Bulk tests verify *imagined* behavior: they capture the
shape of things rather than what a user can do, they go insensitive to real
changes, and they lock in test structure before the implementation is
understood. Work in **vertical slices**: one test, one minimal
implementation, repeat. Each test is a tracer bullet that responds to what
the last cycle taught you.

## Rules of the loop

- **Red before green.** Write the failing test, watch it fail, then write
  only enough code to pass it. A test that has never been red has never
  been proven to detect anything.
- **One slice at a time.** One seam, one test, one minimal implementation
  per cycle. Write for the behavior in front of you rather than the ones
  you expect next.
- **Refactoring belongs to review.** The red-to-green cycle produces
  working code; the review gates and code-styling shape it. Keeping them
  separate is what stops a refactor from silently rewriting the thing the
  test was about to prove.

## Inside cfm

- A test that fails because the product is wrong is a **finding** the
  e2e-test agent reports with `file:line` and what the test proves. The
  coder fixes product code; the test agent does not.
- Fixtures and seeds use obviously-fake placeholder values, so a leaked
  fixture is never a leaked credential.
- The full suite belongs to the human (`verify_full`). Scoped runs by
  explicit path are the agents' only test command, which is exactly why the
  seam has to be right: a narrow run at a wrong seam is confidently green
  and proves nothing.
- **No correct seam exists** for a behavior worth locking down? Record it
  as carried-forward debt in the phase's PROGRESS.md entry. The
  architecture is preventing the behavior from being tested, and that is a
  design finding, not a reason to write a test that gives false confidence.
