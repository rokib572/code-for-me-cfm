#!/usr/bin/env python3
"""cfm configuration — schema v2 loader, merger, and validator.

This module is the single mechanical source of truth for the shape of
.cfm-workflow.yml. Everything that consumes config (doctor.py, future
cfm scripts) imports from here — never reimplement parsing or validation
elsewhere.

Requires python3 + PyYAML; doctor check #0 reports a friendly fix if absent.
"""

from __future__ import annotations

import argparse
import copy
import fnmatch
import json
import os
import sys

try:
    import yaml
except ImportError:  # surfaced by doctor check #0 with an install hint
    yaml = None

CONFIG_FILE = ".cfm-workflow.yml"
LOCAL_CONFIG_FILE = ".cfm-workflow.local.yml"
SUPPORTED_SCHEMA_VERSIONS = (2,)
REQUIRED_SURFACE = "claude-code"

PROFILES = ("supervised", "collaborative", "autonomous")
# cfm mode: enforced = the guard refuses main-session writes to product code
# and the session hooks inject the orchestrator doctrine; advisory = the
# doctrine is injected but the guard stays silent; off = neither. Every
# other guard rule (secrets, git, verify_full, policy files) is unaffected.
MODES = ("enforced", "advisory", "off")
GIT_LEVELS = ("L0", "L1", "L2", "L3")
AGENT_TIERS = ("judgment", "implementation", "mechanical")
AUTONOMY_LEVELS = ("auto", "confirm", "confirm-plan")
REVIEW_TRIGGERS = ("manual", "phase-gate", "on-stop", "pre-commit")
AUTO_SCOPES = ("fast", "full")
# phase = one review pass over the whole phase diff (cross-layer findings
# such as tenancy scoping need the whole picture); layer = a pass per layer
REVIEW_SCOPES = ("phase", "layer")
# the Agent tool's model parameter takes an alias, not a full model id
MODEL_ALIASES = ("fable", "opus", "sonnet", "haiku")
CLAUDE_MD_LAYOUTS = ("single", "router")
COMMAND_SLOTS = (
    "lint",
    "lint_arch",
    "typecheck",
    "test_scoped",
    "verify_full",
    "migrate_generate",
    "migrate_apply",
)

# Hard invariant: extendable, never shrinkable. load() unions this list into
# the config, so a file that omits one cannot shrink the set — and adding a
# default here never breaks an existing project's config.
DEFAULT_SECRET_GLOBS = [
    ".env*",
    "*.env",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.jks",
    "*.keystore",
    "id_rsa*",
    "id_dsa*",
    "id_ecdsa*",
    "id_ed25519*",
    ".npmrc",
    ".pypirc",
    ".netrc",
    ".git-credentials",
    ".htpasswd",
    ".pgpass",
    "**/credentials",
    "service-account*.json",
    "secrets.json",
    "secrets.yml",
    "secrets.yaml",
    "secrets.toml",
    "kubeconfig*",
    "*.tfstate",
    "*.tfvars",
]

# Git operations by level. The guard forbids ALL_MUTATING_OPS minus what the
# configured level grants, unioned with the config's own forbidden_ops — so
# the config can only ever extend the forbidden set, never shrink it.
ALL_MUTATING_OPS = [
    "git add", "git commit", "git push", "git reset", "git rebase",
    "git merge", "git stash", "git tag", "git rm", "git mv", "git pull",
    "git checkout", "git switch", "git restore", "git clean",
    "git cherry-pick", "git revert", "git am", "git apply", "git worktree",
    "git submodule", "git remote", "git notes", "git config",
    "gh pr create", "gh pr edit", "gh pr comment", "gh pr close",
    "gh pr review", "gh issue create", "gh issue edit", "gh issue close",
    "gh issue comment", "gh release",
]
GIT_LEVEL_GRANTS = {  # cumulative: L2 grants everything L1 does, and so on
    "L0": [],
    "L1": ["git add", "git commit", "git stash", "git rm", "git mv",
           "git restore", "git cherry-pick", "git revert", "git am",
           "git apply"],
    "L2": ["git push", "git checkout", "git switch", "git pull", "git merge",
           "git rebase", "git tag"],
    "L3": ["gh pr create", "gh pr edit", "gh pr comment", "gh pr review",
           "gh issue create", "gh issue edit", "gh issue comment"],
}
# Blocked at EVERY level, whatever forbidden_ops says: these land on the
# default branch, rewrite history, or reach the host account directly.
ALWAYS_FORBIDDEN_OPS = [
    "gh pr merge", "gh repo delete", "gh repo edit", "gh secret",
    "gh variable", "gh auth", "git filter-branch", "git update-ref",
    "git symbolic-ref", "git replace", "git reflog expire", "git gc",
]


