# Privacy Policy

**cfm (Code For Me)** · Last updated: 2026-10-03

cfm is a Claude Code plugin that runs entirely on your machine. It has no server, no account, and no telemetry. The author of cfm never receives, sees, or stores any of your data.

## What cfm reads

- Files in the project you run it in (source code, `.cfm-workflow.yml`, plans, tasks), so its agents can plan, implement, and review work.
- It deliberately **refuses** to read secret files (`.env*`, keys, credentials, and the other patterns in `secret_globs`), even when asked.

cfm does not collect personal data such as names, emails, or addresses.

## What cfm writes

Only files inside your project, for example `.cfm-workflow.yml`, `.cfm/state.json`, `docs/plans/`, `docs/tasks/`, `docs/PROGRESS.md`, and `.claude/settings.json`. Everything stays on your machine and under your version control. Delete those files and cfm's data is gone.

## What cfm sends off your machine

**Nothing, by default.** The plugin's scripts make no network calls and the plugin declares no MCP servers.

**Optional tracker sync.** If you choose to run `/cfm:connect-tracker`, cfm mirrors plans and tasks to the tracker you pick (Jira, ClickUp, Trello, or a custom MCP server) through the MCP connector you authorize with that vendor's own OAuth. What is sent: phase and task titles, descriptions, acceptance criteria, and progress notes. Every outbound payload first passes through cfm's redaction filter (`scripts/redact.py`), which removes tokens, keys, passwords, and other secrets; if the filter fails, nothing is sent. That data is then handled under the tracker vendor's own privacy policy. You can disconnect at any time with `/cfm:connect-tracker`.

**Claude itself.** cfm runs inside Claude Code, so your prompts and the files Claude reads are processed by Anthropic under [Anthropic's privacy policy](https://www.anthropic.com/legal/privacy), exactly as in any Claude Code session. cfm adds no other recipient.

## Retention

cfm operates no service and retains nothing. Files it writes live in your project for as long as you keep them.

## Children

cfm is a software development tool and is not intended for anyone under 18.

## Changes and contact

Changes to this policy are published in this file in the [repository](https://github.com/rokib572/code-for-me). Questions: rokib572@gmail.com.
