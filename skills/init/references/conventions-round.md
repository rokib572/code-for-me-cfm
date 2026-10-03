# The conventions round

Runs inside `/cfm:init` (SKILL.md step 4), on every scenario. Input: the
settled stack, the layer list, and the enabled roster. Output: the
project's coding conventions as numbered rules appended to `rules_file`,
plus a `## Feature structure` section in the CLAUDE.md files. No config
value is written here — conventions live in the rules file, which
`coder`, `code-reviewer`, and `code-styling` already read.

## Entry point per scenario

- **Greenfield** — after `scaffold.py` has rendered the R1/R2 seed and
  BEFORE the coder is dispatched for the stack skeleton, so the skeleton
  is built to the conventions (`scaffold.md` step 1.5).
- **Existing / scaffolded** — after the step-3 config write creates the
  seed. PRE-FILL every option from the deep scan's convention-conformance
  verdict: say what the code already does and let the user confirm or
  correct. Never ask blind about a convention the repo demonstrates.
- **Adoption** — ask ONLY about categories the adopted rules file does not
  already cover. Never restate an adopted rule as a new one.

## The category sweep

One AskUserQuestion per category, `multiSelect: true`, options phrased as
concrete convention statements the user ticks. The auto-provided Other
option is the free-text escape hatch. Every category may be answered
"none — no rule here"; a category with no selection produces no rule.
Skip a category outright when it cannot apply to the stack.

1. **Symbol naming** — casing per symbol kind (variables, functions,
   types, constants); whether abbreviations are banned (if so, capture the
   banned→required pairs); singular/plural by cardinality; verb-prefixed
   function names.
2. **File & directory naming** — casing per file kind; test file naming;
   whether barrel/index files are used and what they may re-export.
3. **Feature folder structure** — the file layout INSIDE a `feature_roots`
   directory; one export per file vs grouped modules; canonical filenames
   for the common operations; where shared helpers go and the extraction
   threshold (N occurrences before extracting).
4. **Layer boundaries & imports** — are cross-feature imports allowed;
   dependency direction between layers; libraries quarantined to a single
   layer; import ordering.
5. **Function & module design** — declaration style; single
   responsibility (may a flag change a function's behavior, or must it
   split); explicit return types.
6. **Type safety & data contracts** — the escape-hatch type policy; DTO /
   payload type-name templates; validation library and where validation
   happens; when types move to their own module; single source of truth
   for cross-layer enums and contracts.
7. **Errors, constants & comments** — error class and wrapping pattern;
   whether inline literals are allowed or must be named constants; comment
   policy (none-by-default vs documented-everywhere).
8. **Testing conventions** — test location per layer, framework, required
   coverage, fixture and seed strategy.
9. **Component conventions** — ONLY when a web/frontend/ui/app layer
   exists: container/presentational split, page and component naming
   templates, where data hooks live.

The categories above are the *shape*; the OPTIONS inside each are derived
from the actual stack settled in the architecture round (greenfield) or
detected from the repo (existing) — never a lookup table. A declaration-
style option that names arrow functions is nonsense in a language without
them; derive from the stack or drop the category.

## Assign enforcement

Then ONE confirmation table — rule, proposed enforcement, why — not a
per-rule quiz. The user confirms or edits once. Preference order:

1. `lint(<rule-id>)` — a real linter rule in this stack expresses it AND
   `commands.lint` is configured. Name the concrete rule id.
2. `lint(lint_arch)` — layering and import-boundary rules, only when that
   slot exists (`command-derivation.md` §3 leaves it absent otherwise).
3. `reviewer(code-styling)` — naming and formatting nits.
4. `reviewer(code-reviewer)` — design, structure, and granularity judgment.
5. `reviewer(security-check)` — secret and tenancy rules.

Two hard constraints:

- A `reviewer(<name>)` owner MUST be an enabled agent — doctor check 6
  fails on a missing or disabled one. If the preferred owner is not
  enabled, fall down the list to one that is.
- NEVER invent a lint rule id. If you are not sure the rule exists in this
  stack's linter, assign a reviewer. An honest reviewer beats a fake
  lint — the same principle as never faking a green command.

A `lint(...)` assignment is a CLAIM at this point, not a fact. The proof
phase below turns each one into a measurement or demotes it.

## Prove the lint teeth

A green doctor proves the lint slot RUNS, never that a rule BITES — clean
code passes a linter with zero rules configured just as happily. So every
`lint(...)` assignment is measured here, against a deliberate violation.
The only acceptable proof is a NON-ZERO exit.

Skip this phase entirely when no rule was assigned `lint(...)` or no lint
slot exists. Otherwise run it batched — one dispatch per stage covering
ALL lint-assigned rules at once, never a loop per rule.

The write/run split is forced by the single-owner principle and is not
negotiable: `coder` writes but may run nothing (`owns_commands: []`);
`mechanical-gate` runs the lint slot but has no write tools by design. The
orchestrator sequences them and interprets the verdict.

**Stage 1 — coder writes the violations.** One dispatch. For each
lint-assigned rule, one small file that violates ONLY that rule, at an
unmistakable path inside the layer the rule governs (e.g.
`<layer path>/__cfm_lint_proof_R7.<ext>`), with a header comment naming
the rule number. The brief must forbid touching product code, lint
config, `.gitignore`, or anything else.

