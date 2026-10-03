#!/usr/bin/env python3
"""Render the README terminal screenshots as SVG.

    python3 docs/screenshots/render.py

Each screenshot is a transcript below. `doctor` and `guard` are pasted
from real script output; the skill transcripts (init, plan, implement-
phase, configure, ...) are illustrative — condensed from what the skills
in skills/*/SKILL.md do, not captures of a live session. Inline colour:
⟨k|text⟩ with k = p prompt · t tool · r result · g green · y yellow ·
e red · b bold · d dim · c cyan · m magenta.
"""

from __future__ import annotations

import html
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
COLORS = {
    "": "#d4d4d4", "p": "#c792ea", "t": "#82aaff", "r": "#8a8f98", "g": "#c3e88d",
    "y": "#ffcb6b", "e": "#f07178", "b": "#ffffff", "d": "#6b7280", "c": "#89ddff",
    "m": "#c792ea",
}
SEG = re.compile(r"⟨([a-z]?)\|(.*?)⟩")
FONT = "ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace"
CH, LH, PAD_X, PAD_Y, TOP = 7.6, 19, 18, 14, 40


def render(name, title, lines, width=100):
    w = int(PAD_X * 2 + CH * width)
    h = int(TOP + PAD_Y + LH * len(lines) + PAD_Y)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
           f'viewBox="0 0 {w} {h}" font-family="{FONT}" font-size="12.6">',
           f'<rect width="{w}" height="{h}" rx="10" fill="#1e1f24"/>',
           f'<rect width="{w}" height="{TOP}" rx="10" fill="#2a2b31"/>',
           f'<rect y="{TOP - 10}" width="{w}" height="10" fill="#2a2b31"/>',
           '<circle cx="20" cy="20" r="6" fill="#ff5f57"/>'
           '<circle cx="40" cy="20" r="6" fill="#febc2e"/>'
           '<circle cx="60" cy="20" r="6" fill="#28c840"/>',
           f'<text x="{w / 2}" y="24.5" text-anchor="middle" fill="#9a9ca5" '
           f'font-size="12">{html.escape(title)}</text>']
    y = TOP + PAD_Y + 13
    for line in lines:
        out.append(f'<text x="{PAD_X}" y="{y}" xml:space="preserve">')
        pos = 0
        for match in SEG.finditer(line):
            if match.start() > pos:
                out.append(f'<tspan fill="{COLORS[""]}">{html.escape(line[pos:match.start()])}</tspan>')
            key, text = match.group(1), match.group(2)
            weight = ' font-weight="bold"' if key == "b" else ""
            out.append(f'<tspan fill="{COLORS[key]}"{weight}>{html.escape(text)}</tspan>')
            pos = match.end()
        if pos < len(line):
            out.append(f'<tspan fill="{COLORS[""]}">{html.escape(line[pos:])}</tspan>')
        out.append("</text>")
        y += LH
    out.append("</svg>")
    with open(os.path.join(HERE, f"{name}.svg"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")


U = "⟨p|❯⟩ "          # the user's prompt
T = "⟨t|⏺⟩ "          # a tool call
R = "  ⟨r|⎿⟩  "       # a tool result
A = "⟨c|●⟩ "          # Claude speaking

SHOTS = {}

SHOTS["brainstorm"] = ("cfm:brainstorm — an idea becomes docs/brief.md, zero setup questions", [
    U + "⟨b|/cfm:brainstorm⟩ a tool that lets small teams track shared expenses and settle up",
    "",
    A + "Let's think this through. One question at a time.",
    "",
    A + "⟨b|Problem.⟩ What hurts today when a group shares costs? Who feels it most, and how do they",
    "  cope now — a spreadsheet, a group chat, one person's memory?",
    U + "Flatmates. Someone pays for everything and chases people for months. Spreadsheet nobody updates.",
    "",
    A + "⟨b|Core value.⟩ If the tool did exactly one thing well, what would it be?",
    U + "You always know who owes whom, without anyone doing bookkeeping.",
    "",
    A + "⟨b|MVP.⟩ You listed six features. For each: what breaks if it ships without it?",
    "  · add an expense and split it            ⟨g|survives⟩ — the core loop",
    "  · running balances per person            ⟨g|survives⟩ — the value itself",
    "  · settle up (record a repayment)         ⟨g|survives⟩ — balances never reach zero without it",
    "  · receipt photo upload                   ⟨y|deferred⟩ — nothing breaks; it's a non-goal for now",
    "  · recurring expenses                     ⟨y|deferred⟩ — no persona asked for it",
    "  · multi-currency                         ⟨y|open question⟩ — depends on who the first users are",
    "",
    A + "⟨d|(You asked whether to use Postgres — noted under Open questions for the architecture round.⟩",
    "  ⟨d|This step stays config-free.)⟩",
    "",
    T + "⟨b|Write⟩(docs/brief.md)",
    R + "Wrote 61 lines: problem · personas · MVP features (with whys) · non-goals · open questions",
    "",
    A + "The brief is written and nothing else was created. ⟨b|Move to development?⟩ If yes, run",
    "  ⟨b|/cfm:init⟩ — it runs the architecture round and writes the config. If not yet, you're done.",
])

SHOTS["init"] = ("cfm:init — detect the scenario, interview, write config, scaffold, prove it green", [
    U + "⟨b|/cfm:init⟩",
    "",
    T + "⟨b|Bash⟩(python3 $CLAUDE_PLUGIN_ROOT/scripts/init_scan.py --project-dir .)",
    R + '{"scenario": "greenfield", "signals": {"manifests": [], "source_files": 0, "git_repo": true}}',
    "",
    A + "Empty directory with a brief — ⟨b|greenfield⟩. I'll ask only what the config needs.",
    "",
    T + "⟨b|AskUserQuestion⟩  Stack?                → ⟨g|TypeScript · Fastify · Postgres (Drizzle)⟩",
    T + "⟨b|AskUserQuestion⟩  Layers, in build order? → ⟨g|database → api → web⟩",
    T + "⟨b|AskUserQuestion⟩  Git autonomy?          → ⟨g|L0 — agents never touch git (default)⟩",
    T + "⟨b|AskUserQuestion⟩  Roster?                → ⟨g|default 9 agents; ui-design activates for web⟩",
    "",
    A + "⟨b|Architecture round⟩ — each answer is routed to config (enforceable) or an ADR (rationale):",
    "  · migrations: Drizzle Kit          → ⟨c|commands.migrate_generate / migrate_apply⟩",
    "  · tenancy: none (single household) → ⟨c|tenancy.scope_field: null⟩",
    "  · money as integer minor units     → ⟨c|docs/adr/0001-store-money-as-integer-minor-units.md⟩",
    "",
    A + "⟨b|Conventions round⟩ — 8 categories, each pick becomes a numbered rule with an owner:",
    "  R3 camelCase symbols, no abbreviations (⟨c|lint(naming)⟩) · R4 one export per file (⟨c|reviewer(code-reviewer)⟩)",
    "  R5 no cross-feature imports (⟨c|lint(lint_arch)⟩) · R6 errors extend AppError (⟨c|reviewer(security-check)⟩)",
    "",
    T + "⟨b|Write⟩(.cfm-workflow.yml)                                     ⟨d|— shown as a diff, applied on approval⟩",
    T + "⟨b|Bash⟩(python3 $CLAUDE_PLUGIN_ROOT/scripts/scaffold.py --project-dir .)",
    R + "written CLAUDE.md, .claude/rules/rules.md, CONTEXT.md, .env.example, docs/PROGRESS.md, .cfm/state.json",
    T + "⟨b|Agent⟩(coder) — stack skeleton: package.json, tsconfig, drizzle.config.ts, one green test",
    R + "Done (34.1k tokens). Did NOT run: verify_full (human's command)",
    "",
    A + "⟨b|Prove the lint teeth.⟩ R3 is claimed lint-enforced — the coder writes a deliberate violation:",
    T + "⟨b|Agent⟩(mechanical-gate) — lint",
    R + "lint: ⟨e|FAIL (exit 1)⟩  src/tmp/badName.ts:1  identifier 'usr_cnt' is not camelCase   ⟨g|← it bites; R3 stands⟩",
    "",
    T + "⟨b|Bash⟩(python3 $CLAUDE_PLUGIN_ROOT/scripts/gen_settings.py --project-dir . --write)",
    R + "341 deny rules written to .claude/settings.json (recorded in .claude/cfm-denies.json)",
    T + "⟨b|Bash⟩(python3 $CLAUDE_PLUGIN_ROOT/scripts/doctor.py --project-dir .)",
    R + "verdict: ⟨g|healthy⟩ — 10 checks, 0 failures",
    "",
    A + "cfm is set up. Next: ⟨b|/cfm:plan⟩ for the first feature, or ⟨b|/cfm:configure⟩ to tune anything.",
])

SHOTS["plan"] = ("cfm:plan — a feature becomes phases grounded in the real code, approved in plan mode", [
    U + "⟨b|/cfm:plan⟩ expense splitting",
    "",
    T + "⟨b|EnterPlanMode⟩",
    T + "⟨b|Read⟩(docs/brief.md)  ⟨b|Read⟩(CONTEXT.md)  ⟨b|Read⟩(domain/database/src/households/*.ts)",
    A + "Grounded in the actual code: households already own the `Member` table and the",
    "  `HouseholdRepository` shape — the plan reuses both rather than inventing a second pattern.",
    "",
    A + "⟨b|Plan: expense-splitting⟩  ⟨d|(docs/plans/expense-splitting.md, status: draft)⟩",
    "",
    "  ⟨b|Phase 1 — expense-ledger⟩   layers: database",
    "    scope    domain/database/src/expenses/{schema,repository}.ts + migration",
    "    AC       an Expense records payer, amount (minor units), and one Share per member",
    "    seams    the `ExpenseRepository` public interface",
    "    tests    insert an expense with 3 shares → shares sum to the amount; a share for a non-member fails",
    "",
    "  ⟨b|Phase 2 — balances⟩          layers: database, api",
    "    scope    domain/database/src/balances/*.ts · apps/api/src/balances/{route,handler}.ts",
    "    AC       GET /households/:id/balances returns who owes whom, net, in minor units",
    "    seams    `POST /expenses` and `GET /households/:id/balances`",
    "    tests    two expenses paid by different members → the net matrix is antisymmetric",
    "",
    "  ⟨b|Phase 3 — settle-up⟩         layers: database, api, web",
    "    ⟨d|…⟩",
    "",
    A + "⟨b|YAGNI pass:⟩ Phase 2 AC-4 (\"balances can be exported as CSV\") is speculative — no persona",
    "  in the brief reaches it. Recommend cutting; your call at the gate.",
    "",
    T + "⟨b|ExitPlanMode⟩  ⟨d|— the plan-mode approval gate IS the approval⟩",
    U + "⟨g|Approved⟩ — cut AC-4",
    T + "⟨b|Write⟩(docs/plans/expense-splitting.md)",
    "",
    A + "Greenfield project, first plan approved — one question, once: connect a tracker (Jira, ClickUp,",
    "  Trello) so phases mirror as tasks? ⟨d|(/cfm:connect-tracker any time later)⟩",
    U + "not now",
    A + "Noted in state as declined. Start with ⟨b|/cfm:implement-phase expense-ledger⟩.",
])

SHOTS["implement-phase"] = ("cfm:implement-phase — dispatch per layer, scoped tests, review gates, then stop at the human gate", [
    U + "⟨b|/cfm:implement-phase⟩ balances",
    "",
    T + "⟨b|EnterPlanMode⟩",
    A + "⟨b|Dispatch plan — phase balances⟩ (docs/plans/expense-splitting.md)",
    "  database  coder → e2e-test        scope: domain/database/src/balances/**   seams: `ExpenseRepository`",
    "  api       coder → e2e-test        scope: apps/api/src/balances/**          seams: `GET …/balances`",
    "  gates     [code-reviewer, security-check, simplicity-check] in parallel → mechanical-gate",
    "  done      tests-green-scoped · gates-pass · progress-log-updated",
    T + "⟨b|ExitPlanMode⟩  ⟨d|— approve with auto-accept edits and the phase runs unattended⟩",
    "",
    T + "⟨b|Bash⟩(state.py init --id balances --layers database api)         ⟨d|.cfm/state.json: init recorded⟩",
    T + "⟨b|Agent⟩(coder · sonnet) — database layer",
    R + "dispatch: coder(database) — 54.2k tokens; phase total: 54.2k",
    T + "⟨b|Agent⟩(e2e-test · sonnet) — tests at the declared seam, by explicit path",
    R + "wrote domain/database/src/balances/balances.test.ts · ran test_scoped → ⟨g|3 passed⟩ — 31.1k tokens",
    T + "⟨b|Agent⟩(coder · sonnet) — api layer",
    R + "dispatch: coder(api) — 72.8k tokens; phase total: 158.1k",
    T + "⟨b|Agent⟩(e2e-test · sonnet)",
    R + "wrote apps/api/src/balances/balances.route.test.ts → ⟨g|4 passed⟩ — 40.3k tokens",
    "",
    A + "⟨b|Review pipeline⟩ over the whole phase diff (review.scope: phase):",
    T + "⟨b|Agent⟩(code-reviewer · opus) ⟨b|Agent⟩(security-check · opus) ⟨b|Agent⟩(simplicity-check · opus)   ⟨d|parallel⟩",
    R + "code-reviewer    ⟨g|PASS⟩",
    R + "security-check   ⟨e|FAIL⟩  apps/api/src/balances/handler.ts:41 — household id read from the body, not the route",
    R + "simplicity-check ⟨g|PASS⟩  \"Lean already. Ship.\"  net: -12 lines vs a hand-rolled matrix helper",
    T + "⟨b|Agent⟩(coder) — re-dispatched with the reviewer's raw finding",
    T + "⟨b|Agent⟩(security-check) — re-run ONLY the failed gate",
    R + "security-check   ⟨g|PASS⟩",
    T + "⟨b|Agent⟩(mechanical-gate · haiku)",
    R + "lint: ⟨g|PASS⟩  typecheck: ⟨g|PASS⟩  Did NOT run: test_scoped (e2e-test's), verify_full (human's)",
    "",
    A + "⟨b|Phase report — balances⟩   complete, waiting for your review",
    "  ⟨c|█⟩ input   ⟨y|█⟩ output",
    "  coder · database                  ⟨c|██████████████⟩⟨y|█⟩        54.2k  (in 50.0k · out 4.2k)  ⟨d|claude-sonnet-5 · 4m 20s⟩",
    "  e2e-test · database               ⟨c|████████⟩⟨y|█⟩              31.1k  (in 28.0k · out 3.1k)  ⟨d|claude-sonnet-5 · 3m 10s⟩",
    "  coder · api                       ⟨c|██████████████████⟩⟨y|██⟩   72.8k  (in 66.0k · out 6.8k)  ⟨d|claude-sonnet-5 · 5m 40s⟩",
    "  e2e-test · api                    ⟨c|██████████⟩⟨y|█⟩            40.3k  (in 37.0k · out 3.3k)  ⟨d|claude-sonnet-5 · 3m 40s⟩",
    "  code-reviewer · phase review      ⟨c|████████████████⟩⟨y|█⟩      61.0k  (in 58.0k · out 3.0k)  ⟨d|claude-opus-5 · 2m 30s⟩",
    "  security-check · phase review ×2  ⟨c|████████████⟩⟨y|█⟩          48.5k  (in 46.0k · out 2.5k)  ⟨d|claude-opus-5 · 2m 0s⟩",
    "  simplicity-check · phase review   ⟨c|███████████⟩⟨y|█⟩           44.2k  (in 42.0k · out 2.2k)  ⟨d|claude-opus-5 · 1m 50s⟩",
    "  mechanical-gate · lint+typecheck  ⟨c|██⟩⟨y|█⟩                     9.8k  (in 9.0k · out 800)  ⟨d|claude-haiku-4-5 · 40s⟩",
    "",
    "  ⟨b|Totals⟩                            ⟨c|███████████████████⟩⟨y|█⟩  361.9k  (in 336.0k · out 25.9k)  ⟨d|9 dispatches · 24m 12s⟩",
    "",
    "  ⟨b|Carried forward⟩  apps/api/src/balances/handler.ts:58 — in-memory net matrix; revisit when a",
    "                   household exceeds ~50 members ⟨d|(cfm-debt marker, has a trigger)⟩",
    "",
    "  ⟨b|Your next steps⟩ — the human gates, in prose because there is no tool call to intercept:",
    "  1. run the full suite yourself: ⟨c|npm test⟩   (verify_full — blocked for every agent)",
    "  2. review the diff, and do the git work your level reserves (L0: all of it)",
    "  3. switch auto-accept edits back off if you turned it on at the plan gate",
    "  4. start the next phase explicitly — cfm never auto-starts one.",
])

SHOTS["configure"] = ("cfm:configure — current value → YAML diff → explicit apply → automatic doctor", [
    U + "⟨b|/cfm:configure⟩ git level L1",
    "",
    T + "⟨b|Bash⟩(python3 $CLAUDE_PLUGIN_ROOT/scripts/cfm_config.py --project-dir . --json)",
    A + "git.level is ⟨b|L0⟩ (agents never touch git). L1 grants local commits: add, commit, stash,",
    "  restore, cherry-pick, revert, am, apply. Pushes, branches, and the default branch stay yours.",
    "",
    "  ⟨d|--- a/.cfm-workflow.yml⟩",
    "  ⟨d|+++ b/.cfm-workflow.yml⟩",
    "  ⟨c|@@ -55,3 +55,3 @@⟩",
    "   git:",
    "  ⟨e|-  level: L0⟩",
    "  ⟨g|+  level: L1⟩",
    "     branch_prefixes: [feature/, project/, hotfix/, chore/]",
    "",
    "  ⟨b|Consequences:⟩ the coder may commit locally after each layer; still no push, no branch",
    "  delete, no push to main, no git aliases, no `git config` writes — those hold at every level.",
    "",
    T + "⟨b|AskUserQuestion⟩  Apply this change?  → ⟨g|Yes⟩",
    T + "⟨b|Edit⟩(.cfm-workflow.yml)                                             ⟨d|— surgical: one line⟩",
    T + "⟨b|Bash⟩(python3 $CLAUDE_PLUGIN_ROOT/scripts/cfm_config.py --project-dir .)",
    R + "ok",
    T + "⟨b|Bash⟩(python3 $CLAUDE_PLUGIN_ROOT/scripts/doctor.py --project-dir .)",
    R + "[⟨e|FAIL⟩] #7 secrets hygiene",
    R + "    ✘ 10 stale deny entries in .claude/settings.json from an earlier config (Bash(git add:*),",
    R + "      Bash(git commit:*), …) — the permission layer contradicts the config; run gen_settings --write",
    "",
    A + "The settings denies still say L0. cfm owns those rules, so regenerating ⟨b|retracts⟩ the ten",
    "  the new level grants and keeps everything you wrote yourself:",
    T + "⟨b|Bash⟩(python3 $CLAUDE_PLUGIN_ROOT/scripts/gen_settings.py --project-dir .)          ⟨d|— diff shown⟩",
    T + "⟨b|AskUserQuestion⟩  Write the settings?  → ⟨g|Yes⟩",
    T + "⟨b|Bash⟩(… gen_settings.py --project-dir . --write)",
    R + "retracted 10 stale denies: Bash(git add:*), Bash(git am:*), Bash(git apply:*), Bash(git commit:*), …",
    T + "⟨b|Bash⟩(… doctor.py --project-dir .)",
    R + "verdict: ⟨g|healthy⟩",
])

SHOTS["doctor"] = ("cfm:doctor — real output: config values are promises, the doctor converts them to facts", [
    U + "⟨b|/cfm:doctor⟩",
    T + "⟨b|Bash⟩(python3 $CLAUDE_PLUGIN_ROOT/scripts/doctor.py --project-dir .)",
    "",
    "  cfm doctor",
    "  [⟨g|PASS⟩] #0 environment",
    "      · running inside Claude Code",
    "      · cfm 0.10.0 satisfies min_version 0.1.0",
    "  [⟨g|PASS⟩] #1 schema & invariants",
    "      · config parses; schema v2 valid; hard invariants intact",
    "  [⟨y|WARN⟩] #2 paths",
    "      ⟨y|⚠⟩ context_file: CONTEXT.md does not exist — dispatched agents have no shared vocabulary; /cfm:init scaffolds it",
    "  [⟨g|PASS⟩] #3 commands",
    "      · commands.lint: green (eslint .)",
    "      · commands.typecheck: green (tsc --noEmit)",
    "      · absent slots (capability deactivated): lint_arch, migrate_generate, migrate_apply",
    "  [⟨g|PASS⟩] #4 roster coherence",
    "      · layers resolve, review gates enabled, single-owner matrix clean",
    "  [⟨g|PASS⟩] #5 models",
    "      · live model-list verification is done by the doctor skill",
    "  [⟨g|PASS⟩] #6 rules have teeth",
    "      · 6 rules, all with declared enforcement",
    "  [⟨y|WARN⟩] #7 secrets hygiene",
    "      ⟨y|⚠⟩ no pre-commit hook installed — install it via /cfm:code-review's trigger section",
    "      · .gitignore env coverage checked, .env.example values blank, no tracked secrets, settings denies present,",
    "        sandbox OS-level denies present",
    "      · the pre-commit hook stays WARN, not FAIL — it protects the human's commits, not the agents' tool calls",
    "  [⟨g|PASS⟩] #8 pipeline wiring",
    "      · plugin hook wiring intact (guard + stop review + session context)",
    "      · guard self-test: secret read (path, stdin, glued redirect, git blob spec), secret Read, default-branch push,",
    "        git env alias, and subagent writes to the config and settings (edit, redirect, download, patch, archive)",
    "        all blocked; harmless calls and the main session's config edit allowed; the main session's product writes",
    "        (Write, redirect, copy) blocked while its docs/ write and plugin-script runs are allowed (24 synthetic events)",
    "      · cfm mode: enforced — session context injected at start/resume/compact, routing through /cfm:* skills",
    "      · cfm status line on (mode and phase in the status bar)",
    "      · subagent events observed live: the hook payload carried agent_id, so the policy-file rule fires on real dispatches",
    "  [⟨g|PASS⟩] #9 state",
    "      · .cfm/state.json is schema-valid (v1); no orphaned in-flight phase",
    "  verdict: ⟨g|healthy⟩",
    "",
    A + "⟨b|healthy⟩ — two warnings. The missing glossary is earned term by term (not a failure); the",
    "  pre-commit hook protects your commits and can be installed from /cfm:code-review.",
])

SHOTS["guard"] = ("the PreToolUse guard — real refusals, whatever the prompt says", [
    A + "Reading the database password so I can reproduce the connection error…",
    T + "⟨b|Bash⟩(cat .env)",
    R + "⟨e|cfm: blocked — '.env' matches secret glob '.env*'. The secrets policy is a hard invariant: never read⟩",
    R + "⟨e|secret files, even on an explicit user request.⟩",
    "",
    T + "⟨b|Bash⟩(git push origin main)",
    R + "⟨e|cfm: blocked — hard invariant: never push directly to the default branch ('main'). This holds at⟩",
    R + "⟨e|every git level.⟩",
    "",
    T + "⟨b|Bash⟩(npm test)",
    R + "⟨e|cfm: blocked — that is the verify_full command. The full test suite is the human's command; agents⟩",
    R + "⟨e|run tests only by explicit file path (test_scoped).⟩",
    "",
    "  ⟨d|— in the main session (cfm mode: enforced) —⟩",
    T + "⟨b|Edit⟩(src/balances/service.ts)",
    R + "⟨e|cfm: blocked — 'src/balances/service.ts' is product code; in cfm mode the main session orchestrates and⟩",
    R + "⟨e|never writes it. Dispatch the coder (or /cfm:implement-phase, /cfm:diagnose) instead.⟩",
    "",
    "  ⟨d|— inside a dispatched subagent (the hook event carries agent_id) —⟩",
    T + "⟨b|Bash⟩(sed -i 's/level: L0/level: L3/' .cfm-workflow.yml)",
    R + "⟨e|cfm: blocked — '.cfm-workflow.yml' is workflow policy (the cfm config, the generated settings denies,⟩",
    R + "⟨e|an agent file, or the plugin itself). Subagents never modify it; config changes go through⟩",
    R + "⟨e|/cfm:configure in the main session, with the human approving the diff.⟩",
    T + "⟨b|Bash⟩(git apply fix.patch)",
    R + "⟨e|cfm: blocked — 'git apply' lands content the guard cannot inspect in the working tree, which can⟩",
    R + "⟨e|rewrite workflow policy … Subagents never run it; the human applies patches, stashes and archives.⟩",
    "",
    "  ⟨d|— and what still works —⟩",
    T + "⟨b|Bash⟩(cp .env.example .env)                        ⟨g|allowed⟩  ⟨d|write-only destination (from the coder)⟩",
    T + "⟨b|Write⟩(docs/plans/balances.md)                     ⟨g|allowed⟩  ⟨d|a workflow file: the orchestrator's to write⟩",
    T + "⟨b|Bash⟩(grep -q '\\.env' .gitignore)                  ⟨g|allowed⟩  ⟨d|the pattern argument is not a file⟩",
    T + "⟨b|Bash⟩(git commit -m \"docs: mention .env && why\")   ⟨g|allowed at L1⟩  ⟨d|a quoted message is text⟩",
    T + "⟨b|Bash⟩(npm test src/balances/balances.test.ts)     ⟨g|allowed⟩  ⟨d|a path makes it a scoped run⟩",
])

SHOTS["status"] = ("cfm:status — a pure read of where the workflow stands", [
    U + "⟨b|/cfm:status⟩",
    T + "⟨b|Bash⟩(python3 $CLAUDE_PLUGIN_ROOT/scripts/state.py --project-dir . show)",
    T + "⟨b|Bash⟩(python3 $CLAUDE_PLUGIN_ROOT/scripts/debt_scan.py --project-dir .)",
    "",
    A + "⟨b|Current phase⟩   settle-up — \"record a repayment and net it against balances\"",
    "                  docs/plans/expense-splitting.md · in flight since 14:02",
    "",
    "  ⟨b|Pipeline cursor⟩",
    "    database   coder ⟨g|done⟩   tests ⟨g|written 1 / passed 1⟩   settlements.test.ts",
    "    api        coder ⟨y|dispatched⟩   tests —",
    "    web        coder pending",
    "    gates      code-reviewer pending · security-check pending · simplicity-check pending",
    "",
    "  ⟨b|Pending human gates⟩   none yet — the phase is still running",
    "",
    "  ⟨b|Carried forward⟩",
    "    · Phase balances: apps/api/src/balances/handler.ts:58 — in-memory net matrix; revisit when a household",
    "      exceeds ~50 members",
    "    · 3 cfm-debt markers, ⟨y|1 with no upgrade trigger⟩:",
    "      apps/api/src/expenses/handler.ts:112 — retries hard-coded to 3   ⟨d|(names a ceiling, no trigger — rot risk)⟩",
    "",
    "  ⟨b|Deferred config questions⟩   tracker connection — declined at /cfm:plan; ask again via /cfm:connect-tracker",
    "",
    "  ⟨b|Tracker sync⟩   offline (markdown plan is canonical)",
    "",
    A + "Nothing to do until the phase stops at its gate. To pick it up in a fresh session: ⟨b|/cfm:implement-phase⟩",
    "  with no argument resumes from state, verifying the ledger against the working tree first.",
])

SHOTS["code-review"] = ("cfm:code-review — the configured pipeline over a scope, findings by severity with file:line", [
    U + "⟨b|/cfm:code-review⟩ the settlements module, watch for double-counting",
    "",
    T + "⟨b|Grep⟩(pattern: \"settle\", glob: **/*.ts)   ⟨d|→ 4 files, intersected with uncommitted work⟩",
    A + "Resolved scope: apps/api/src/settlements/{handler,route}.ts, domain/database/src/settlements/repository.ts,",
    "  domain/database/src/settlements/settlements.test.ts. Focus directive passed verbatim to every reviewer.",
    "",
    T + "⟨b|Agent⟩(code-reviewer · opus)  ⟨b|Agent⟩(security-check · opus)  ⟨b|Agent⟩(simplicity-check · opus)   ⟨d|parallel⟩",
    T + "⟨b|Agent⟩(mechanical-gate · haiku)",
    "",
    A + "⟨b|Verdicts⟩   code-reviewer ⟨e|FAIL⟩ · security-check ⟨g|PASS⟩ · simplicity-check ⟨g|PASS⟩ · mechanical-gate ⟨g|PASS⟩",
    "",
    "  ⟨e|HIGH⟩    apps/api/src/settlements/handler.ts:47",
    "          a settlement is applied to the balance AND re-derived from the ledger on the next read —",
    "          the repayment counts twice when both paths run. ⟨d|(the focus you asked for)⟩",
    "  ⟨y|MEDIUM⟩  domain/database/src/settlements/repository.ts:23",
    "          `Settlement` is called `Repayment` here — CONTEXT.md names the concept Settlement; a renamed",
    "          glossary term is a finding.",
    "  ⟨d|LOW⟩     domain/database/src/settlements/settlements.test.ts:31",
    "          asserts `total === computeTotal(items)` — tautological; assert against an independent expected value.",
    "",
    A + "Scoped to a focus, so the tree is ⟨b|still unreviewed⟩ for the on-stop trigger — a no-argument run marks it.",
    "  Tokens: 4 dispatches, 171.4k.",
])

if __name__ == "__main__":
    for name, (title, lines) in SHOTS.items():
        width = max(100, max(len(SEG.sub(r"\2", l)) for l in lines) + 2)
        render(name, title, lines, width=width)
        print(f"rendered {name}.svg ({len(lines)} lines, {width} cols)")