def forbidden_ops_for_level(level):
    granted = []
    for name in GIT_LEVELS:
        granted.extend(GIT_LEVEL_GRANTS.get(name, ()))
        if name == level:
            break
    return [op for op in ALL_MUTATING_OPS if op not in granted]


def forbidden_ops(config):
    """The effective forbidden set: the level's list, extended (never
    shrunk) by whatever the config lists, plus the always-forbidden ops."""
    level = (config.get("git") or {}).get("level")
    if level not in GIT_LEVELS:
        level = DEFAULTS["git"]["level"]
    ops = list(forbidden_ops_for_level(level))
    raw = config.get("forbidden_ops")
    if isinstance(raw, list):
        ops.extend(o.strip() for o in raw if isinstance(o, str) and o.strip())
    ops.extend(ALWAYS_FORBIDDEN_OPS)
    return list(dict.fromkeys(ops))


def model_alias(model):
    """Map a model id to the alias the Agent tool's model parameter takes
    (fable/opus/sonnet/haiku); None when no alias is recognizable."""
    if not isinstance(model, str):
        return None
    lowered = model.lower()
    for alias in MODEL_ALIASES:
        if alias in lowered:
            return alias
    return None

# Dotted key patterns a developer's .cfm-workflow.local.yml may override.
# Model choice and autonomy comfort are personal; everything else is a team
# decision or a hard invariant.
LOCAL_OVERRIDE_ALLOWLIST = (
    "agents.*.model",
    "agents.*.autonomy",
    "implement.plan_gate",
    "token_reporting",
)

DEFAULTS = {
    "profile": "supervised",
    "mode": "enforced",
    "feature_roots": {},
    "claude_md": {"layout": "single", "files": ["CLAUDE.md"]},
    "commands": {},
    "agents": {},
    "review_gates": [],
    "review": {"trigger": "phase-gate", "auto_scope": "full", "scope": "phase"},
    "implement": {"plan_gate": True},
    "git": {
        "level": "L0",
        "branch_prefixes": ["feature/", "project/", "hotfix/", "chore/"],
    },
    "forbidden_ops": [],  # extends the level's list; see forbidden_ops()
    "secret_globs": [],   # extends DEFAULT_SECRET_GLOBS; unioned in load()
    "tenancy": {"scope_field": None},
    "human_gates": [
        "full-test-suite", "git-per-level", "next-phase-start",
        "feature-scope-confirm",
    ],
    "done_criteria": ["tests-green-scoped", "gates-pass", "progress-log-updated"],
    "shared_commands_ack": [],
    "token_reporting": True,
    "tracker": {
        "provider": None,
        "sync": {
            "create_tasks": True,
            "transition_status": True,
            "post_notes": True,
            "fetch_tasks": True,
        },
    },
    "rules_file": ".claude/rules/rules.md",
    "context_file": "CONTEXT.md",
    "progress_log": "docs/PROGRESS.md",
    "state_file": ".cfm/state.json",
}


def deep_merge(base, override):
    """Dicts merge recursively; scalars and lists in override replace base."""
    if not isinstance(base, dict) or not isinstance(override, dict):
        return copy.deepcopy(override)
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def leaf_paths(node, prefix=""):
    """Yield dotted paths of every non-dict leaf in a nested dict."""
    if isinstance(node, dict) and node:
        for key, value in node.items():
            dotted = f"{prefix}.{key}" if prefix else str(key)
            yield from leaf_paths(value, dotted)
    else:
        if prefix:
            yield prefix