**Stage 2 — mechanical-gate runs the lint slot.** One dispatch. It lints
the whole project, so a single run classifies every rule at once: a
fixture named in the output BITES; a fixture absent from it does NOT.
Expect FAIL overall — here a failure is the success condition, and the
orchestrator, not the gate, draws that conclusion.

**Stage 3 — coder wires only the rules that did not bite.** One dispatch,
skipped when stage 2 flagged everything. Add the rule to the project's
existing lint configuration, with a message that CITES the rule number
(`R7: use arrow functions`) so a CI failure points back at the rule. The
brief must forbid weakening, disabling, or reordering any rule already
configured, and forbid editing product code.

**Stage 4 — mechanical-gate re-runs.** Every fixture must now be flagged.

**Stage 5 — coder deletes every fixture.** One dispatch, deletions only.
Do not add a Stage 6 gate run: doctor check 3 executes the lint slot and
requires exit 0, so the doctor run in SKILL.md step 5 is the clean-tree
proof. A fixture left behind turns the doctor red — which is the intended
safety net, not a bug to work around.

**Demote whatever still does not bite.** After stage 4, rewrite the
`**Enforcement:**` of every unflagged rule to its best `reviewer(<name>)`
owner from the preference order above. Tell the user plainly which rules
were demoted and why. Never leave a `lint(...)` claim that failed to
measure — an unproven claim is exactly the fake green this phase exists
to prevent.

The user may decline the wiring at stage 3; that is a normal answer, and
those rules demote the same way. On an existing repo many rules bite at
stage 2 with no wiring at all — the linter already implements them, and
stage 3 has nothing to do for those.

If wiring needs a lint slot that does not exist yet, or needs the existing
one split (a separate rules-lint command alongside an architecture-lint
one), add or amend `commands` in `.cfm-workflow.yml` — init owns config,
so state the change and include it in the config the user approved.

## Output 1 — append to `rules_file`

Continue numbering from the highest existing `## R<n>` heading in the file
(R3 onward after the scaffold seed). Never renumber existing rules; their
numbers are the cross-reference key reviewers and lint messages cite.

Per rule: the heading, one imperative sentence, then ONE of three body
shapes — a banned/required table, a `**Not allowed:**` / `**Required:**`
code pair in the project's actual language, or a responsibility matrix —
then the enforcement line. A rule is a record, not an essay.

    ## R7. Expressive names — no abbreviations

    Variables, parameters, and functions use full words.

    | Banned | Required |
    |--------|----------|
    | `ctx`  | `context` |
    | `req`  | `request` |

    **Enforcement:** reviewer(code-styling)

## Output 2 — feature structure into CLAUDE.md

The category 3 (and 9) answers produce a `## Feature structure` section
holding the concrete directory and file template for a new feature in that
layer. Append it to each layer's CLAUDE.md under `claude_md.layout:
router`, or to the root CLAUDE.md under `single`.

`scaffold.py` stamps rendered files as "rendered from .cfm-workflow.yml";
this section is not, so it carries its own marker so provenance stays
honest:

    <!-- authored by the cfm:init conventions round — not rendered from config -->
    ## Feature structure

The rules file holds the enforceable half and points at it, so the
template and the rule can never disagree about who is authoritative:

    ## R9. Feature file layout

    New feature files follow the layout in `<layer path>/CLAUDE.md` §
    Feature structure.

    **Enforcement:** reviewer(code-reviewer)

## Re-run (from `/cfm:configure`, conventions domain)

Conventions change as a project learns. `/cfm:configure` routes here to
revise them; that path is a TARGETED edit, never the init sweep again.

- Ask which category — or which rule number — the user wants to change,
  and touch only that. Configure applies one domain change per approval;
  re-asking all nine categories is a bug, not thoroughness.
- **Numbering is append-only.** Rule numbers are the cross-reference key
  that reviewers, lint messages, and progress entries cite. Editing a rule
  keeps its number. Adding takes the next free one. Removing deletes the
  block and RETIRES the number — a later rule never backfills the gap.
- **The CLAUDE.md `## Feature structure` section already exists** on a
  re-run. Replace it in place; never append a second one. Under `router`
  layout, change only the layers the user is actually revising.
- Enforcement is re-checkable too: moving a rule from a reviewer to a real
  lint rule (or back, when an owner is disabled) is a valid change on its
  own, with no edit to the rule's text. Moving TO `lint(...)` runs the
  proof phase for that one rule — the claim is measured on a re-run
  exactly as it is at init, and demoted if it does not bite.
- Removing a rule outright is fine. Keeping one with no enforcement is
  not — that is a hard invariant, and configure declines it.

Configure shows the markdown diff, applies on approval, and auto-runs the
doctor; check 6 polices the result exactly as it does at init.

## Exit criteria

Every ticked convention is a rule with a declared enforcement whose owner
is live; every layer that takes feature code has a `## Feature structure`
section; no category was asked whose answer changed nothing. Then return
to SKILL.md step 5 (validate) — the doctor policies the result.

Tell the user once, in init's closing summary, that `/cfm:configure` →
conventions is how they revise any of this later.
