---
name: connect-tracker
description: Connects a project tracker on demand — Jira, ClickUp, Trello, or a custom MCP server URL — wiring the MCP server, asking the sync flags, and writing tracker config as a diff applied only on approval. Use when the user wants plans and tasks mirrored to a tracker, names one to integrate, or wants the current one disconnected.
compatibility: Requires Claude Code (terminal, IDE extension, or Desktop Code tab)
---

# cfm:connect-tracker

The canonical tracker connection flow: let the user pick a tracker, wire up
its MCP server for them, ask the sync flags, then write config with the
diff → approval → doctor discipline. Jira, ClickUp, and Trello are
one-click — cfm knows their official MCP endpoints and runs the connection
itself; anything else connects by URL through the Custom option. This
skill owns the flow — `cfm:plan` (greenfield, once, after the first plan) and
`cfm:configure` (tracker domain) route here instead of duplicating it.
The markdown plans and tasks stay canonical either way — a tracker adds
visibility, never capability.

## Step 0 — environment gate

Run: `bash "${CLAUDE_PLUGIN_ROOT}/scripts/require-claude-code.sh"`
If it exits non-zero, STOP and show its stderr verbatim.

## Step 1 — load config

Run: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/cfm_config.py" --project-dir "$(pwd)" --json`

- No config → tell the user to run `/cfm:init` first and STOP.
- Validation errors → send them to `/cfm:doctor` and STOP (never write
  tracker config on a broken config).

## Step 2 — already connected?

If `tracker.provider` is set: show the current provider and the four
`tracker.sync` flags, then ask (AskUserQuestion) whether to **change** the
connection (continue to step 3), **disconnect** (a `provider: null` diff —
go straight to step 6; the sync flags keep their values, they are inert
without a provider), or **leave it as is** (STOP). A disconnect never
removes the MCP server — that stays for the user to remove if they want
(`claude mcp remove <name>`); say so in one line.

## Step 3 — pick the tracker

First, take stock of what is already live: scan the MCP tools available in
THIS session for tracker-shaped ones (names/descriptions that name a
tracker product or expose create/update/comment task operations), and run
`claude mcp list` for servers that are configured but not yet
authenticated. This is context for the menu, not a gate — an empty result
is normal and stops nothing.

Then ask (AskUserQuestion), always these four options, in this order:

1. **Jira** — Atlassian Rovo MCP server.
2. **ClickUp** — ClickUp's hosted MCP server.
3. **Trello Board** — Trello's own MCP server.
4. **Custom** — any other tracker, connected by MCP server URL.

Mark an option "already connected" in its description when step 3's scan
found its tools or `claude mcp list` already has its server — the user can
still pick it; the flow just skips the add. Keep descriptions to one line.

## Step 4 — connect the MCP server

**You connect the server. The user only signs in.** Do not print a
`claude mcp add` command for the user to run — running it is this step's
whole job. The one thing that is genuinely theirs is the OAuth browser
round-trip at the end.

Read `${CLAUDE_PLUGIN_ROOT}/skills/connect-tracker/references/mcp-servers.md`
— it holds the built-in endpoints, the add/verify/auth-handoff procedure,
the custom-URL rules (https-only, credential refusal, transport inference),
and the failure path. Follow it; never type an endpoint from memory.

For **Jira / ClickUp / Trello**:

1. Ask the one scope question (local — recommended, nothing written to the
   repo — vs project, which writes `.mcp.json`, vs user).
2. Run the reference's exact command for that provider with the **Bash
   tool**, now. A permission prompt on that call is normal AND intended —
   registering an MCP server is never auto-approved, because a stdio
   server is an arbitrary command. Wait for the user to approve it rather
   than handing the command over.
3. Verify with `claude mcp list`. "Not connected yet" in that output is
   expected before sign-in and is not a failure.

Skip the add — and say why in one line — when the provider's tools are
already live in this session (a claude.ai connector counts) or
`claude mcp get <server-name>` exits 0. Already connected is a success,
not a reason to add a second server.

For **Custom**: ask for the URL in plain conversation, validate it against
the reference's rules, confirm the derived server name, then add it the
same way — with the Bash tool, not as a suggestion.

