---
name: connect-tracker
description: Connects a project tracker on demand — Jira, ClickUp, Trello, or any tracker the user has connected themselves — recognising its live tools, asking the sync flags, and writing tracker config as a diff applied only on approval. Use when the user wants plans and tasks mirrored to a tracker, names one to integrate, or wants the current one disconnected.
compatibility: Requires Claude Code (terminal, IDE extension, or Desktop Code tab)
---

# cfm:connect-tracker

The canonical tracker connection flow: let the user pick a tracker, check
whether its tools are live in this session, hand them the connection step
when they are not, ask the sync flags, then write config with the
diff → approval → doctor discipline. cfm never registers or configures
an MCP server: Jira, ClickUp, and Trello connect through the connectors
Claude Code already offers, and anything else through the user's own
connector via the Custom option. This skill owns the flow — `cfm:plan` (greenfield, once, after the first plan) and
`cfm:configure` (tracker domain) route here instead of duplicating it.
The markdown plans and tasks stay canonical either way — a tracker adds
visibility, never capability.

## Step 0 — environment gate

Run `test "$CLAUDECODE" = "1"` with the Bash tool. If it fails, STOP and
show exactly: "cfm runs only in Claude Code (terminal, IDE, or the
Desktop Code tab). Your project config and brief are untouched — open
this repo in Claude Code to continue."

## Step 1 — load config

Load the effective config per
`${CLAUDE_PLUGIN_ROOT}/references/config.md` ("Load and validate the
config").

- No config → tell the user to run `/cfm:init` first and STOP.
- Validation errors → send them to `/cfm:doctor` and STOP (never write
  tracker config on a broken config).

## Step 2 — already connected?

If `tracker.provider` is set: show the current provider and the four
`tracker.sync` flags, then ask (AskUserQuestion) whether to **change** the
connection (continue to step 3), **disconnect** (a `provider: null` diff —
go straight to step 6; the sync flags keep their values, they are inert
without a provider), or **leave it as is** (STOP). A disconnect never
touches the connector — that stays for the user to remove in `/mcp` if
they want; say so in one line.

## Step 3 — pick the tracker

First, take stock of what is already live: scan the MCP tools available in
THIS session for tracker-shaped ones (names/descriptions that name a
tracker product or expose create/update/comment task operations). This is
context for the menu, not a gate — an empty result is normal and stops
nothing.

Then ask (AskUserQuestion), always these four options, in this order:

1. **Jira** — Atlassian Rovo MCP server.
2. **ClickUp** — ClickUp's hosted MCP server.
3. **Trello Board** — Trello's own MCP server.
4. **Custom** — any other tracker the user has connected, or will connect, themselves.

Mark an option "already connected" in its description when step 3's scan
found its tools — the user can still pick it; the flow just skips the
hand-off. Keep descriptions to one line.

## Step 4 — connect the tracker

**The user connects; cfm recognises.** cfm registers no MCP server, runs
no `mcp` command, and never asks for an endpoint, a transport, or a
credential. Read
`${CLAUDE_PLUGIN_ROOT}/skills/connect-tracker/references/mcp-servers.md`
— it holds the built-in provider names, their tool-name prefixes, the
hand-off text, and the Custom rules. Follow it; never describe a
connector's configuration from memory.

For **Jira / ClickUp / Trello**:

1. Tools with the provider's prefix are live in this session (a claude.ai
   connector counts) → already connected; say so in one line.
2. Otherwise hand off the connection in one short block, per the
   reference: add the provider's connector from the Anthropic Directory
   through `/mcp` (or the claude.ai connectors settings), complete the
   browser sign-in, and expect the tools after a session restart.

For **Custom**: ask only for the provider name, derive and confirm the
slug, and scan for its tools. Absent → the same hand-off, naming their
own connector. A pasted URL, command, or setup value is not acted on and
not echoed back; point them to `/mcp`.

Report the outcome in at most two lines: connected, or how to connect.
Then continue to step 5 regardless; a provider with no live tools is
recorded and degrades to the offline warning, it never blocks.

## Step 5 — sync flags

One AskUserQuestion, `multiSelect: true`, all four options recommended as
the default selection:

- `create_tasks` — every plan phase becomes a tracker task, and plan
  amendments update those tasks (outbound);
- `transition_status` — phase boundaries move task status (outbound);
- `post_notes` — phase-gate notes become comments (outbound);
- `fetch_tasks` — cfm may READ tasks back out of the tracker: implement a
  ticket by key, pick one from the open list, and check a bound task for
  divergence before implementing. The only inbound flag; turning it off
  makes the integration write-only.

## Step 6 — diff, apply, doctor, bookkeeping

1. Show the exact change as a unified YAML diff — `tracker.provider` plus
   the `tracker.sync` flags (or `provider: null` for a disconnect) — with
   2 lines of context and one sentence per behavioral consequence. The
   provider value is the provider KEY, not the MCP server name: `jira`,
   `clickup`, `trello`, or the custom slug confirmed in step 4.
2. Apply ONLY on explicit approval. Edit `.cfm-workflow.yml` surgically —
   never rewrite untouched sections, never reformat, keep the user's
   comments.
