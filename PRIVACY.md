# Privacy Policy

**cfm (Code For Me)** · Last updated: 2026-11-07

cfm is a Claude Code plugin that runs entirely on your machine. It has no server, no account, and no telemetry. The author of cfm never receives, sees, or stores any of your data.

## What cfm reads

- Files in the project you run it in (source code, `.cfm-workflow.yml`, plans, tasks), so its agents can plan, implement, and review work.
- It deliberately **refuses** to read secret files (`.env*`, keys, credentials, and the other patterns in `secret_globs`), even when asked: `/cfm:init` writes Read, Edit, and Bash deny rules for every secret pattern into your project's `.claude/settings.json`, which Claude Code enforces in every session.

cfm does not collect personal data such as names, emails, or addresses.

## What cfm writes

Only files inside your project, for example `.cfm-workflow.yml`, `.cfm/state.json`, `docs/plans/`, `docs/tasks/`, `docs/PROGRESS.md`, and `.claude/settings.json`. Everything stays on your machine and under your version control. Delete those files and cfm's data is gone.

## What cfm sends off your machine

**Nothing.** The plugin ships no executable code at all (it is Markdown, JSON, YAML, and one icon) and runs no hooks. Nothing in it can make a network call on its own.

**Claude itself.** cfm runs inside Claude Code, so your prompts and the files Claude reads are processed by Anthropic under [Anthropic's privacy policy](https://www.anthropic.com/legal/privacy), exactly as in any Claude Code session. cfm adds no other recipient.

## Retention

cfm operates no service and retains nothing. Files it writes live in your project for as long as you keep them.

## Children

cfm is a software development tool and is not intended for anyone under 18.

## Changes and contact

Changes to this policy are published in this file in the [repository](https://github.com/rokib572/code-for-me). Questions: rokib572@gmail.com.
