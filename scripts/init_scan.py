#!/usr/bin/env python3
"""cfm init scan — deterministic repo evidence for scenario detection.

cfm:init calls this to classify the project (greenfield / existing /
scaffolded / adoption / already-initialized) and to collect the evidence
that beats LLM proposals during command derivation. Pure read, no writes.

Usage: python3 init_scan.py [--project-dir DIR]   (always JSON on stdout)
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys

MANIFESTS = [
    "package.json", "pyproject.toml", "setup.py", "requirements.txt",
    "go.mod", "Cargo.toml", "composer.json", "Gemfile", "pom.xml",
    "build.gradle", "build.gradle.kts", "mix.exs", "pubspec.yaml",
    "Makefile", "justfile", "Taskfile.yml",
]
MANIFEST_GLOBS = ["*.csproj", "*.sln", "*.fsproj"]

CI_PATHS = [
    ".github/workflows", ".gitlab-ci.yml", ".circleci/config.yml",
    "azure-pipelines.yml", "Jenkinsfile", "bitbucket-pipelines.yml",
    ".travis.yml",
]

LOCKFILES = [
    "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb",
    "poetry.lock", "uv.lock", "Pipfile.lock", "go.sum", "Cargo.lock",
    "composer.lock", "Gemfile.lock",
]

SOURCE_EXTENSIONS = {
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".py", ".go", ".rs", ".cs",
    ".php", ".rb", ".java", ".kt", ".ex", ".exs", ".dart", ".vue",
    ".svelte", ".c", ".cc", ".cpp", ".h", ".swift", ".scala", ".sql",
}

IGNORE_DIRS = {
    ".git", "node_modules", "vendor", "dist", "build", "out", "target",
    ".venv", "venv", "__pycache__", ".next", ".nuxt", ".turbo", "coverage",
    ".idea", ".vscode", "bin", "obj",
}

# Source files under this count reads as scaffold boilerplate, not features.
SCAFFOLD_THRESHOLD = 15

# Doc-candidate matching: where existing repos keep a progress/status ledger
# or a coding-rules file under a name cfm's defaults would never find.
# Searched shallowly, in this order (root first — earlier dir wins ties).
DOC_DIRS = ["", "docs", "doc", ".github"]
PROGRESS_STRONG = re.compile(
    r"^(progress|status|journal|devlog|history|worklog)\.md$", re.IGNORECASE)
RULES_STRONG = re.compile(
    r"(rule|convention|guideline|styleguide|style-guide)", re.IGNORECASE)


def _exists(root, rel):
    return os.path.exists(os.path.join(root, rel))


def scan_claude_setup(root):
    setup = {
        "claude_md": [],
        "agents": [],
        "commands": [],
        "skills": [],
        "rules": [],
        "settings": [],
    }
    for md in glob.glob(os.path.join(root, "CLAUDE.md")) + \
              glob.glob(os.path.join(root, "**", "CLAUDE.md"), recursive=True):
        rel = os.path.relpath(md, root)
        if not any(part in IGNORE_DIRS for part in rel.split(os.sep)):
            setup["claude_md"].append(rel)
    for key, pattern in (
        ("agents", ".claude/agents/*.md"),
        ("commands", ".claude/commands/*.md"),
        ("skills", ".claude/skills/*/SKILL.md"),
        ("rules", ".claude/rules/*.md"),
        ("settings", ".claude/settings*.json"),
    ):
        setup[key] = sorted(
            os.path.relpath(p, root)
            for p in glob.glob(os.path.join(root, pattern))
        )
    setup["claude_md"] = sorted(set(setup["claude_md"]))
    return setup


def scan_doc_candidates(root):
    """Existing files that could BE the progress_log / rules_file.

    Strong candidates (exact/primary names) sort before weak ones
    (CHANGELOG.md is releases, not a work ledger; CONTRIBUTING.md is
    process, not rules). `.claude/rules/*.md` is deliberately excluded —
    the claude_setup signal already lists those; this covers everywhere
    else. Pure read.
    """
    progress_strong, progress_weak = [], []
    rules_strong, rules_weak = [], []
    for sub in DOC_DIRS:
        base = os.path.join(root, sub) if sub else root
        if sub in IGNORE_DIRS or not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            if not name.lower().endswith(".md") \
                    or not os.path.isfile(os.path.join(base, name)):
                continue
            rel = os.path.join(sub, name) if sub else name
            lowered = name.lower()
            if PROGRESS_STRONG.match(lowered):
                progress_strong.append(rel)
            elif lowered == "changelog.md":
                progress_weak.append(rel)
            if lowered == "contributing.md":
                rules_weak.append(rel)
            elif RULES_STRONG.search(lowered[:-3]):
                rules_strong.append(rel)
    return {
        "progress": progress_strong + progress_weak,
        "rules": rules_strong + rules_weak,
    }


def count_files(root):
    source, tests = 0, 0
    top_dirs = []
    for current, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]
        if current == root:
            top_dirs = sorted(dirs)
        for name in files:
            ext = os.path.splitext(name)[1].lower()
            if ext not in SOURCE_EXTENSIONS:
                continue
            source += 1
            lowered = name.lower()
            rel_dir = os.path.relpath(current, root)
            if ".test." in lowered or ".spec." in lowered or "_test" in lowered \
                    or lowered.startswith("test_") \
                    or any(part in ("tests", "test", "__tests__", "e2e", "spec")
                           for part in rel_dir.split(os.sep)):
                tests += 1
    return source, tests, top_dirs


def package_json_scripts(root):
    path = os.path.join(root, "package.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh).get("scripts", {}) or {}
    except (OSError, json.JSONDecodeError):
        return {}


def scan(root):
    manifests = [m for m in MANIFESTS if _exists(root, m)]
    for pattern in MANIFEST_GLOBS:
        manifests.extend(
            sorted(os.path.relpath(p, root)
                   for p in glob.glob(os.path.join(root, "**", pattern),
                                      recursive=True)
                   if not any(part in IGNORE_DIRS
                              for part in os.path.relpath(p, root).split(os.sep)))
        )

    ci_files = []
    for ci in CI_PATHS:
        full = os.path.join(root, ci)
        if os.path.isdir(full):
            ci_files.extend(
                sorted(os.path.relpath(p, root)
                       for p in glob.glob(os.path.join(full, "*.yml"))
                       + glob.glob(os.path.join(full, "*.yaml")))
            )
        elif os.path.exists(full):
            ci_files.append(ci)

    source_files, test_files, top_dirs = count_files(root)
    claude_setup = scan_claude_setup(root)
    has_claude_setup = any(claude_setup[k] for k in claude_setup)

    signals = {
        "has_cfm_config": _exists(root, ".cfm-workflow.yml"),
        "git_repo": os.path.isdir(os.path.join(root, ".git")),
        "manifests": manifests,
        "lockfiles": [l for l in LOCKFILES if _exists(root, l)],
        "ci_files": ci_files,
        "package_json_scripts": package_json_scripts(root),
        "source_files": source_files,
        "test_files": test_files,
        "top_dirs": top_dirs,
        "claude_setup": claude_setup,
        "doc_candidates": scan_doc_candidates(root),
    }

    if signals["has_cfm_config"]:
        scenario = "already-initialized"
    elif has_claude_setup:
        scenario = "adoption"
    elif not manifests and source_files == 0:
        scenario = "greenfield"
    elif source_files < SCAFFOLD_THRESHOLD:
        scenario = "scaffolded"
    else:
        scenario = "existing"

    return {
        "scenario": scenario,
        "scenario_note": (
            "scaffolded-vs-existing is a heuristic "
            f"(threshold: {SCAFFOLD_THRESHOLD} source files) — confirm with the user"
            if scenario in ("scaffolded", "existing") else ""
        ),
        "signals": signals,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="cfm init — repo evidence scan")
    parser.add_argument("--project-dir", default=".", help="project root (default: .)")
    args = parser.parse_args(argv)
    json.dump(scan(os.path.abspath(args.project_dir)), sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