3. Validate: re-run the load per `${CLAUDE_PLUGIN_ROOT}/references/config.md`
   ("Validate after a write") — if it errors on what you wrote, fix your
   edit (not the user's other config) until clean.
3b. **Auto-approve the tracker's tools** so sync does not prompt per call:
   follow the allow procedure ("Allows — exact MCP tool names only") in
   `${CLAUDE_PLUGIN_ROOT}/references/settings-denies.md`.

   Give it one EXACT tool name per tool you OBSERVED live in this session
   and that the adapter contract actually calls — create, update,
   transition, comment, get, search. Read the names off the live tools
   (claude.ai connector tools arrive as `mcp__claude_ai_<server>__<tool>`);
   never guess the spelling, and never a wildcard — the procedure refuses
   `mcp__<server>__*`, because a server glob approves every tool the server
   exposes (the Atlassian server carries Confluence and Bitbucket writes
   too). If the tools are not live yet (auth pending), skip this and
   redo the procedure after `/mcp`.

   This edits `.claude/settings.json`, a repo file, so show the added
   `permissions.allow` entries as part of step 1's diff and write them on
   the same approval. Skip this on a disconnect: leave the rules in place
   (they are inert without a provider) and say so in one line, or remove
   them by hand if the user asks.
4. Auto-run the doctor: run every check in
   `${CLAUDE_PLUGIN_ROOT}/references/doctor.md` and show the report. A
   change that turns the doctor red gets flagged immediately with the
   offer to revert the diff.
5. **State bookkeeping**: resolve the deferred tracker question in place
   with the `question` operation in
   `${CLAUDE_PLUGIN_ROOT}/references/state.md` — resolve, `asked_by`
   `cfm:plan`, outcome `accepted` on a connect, `declined` on a disconnect
   that leaves no provider — so no cfm command ever auto-asks. The
   operation stops with `error: no deferred question asked_by 'cfm:plan'`
   when no such entry exists (existing repos never recorded one); that is
   fine, move on.
6. **Backfill the plans** (connect only, when `docs/plans/*.md` exist and
   `create_tasks` is on). Every phase of every plan becomes a task — this
   is the default outcome of connecting, not an optional extra.
   1. Read the plans and count: "N plans, M phases → M tasks (P already
      bound, skipped)". Show the per-plan breakdown and confirm ONCE —
      it is a bulk write to an external service. The user may narrow it
      to specific plans; "not now" is also an answer, and then the next
      `/cfm:plan` sync picks the work up.
   2. Run the **create_tasks (backfill)** operation in
      `${CLAUDE_PLUGIN_ROOT}/CONNECTORS.md` Part 2 exactly — container
      per plan, then one task per phase, binding line written back into
      the plan file after each create, phases already bound skipped.
   3. Run every outbound payload through the redaction pass in
      `${CLAUDE_PLUGIN_ROOT}/references/redaction.md` (the single
      redaction source — never reimplement or inline its patterns) and
      send only the pass's OUTPUT. If the pass cannot be completed, post
      nothing for that payload. When unsure whether a string is a
      credential, drop it and note `[redacted]`.
   4. Report the tally per plan. Per-task failures are lines in that
      tally, not stops — leave those phases unbound so the next sync
      retries them. A wholesale failure (auth not completed, connector
      down) is one warning line: the markdown files remain canonical and
      the backfill can be re-run any time by re-running this command.
   5. After ANY sync attempt, record it in one `tracker` operation
      (`${CLAUDE_PLUGIN_ROOT}/references/state.md`): provider
      `<provider>`, last_sync `"ok"`, and one bind
      `<plan path>#<phase id>` → `<provider>:<key>` per binding written
      (last_sync `"failed: <reason>"` when it failed).

   If auth from step 4 is not complete yet, the tools are not live — say
   so plainly, skip the backfill, and tell the user to re-run
   `/cfm:connect-tracker` after `/mcp`; it will pick up exactly the
   unbound phases.

## Hard limits

- Never touch git; never write product files.
- The only writes: the approved config diff, the `permissions.allow` entries of step 6.3b,
  the ledger through the operations in `references/state.md` only (the
  deferred-question outcome and the tracker fields), the binding lines
  added to plan files by step 6's backfill, and — only after approval —
  tracker calls through the redaction pass. Nothing else.
- Never add an allow rule beyond what the allow procedure in
  `references/settings-denies.md` accepts, and never a wildcard: no
  `mcp__<server>__*`, no `Bash(claude mcp add *)`, no allow the config
  does not derive. Each trades a permission layer for convenience and is
  never worth it.
- The backfill adds binding lines to plans; it never edits a plan's
  phases, goals, or criteria. Plan content changes belong to `/cfm:plan`.
- Never ask for, accept, echo, or store a tracker credential, endpoint,
  or setup value. The built-in providers are OAuth-only through their
  connectors; a pasted value is dropped, not redacted.
- Never run an `mcp` command of any kind — registering, listing,
  removing, or signing in to a server is the user's own step through
  `/mcp`. Telling the user how to connect is this skill's job, not a
  fallback.
