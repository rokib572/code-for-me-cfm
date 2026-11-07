# Tracker providers — the built-in registry

This file is the single source of the built-in provider names and of how
a tracker gets connected. `cfm:connect-tracker` reads it; nothing else
hardcodes a provider. A tracker that is not in this table is still fully
supported — it goes through the **Custom** path below and lands in
`tracker.provider` exactly like a built-in one.

cfm never registers, configures, or modifies an MCP server. The plugin
declares none, and no skill runs an `mcp` command. Connecting a tracker
is the user's own step through Claude Code's connector surface; cfm's
part is to recognise the tracker's tools once they are live and to
record the provider in config.

## The three built-in providers

| Provider key | Menu label | Connector | Tool-name prefix | Auth |
|---|---|---|---|---|
| `jira` | Jira | Atlassian (Rovo) | `atlassian` / `jira` | OAuth in the browser |
| `clickup` | ClickUp | ClickUp | `clickup` | OAuth in the browser |
| `trello` | Trello Board | Trello | `trello` | OAuth in the browser |

Per-provider notes worth telling the user:

- **Jira** — the connector is Atlassian's Rovo server, so one connection
  also brings Confluence, Jira Service Management, Bitbucket, and Compass
  tools into the session. That is why the tool prefix is `atlassian`
  while the cfm provider key is `jira`.
- **ClickUp** — first-party hosted connector; covers tasks, docs,
  comments, assignees, due dates, time entries.
- **Trello** — Trello's own connector, not the Atlassian one; the two are
  separate connections. It deliberately exposes **no destructive delete
  tools**, which is fine for cfm: create / transition / comment all work.

None of these take a token, a header, or a configuration value from cfm.
Sign-in is an OAuth browser round-trip owned by the connector. cfm never
asks for a credential and never stores one.

## Connecting a built-in provider

1. **Check first.** Scan the MCP tools available in THIS session for the
   provider's tool-name prefix. Tools present means the tracker is
   already connected: say so and move on to the provider write. A
   claude.ai connector (tools named `mcp__claude_ai_<Provider>__*`)
   counts exactly the same.
2. **Hand off the connection.** Tools absent: tell the user, in one short
   block, how to connect it themselves — this is their step, because it
   needs their account:
   - open `/mcp` in this session and add the provider's connector from
     the Anthropic Directory (Atlassian, ClickUp, and Trello are all
     listed there), or add it in the claude.ai connectors settings, which
     makes the tools available in Claude Code too;
   - complete the sign-in in the browser when prompted;
   - the tracker's tools land in the session once sign-in completes — a
     session restart may be needed before they show up.
   Never type an endpoint, a transport, or a command for them: the
   connector carries its own configuration, and a URL from memory is
   wrong more often than it is right.
3. **Do not wait.** Connecting is **not** a precondition for the config
   write. cfm records the provider either way; a provider with no live
   tools degrades to the offline warning in `CONNECTORS.md` Part 2 and
   never blocks a workflow.

Step done means: the provider's tools are live in the session, or the
user has been told how to connect it. Both are a success.

## Connecting a custom provider

A tracker outside the table is one the user connects themselves, through
`/mcp` or the connectors settings, before or after this flow. cfm asks
for nothing about the server — no URL, no transport, no command, no
credential:

- Ask only for the **provider name**, in plain conversation, and derive
  the slug from it (`linear`, `github-issues`, `youtrack`); confirm it
  with the user, and use that slug as `tracker.provider`.
- Scan the session's MCP tools for that name. Present → connected. Absent
  → the same hand-off as step 2 above, naming their own connector instead
  of a built-in one.
- If the user pastes a server URL, a command, or anything that looks like
  a setup value, do not act on it and do not echo it back: say that cfm
  does not configure servers, and point them to `/mcp` to add it
  themselves. A pasted value that contains a credential is dropped from
  the conversation and noted as `[redacted]`.

## Provider → tools, at sync time

`CONNECTORS.md` Part 2 resolves `tracker.provider` to live MCP tools by
name and description match. The one alias that is not literal:

- `jira` → the Atlassian connector; its tools are named `atlassian*` /
  `jira*`. Match either.

`clickup`, `trello`, and custom providers match their own names directly.

## Sources

- Jira / Atlassian Rovo MCP: <https://github.com/atlassian/atlassian-mcp-server>
- ClickUp MCP: <https://developer.clickup.com/docs/connect-an-ai-assistant-to-clickups-mcp-server-1>
- Trello MCP: <https://github.com/atlassian/trello-mcp-server> · <https://trello.com/mcp>