Report the outcome in at most three lines: what was added (or was already
there), and the OAuth hand-off — `/mcp` in this session to sign in, tools
appear once auth completes. Then continue to step 5 regardless of whether
the add succeeded; a provider with no live tools is recorded and degrades
to the offline warning, it never blocks.

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
3. Validate: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/cfm_config.py" --project-dir "$(pwd)"`
   — if it errors on what you wrote, fix your edit (not the user's other
   config) until clean.
3b. **Auto-approve the tracker's tools** so sync does not prompt per call:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/gen_settings.py" --project-dir "$(pwd)" --write \
     --allow-tool mcp__<server>__<tool> --allow-tool ...
   ```

   Pass `--allow-tool` once per EXACT tool name you OBSERVED live in this
   session and that the adapter contract actually calls — create, update,
   transition, comment, get, search. Read the names off the live tools
   (claude.ai connector tools arrive as `mcp__claude_ai_<server>__<tool>`);
   never guess the spelling, and never a wildcard — the script rejects
   `mcp__<server>__*`, because a server glob approves every tool the server
   exposes (the Atlassian server carries Confluence and Bitbucket writes
   too). If the tools are not live yet (auth pending), skip this and
   re-run the command after `/mcp`.

   This edits `.claude/settings.json`, a repo file, so show the added
   `permissions.allow` entries as part of step 1's diff and write them on
   the same approval. Skip this on a disconnect: leave the rules in place
   (they are inert without a provider) and say so in one line, or remove
   them by hand if the user asks.
4. Auto-run the doctor: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/doctor.py" --project-dir "$(pwd)"`
   and show the report. A change that turns the doctor red gets flagged
   immediately with the offer to revert the diff.
5. **State bookkeeping**: resolve the deferred tracker question in place —
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state.py" --project-dir "$(pwd)" question --resolve --asked-by cfm:plan --outcome accepted` on a
   connect, `--outcome declined` on a disconnect that leaves no provider —
   so no cfm command ever auto-asks. The command exits 1 when no such
   entry exists (existing repos never recorded one); that is fine, move on.
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
   3. Pipe every outbound payload through
      `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/redact.py"` (the single
      redaction source — never reimplement or inline its patterns) and
      send only the pipe's OUTPUT. When unsure whether a string is a
      credential, drop it and note `[redacted]`.
   4. Report the tally per plan. Per-task failures are lines in that
      tally, not stops — leave those phases unbound so the next sync
      retries them. A wholesale failure (auth not completed, connector
      down) is one warning line: the markdown files remain canonical and
      the backfill can be re-run any time by re-running this command.
   5. After ANY sync attempt, record it in one call:
      `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state.py" --project-dir "$(pwd)" tracker --provider <provider> --last-sync "ok" --bind "<plan path>#<phase id>=<provider>:<key>" ...`
      (`--last-sync "failed: <reason>"` when it failed).

   If auth from step 4 is not complete yet, the tools are not live — say
   so plainly, skip the backfill, and tell the user to re-run
   `/cfm:connect-tracker` after `/mcp`; it will pick up exactly the
   unbound phases.

## Hard limits

- Never touch git; never write product files.
- The only writes: the MCP server registration from step 4 (at the scope
  the user picked — `.mcp.json` ONLY when they chose project scope), the
  approved config diff, the `permissions.allow` entries of step 6.3b,
  state bookkeeping through `scripts/state.py` only (the deferred-question
  outcome and the tracker fields), the binding lines added to
  plan files by step 6's backfill, and — only after approval — tracker
  calls through the redaction pipe. Nothing else.
- Never add an allow rule beyond what `gen_settings.py` generates, and
  never a wildcard: no `mcp__<server>__*`, no `Bash(claude mcp add *)`, no
  bare `Bash(python3 *)` to skip the redaction prompt. Each trades a guard
  layer for convenience and is never worth it.
- The backfill adds binding lines to plans; it never edits a plan's
  phases, goals, or criteria. Plan content changes belong to `/cfm:plan`.
- Never ask for, accept, echo, or store a tracker credential. The built-in
  providers are OAuth-only; a custom URL carrying a token is refused, not
  redacted (see the reference's custom-URL rules).
- Never run `claude mcp login` from a tool call — the browser round-trip
  is the user's, via `/mcp`. This applies to `login` ONLY: `claude mcp
  add`, `get`, `list`, and `remove` are non-interactive and are yours to
  run. Telling the user to add the server by hand is a bug in this skill.
