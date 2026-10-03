# cfm:init scenario playbooks

One shared spine everywhere: requirements → architecture decisions → config
→ plan → implement loop. Each scenario just enters the spine differently.

## Greenfield (empty directory)

1. **Brainstorm first, admin never.** If `docs/brief.md` already exists and
   the user confirms it is current, skip to the architecture round.
   Otherwise run `/cfm:brainstorm` (product scope) — it produces the brief
   with zero configuration questions and ends at the "move to development"
   gate. Only continue past this point if the user crosses that gate.
2. **Architecture round.** Follow `architecture-round.md`: ask only the
   stack questions the brief leaves open, and route every answer to its
   home — machine-enforceable choice → config value, rationale → ADR in
   `docs/adr/` (template: `${CLAUDE_PLUGIN_ROOT}/templates/adr.md`), some
   answers produce both.
3. **Command derivation** for the chosen stack (see
   `command-derivation.md`) — proposals only; the doctor will verify them
   against the scaffold.
4. **Config genesis** (SKILL.md step 3), then ask the claude_md layout
   question (single vs router).
5. **Scaffold via coder.** Never scaffold in the main session. Follow the
   `scaffold.md` playbook: workflow files rendered from config, the
   conventions round (`conventions-round.md`) run against the fresh rules
   seed so the skeleton is built to the conventions, then the product
   skeleton dispatched to a coder subagent with the stack decisions, the
   layer list, the typed config module requirement (env access only
   through one validated module, `.env.example` with names only), and
   `.gitignore` seeded with the secret glob family. Orchestration-only
   applies from minute zero.
6. Doctor must be fully green on the empty skeleton — every configured
   command running against zero product code — before init ends.

## Existing project (mature repo)

1. **Deep scan.** Read the manifests and CI files the scan listed, plus the
   top-level directory structure. Build a picture of: layers, build/test
   toolchain, conventions (naming, module layout), and anything unusual.
   If the scan's `doc_candidates` lists anything (e.g. `docs/STATUS.md`,
   `coding-rules.md`), those are candidates for `progress_log` and
   `rules_file` — map them into config via the step-2 existing-ledgers
   question, never by assuming the cfm defaults.
2. **Present the as-built architecture** in ~10 lines and ask the user to
   confirm or correct. Their corrections are facts; your scan is a draft.
3. **Convention conformance verdict**: note where the repo deviates from
   its own dominant conventions, plus up to three improvement suggestions.
   Suggestions are informational — do not act on them. The dominant
   conventions themselves are NOT informational: they PRE-FILL the
   conventions round's options in step 6, so record them (naming per
   symbol and file kind, feature layout, import boundaries, declaration
   style, test layout) as you find them.
4. **Command derivation from evidence** (see `command-derivation.md`):
   whatever CI runs IS `verify_full`; manifest scripts beat proposals.
5. Config genesis. Layers come from the real directory structure; propose
   `feature_roots` from where feature code demonstrably lives.
6. **Conventions round** (`conventions-round.md`), every option pre-filled
   from step 3's dominant conventions — the user confirms or corrects what
   the code already does, and is never asked blind about a convention the
   repo demonstrates.
7. **Closing summary**: mention `/cfm:connect-tracker` once — it connects
   a project tracker whenever the user wants plans and tasks mirrored.
   Existing repos are never auto-asked the tracker question, so do NOT
   record a deferred tracker question here.

## Scaffolded repo (skeleton, no real features)

1. Run the existing-project deep scan (abbreviated — there is less to read).
2. **Reconcile scaffold vs intent**: ask what the project is meant to
   become (or route to `/cfm:brainstorm` if the user has no brief yet).
   Compare: does the scaffold's stack and layout serve that brief? Surface
   every mismatch BEFORE config genesis and let the user decide: keep,
   change, or note as debt in the progress log later.
3. Command derivation from evidence where it exists, proposals where the
   scaffold is silent.
4. Config genesis as normal.
5. **Conventions round** (`conventions-round.md`), abbreviated: pre-fill
   from whatever conventions the scaffold already demonstrates, and ask
   fresh wherever it is silent.
6. **Closing summary**: mention `/cfm:connect-tracker` once for on-demand
   tracker integration — the scaffolded path never records a deferred
   tracker question.

## Adoption (existing .claude/ setup)

Never clobber. The user's current setup keeps working until they approve
the migration.

1. Read everything the scan found: CLAUDE.md files, `.claude/agents/*.md`,
   `.claude/commands/*.md`, `.claude/skills/*/SKILL.md`,
   `.claude/rules/*.md`, `.claude/settings*.json`.
2. **Build the absorption map** — for each artifact, where its content
   lands in cfm config:
   - project descriptions / context blurbs → one merged `project_context`
     (flag contradictions between files to the user — stale copies are
     exactly the drift cfm cures),
   - agent files → matching roster entries (custom agents become custom
     roster entries with their tools and models preserved),
   - command lists / verification commands → command slots,
   - rules files → `rules_file`. Rules may live outside `.claude/` too
     (e.g. `coding-rules.md` — the scan's `doc_candidates.rules` lists
     them). When adopting a rules file that is NOT in the doctor's format
     (`## R<n>. <title>` headings + an `**Enforcement:**` line per rule),
     offer two exits and let the user pick:
     - (a) keep the file as `rules_file` and reformat it in place into
       `## R<n>.` + `**Enforcement:**` blocks — content preserved, only
       WITH the user's approval; propose an enforcement owner per rule,
       and flag toothless rules for the user to assign an owner;
     - (b) leave the file untouched and seed a fresh cfm rules file that
       references it.
     Say plainly: the doctor's check 6 will FAIL on an unformatted
     adopted file, so option (b) — or reformatting — is required for a
     green doctor. The choice must be informed,
   - settings deny globs → compare with what cfm will generate; keep the
     union.
3. Present the absorption map as a table (source file → destination →
   kept/changed/needs-decision) and resolve every needs-decision with the
   user.
4. Config genesis from the approved map. Leave every original file in
   place; recommend the user archive them only after a few green phases.
5. **Conventions round** (`conventions-round.md`) as a GAP FILL only: the
   adopted rules are already the project's conventions, so ask only about
   categories the adopted file does not cover, and never restate an
   adopted rule as a new one. If the adopted file covers everything, say
   so and skip the round.
6. In the closing summary, mention `/cfm:connect-tracker` once for
   on-demand tracker integration — adoption never records a deferred
   tracker question.
