#!/usr/bin/env python3
"""cfm doctor — mechanical health checks.

Config values are promises; the doctor converts them to facts.

Usage: python3 doctor.py [--project-dir DIR] [--json]
Exit code: 0 all checks pass (warnings allowed), 1 any check fails.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys

import agent_file
import cfm_config
import gen_settings
import guard_check
import state as state_mod

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMMAND_TIMEOUT_SECONDS = 120

# How check 3 treats each slot. Human-only and mutating slots are never
# executed by the doctor; templates can't run without arguments.
SLOT_POLICY = {
    "lint": "run",
    "lint_arch": "run",
    "typecheck": "run",
    "test_scoped": "template",
    "verify_full": "exists",       # contractually the human's command
    "migrate_generate": "resolve",  # mutating — resolve the binary only
    "migrate_apply": "resolve",
}


class Check:
    def __init__(self, check_id, name):
        self.id = check_id
        self.name = name
        self.failures = []
        self.warnings = []
        self.notes = []
        self.skipped = False

    @property
    def status(self):
        if self.skipped:
            return "SKIP"
        if self.failures:
            return "FAIL"
        if self.warnings:
            return "WARN"
        return "PASS"

    def as_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "failures": self.failures,
            "warnings": self.warnings,
            "notes": self.notes,
        }


def _version_tuple(version):
    parts = re.findall(r"\d+", version)
    return tuple(int(p) for p in parts) if parts else None


def _plugin_version():
    manifest = os.path.join(PLUGIN_ROOT, ".claude-plugin", "plugin.json")
    try:
        with open(manifest, encoding="utf-8") as fh:
            return json.load(fh).get("version")
    except (OSError, json.JSONDecodeError):
        return None


def check_0_environment(check, project_dir, config):
    gate = os.path.join(PLUGIN_ROOT, "scripts", "require-claude-code.sh")
    result = subprocess.run(
        ["bash", gate], capture_output=True, text=True, timeout=10
    )
    if result.returncode != 0:
        check.failures.append(result.stderr.strip() or "environment gate failed")
        return
    check.notes.append("running inside Claude Code")

    if cfm_config.yaml is None:
        check.failures.append("PyYAML is not installed. Fix: pip install pyyaml")

    if config is None:
        check.warnings.append("config unavailable — min_version not checked")
        return
    min_version = (config.get("cfm", {}).get("requires") or {}).get("min_version")
    plugin_version = _plugin_version()
    if min_version and plugin_version:
        wanted, have = _version_tuple(min_version), _version_tuple(plugin_version)
        if wanted and have and have < wanted:
            check.failures.append(
                f"config requires cfm >= {min_version}, installed plugin is "
                f"{plugin_version} — update cfm"
            )
        else:
            check.notes.append(f"cfm {plugin_version} satisfies min_version {min_version}")


def check_1_schema(check, cfg_errors, cfg_warnings):
    check.failures.extend(cfg_errors)
    check.warnings.extend(cfg_warnings)
    if not cfg_errors:
        check.notes.append("config parses; schema v2 valid; hard invariants intact")


def check_2_paths(check, project_dir, config):
    if config is None:
        check.skipped = True
        return

    def missing(rel):
        return not os.path.exists(os.path.join(project_dir, rel))

    for layer in config.get("layers") or []:
        if isinstance(layer, dict) and isinstance(layer.get("path"), str):
            if missing(layer["path"]):
                check.failures.append(
                    f"layers.{layer.get('name')}: path does not exist: {layer['path']}"
                )

    for md_file in (config.get("claude_md") or {}).get("files") or []:
        if isinstance(md_file, str) and missing(md_file):
            check.failures.append(f"claude_md.files: routing target missing: {md_file}")

    rules_file = config.get("rules_file")
    if isinstance(rules_file, str) and missing(rules_file):
        check.failures.append(f"rules_file: does not exist: {rules_file}")

    for field in ("progress_log", "state_file"):
        rel = config.get(field)
        if isinstance(rel, str) and missing(rel):
            check.warnings.append(
                f"{field}: {rel} does not exist yet (created by the workflow)"
            )

    # A glossary is earned term by term, so its absence is a warning: a fresh
    # repo has nothing to say yet, and failing it would punish the honest case.
    context_file = config.get("context_file")
    if isinstance(context_file, str) and missing(context_file):
        check.warnings.append(
            f"context_file: {context_file} does not exist — dispatched agents "
            f"have no shared vocabulary; /cfm:init scaffolds it"
        )

    for name, template in (config.get("feature_roots") or {}).items():
        if isinstance(template, str) and "{feature}" in template:
            prefix = template.split("{feature}")[0].rstrip("/")
            if prefix and missing(prefix):
                check.warnings.append(
                    f"feature_roots.{name}: base directory missing: {prefix}"
                )


def _binary_resolves(command, project_dir):
    try:
        binary = shlex.split(command)[0]
    except (ValueError, IndexError):
        return None
    if os.path.isabs(binary):
        return binary if os.access(binary, os.X_OK) else None
    local = os.path.join(project_dir, binary)
    if os.sep in binary and os.access(local, os.X_OK):
        return binary
    return shutil.which(binary)


def check_3_commands(check, project_dir, config):
    if config is None:
        check.skipped = True
        return
    commands = config.get("commands") or {}

    if not commands.get("verify_full"):
        check.failures.append(
            "commands.verify_full: must be defined — it is the human's command "
            "(agents are banned from running it, but it has to exist)"
        )

    for slot in commands:
        policy = SLOT_POLICY.get(slot, "resolve")
        for command in cfm_config.slot_commands(config, slot):
            if policy == "exists":
                continue
            if _binary_resolves(command, project_dir) is None:
                check.failures.append(
                    f"commands.{slot}: binary not found for: {command}"
                )
                continue
            if policy == "template":
                if "{files}" not in command:
                    check.failures.append(
                        f"commands.{slot}: template must contain {{files}}: {command}"
                    )
                elif "{pkg}" not in command:
                    check.warnings.append(
                        f"commands.{slot}: no {{pkg}} placeholder — fine for "
                        f"single-package repos"
                    )
                continue
            if policy == "run":
                try:
                    result = subprocess.run(
                        command, shell=True, cwd=project_dir, capture_output=True,
                        text=True, timeout=COMMAND_TIMEOUT_SECONDS,
                    )
                except subprocess.TimeoutExpired:
                    check.failures.append(
                        f"commands.{slot}: timed out after "
                        f"{COMMAND_TIMEOUT_SECONDS}s: {command}"
                    )
                    continue
                if result.returncode != 0:
                    tail = (result.stderr or result.stdout or "").strip().splitlines()
                    detail = " | ".join(tail[-3:]) if tail else "no output"
                    check.failures.append(
                        f"commands.{slot}: exited {result.returncode}: "
                        f"{command} — {detail}"
                    )
                else:
                    check.notes.append(f"commands.{slot}: green ({command})")

    absent = [s for s in cfm_config.COMMAND_SLOTS if s not in commands]
    if absent:
        check.notes.append(
            f"absent slots (capability deactivated): {', '.join(absent)}"
        )


def _agents(config):
    agents = config.get("agents")
    if not isinstance(agents, dict):
        return {}
    return {n: a for n, a in agents.items() if isinstance(a, dict)}


# tools that can change the repo or run commands: a file granting one the
# config does not list is a false promise, not a cosmetic drift
MUTATING_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit", "Bash"}


def _read_frontmatter(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return agent_file.parse_frontmatter(fh.read())
    except OSError:
        return None


def _check_agent_files(check, project_dir, agents):
    """Config `tools` is a promise; the agent FILE's frontmatter is what
    Claude Code enforces. Shipped agents: the plugin file is fixed, so the
    config must not claim fewer mutating tools than the file grants.
    Custom agents: the project file must exist and match exactly."""
    shipped = agent_file.shipped_agents()
    for name, agent in agents.items():
        if agent.get("enabled") is not True:
            continue
        cfg_tools = [t for t in (agent.get("tools") or []) if isinstance(t, str)]
        if name in shipped:
            fields = _read_frontmatter(
                os.path.join(PLUGIN_ROOT, "agents", f"{name}.md"))
            file_tools = agent_file.frontmatter_tools(fields or {})
            extra = sorted(set(file_tools) - set(cfg_tools))
            if extra:
                if set(extra) & MUTATING_TOOLS:
                    check.failures.append(
                        f"agents.{name}.tools omits {extra}, but the shipped "
                        f"agent file grants them — Claude Code enforces the "
                        f"file, so the config understates what this agent can "
                        f"do; list the file's tools {sorted(file_tools)} "
                        f"or add a custom agent instead"
                    )
                else:
                    check.warnings.append(
                        f"agents.{name}.tools omits read-only {extra} that the "
                        f"shipped agent file grants — align the config"
                    )
            missing = sorted(set(cfg_tools) - set(file_tools))
            if missing:
                check.warnings.append(
                    f"agents.{name}.tools lists {missing} that the shipped "
                    f"agent file does not grant — the file wins at dispatch"
                )
            fm_alias = cfm_config.model_alias((fields or {}).get("model"))
            cfg_alias = cfm_config.model_alias(agent.get("model"))
            if fm_alias and cfg_alias and fm_alias != cfg_alias:
                check.notes.append(
                    f"agents.{name}.model resolves to '{cfg_alias}'; the "
                    f"orchestrator passes that alias at dispatch (the shipped "
                    f"file's '{fm_alias}' is only the fallback)"
                )
            continue
        path = os.path.join(project_dir, agent_file.AGENTS_REL, f"{name}.md")
        fields = _read_frontmatter(path)
        if fields is None:
            check.failures.append(
                f"agents.{name}: custom agent has no {agent_file.AGENTS_REL}/"
                f"{name}.md — without it the agent is dispatched with EVERY "
                f"tool and its config tools are unenforced; run "
                f"scripts/agent_file.py --agent {name} --write"
            )
            continue
        file_tools = agent_file.frontmatter_tools(fields)
        if fields.get("name") != name or set(file_tools) != set(cfg_tools):
            check.failures.append(
                f"agents.{name}: {agent_file.AGENTS_REL}/{name}.md frontmatter "
                f"(name '{fields.get('name')}', tools {sorted(file_tools)}) "
                f"drifted from config (tools {sorted(cfg_tools)}) — re-run "
                f"scripts/agent_file.py --agent {name} --write"
            )


def check_4_roster(check, project_dir, config):
    if config is None:
        check.skipped = True
        return
    agents = _agents(config)
    layer_names = {
        layer["name"]
        for layer in config.get("layers") or []
        if isinstance(layer, dict) and isinstance(layer.get("name"), str)
    }

    # per-name misses are check-1 schema errors; here: an enabled agent whose
    # layer list resolves to NOTHING can never activate
    for name, agent in agents.items():
        if agent.get("enabled") is not True:
            continue
        agent_layers = agent.get("layers")
        if isinstance(agent_layers, list) and not any(
            l in layer_names for l in agent_layers
        ):
            check.failures.append(
                f"agents.{name}: enabled but none of its layers exist — "
                f"it can never activate"
            )

    gates = config.get("review_gates")
    flat = []
    for entry in gates if isinstance(gates, list) else []:
        flat.extend(entry if isinstance(entry, list) else [entry])
    for gate in flat:
        # unknown agents are check-1 failures; disabled ones are pipeline rot
        if gate in agents and agents[gate].get("enabled") is not True:
            check.failures.append(
                f"review_gates: '{gate}' is disabled — a disabled agent "
                f"cannot gate the pipeline"
            )

    # only ENABLED agents contribute ownership — a disabled agent runs
    # nothing, so counting it manufactures phantom conflicts
    owners = {}
    for name, agent in agents.items():
        if agent.get("enabled") is not True:
            continue
        owned = agent.get("owns_commands")
        for slot in owned if isinstance(owned, list) else []:
            if isinstance(slot, str):
                if slot == "verify_full":
                    check.failures.append(
                        f"agents.{name}: owns_commands lists verify_full — "
                        f"verify_full is the human's command — no agent may "
                        f"own it"
                    )
                owners.setdefault(slot, []).append(name)
    _check_agent_files(check, project_dir, agents)

    ack = config.get("shared_commands_ack")
    ack = [a for a in ack if isinstance(a, str)] if isinstance(ack, list) else []
    for slot, names in sorted(owners.items()):
        if len(names) < 2:
            continue
        if slot in ack:
            check.warnings.append(
                f"shared ownership of {slot} acknowledged — the doctor will "
                f"keep nagging (owners: {', '.join(names)})"
            )
        else:
            check.failures.append(
                f"commands.{slot}: shared ownership ({', '.join(names)}) "
                f"violates the single-owner matrix — reassign, or acknowledge "
                f"via shared_commands_ack: [{slot}]"
            )
    if not check.failures and not check.warnings:
        check.notes.append(
            "layers resolve, review gates enabled, single-owner matrix clean"
        )


def check_5_models(check, project_dir, config):
    if config is None:
        check.skipped = True
        return
    for name, agent in _agents(config).items():
        if agent.get("enabled") is not True:
            continue
        model = agent.get("model")
        if not isinstance(model, str):
            continue  # missing/typed wrong is a check-1 schema error
        # WARN, not FAIL: model is free-text by design (escape hatch)
        if not model.strip():
            check.warnings.append(f"agents.{name}.model: empty string")
        elif not re.fullmatch(r"claude-[A-Za-z0-9][A-Za-z0-9.-]*", model):
            check.warnings.append(
                f"agents.{name}.model: '{model}' does not look like an "
                f"Anthropic model id (expected claude-*)"
            )
        elif cfm_config.model_alias(model) is None:
            check.warnings.append(
                f"agents.{name}.model: '{model}' has no dispatch alias "
                f"({'/'.join(cfm_config.MODEL_ALIASES)}) — the Agent tool's "
                f"model parameter takes an alias, so this agent will run on "
                f"its file's default model"
            )
    check.notes.append("live model-list verification is done by the doctor skill")


RULE_HEADING = re.compile(r"^##\s+R(\d+)\b.*$", re.MULTILINE)
ENFORCEMENT = re.compile(r"\*\*Enforcement:\*\*\s*(\S.*)")
# only the reviewer(<name>) form is checkable against the roster; other
# kinds (lint(...), hook(...), ci(...), doctor(...), free text) stay accepted
REVIEWER_ENFORCEMENT = re.compile(r"reviewer\s*\(\s*([^()]*?)\s*\)")
# lint(...)'s argument is a rule id in some rules and a slot name in others,
# so the argument itself is not checkable — but claiming lint teeth with no
# lint command configured at all is always wrong
LINT_ENFORCEMENT = re.compile(r"\blint\s*\(")
LINT_SLOTS = ("lint", "lint_arch")


def check_6_rules(check, project_dir, config):
    if config is None:
        check.skipped = True
        return
    rules_path = os.path.join(project_dir, config.get("rules_file") or "")
    if not os.path.isfile(rules_path):
        check.skipped = True  # absence itself is a check-2 failure
        return
    with open(rules_path, encoding="utf-8") as fh:
        text = fh.read()

    headings = list(RULE_HEADING.finditer(text))
    if not headings:
        check.warnings.append(
            f"{config['rules_file']}: no rules found (expected '## R<n>. <title>' "
            f"headings)"
        )
        return
    agents = _agents(config)
    commands = config.get("commands") or {}
    has_lint_slot = any(slot in commands for slot in LINT_SLOTS)
    lint_enforced = []
    for i, match in enumerate(headings):
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        block = text[match.start():end]
        enforcement = ENFORCEMENT.search(block)
        if not enforcement:
            check.failures.append(
                f"R{match.group(1)}: no '**Enforcement:**' declared — rules "
                f"without teeth are rejected (hard invariant 3)"
            )
            continue
        if not has_lint_slot and LINT_ENFORCEMENT.search(enforcement.group(1)):
            lint_enforced.append(f"R{match.group(1)}")
        reviewer = REVIEWER_ENFORCEMENT.fullmatch(enforcement.group(1).strip())
        if reviewer:
            name = reviewer.group(1)
            # a reviewer that doesn't exist — or exists but is disabled —
            # will never actually check the rule
            if agents.get(name, {}).get("enabled") is not True:
                check.failures.append(
                    f"R{match.group(1)}: enforcement names reviewer "
                    f"'{name}' which is not an enabled agent — teeth "
                    f"require a live owner"
                )
    if lint_enforced:
        check.warnings.append(
            f"{', '.join(lint_enforced)}: enforcement claims lint(...) but "
            f"neither the 'lint' nor the 'lint_arch' command slot is "
            f"configured — nothing runs it; assign a reviewer instead"
        )
    if not check.failures:
        check.notes.append(f"{len(headings)} rules, all with declared enforcement")


def check_7_secrets(check, project_dir, config, cfg_errors=()):
    if config is None:
        check.skipped = True
        return
    is_repo = os.path.exists(os.path.join(project_dir, ".git"))
    try:
        env_files = [n for n in os.listdir(project_dir) if n.startswith(".env")]
    except OSError:
        env_files = []

    # what actually ran, so the success note never overclaims
    verified = []
    guard_layer_warned = False

    # pragmatic: a project with no git repo and no .env* has nothing for
    # .gitignore to protect yet — note instead of failing
    gitignore = os.path.join(project_dir, ".gitignore")
    if is_repo or env_files:
        if not os.path.isfile(gitignore):
            check.failures.append(
                ".gitignore missing — the .env glob family is uncovered"
            )
        else:
            with open(gitignore, encoding="utf-8") as fh:
                lines = [line.strip() for line in fh]
            if ".env*" not in lines:
                if ".env" in lines:
                    check.failures.append(
                        ".gitignore: bare '.env' leaves the rest of the env "
                        "family committable (.env.local etc — use '.env*', "
                        "and '!.env.example')"
                    )
                else:
                    check.failures.append(
                        ".gitignore does not cover the env family — add "
                        "'.env*' (and '!.env.example')"
                    )
            elif "!.env.example" not in lines:
                check.warnings.append(
                    ".gitignore: no '!.env.example' negation — the sanctioned "
                    "example file gets ignored too"
                )
            else:
                # later rules win in .gitignore: a negation ABOVE the env
                # ignore lines is dead — .env.example ends up ignored
                last_env = max(i for i, l in enumerate(lines)
                               if l.startswith(".env"))
                last_neg = max(i for i, l in enumerate(lines)
                               if l == "!.env.example")
                if last_neg < last_env:
                    check.warnings.append(
                        ".gitignore: '!.env.example' appears before the env "
                        "ignore lines — the negation is overridden by later "
                        "rules — move '!.env.example' last"
                    )
            verified.append(".gitignore env coverage checked")
    else:
        check.notes.append(
            ".gitignore rule deferred — applies once the project is a git "
            "repo or a .env* file exists"
        )

    example = os.path.join(project_dir, ".env.example")
    if os.path.isfile(example):
        with open(example, encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                name, sep, value = stripped.partition("=")
                if not sep:
                    # the line could be anything, including a pasted raw
                    # token — never echo any part of it
                    check.failures.append(
                        f".env.example:{lineno}: line is not NAME= form "
                        f"(content not shown)"
                    )
                elif value.strip():
                    # never print the value — the name alone locates the line
                    check.failures.append(
                        f".env.example:{lineno}: '{name.strip()}' must be "
                        f"'NAME=' with a blank value (value not shown)"
                    )
        verified.append(".env.example values blank")
    else:
        check.notes.append(".env.example absent — nothing to verify")

    if is_repo:
        try:
            result = subprocess.run(
                ["git", "-C", project_dir, "ls-files"],
                capture_output=True, text=True, timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired):
            result = None
        if result is not None and result.returncode == 0:
            globs = guard_check._secret_globs(config)
            for path in result.stdout.splitlines():
                glob = guard_check._match_path(path, project_dir, globs)
                if glob:
                    check.failures.append(
                        f"tracked file '{path}' matches secret glob '{glob}' "
                        f"(critical) — a secret that touched git history is "
                        f"burned — rotate it"
                    )
            verified.append("no tracked secrets")

        hook = os.path.join(project_dir, ".git", "hooks", "pre-commit")
        if not os.path.isfile(hook):
            check.warnings.append(
                "no pre-commit hook installed — install it via /cfm:code-review's "
                "trigger section"
            )
            guard_layer_warned = True
        else:
            with open(hook, encoding="utf-8", errors="replace") as fh:
                if "gitleaks" not in fh.read():
                    check.warnings.append(
                        ".git/hooks/pre-commit does not mention gitleaks — "
                        "staged-content secret scan is missing"
                    )
                    guard_layer_warned = True

    settings_path = os.path.join(project_dir, gen_settings.SETTINGS_REL)
    try:
        settings = gen_settings.read_settings(settings_path)
    except (ValueError, OSError) as exc:
        check.warnings.append(f"{gen_settings.SETTINGS_REL}: unreadable ({exc})")
    else:
        present = set(gen_settings.current_denies(settings))
        missing = [d for d in gen_settings.required_denies(config)
                   if d not in present]
        managed = gen_settings.read_managed(
            os.path.join(project_dir, gen_settings.MANAGED_REL))
        stale = gen_settings.stale_denies(config, settings, managed)
        if stale and not cfg_errors:
            # a deny from an earlier config (a git level since raised) makes
            # the level change silently ineffective at this layer
            check.failures.append(
                f"{len(stale)} stale deny entries in "
                f"{gen_settings.SETTINGS_REL} from an earlier config "
                f"({', '.join(stale[:3])}{', …' if len(stale) > 3 else ''}) "
                f"— the permission layer contradicts the config; run "
                f"gen_settings --write to retract them"
            )
        if missing and cfg_errors:
            # the required set derives from a config check 1 already
            # rejected — report, but let check 1 own the failure
            check.warnings.append(
                f"{len(missing)} deny entries missing from "
                f"{gen_settings.SETTINGS_REL} — not failed because the config "
                f"has schema errors; fix those, then run gen_settings --write"
            )
        elif missing:
            # the settings denies are enforcement layer 2; the guard hook
            # (layer 1) fails open without python3 or on an internal error,
            # so a project without the denies has ONE layer, not two
            check.failures.append(
                f"{len(missing)} deny entries missing from "
                f"{gen_settings.SETTINGS_REL} — the permission-layer backstop "
                f"behind the guard hook is absent; run gen_settings --write "
                f"(cfm:init does this; /cfm:configure re-offers it)"
            )
        else:
            verified.append("settings denies present")
        if gen_settings.sandbox_enabled(settings):
            gaps = gen_settings.sandbox_missing(settings, config)
            if gaps:
                check.warnings.append(
                    f"sandbox is enabled but {len(gaps)} cfm filesystem "
                    f"entries are missing ({gaps[0]}, …) — run "
                    f"gen_settings --sandbox --write; verify the resolved "
                    f"paths in /sandbox → Config"
                )
            else:
                verified.append("sandbox OS-level denies present")
        else:
            check.notes.append(
                "Bash sandbox off: the secret and policy-file rules are "
                "enforced on command TEXT only (guard + settings denies); "
                "gen_settings --sandbox --write adds the OS-level layer that "
                "closes the interpreter, variable and script-file evasions"
            )
        # Allows are convenience, not enforcement — but a WILDCARD allow is a
        # hole: a server glob approves every tool the server exposes, and a
        # `claude mcp add` allow lets an agent register an arbitrary command.
        for rule in gen_settings.current_allows(settings):
            if rule.startswith("mcp__") and "*" in rule:
                check.warnings.append(
                    f"{gen_settings.SETTINGS_REL}: allow '{rule}' is a wildcard "
                    f"over a whole MCP server — replace it with the exact "
                    f"tool names sync uses (gen_settings --allow-tool)"
                )
            if rule.startswith("Bash(claude mcp add"):
                check.warnings.append(
                    f"{gen_settings.SETTINGS_REL}: allow '{rule}' lets an agent "
                    f"register any MCP server — including a stdio server, "
                    f"which is an arbitrary command — without a prompt; remove it"
                )
    if not check.failures and verified:
        check.notes.append(", ".join(verified))
    if guard_layer_warned:
        check.notes.append(
            "the pre-commit hook stays WARN, not FAIL — it protects the "
            "human's commits, not the agents' tool calls"
        )


def check_8_pipeline(check, project_dir, config):
    if config is None:
        check.skipped = True
        return
    hooks_path = os.path.join(PLUGIN_ROOT, "hooks", "hooks.json")
    try:
        with open(hooks_path, encoding="utf-8") as fh:
            hooks = (json.load(fh).get("hooks") or {})
    except (OSError, json.JSONDecodeError) as exc:
        hooks = {}
        check.failures.append(
            f"plugin hooks/hooks.json unreadable ({exc}) — plugin integrity "
            f"broken, reinstall cfm"
        )

    def references(event, script):
        for entry in hooks.get(event) or []:
            for hook in (entry.get("hooks") or []) if isinstance(entry, dict) else []:
                if isinstance(hook, dict) and script in str(hook.get("command", "")):
                    return True
        return False

    if hooks:
        if not references("PreToolUse", "guard.sh"):
            check.failures.append(
                "plugin hooks.json: no PreToolUse entry referencing guard.sh "
                "— the secrets/git guard is disconnected"
            )
        if not references("Stop", "on_stop_review.sh"):
            check.failures.append(
                "plugin hooks.json: no Stop entry referencing "
                "on_stop_review.sh — the on-stop review trigger is disconnected"
            )
        for event in ("SessionStart", "UserPromptSubmit"):
            if not references(event, "session_context.sh"):
                check.failures.append(
                    f"plugin hooks.json: no {event} entry referencing "
                    f"session_context.sh — cfm mode's context never reaches "
                    f"the session"
                )
        if not check.failures:
            check.notes.append(
                "plugin hook wiring intact (guard + stop review + session context)")

    mode = config.get("mode") if config.get("mode") in cfm_config.MODES \
        else cfm_config.DEFAULTS["mode"]
    enforced = mode == "enforced"
    product = 2 if enforced else 0

    # the wiring above proves the hook is DECLARED; this proves it DECIDES —
    # synthetic events through the real entry script, expected verdicts
    guard = os.path.join(PLUGIN_ROOT, "scripts", "guard.sh")
    env = dict(os.environ, CLAUDECODE="1", CLAUDE_PROJECT_DIR=project_dir,
               CLAUDE_PLUGIN_ROOT=PLUGIN_ROOT, CFM_GUARD_SELFTEST="1")
    sub = {"agent_id": "cfm-doctor-self-test", "agent_type": "coder"}
    probes = [
        ({"tool_name": "Bash", "tool_input": {"command": "cat .env"}}, 2,
         "secret-file read"),
        ({"tool_name": "Read",
          "tool_input": {"file_path": os.path.join(project_dir, ".env")}}, 2,
         "secret-file Read"),
        ({"tool_name": "Bash", "tool_input": {"command": "git push origin main"}},
         2, "push to default branch"),
        # each of these was a verified bypass once; they stay as regressions
        ({"tool_name": "Bash", "tool_input": {"command": "tee < .env"}}, 2,
         "secret file on stdin"),
        ({"tool_name": "Bash", "tool_input": {"command": "cat<.env"}}, 2,
         "secret file by glued redirect"),
        ({"tool_name": "Bash", "tool_input": {"command": "git show HEAD:.env.local"}},
         2, "secret file by git blob spec"),
        ({"tool_name": "Bash",
          "tool_input": {"command": "GIT_CONFIG_PARAMETERS='alias.ci=commit' git ci"}},
         2, "git alias via environment"),
        # policy files: a subagent never modifies them; the main session may
        ({"tool_name": "Write", "tool_input": {
            "file_path": os.path.join(project_dir, ".cfm-workflow.yml"),
            "content": ""}, **sub}, 2, "subagent Write to the config"),
        ({"tool_name": "Bash", "tool_input": {
            "command": "sed -i 's/level: L0/level: L3/' .cfm-workflow.yml"},
          **sub}, 2, "subagent in-place edit of the config"),
        ({"tool_name": "Bash", "tool_input": {
            "command": "echo '{}' > .claude/settings.json"}, **sub}, 2,
         "subagent redirect into the settings denies"),
        # each of these was a verified bypass of the policy rule once
        ({"tool_name": "Bash", "tool_input": {
            "command": "curl -o .cfm-workflow.yml"}, **sub}, 2,
         "subagent download over the config"),
        ({"tool_name": "Bash", "tool_input": {"command": "git apply x.patch"},
          **sub}, 2, "subagent applying an uninspectable patch"),
        ({"tool_name": "Bash", "tool_input": {"command": "tar -xf bundle.tar"},
          **sub}, 2, "subagent extracting an archive into the project"),
        ({"tool_name": "Edit", "tool_input": {
            "file_path": os.path.join(project_dir, ".cfm-workflow.yml")}}, 0,
         "main-session Edit of the config (the /cfm:configure path)"),
        ({"tool_name": "Bash", "tool_input": {"command": "ls -la"}}, 0,
         "harmless command"),
        ({"tool_name": "Bash", "tool_input": {"command": "echo .env >> .gitignore"}},
         0, "naming a secret file without reading it"),
        ({"tool_name": "Bash", "tool_input": {"command": "cat .cfm-workflow.yml"},
          **sub}, 0, "subagent reading the config"),
        # cfm mode: the main session orchestrates; product writes are the
        # coder's. The verdicts flip to 0 when the mode is advisory or off.
        ({"tool_name": "Write", "tool_input": {
            "file_path": os.path.join(project_dir, "src", "cfm-probe.ts"),
            "content": ""}}, product, "main-session Write to product code"),
        ({"tool_name": "Bash", "tool_input": {"command": "echo x > src/cfm-probe.ts"}},
         product, "main-session redirect into product code"),
        ({"tool_name": "Bash", "tool_input": {"command": "cp x src/cfm-probe.ts"}},
         product, "main-session copy into product code"),
        ({"tool_name": "Write", "tool_input": {
            "file_path": os.path.join(project_dir, "docs", "plans", "cfm-probe.md"),
            "content": ""}}, 0, "main-session Write to docs/ (an orchestrator root)"),
        ({"tool_name": "Write", "tool_input": {
            "file_path": os.path.join(project_dir, "src", "cfm-probe.ts"),
            "content": ""}, **sub}, 0, "subagent Write to product code"),
        ({"tool_name": "Bash", "tool_input": {
            "command": f"python3 {PLUGIN_ROOT}/scripts/state.py --project-dir . show"}},
         0, "main session running a plugin script"),
        ({"tool_name": "Bash", "tool_input": {"command": "ls 2>&1"}}, 0,
         "a descriptor dup is not a file write"),
    ]
    self_test_ok = True
    for event_dict, expected, label in probes:
        event = json.dumps(event_dict)
        try:
            result = subprocess.run(
                ["bash", guard], input=event, capture_output=True, text=True,
                timeout=20, env=env,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            check.failures.append(f"guard self-test could not run ({exc})")
            self_test_ok = False
            break
        if result.returncode != expected:
            self_test_ok = False
            check.failures.append(
                f"guard self-test: {label} exited {result.returncode}, expected "
                f"{expected} — the PreToolUse guard is not deciding correctly"
                + (f" ({result.stderr.strip()[:120]})" if result.stderr.strip() else "")
            )
    if self_test_ok:
        orchestrator = (
            "the main session's product writes (Write, redirect, copy) blocked "
            "while its docs/ write and plugin-script runs are allowed"
            if enforced else
            f"cfm mode is {mode}, so the main session's product writes pass")
        check.notes.append(
            f"guard self-test: secret read (path, stdin, glued redirect, git "
            f"blob spec), secret Read, default-branch push, git env alias, "
            f"and subagent writes to the config and settings (edit, "
            f"redirect, download, patch, archive) all blocked; harmless "
            f"calls and the main session's config edit allowed; "
            f"{orchestrator} ({len(probes)} synthetic events)")

    # cfm mode's prose half: the session-context hook must produce the
    # context, or the mode is a guard without a doctrine
    _check_session_context(check, project_dir, env, mode)

    # the probes above INJECT agent_id; this proves real subagent events
    # carry it. The guard records the first one it sees; a phase that
    # dispatched agents without a sighting means the policy-file layer
    # never fired on a real event.
    marker = os.path.join(project_dir, guard_check.SUBAGENT_OBSERVED_REL)
    dispatched = 0
    state_rel = config.get("state_file")
    if isinstance(state_rel, str) and state_rel:
        state, _error = state_mod.load_state(os.path.join(project_dir, state_rel))
        if isinstance(state, dict):
            dispatches = (state.get("tokens") or {}).get("dispatches")
            dispatched = len(dispatches) if isinstance(dispatches, list) else 0
    if os.path.isfile(marker):
        check.notes.append(
            "subagent events observed live: the hook payload carried "
            "agent_id, so the policy-file rule fires on real dispatches")
    elif dispatched:
        check.warnings.append(
            f"{dispatched} dispatches recorded but no subagent event ever "
            f"reached the guard with agent_id — the policy-file layer has "
            f"not been seen to fire on a real event (Claude Code documents "
            f"agent_id/agent_type on hook input inside subagents; check the "
            f"installed version)"
        )
    else:
        check.notes.append(
            "subagent identification (hook agent_id) not yet observed — "
            "verifiable after the first dispatch")

    trigger = (config.get("review") or {}).get("trigger")
    if trigger == "pre-commit":
        if not os.path.isfile(
            os.path.join(project_dir, ".git", "hooks", "pre-commit")
        ):
            check.failures.append(
                "review.trigger is 'pre-commit' but .git/hooks/pre-commit is "
                "not installed — the configured trigger has no teeth"
            )
    elif trigger == "on-stop":
        check.notes.append(
            "review.trigger 'on-stop' is served by the plugin Stop hook "
            "(verified above)"
        )


def _check_session_context(check, project_dir, env, mode):
    script = os.path.join(PLUGIN_ROOT, "scripts", "session_context.sh")
    event = json.dumps({"hook_event_name": "SessionStart",
                        "session_start_reason": "startup"})
    try:
        result = subprocess.run(
            ["bash", script, "SessionStart"], input=event, capture_output=True,
            text=True, timeout=20, env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        check.failures.append(f"session-context self-test could not run ({exc})")
        return
    if result.returncode != 0:
        check.failures.append(
            f"session-context hook exited {result.returncode} — it must never "
            f"block a session" + (f" ({result.stderr.strip()[:120]})"
                                  if result.stderr.strip() else ""))
        return
    if mode == "off":
        if result.stdout.strip():
            check.failures.append(
                "cfm mode is off but the session-context hook still injects "
                "context")
        else:
            check.notes.append("cfm mode: off — no session context, guard "
                               "orchestrator rule silent")
        return
    try:
        payload = json.loads(result.stdout)
        context = payload["hookSpecificOutput"]["additionalContext"]
    except (ValueError, KeyError, TypeError):
        check.failures.append(
            "session-context hook printed no additionalContext JSON — the "
            "orchestrator doctrine never reaches the session")
        return
    if f"cfm mode: {mode.upper()}" not in context:
        check.failures.append(
            f"session-context hook does not announce cfm mode '{mode}'")
        return
    check.notes.append(
        f"cfm mode: {mode} — session context injected at start/resume/"
        f"compact, routing through /cfm:* skills"
        + ("" if mode == "enforced" else
           "; the guard's orchestrator rule is silent (advisory)"))

    settings_path = os.path.join(project_dir, gen_settings.SETTINGS_REL)
    try:
        settings = gen_settings.read_settings(settings_path)
    except (OSError, ValueError):
        return
    managed = gen_settings.read_managed_statusline(
        os.path.join(project_dir, gen_settings.MANAGED_REL))
    owner = gen_settings.statusline_owner(settings, managed)
    if owner == "cfm":
        command = gen_settings.current_statusline(settings)
        if os.path.isfile(command):
            check.notes.append("cfm status line on (mode and phase in the status bar)")
        else:
            check.warnings.append(
                f"cfm status line points at {command}, which no longer exists "
                f"(plugin moved?) — re-run gen_settings --statusline --write")
    elif owner == "user":
        check.notes.append("status line: the project's own (cfm's is available "
                           "via gen_settings --statusline --write)")
    else:
        check.notes.append("status line off (opt-in: gen_settings --statusline --write)")


def check_9_state(check, project_dir, config):
    if config is None:
        check.skipped = True
        return
    state_rel = config.get("state_file")
    if not isinstance(state_rel, str) or not state_rel:
        return  # typed wrong is a check-1 schema error
    state_path = os.path.join(project_dir, state_rel)
    if not os.path.exists(state_path):
        check.notes.append(f"{state_rel} absent — no phase started yet")
        return
    state, error = state_mod.load_state(state_path)
    if error:
        check.failures.append(f"{state_rel}: {error}")
        return
    # the same validator scripts/state.py runs before every write, so a
    # failure here means the file was hand-edited or written by something else
    errors, warnings = state_mod.validate_state(state, config)
    check.failures.extend(f"{state_rel}: {e}" for e in errors)
    check.warnings.extend(f"{state_rel}: {w}" for w in warnings)
    phase = state.get("phase")
    if isinstance(phase, dict) and phase.get("status") == "in-flight":
        plan = phase.get("plan")
        if isinstance(plan, str) and plan \
                and not os.path.exists(os.path.join(project_dir, plan)):
            check.failures.append(
                f"orphaned in-flight phase references missing plan {plan}"
            )
    if not check.failures:
        check.notes.append(f"{state_rel} is schema-valid (v1); no orphaned in-flight phase")


def run_doctor(project_dir):
    config, cfg_errors, cfg_warnings = cfm_config.load(project_dir)

    checks = []

    env = Check(0, "environment")
    check_0_environment(env, project_dir, config)
    checks.append(env)

    schema = Check(1, "schema & invariants")
    check_1_schema(schema, cfg_errors, cfg_warnings)
    checks.append(schema)

    paths = Check(2, "paths")
    check_2_paths(paths, project_dir, config)
    checks.append(paths)

    commands = Check(3, "commands")
    check_3_commands(commands, project_dir, config)
    checks.append(commands)

    roster = Check(4, "roster coherence")
    check_4_roster(roster, project_dir, config)
    checks.append(roster)

    models = Check(5, "models")
    check_5_models(models, project_dir, config)
    checks.append(models)

    rules = Check(6, "rules have teeth")
    check_6_rules(rules, project_dir, config)
    checks.append(rules)

    secrets = Check(7, "secrets hygiene")
    check_7_secrets(secrets, project_dir, config, cfg_errors)
    checks.append(secrets)

    pipeline = Check(8, "pipeline wiring")
    check_8_pipeline(pipeline, project_dir, config)
    checks.append(pipeline)

    state = Check(9, "state")
    check_9_state(state, project_dir, config)
    checks.append(state)

    return checks


def render(checks):
    lines = ["cfm doctor"]
    for check in checks:
        lines.append(f"[{check.status}] #{check.id} {check.name}")
        for failure in check.failures:
            lines.append(f"    ✘ {failure}")
        for warning in check.warnings:
            lines.append(f"    ⚠ {warning}")
        for note in check.notes:
            lines.append(f"    · {note}")
    failed = [c for c in checks if c.status == "FAIL"]
    lines.append(
        "verdict: " + ("UNHEALTHY — fix the failures above" if failed else "healthy")
    )
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="cfm doctor — config↔reality checks")
    parser.add_argument("--project-dir", default=".", help="project root (default: .)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    project_dir = os.path.abspath(args.project_dir)
    checks = run_doctor(project_dir)
    ok = all(c.status != "FAIL" for c in checks)

    if args.json:
        json.dump({"ok": ok, "checks": [c.as_dict() for c in checks]},
                  sys.stdout, indent=2)
        print()
    else:
        print(render(checks))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
