---
name: simplicity
description: The discipline that keeps a diff small — reuse before writing, stdlib and native platform before dependencies, one line before fifty, and the carve-outs where simplifying is wrong. Use when implementing a feature, choosing whether to add a dependency or an abstraction, reviewing for over-engineering, or deciding how much code a requirement actually needs.
compatibility: Requires Claude Code (terminal, IDE extension, or Desktop Code tab)
---

# cfm:simplicity

Reference, not a workflow. There is no environment gate and nothing to run
here — read it, apply it, and carry on with whatever dispatched you.

The best code is the code never written. Second best is the code that was
already written and you found it.

cfm's dispatch model makes over-building the default failure. Every coder
arrives cold, holds no memory of the codebase, and is handed a brief that
describes work to do. Absent a reason not to, it builds — including things
the repo already has three files over.

## The ladder

Climb it in order and stop at the first rung that holds.

1. **Already in this codebase?** A helper, util, type, component, or pattern
   that already lives here — use it. Grep before you write. Re-implementing
   what exists a few files away is the single most common way a cold-started
   agent adds slop, and it is invisible in review because the new code looks
   fine on its own.
2. **Stdlib does it?** Use it.
3. **Native platform feature covers it?** `<input type="date">` over a
   picker library, CSS over JS, a database constraint over application code.
4. **Already-installed dependency solves it?** Use it. A *new* dependency
   has to beat "a few lines of our own", and it rarely does.
5. **Can it be one line?** One line.
6. **Only then:** the minimum code that works.

Two rungs both work? Take the higher one and move on. The ladder is a
reflex, not a research project.

## Rules

- No unrequested abstractions: no interface with one implementation, no
  factory for one product, no config for a value nobody will ever set, no
  layer with one caller.
- No scaffolding "for later". Later can scaffold for itself, and will know
  more than you do now.
- Deletion over addition. Boring over clever — clever is what someone
  decodes at 3am.
- Fewest files. A new file needs a reason beyond "it felt tidy".
- Two options of the same size? Take the one that is correct at the edges.
  Writing less code never means picking the flimsier algorithm.

## Where rung 0 lives

Ponytail's ladder opens with "does this need to exist at all? — skip it."
In cfm that rung belongs to a **different role**, and getting this wrong
breaks the workflow:

- **`/cfm:plan` owns it.** The plan gate is where speculative scope gets cut,
  with the human present to decide. A phase or acceptance criterion that
  exists for an imagined future is named there, before it is approved.
- **The coder reports it.** A dispatched agent works from an approved plan.
  Silently skipping approved scope is a plan-conformance failure, not
  laziness done right. So when a briefed criterion looks speculative, say so
  in your report — "AC-3 looks speculative: nothing calls this path yet" —
  and build it. The orchestrator carries the finding to the user, who can
  amend the plan.

Reporting costs one line. Guessing costs a re-dispatch, or worse, a quiet
gap between the plan and the code.

## Never simplify away

These are not candidates for the ladder, at any rung:

- Input validation at trust boundaries.
- Error handling that prevents data loss.
- Security measures, including the ones that look redundant.
- Accessibility basics — labels, keyboard paths, contrast.
- Anything the user explicitly asked for. They asked; build it. Name the
  smaller alternative once, then stop re-arguing.

## Never lazy about understanding

The ladder shortens the **solution**, never the reading.

Read the task and the code it touches, trace the real flow end to end, and
only then climb. The smallest change in the wrong place is not a lean diff,
it is a second bug wearing efficiency as a disguise — and it is more
dangerous than over-building, because it ships looking disciplined.

A bug fix is the sharpest case: a report names a symptom, and the fix
belongs at the root. Grep every caller of the function you are about to
touch. One guard in the shared function is both the smaller diff *and* the
correct fix; a guard in the one path the ticket named leaves every sibling
caller broken. `skills/diagnose/SKILL.md` holds the full discipline, and its
refusal to name a cause before a red command exists is the same principle.

## Marking a deliberate shortcut

Taking a simplification with a known ceiling is fine, and losing track of it
is not. Mark it where you took it:

```
# cfm-debt: <the ceiling>, <the trigger to revisit>
```

For example: `# cfm-debt: global lock, per-account locks if throughput
matters`. Both halves are load-bearing. A marker naming a ceiling with no
trigger is how "later" quietly becomes "never", and
`scripts/debt_scan.py` flags exactly those.

The marker is for a real corner cut with a known limit — a global lock, an
O(n²) scan over data expected to stay small, a naive heuristic. Code that is
simply short needs no marker; short is the target, not a debt.

## What this is not

Fewer lines is the usual *consequence* of the ladder, never the goal. Three
signs the discipline has been misread:

- Golfed code: dense one-liners nobody can read. Boring beats clever, and a
  clever one-liner is clever.
- A test deleted to shrink a diff. A test at a declared seam is cfm's
  minimum (`skills/testing/SKILL.md`), and it is never bloat.
- An explanation the user asked for, cut for brevity. A requested report or
  walkthrough is the deliverable. The rule is only against *unrequested*
  prose defending a simplification — every paragraph of that is complexity
  smuggled back in as words.
