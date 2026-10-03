---
name: brainstorm
description: Turns a raw idea into a written brief through guided ideation — docs/brief.md for a product, a feature brief on an existing repo — asking zero configuration or setup questions. Use when the user has an idea to think through or scope, before any code or config exists.
compatibility: Requires Claude Code (terminal, IDE extension, or Desktop Code tab)
---

# cfm:brainstorm

Turn an idea into a written brief. This skill is thinking, not setup:
stopping after it costs the user nothing.

## Step 0 — environment gate

Run: `bash "${CLAUDE_PLUGIN_ROOT}/scripts/require-claude-code.sh"`
If it exits non-zero, STOP and show its stderr verbatim.

## The config-free contract

Ask ZERO administrative questions in this skill. No stack, no tooling, no
git, no agents, no models, no trackers, no file layout. If the user raises
one ("should I use Postgres?"), note it under **Open questions** as an
architecture-round item and steer back to the product. Configuration
happens later, in `/cfm:init`, only if the user chooses to move to
development.

## Step 1 — pick the scope

- **Product scope**: empty or nearly-empty directory, no `docs/brief.md`,
  or the user is describing a whole product.
- **Feature scope**: an existing project (code or `.cfm-workflow.yml`
  present) and the user is describing an addition to it.
- Ambiguous → ask which one, in one sentence.

## Step 2 — elicit

One question at a time; build each question on the previous answer. Cover,
in whatever order the conversation flows:

1. **Problem** — what hurts today, for whom, how they cope now.
2. **Users/personas** — who touches this; primary vs secondary.
3. **Core value** — the one thing that must work for this to matter.
4. **MVP features** — push hard for less: for every feature ask what breaks
   if it ships without it. Everything that survives gets a one-line "why".
5. **Non-goals** — name explicitly what this will NOT do; deferred ideas
   land here, not in the MVP.
6. **Open questions** — anything unresolved stays a question in the brief;
   do not force answers the user doesn't have.

Challenge gently: point out scope creep, contradictions with earlier
answers, and features with no persona attached. You are a thinking partner,
not a stenographer.

For feature scope, additionally read enough of the existing project (brief,
progress log, top-level structure) to ask informed questions — but keep the
config-free contract: read for context, never for setup.

## Step 3 — write the brief

Draft, show the full text, iterate until the user approves, then write:

- **Product scope** → `docs/brief.md`:
  problem · personas · MVP features (with whys) · non-goals · open
  product questions.
- **Feature scope** → `docs/briefs/<feature-slug>.md` (kebab-case slug):
  what & why · fit with the product brief · acceptance criteria ·
  non-goals · open questions.

Never overwrite an existing brief without showing a diff and getting
explicit approval.

## Step 4 — the gate (and nothing after it)

- **Product scope**: ask exactly one closing question — "Move to
  development?" If yes, hand off to `/cfm:init` (it runs the architecture
  round and config genesis). If no or not yet, stop warmly: the brief is
  done and nothing else was created.
- **Feature scope**: offer `/cfm:create-task` to turn the brief into a
  tracked task, or `/cfm:plan` when the feature is big enough to need
  phases.

## Hard limits

- No files created other than the brief (and its `docs/` directories).
- No config, no scaffold, no git, no ADRs — those belong to `/cfm:init`.
