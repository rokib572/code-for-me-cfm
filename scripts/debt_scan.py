#!/usr/bin/env python3
"""cfm debt scan — harvest `cfm-debt:` markers into a ledger.

A deliberate shortcut with a known ceiling is fine; losing track of it is
not. The coder marks the line it cut a corner on:

    # cfm-debt: global lock, per-account locks if throughput matters

This collects every marker so a deferral cannot quietly become permanent,
and flags the ones naming no upgrade trigger — those are the rot risk.

Consumed by cfm:status (its Carried-forward section) and by
cfm:implement-phase at the phase gate. Pure read, no writes, always JSON on
stdout.

Known limit: a comment-prefixed marker in documentation is indistinguishable
from a real one, because being plainly greppable is the point. A repo that
documents this convention in code comments will see its own examples in a
whole-repo scan. The phase gate is unaffected — it passes --paths, scoped to
the files the phase touched. Filtering docs would need a config nobody would
set, so it stays a documented limit rather than machinery.

Usage: python3 debt_scan.py [--project-dir DIR] [--paths FILE ...]
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cfm_config import DEFAULT_SECRET_GLOBS, load  # noqa: E402

MARKER = "cfm-debt:"

# `<comment-prefix> cfm-debt: <ceiling>, <upgrade trigger>`. The comment
# prefix is required so prose merely naming the convention (this docstring,
# the skills that define it) stays out of the ledger.
MARKER_RE = re.compile(
    r"(?:#|//|--|/\*|\*|<!--|;|%)\s*" + re.escape(MARKER) + r"\s*(?P<body>.*?)\s*(?:\*/|-->)?\s*$"
)

IGNORE_DIRS = {
    ".git", "node_modules", "vendor", "dist", "build", "out", "target",
    ".venv", "venv", "__pycache__", ".next", ".nuxt", ".turbo", "coverage",
    ".idea", ".vscode", "bin", "obj", ".mypy_cache", ".pytest_cache",
}

# Binary and generated files carry no markers worth reading.
SKIP_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".pdf", ".zip", ".gz",
    ".tar", ".woff", ".woff2", ".ttf", ".eot", ".mp4", ".mp3", ".wasm",
    ".pyc", ".so", ".dylib", ".dll", ".exe", ".lock",
}

MAX_BYTES = 2_000_000  # a file larger than this is generated, not authored


def secret_globs(project_dir):
    """Config's globs when the config loads, defaults otherwise.

    A broken config must not disable the skip — falling back to the defaults
    keeps the scan from reading a .env while the user fixes their YAML.
    """
    try:
        config, _errors, _warnings = load(project_dir)
    except Exception:
        return list(DEFAULT_SECRET_GLOBS)
    if not isinstance(config, dict):
        return list(DEFAULT_SECRET_GLOBS)
    globs = config.get("secret_globs")
    return list(globs) if isinstance(globs, list) else list(DEFAULT_SECRET_GLOBS)


def is_secret(rel, globs):
    base = os.path.basename(rel)
    return any(fnmatch.fnmatch(rel, g) or fnmatch.fnmatch(base, g) for g in globs)


def split_body(body):
    """`<ceiling>, <upgrade trigger>` — first comma splits the two halves.

    A marker naming only a ceiling has no trigger, which is precisely the
    shape that rots into "later means never".
    """
    body = body.strip().rstrip(".")
    if not body:
        return "", "", True
    ceiling, sep, upgrade = body.partition(",")
    ceiling, upgrade = ceiling.strip(), upgrade.strip()
    return ceiling, upgrade, not (sep and upgrade)


def scan_file(path, rel):
    records = []
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for number, line in enumerate(fh, 1):
                match = MARKER_RE.search(line)
                if not match:
                    continue
                ceiling, upgrade, no_trigger = split_body(match.group("body"))
                records.append({
                    "file": rel,
                    "line": number,
                    "ceiling": ceiling,
                    "upgrade": upgrade,
                    "no_trigger": no_trigger,
                })
    except OSError:
        pass
    return records


def walk(project_dir, globs):
    for dirpath, dirnames, filenames in os.walk(project_dir):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        for name in filenames:
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, project_dir).replace(os.sep, "/")
            if os.path.splitext(name)[1].lower() in SKIP_EXTENSIONS:
                continue
            if is_secret(rel, globs):
                continue
            if os.path.islink(path):
                continue
            try:
                if os.path.getsize(path) > MAX_BYTES:
                    continue
            except OSError:
                continue
            yield path, rel


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="cfm debt scan — harvest cfm-debt: markers into a ledger"
    )
    parser.add_argument("--project-dir", default=".")
    parser.add_argument(
        "--paths", nargs="*", default=None,
        help="limit the scan to these repo-relative paths (the phase's touched files)",
    )
    args = parser.parse_args(argv)

    project_dir = os.path.abspath(args.project_dir)
    globs = secret_globs(project_dir)

    markers = []
    if args.paths:
        for rel in args.paths:
            rel = rel.replace(os.sep, "/")
            path = os.path.join(project_dir, rel)
            if is_secret(rel, globs) or not os.path.isfile(path):
                continue
            markers += scan_file(path, rel)
    else:
        for path, rel in walk(project_dir, globs):
            markers += scan_file(path, rel)

    markers.sort(key=lambda m: (m["file"], m["line"]))
    no_trigger = [m for m in markers if m["no_trigger"]]
    json.dump({
        "marker": MARKER,
        "scanned": "paths" if args.paths else "repo",
        "markers": markers,
        "total": len(markers),
        "no_trigger": len(no_trigger),
    }, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