def _read_yaml(path, errors):
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        errors.append(f"{os.path.basename(path)}: not valid YAML: {exc}")
        return None
    except OSError as exc:
        errors.append(f"{os.path.basename(path)}: unreadable: {exc}")
        return None
    if data is None:
        errors.append(f"{os.path.basename(path)}: file is empty")
        return None
    if not isinstance(data, dict):
        errors.append(f"{os.path.basename(path)}: top level must be a mapping")
        return None
    return data


def slot_commands(config, slot):
    """Normalize a command slot to a list of command strings ([] if absent)."""
    value = (config.get("commands") or {}).get(slot)
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [v for v in value if isinstance(v, str)]
    return []


def load(project_dir):
    """Load, merge, and validate config.

    Returns (config_or_None, errors, warnings). config is None only when the
    file is missing or unparseable; validation errors still return the merged
    config so downstream checks can degrade gracefully.
    """
    errors, warnings = [], []
    if yaml is None:
        errors.append(
            "PyYAML is not installed — cfm's parser needs it. Fix: pip install pyyaml"
        )
        return None, errors, warnings

    main_path = os.path.join(project_dir, CONFIG_FILE)
    if not os.path.exists(main_path):
        errors.append(f"{CONFIG_FILE} not found in {project_dir} — run /cfm:init")
        return None, errors, warnings

    main = _read_yaml(main_path, errors)
    if main is None:
        return None, errors, warnings

    local_path = os.path.join(project_dir, LOCAL_CONFIG_FILE)
    local = None
    if os.path.exists(local_path):
        local = _read_yaml(local_path, errors)
    if local:
        violations = [
            path
            for path in leaf_paths(local)
            if not any(fnmatch.fnmatch(path, pat) for pat in LOCAL_OVERRIDE_ALLOWLIST)
        ]
        if violations:
            allowed = ", ".join(LOCAL_OVERRIDE_ALLOWLIST)
            for path in violations:
                errors.append(
                    f"{LOCAL_CONFIG_FILE}: override of '{path}' is not permitted "
                    f"(local overrides are limited to: {allowed})"
                )
            local = None  # invariant: reject the whole local file, keep team config

    # YAML 1.1 reads a bare `off` as boolean false; `mode: off` means "off"
    if main.get("mode") is False:
        main["mode"] = "off"
    config = deep_merge(DEFAULTS, main)
    if local:
        config = deep_merge(config, local)

    # Hard invariant 2, mechanically: the default globs are always present.
    # A file that lists a subset gets them back and a warning, not an error
    # that would strand every existing project whenever a default is added.
    listed = config.get("secret_globs")
    listed = [g for g in listed if isinstance(g, str)] if isinstance(listed, list) else []
    if "secret_globs" in main and isinstance(main.get("secret_globs"), list):
        omitted = [g for g in DEFAULT_SECRET_GLOBS if g not in listed]
        if omitted:
            warnings.append(
                "secret_globs: re-added default globs the file omits "
                f"(extendable, never shrinkable — hard invariant): {omitted}"
            )
    config["secret_globs"] = list(dict.fromkeys(listed + DEFAULT_SECRET_GLOBS))

    validate(config, errors, warnings)
    return config, errors, warnings


def _expect(config, dotted, types, errors, required=True, enum=None):
    """Fetch config[dotted], checking presence, type, and enum membership."""
    node = config
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            if required:
                errors.append(f"{dotted}: required field is missing")
            return None
        node = node[part]
    if types and not isinstance(node, types):
        names = "/".join(t.__name__ for t in types)
        errors.append(f"{dotted}: expected {names}, got {type(node).__name__}")
        return None
    if enum and node not in enum:
        errors.append(f"{dotted}: '{node}' is not one of {list(enum)}")
        return None
    return node


def _require_relative(field, value, errors):
    """Config paths must stay inside the project — no absolutes, no '..'."""
    if not isinstance(value, str):
        return
    parts = value.replace("\\", "/").split("/")
    if os.path.isabs(value) or ".." in parts:
        errors.append(f"{field}: must be a relative path inside the project")


