# The architecture round

Runs inside `/cfm:init` for greenfield projects after the user crosses the
"move to development" gate (and, abbreviated, when a scaffolded repo's
reconciliation surfaces stack decisions still open). Input: the approved
`docs/brief.md`. Output: config values + ADRs, produced from the same
answers in the same pass — so config, templates, and rationale can never
diverge.

## Question areas

Ask conversationally, one at a time, and ONLY where the brief doesn't
already imply the answer. Stop as soon as layers and command slots are
derivable.

1. **Language & runtime** — and why it fits the team, not just the product.
2. **Framework(s)** — per layer if the product implies more than one.
3. **Persistence** — database/storage, and whether migrations exist as a
   concept (absent → no migrate slots).
4. **Package manager & repo layout** — single package vs monorepo; this
   plus the framework largely determines `layers` and `feature_roots`.
5. **API style** — REST/GraphQL/RPC/none; affects layer boundaries.
6. **Auth & tenancy** — if the brief implies multiple customers' data in
   one system, ask for the tenancy scope field → `tenancy.scope_field`
   (security-check audits it every phase).
7. **Testing approach** — the runner and what "scoped" means here.
8. **Deploy target** — only if it constrains the stack; otherwise defer.

## Route every answer

For EACH answer decide its destination — most have one, some have both:

- **Machine-enforceable choice → config value.** Package manager and test
  runner → command slots (see `command-derivation.md`); repo layout →
  `layers` + `feature_roots`; migrations concept → migrate slots present
  or absent; tenancy field → `tenancy.scope_field`.
- **Rationale → an ADR** (see below). Anything a future contributor would
  ask "why did they pick this?" about: language, framework, database,
  API style, auth model.
- **Both** is common: "Postgres via Drizzle" writes migrate slots into
  config AND an ADR explaining why Postgres.

Do NOT write coding rules here. Layer boundaries, naming, and structure
are elicited by `conventions-round.md` (SKILL.md step 4), which owns the
rules file. This round's only rules-adjacent job is the `lint_arch` slot:
propose the stack's architecture-lint tool; if the ecosystem has none,
leave the slot absent and let the conventions round assign the layering
rule to a named reviewer instead.

## Writing ADRs

- Location: `docs/adr/NNNN-<kebab-slug>.md`, numbered from `0001` in
  decision order.
- Template: `${CLAUDE_PLUGIN_ROOT}/templates/adr.md`. Keep each under ~20
  lines — an ADR is a record, not an essay.
- Write ADRs in the same pass as the config values they justify, before
  scaffold dispatch. Show the user the list of ADR titles for approval;
  show full text only if they ask.
- One decision per ADR. "We chose the T3 stack" is several decisions.

## Exit criteria

The round is done when: every MVP feature in the brief maps onto a layer,
every command slot is filled or deliberately absent, each significant
choice has an ADR, and no question was asked whose answer changed nothing.
Then return to SKILL.md step 3 (config genesis).
