---
name: domain-modeling
description: Builds and sharpens the project's shared language — challenges a term against the glossary, collapses fuzzy words to one canonical name, stress-tests relationships with concrete scenarios, and records terms as they settle. Use when naming a concept, when two words seem to mean the same thing, when editing the glossary, or when deciding whether a decision deserves an ADR.
compatibility: Requires Claude Code (terminal, IDE extension, or Desktop Code tab)
---

# cfm:domain-modeling

Reference, not a workflow. There is no environment gate and nothing to run
here — read it, apply it, and carry on with whatever dispatched you.

The glossary lives at the config's `context_file` (default `CONTEXT.md`).
Read it before naming anything.

## Why cfm needs this more than a single session does

Every cfm agent starts cold. The coder, the reviewer, the test agent and
the architect each receive a brief and no conversation history, so each one
re-derives the project's jargon from `project_context` prose — and derives
it slightly differently. That drift shows up as three names for one
concept across three layers, and as review findings that argue about words
rather than behavior.

A resolved glossary fixes this at the source: briefs get shorter because
the term carries the meaning, and findings get sharper because every agent
reaches for the same word.

## Consuming versus building

Reading the glossary to match its vocabulary is a habit any agent has, and
it needs no skill. **This file is for changing the model**: when a term is
contested, fuzzy, missing, or wrong.

## The four moves

**Challenge against the glossary.** A term is being used in a way the
glossary does not define, or contradicts. Say so immediately: "The glossary
defines *cancellation* as voiding the whole order, but this reads like a
partial refund. Which is it?" A silent redefinition is how a glossary
rots.

**Sharpen fuzzy language.** A word is carrying two meanings. Propose one
canonical term for each: "*account* here is doing two jobs — the paying
**Customer** and the login **User**. They have different lifecycles, so
they need different names."

**Stress-test with concrete scenarios.** When a relationship is asserted,
invent the specific case that probes its edge. "A Subscription belongs to
one Customer" survives until you ask what happens when a company's billing
contact leaves. Scenarios force precision that abstract definitions let
people skip.

**Cross-reference with the code.** A claim about how something works is
checkable. When the code disagrees, surface the contradiction rather than
picking a side: "The code cancels whole Orders only, but the plan assumes
partial cancellation. Which is right?" One of them is a bug and the other
is a stale mental model, and finding out which is the point.

## Recording a term

Update the glossary the moment a term resolves, in the same turn. Batching
loses them.

```markdown
**Order**:
A customer's committed request for a set of Line Items at agreed prices.
Committed is the load-bearing word: before commitment it is a Cart.
_Avoid_: purchase, transaction, basket
```

The `_Avoid_` line is what stops a retired synonym from drifting back in.

Keep the glossary a glossary. Implementation detail, specs, schemas, and
scratch notes belong in the plan, the rules file, or `PROGRESS.md`. A
glossary that accumulates implementation goes stale on the next refactor,
and a stale glossary is worse than none, because agents trust it.

## Relationship to cfm's other artifacts

| Artifact | Holds |
|---|---|
| `context_file` (glossary) | What things are called and what they mean |
| `rules_file` | How code must be written, each rule with an enforcement owner |
| `docs/adr/` | Why a hard-to-reverse decision went the way it did |
| `docs/plans/` | What is being built, in phases |

A concept coined in an ADR earns a glossary entry, so later phases can name
it without reading the ADR.

## When a decision deserves an ADR

Offer one only when all three hold:

1. **Hard to reverse** — changing your mind later has real cost.
2. **Surprising without context** — a future reader will ask "why this
   way?"
3. **The result of a real trade-off** — there were genuine alternatives and
   one was chosen for stated reasons.

Miss any one and skip it. An ADR directory that records every decision
records nothing, because nobody reads it. cfm's ADR shape is
`templates/adr.md`, and the architect agent writes them.
