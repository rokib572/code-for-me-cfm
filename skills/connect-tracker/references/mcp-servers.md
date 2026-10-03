# Tracker MCP servers — the built-in registry

This file is the single source of the built-in tracker endpoints and the
rules for connecting one. `cfm:connect-tracker` reads it; nothing else
hardcodes a URL. A tracker that is not in this table is still fully
supported — it goes through the **Custom** path below and lands in
`tracker.provider` exactly like a built-in one.

## The three built-in providers

| Provider key | Menu label | MCP server name | URL | Transport | Auth |
|---|---|---|---|---|---|
| `jira` | Jira | `atlassian` | `https://mcp.atlassian.com/v2/mcp` | http | OAuth 2.1 (browser) |
| `clickup` | ClickUp | `clickup` | `https://mcp.clickup.com/mcp` | http | OAuth (browser) |
| `trello` | Trello Board | `trello` | `https://mcp.trello.com/v1` | http | OAuth 2.0 (browser) |

Per-provider notes worth telling the user:

- **Jira** — the server is Atlassian's Rovo MCP server, so one connection
  also brings Confluence, Jira Service Management, Bitbucket, and Compass
  tools into the session. That is why the MCP server name is `atlassian`
  while the cfm provider key is `jira`. The legacy `/v1/sse` endpoint is
  retired; only `/v2/mcp` is current.
- **ClickUp** — first-party hosted endpoint; covers tasks, docs, comments,
  assignees, due dates, time entries.
- **Trello** — Trello's own server, not the Atlassian one; the two are
  separate connections. It deliberately exposes **no destructive delete
  tools**, which is fine for cfm: create / transition / comment all work.

None of these take a token, a header, or a `.env` entry — auth is an OAuth
browser round-trip owned by the MCP server. cfm never asks for a
credential and never stores one.

## Connecting a built-in provider

**YOU run the commands, with the Bash tool, in this session.** The user's
only job in this whole step is the browser sign-in at the end — that one
is genuinely theirs, because it needs their credentials. Everything
before it is yours. Printing `claude mcp add ...` for the user to paste
is a FAILURE of this step, not a polite alternative to it.

1. **Check first** — Bash: `claude mcp get <server-name>`. Exit 0 means
   the server is already configured; skip step 2 and go to the auth
   check. Also skip step 2 if the provider's tools are ALREADY live in
   this session (a claude.ai connector, for instance, gives you
   `mcp__claude_ai_Trello__*` tools with no CLI server at all) — say it is
   already connected and move on. Adding a second server for tools you
   already have is a duplicate, not a fix.
2. **Add** — Bash, one of these three, verbatim except for the scope the
   user chose:

   ```bash
   claude mcp add --transport http atlassian https://mcp.atlassian.com/v2/mcp --scope local
   claude mcp add --transport http clickup   https://mcp.clickup.com/mcp     --scope local
   claude mcp add --transport http trello    https://mcp.trello.com/v1       --scope local
   ```

   The command is non-interactive: it prints `Added HTTP MCP server …` and
   exits 0. If the harness asks the user to approve the Bash call, that
   approval IS the user's consent — wait for it, do not pre-empt it by
   handing the command over.

   Scope, from the step's one question:
   - `local` (default, recommended): this machine + this project only,
     nothing written into the repo;
   - `project`: writes `.mcp.json` in the repo root, so the whole team
     gets the server. Safe to commit for all three built-ins — the entry
     is a URL and each teammate does their own OAuth — but it is a repo
     write, so only ever on an explicit pick;
   - `user`: every project on this machine.
3. **Verify** — Bash: `claude mcp list`. The server must appear. It will
   show as failed-to-connect or unauthenticated until the browser
   sign-in; that is expected, not an error to report as a failure.
4. **Hand off auth — this part only.** The OAuth flow needs a browser and
   the user's credentials. Never run `claude mcp login` from a Bash call:
   it blocks waiting on a browser that the tool call cannot drive. (That
   prohibition is about `login` alone — `add`, `get`, `list`, and `remove`
   are yours to run.) Tell the user, in one short block:
   - run `/mcp` in this session, pick the server, complete the sign-in
     (or run `! claude mcp login <server-name>`);
   - the tracker's tools land in the session once auth completes — a
     session restart may be needed before they show up.
5. Connecting is **not** a precondition for the config write. cfm records
   the provider either way; a provider with no live tools degrades to the
   offline warning in `CONNECTORS.md` Part 2 and never blocks a workflow.

Step done means: `claude mcp list` shows the server (or its tools were
already live), and the user has been told to authenticate. Anything less
— a printed command, a suggestion, a "you can add it with…" — is the step
not done.

## Connecting a custom provider

Ask for the MCP server URL in plain conversation (a URL does not fit
AskUserQuestion's option shape), then:

- **Require** `https://` — the one exception is `http://localhost` /
  `http://127.0.0.1` for a server the user runs themselves.
- **Refuse an embedded credential.** If the URL carries `user:pass@`, or a
  `token` / `api_key` / `access_token` / `key` query parameter, STOP: do
  not run it, do not echo the value back, and tell the user to add that
  server themselves with the secret as a header or an environment-variable
  reference (`claude mcp add --transport http <name> <url> --header "Authorization: Bearer $VAR"`).
  cfm's secrets policy does not carve out an exception for MCP setup.
- **Infer the transport** from the URL: a path ending in `/sse` →
  `--transport sse`, anything else → `--transport http`.
- **Derive the server name** from the host (e.g. `linear` from
  `mcp.linear.app`), confirm it with the user, and use the same string —
  slugified — as `tracker.provider`.
- If the user pastes a **command** rather than a URL (`npx …`, `uvx …`),
  that is a stdio server: give them
  `claude mcp add <name> -- <command>` to run themselves, then continue
  the flow from the provider write. Do not compose stdio commands with
  `-e SECRET=…` on the user's behalf.

## When the add fails — ONLY after a real non-zero exit

This section applies after you have actually run the command and it
failed. It is never the opening move.

`claude` not on PATH, a non-zero exit, a 404 on the URL — none of these
are fatal to the skill. Show the exact command you ran, one line of the
real error, and let the user take it from there; then ask whether to
record the provider in config anyway. Never retry a guessed URL: if a
built-in endpoint 404s, the vendor moved it — say so and point at the
vendor's docs rather than inventing a path. A denied Bash permission is
the user declining, not a failure: acknowledge it and move on to step 5
of the skill.

## Provider → tools, at sync time

`CONNECTORS.md` Part 2 resolves `tracker.provider` to live MCP tools by
name and description match. The one alias that is not literal:

- `jira` → the `atlassian` server; its tools are named `atlassian*` /
  `jira*`. Match either.

`clickup`, `trello`, and custom providers match their own names directly.

## Sources

- Jira / Atlassian Rovo MCP: <https://github.com/atlassian/atlassian-mcp-server>
- ClickUp MCP: <https://developer.clickup.com/docs/connect-an-ai-assistant-to-clickups-mcp-server-1>
- Trello MCP: <https://github.com/atlassian/trello-mcp-server> · <https://trello.com/mcp>
