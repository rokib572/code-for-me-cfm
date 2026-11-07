#!/usr/bin/env python3
"""cfm upgrade — report where a project's config lags the installed plugin.

A PURE READ: it never writes. It reports only what the doctor does not
already check — keys the plugin no longer knows, settings the file leaves
on a default, roster agents added since init, the schema and min_version
stamp, and repo packages and scripts the config never heard of. /cfm:upgrade turns each finding into a diff the user approves.

Usage: python3 upgrade.py [--project-dir DIR] [--json]
Exit code: 0 report rendered, 1 config missing or unparseable.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cfm_config
from doctor import PLUGIN_ROOT, _plugin_version, _version_tuple
from init_scan import IGNORE_DIRS, MANIFESTS, package_json_scripts

ROSTER = os.path.join(PLUGIN_ROOT, "templates", "roster.yml")
# what the file may carry beyond DEFAULTS' own keys
EXTRA_TOP_KEYS = ("cfm", "layers", "project_context")
CFM_KEYS = {"schema_version": None, "requires": {"surface": None, "min_version": None}}
AGENT_FIELDS = ("enabled", "purpose", "model", "tier", "autonomy", "tools",
                "owns_commands", "layers")


def _schema():
    """Known keys as a nested dict; a non-dict value marks a leaf."""
    known = dict(cfm_config.DEFAULTS)
    known.update({key: None for key in EXTRA_TOP_KEYS})
    known["cfm"] = CFM_KEYS
    return known


def unknown_keys(raw, known, prefix=""):
    """Dotted paths in the file the plugin no longer (or never) knew.
    Only sections whose keys cfm fixes are walked — agents, commands, and
    feature_roots are user-named and checked elsewhere."""
    found = []
    for key, value in raw.items():
        dotted = f"{prefix}.{key}" if prefix else str(key)
        if key not in known:
            found.append(dotted)
        elif isinstance(known[key], dict) and known[key] and isinstance(value, dict):
            found.extend(unknown_keys(value, known[key], dotted))
    return found


def defaulted_keys(raw):
    """Scalar settings the file leaves on the plugin default — usually ones
    added after the config was written."""
    found = []
    for dotted in cfm_config.leaf_paths(cfm_config.DEFAULTS):
        default = cfm_config.DEFAULTS
        node = raw
        for part in dotted.split("."):
            default = default[part]
            node = node.get(part) if isinstance(node, dict) else None
        if isinstance(default, (list, dict)) or node is not None:
            continue
        found.append({"key": dotted, "default": default})
    return found


def agent_findings(raw):
    """Roster agents the config never received, enabled agents carrying
    fields the roster no longer defines, and the enabled agents' models."""
    with open(ROSTER, encoding="utf-8") as fh:
        roster = cfm_config.yaml.safe_load(fh)
    agents = raw.get("agents") if isinstance(raw.get("agents"), dict) else {}
    layer_names = {layer.get("name") for layer in raw.get("layers") or []
                   if isinstance(layer, dict)}
    new = []
    for name, entry in roster.items():
        if name in agents:
            continue
        wanted = entry.get("layers") or []
        matched = sorted(layer_names) if "any" in wanted else \
            sorted(layer_names & set(wanted))
        if matched:
            new.append({"agent": name, "entry": dict(entry, layers=matched)})
    # a disabled agent stays out of the flow — it is the user's choice, not
    # a gap, so it is neither "new" (above) nor checked here
    live = {name: agent for name, agent in agents.items()
            if isinstance(agent, dict) and agent.get("enabled") is not False}
    retired = [f"agents.{name}.{field}" for name, agent in live.items()
               for field in agent if field not in AGENT_FIELDS]
    return new, retired, {name: agent.get("model") for name, agent in live.items()}


def repo_findings(project_dir, raw):
    """What the repo has that the config never heard of: packages (a
    manifest one or two levels down) outside every layer, and root
    package.json scripts no command slot runs."""
    layer_paths = [os.path.normpath(layer["path"]) for layer in raw.get("layers") or []
                   if isinstance(layer, dict) and isinstance(layer.get("path"), str)]
    packages = set()
    for manifest in MANIFESTS:
        for pattern in ("*", os.path.join("*", "*")):
            for path in glob.glob(os.path.join(project_dir, pattern, manifest)):
                rel = os.path.relpath(os.path.dirname(path), project_dir)
                if any(part in IGNORE_DIRS or part.startswith(".")
                       for part in rel.split(os.sep)):
                    continue
                if not any(rel == p or rel.startswith(p + os.sep) for p in layer_paths):
                    packages.add(rel.replace(os.sep, "/"))
    commands = raw.get("commands") if isinstance(raw.get("commands"), dict) else {}
    used = " ".join(cmd for slot in commands
                    for cmd in cfm_config.slot_commands(raw, slot))
    unused = [name for name in package_json_scripts(project_dir)
              if not re.search(rf"(?<![\w:-]){re.escape(name)}(?![\w:-])", used)]
    return {"unlayered_packages": sorted(packages), "unused_scripts": unused}


def report(project_dir):
    errors = []
    path = os.path.join(project_dir, cfm_config.CONFIG_FILE)
    if cfm_config.yaml is None:
        return None, ["PyYAML is not installed. Fix: pip install pyyaml"]
    if not os.path.exists(path):
        return None, [f"{cfm_config.CONFIG_FILE} not found — run /cfm:init"]
    raw = cfm_config._read_yaml(path, errors)
    if raw is None:
        return None, errors

    requires = (raw.get("cfm") or {}).get("requires") or {}
    plugin, stamp = _plugin_version(), requires.get("min_version")
    behind = bool(plugin) and (
        not stamp or (_version_tuple(str(stamp)) or ()) < (_version_tuple(plugin) or ()))
    new_agents, retired_fields, models = agent_findings(raw)
    return {
        "schema": {
            "file": (raw.get("cfm") or {}).get("schema_version"),
            "latest": max(cfm_config.SUPPORTED_SCHEMA_VERSIONS),
        },
        "plugin_version": plugin,
        "min_version": stamp,
        "stamp_behind": behind,
        "unknown_keys": unknown_keys(raw, _schema()) + retired_fields,
        "defaulted_keys": defaulted_keys(raw),
        "new_agents": new_agents,
        "models": models,
        "repo": repo_findings(project_dir, raw),
    }, []


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="cfm upgrade — report config drift against the installed plugin"
    )
    parser.add_argument("--project-dir", default=".", help="project root (default: .)")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args(argv)

    result, errors = report(os.path.abspath(args.project_dir))
    if result is None:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    if args.json:
        json.dump(result, sys.stdout, indent=2)
        print()
        return 0

    schema = result["schema"]
    print(f"cfm upgrade — plugin {result['plugin_version']}, "
          f"schema {schema['file']} (latest {schema['latest']})")
    print(f"  min_version: {result['min_version'] or 'unset'}"
          + (" — behind the installed plugin" if result["stamp_behind"] else ""))
    for key in result["unknown_keys"]:
        print(f"  unknown     {key} — not part of the current schema")
    for item in result["defaulted_keys"]:
        print(f"  defaulted   {item['key']} = {json.dumps(item['default'])}")
    for item in result["new_agents"]:
        print(f"  new agent   {item['agent']} — layers {item['entry']['layers']}")
    for package in result["repo"]["unlayered_packages"]:
        print(f"  unlayered   {package} — a package no layer covers")
    for script in result["repo"]["unused_scripts"]:
        print(f"  script      {script} — package.json script no command slot runs")
    for name, model in result["models"].items():
        print(f"  model       {name}: {model}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