def validate(config, errors, warnings):
    """Schema v2 validation, including the hard invariants (plan §4)."""
    version = _expect(config, "cfm.schema_version", (int,), errors)
    if version is not None and version not in SUPPORTED_SCHEMA_VERSIONS:
        errors.append(
            f"cfm.schema_version: {version} unsupported "
            f"(supported: {list(SUPPORTED_SCHEMA_VERSIONS)})"
        )

    # Hard invariant 4: Claude Code only.
    surface = _expect(config, "cfm.requires.surface", (str,), errors)
    if surface is not None and surface != REQUIRED_SURFACE:
        errors.append(
            f"cfm.requires.surface: must be '{REQUIRED_SURFACE}' "
            f"(hard invariant — cfm runs only in Claude Code), got '{surface}'"
        )
    _expect(config, "cfm.requires.min_version", (str,), errors, required=False)

    _expect(config, "profile", (str,), errors, enum=PROFILES)
    _expect(config, "mode", (str,), errors, enum=MODES)

    context = _expect(config, "project_context", (str,), errors)
    if context is not None and not context.strip():
        errors.append("project_context: must be a non-empty paragraph")

    layer_names = []
    layers = _expect(config, "layers", (list,), errors)
    if layers is not None:
        if not layers:
            errors.append("layers: at least one layer is required")
        for i, layer in enumerate(layers):
            if not isinstance(layer, dict) or not isinstance(layer.get("name"), str) \
                    or not isinstance(layer.get("path"), str):
                errors.append(f"layers[{i}]: must be {{name: <str>, path: <str>}}")
                continue
            _require_relative(f"layers[{i}].path", layer["path"], errors)
            layer_names.append(layer["name"])
        dupes = {n for n in layer_names if layer_names.count(n) > 1}
        if dupes:
            errors.append(f"layers: duplicate layer names: {sorted(dupes)}")

    roots = _expect(config, "feature_roots", (dict,), errors, required=False)
    if roots:
        for name, template in roots.items():
            if layer_names and name not in layer_names:
                errors.append(f"feature_roots.{name}: no layer named '{name}'")
            if not isinstance(template, str) or "{feature}" not in template:
                errors.append(
                    f"feature_roots.{name}: must be a string containing {{feature}}"
                )
            else:
                _require_relative(f"feature_roots.{name}", template, errors)

    _expect(config, "claude_md.layout", (str,), errors, enum=CLAUDE_MD_LAYOUTS)
    md_files = _expect(config, "claude_md.files", (list,), errors)
    if md_files is not None:
        if not md_files:
            errors.append("claude_md.files: must list at least one CLAUDE.md path")
        for i, entry in enumerate(md_files):
            _require_relative(f"claude_md.files[{i}]", entry, errors)

    commands = _expect(config, "commands", (dict,), errors)
    if commands is not None:
        for slot, value in commands.items():
            if slot not in COMMAND_SLOTS:
                warnings.append(
                    f"commands.{slot}: not a standard slot "
                    f"(standard: {', '.join(COMMAND_SLOTS)}) — kept as custom"
                )
            ok_str = isinstance(value, str) and value.strip()
            ok_list = isinstance(value, list) and value and all(
                isinstance(v, str) and v.strip() for v in value
            )
            if not (ok_str or ok_list):
                errors.append(
                    f"commands.{slot}: must be a non-empty command string or list of them"
                )

    agents = _expect(config, "agents", (dict,), errors)
    if agents is not None:
        for name, agent in agents.items():
            prefix = f"agents.{name}"
            if not isinstance(agent, dict):
                errors.append(f"{prefix}: must be a mapping")
                continue
            agent_errors = []
            _expect(agent, "enabled", (bool,), agent_errors)
            _expect(agent, "purpose", (str,), agent_errors)
            _expect(agent, "model", (str,), agent_errors)
            _expect(agent, "tier", (str,), agent_errors, enum=AGENT_TIERS)
            _expect(agent, "autonomy", (str,), agent_errors, enum=AUTONOMY_LEVELS)
            _expect(agent, "tools", (list,), agent_errors)
            _expect(agent, "owns_commands", (list,), agent_errors, required=False)
            agent_layers = _expect(agent, "layers", (list,), agent_errors)
            if agent_layers and layer_names:
                for lname in agent_layers:
                    if lname not in layer_names:
                        agent_errors.append(f"layers: no layer named '{lname}'")
            errors.extend(f"{prefix}.{err}" for err in agent_errors)

    gates = _expect(config, "review_gates", (list,), errors)
    if gates is not None and agents is not None:
        flat = []
        for entry in gates:
            flat.extend(entry if isinstance(entry, list) else [entry])
        for gate in flat:
            if not isinstance(gate, str) or gate not in agents:
                errors.append(f"review_gates: '{gate}' is not a configured agent")

    _expect(config, "review.trigger", (str,), errors, enum=REVIEW_TRIGGERS)
    _expect(config, "review.auto_scope", (str,), errors, enum=AUTO_SCOPES)
    _expect(config, "review.scope", (str,), errors, enum=REVIEW_SCOPES)
    _expect(config, "implement.plan_gate", (bool,), errors)
    _expect(config, "git.level", (str,), errors, enum=GIT_LEVELS)
    prefixes = _expect(config, "git.branch_prefixes", (list,), errors)
    if prefixes is not None:
        for p in prefixes:
            if not isinstance(p, str) or not p.endswith("/"):
                errors.append(f"git.branch_prefixes: '{p}' must be a string ending in '/'")

    # Hard invariant 2: secret_globs is extendable, never shrinkable — load()
    # unions the defaults in; here only the shape is checked.
    globs = _expect(config, "secret_globs", (list,), errors)
    if globs is not None:
        for g in globs:
            if not isinstance(g, str) or not g.strip():
                errors.append(f"secret_globs: entries must be non-empty strings, got {g!r}")
    ops = _expect(config, "forbidden_ops", (list,), errors, required=False)
    if ops:
        for op in ops:
            if not isinstance(op, str) or not op.strip():
                errors.append(f"forbidden_ops: entries must be command strings, got {op!r}")

    ack = _expect(config, "shared_commands_ack", (list,), errors, required=False)
    if ack:
        for entry in ack:
            if not isinstance(entry, str):
                errors.append(
                    f"shared_commands_ack: entries must be command-slot strings, "
                    f"got {type(entry).__name__}"
                )

    _expect(config, "token_reporting", (bool,), errors)

    # Tracker: a provider name and boolean sync flags. Three flags are
    # outbound (cfm writes to the tracker), fetch_tasks is the inbound one.
    provider = config.get("tracker", {}).get("provider")
    if provider is not None and not isinstance(provider, str):
        errors.append(
            f"tracker.provider: expected str or null, got {type(provider).__name__}"
        )
    elif isinstance(provider, str) and not provider.strip():
        errors.append("tracker.provider: must be a provider name or null, not empty")
    for flag in ("create_tasks", "transition_status", "post_notes", "fetch_tasks"):
        _expect(config, f"tracker.sync.{flag}", (bool,), errors)

    for field in ("rules_file", "context_file", "progress_log", "state_file"):
        value = _expect(config, field, (str,), errors)
        _require_relative(field, value, errors)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="cfm config schema v2 — parse, merge, validate .cfm-workflow.yml"
    )
    parser.add_argument("--project-dir", default=".", help="project root (default: .)")
    parser.add_argument("--json", action="store_true",
                        help="print the merged, validated config as JSON")
    parser.add_argument("--get", metavar="KEY",
                        help="print one dotted key of the merged, validated config "
                             "(empty when unset), e.g. review.trigger")
    args = parser.parse_args(argv)

    config, errors, warnings = load(args.project_dir)
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    if args.json and config is not None and not errors:
        json.dump(config, sys.stdout, indent=2)
        print()
    if args.get and isinstance(config, dict) and not errors:
        value = config
        for part in args.get.split("."):
            value = value.get(part) if isinstance(value, dict) else None
        print("" if value is None else value)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
