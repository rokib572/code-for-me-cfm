#!/usr/bin/env python3
"""cfm settings generator — enforcement layer 2 (plan §11, enforcement in depth).

Renders the project's .claude/settings.json permission rules from
.cfm-workflow.yml.

Denies (the security invariant), mirroring what the PreToolUse guard
blocks so that the guard failing open (no python3, an internal error)
still leaves a second layer:

- Read/Edit denies for every secret glob (both the bare form and a **/
  form, so nested matches are covered whichever way the permission matcher
  anchors). Claude Code consults only Read and Edit path rules — an Edit
  rule also covers Write, NotebookEdit and MultiEdit, and a Write(...)
  rule is ignored with a startup warning — so no Write rules are emitted.
- Bash denies for the common reader heads naming a secret glob
  (`Bash(cat *.env*)`, ...). The permission matcher has no carve-outs, so
  these also deny `cat .env.example`, which the guard allows; the Read
  rule above already covers that file, and `grep '' .env.example` passes
  both layers.
- A Bash(<op>:*) deny for every effective forbidden op — the git level's
  list, the config's extensions, and the always-forbidden ops.
- The hard invariants the level cannot grant: exact-form denies for
  pushes to main/master, destructive push flags, and branch delete/rename.
  Only the literal shapes are expressible here (`git push origin main`,
  `git push -u origin main`, `HEAD:main`); a bare `git push` while main is
  checked out is caught by the guard alone.
- The exact verify_full command(s) — the human's command.
- Edit denies on .claude/settings.json, .claude/settings.local.json and
  the managed-rules sidecar: the layer protecting itself. cfm writes
  those files only through this script, never through the Edit tool.

The generated set is OWNED, not merely appended: every rule this script
writes is recorded in the sidecar .claude/cfm-denies.json, and the next
run removes the recorded rules the new config no longer requires (a git
level raised from L0 to L2 must stop denying `git push:*`, or the level
change is silently ineffective at this layer). Rules cfm never wrote —
the user's own denies — are preserved verbatim, in place. When the
sidecar is absent (a project initialised before it existed), the rules in
cfm's level-independent shapes (`Bash(git <op>:*)`, the push and branch
invariants, the default secret-glob rules) are treated as cfm's.

Allows (convenience only): exact tracker tool names the caller OBSERVED
live in the session (--allow-tool mcp__server__tool), so tracker sync does
not prompt per call. Never a server wildcard: `mcp__atlassian__*` would
auto-approve every Confluence and Bitbucket write the Rovo server exposes,
and never `claude mcp add` — a stdio server is an arbitrary command Claude
Code launches. Deny always beats allow. Allows are advisory — --check
verifies the denies only, because a stale allow list is friction, not a
hole.

Sandbox (opt-in, --sandbox): an OS-level third layer. Claude Code's Bash
sandbox enforces `sandbox.filesystem.denyRead` / `denyWrite` on the
running process and its children, so the interpreter, variable and
script-file evasions the text guard concedes are closed for Bash. The
block denies reads of every secret glob and writes to the config pair and
the sidecar (the settings files and .claude/agents are on the sandbox's
own built-in protected list). Project settings can enable the sandbox;
verify the resolved paths in `/sandbox` → Config after writing.

Status line (opt-in, --statusline): writes a `statusLine` entry that runs
the plugin's statusline.sh, which prints the cfm mode and the phase in
flight. The command is recorded in the sidecar so a later run can tell
cfm's status line from one the user wrote: --remove-statusline retracts
only cfm's, and the doctor reports which one is on. The entry is sticky,
like the sandbox block — a --write without the flag leaves it alone.

Merge-only for everything that is not cfm's: every existing key and every
existing permissions.allow/deny/ask entry cfm did not write is preserved.
Runs only on a valid config — config errors exit 1.

Modes: default prints the proposed full settings JSON; --check exits 0 iff
every required deny is present and no stale cfm deny remains; --write
writes the settings file and the sidecar atomically.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cfm_config

SETTINGS_REL = os.path.join(".claude", "settings.json")
# the rules cfm last wrote — what lets a later run retract them
MANAGED_REL = os.path.join(".claude", "cfm-denies.json")

# exact MCP tool name: mcp__<server>__<tool>, no wildcard anywhere
TOOL_NAME_RE = re.compile(r"^mcp__[A-Za-z0-9_.-]+__[A-Za-z0-9_.-]+$")


def valid_tool_name(name):
    return isinstance(name, str) and TOOL_NAME_RE.match(name) is not None


def required_allows(config, extra=()):
    """Rules that keep tracker work from prompting per call: only the exact
    tool names the caller OBSERVED live in the session. The config derives
    nothing here on purpose — a provider name cannot tell you which tools a
    server exposes, and a server wildcard approves all of them."""
    allows = []
    for name in extra:
        if valid_tool_name(name):
            allows.append(name)
    return list(dict.fromkeys(allows))


# Bash heads that print a file they name — layer 2 for the secret rule
# under the Bash tool. Kept short on purpose: every head is one deny per
# secret glob, and the guard's token-first rule is the precise layer.
BASH_READER_HEADS = ("cat", "head", "tail", "less", "more", "source")

DEFAULT_BRANCHES = ("main", "master")

# blocked at every git level by the guard; the shapes a Bash rule can name
HARD_INVARIANT_BASH = [
    "Bash(git push -f *)", "Bash(git push * -f *)",
    "Bash(git push --force *)", "Bash(git push * --force *)",
    "Bash(git push --force-with-lease *)", "Bash(git push * --force-with-lease *)",
    "Bash(git push --force-if-includes *)", "Bash(git push * --force-if-includes *)",
    "Bash(git push --delete *)", "Bash(git push * --delete *)",
    "Bash(git push -d *)", "Bash(git push * -d *)",
    "Bash(git push --mirror *)", "Bash(git push * --mirror *)",
    "Bash(git push --prune *)", "Bash(git push * --prune *)",
    "Bash(git branch -D *)", "Bash(git branch * -D *)",
    "Bash(git branch -d *)", "Bash(git branch * -d *)",
    "Bash(git branch --delete *)", "Bash(git branch * --delete *)",
    "Bash(git branch -m *)", "Bash(git branch * -m *)",
    "Bash(git branch -M *)", "Bash(git branch * -M *)",
    "Bash(git branch --move *)", "Bash(git branch * --move *)",
]

# the generated files protect themselves: cfm writes them only here
SELF_DENIES = [
    "Edit(/.claude/settings.json)",
    "Edit(/.claude/settings.local.json)",
    "Edit(/.claude/cfm-denies.json)",
]


def _bash_glob(glob):
    """A secret glob as a Bash-rule wildcard: `*` matches any text, so
    `*.env*` covers `.env`, `apps/.env.local` and `-n .env` alike."""
    bare = glob[3:] if glob.startswith("**/") else glob
    return bare if bare.startswith("*") else f"*{bare}"


def default_branch_push_denies(branches=DEFAULT_BRANCHES):
    denies = []
    for branch in branches:
        for target in (branch, f"*:{branch}", f"*:refs/heads/{branch}"):
            # a rule with two wildcards does not match the bare form, so
            # both the terminal and the trailing-argument shapes are needed
            denies.append(f"Bash(git push * {target})")
            denies.append(f"Bash(git push * {target} *)")
    return denies


def _glob_denies(globs):
    denies = []
    for glob in globs:
        forms = [glob] if "/" in glob else [glob, f"**/{glob}"]
        for form in forms:
            for tool in ("Read", "Edit"):
                denies.append(f"{tool}({form})")
    for head in BASH_READER_HEADS:
        for glob in globs:
            denies.append(f"Bash({head} {_bash_glob(glob)})")
    return denies


def required_denies(config):
    denies = _glob_denies(config.get("secret_globs") or [])
    forbidden = cfm_config.forbidden_ops(config)
    for op in forbidden:
        denies.append(f"Bash({op}:*)")
    if "git push" not in forbidden:
        denies.extend(default_branch_push_denies())
    denies.extend(HARD_INVARIANT_BASH)
    for command in cfm_config.slot_commands(config, "verify_full"):
        denies.append(f"Bash({command.strip()})")
    denies.extend(SELF_DENIES)
    return list(dict.fromkeys(denies))


def managed_universe():
    """Every deny cfm can generate WITHOUT knowing the config: the shapes
    that change with the git level, the invariants, and the default secret
    globs. A rule in this set is cfm's even when no sidecar recorded it."""
    rules = set(_glob_denies(cfm_config.DEFAULT_SECRET_GLOBS))
    for op in cfm_config.ALL_MUTATING_OPS + cfm_config.ALWAYS_FORBIDDEN_OPS:
        rules.add(f"Bash({op}:*)")
    rules.update(default_branch_push_denies())
    rules.update(HARD_INVARIANT_BASH)
    rules.update(SELF_DENIES)
    return rules


def read_managed(path):
    """The deny list cfm last wrote, [] when the sidecar is absent or
    unreadable (an unreadable sidecar only loses retraction precision)."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return []
    rules = data.get("deny") if isinstance(data, dict) else None
    return [r for r in rules if isinstance(r, str)] if isinstance(rules, list) else []


def stale_denies(config, settings, managed):
    """Denies present in settings that cfm wrote (recorded in the sidecar,
    or in a level-independent cfm shape) and the current config no longer
    requires. Preserves settings order."""
    required = set(required_denies(config))
    owned = set(managed) | managed_universe()
    return [d for d in current_denies(settings) if d in owned and d not in required]


def read_settings(path):
    """Existing settings, {} if absent. Raises ValueError when unreadable —
    never clobber a file we cannot parse."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("top level must be a JSON object")
    if "permissions" in data and not isinstance(data["permissions"], dict):
        raise ValueError("'permissions' must be a JSON object")
    if "sandbox" in data and not isinstance(data["sandbox"], dict):
        raise ValueError("'sandbox' must be a JSON object")
    return data


def _current(settings, key):
    rules = (settings.get("permissions") or {}).get(key)
    return [r for r in rules if isinstance(r, str)] if isinstance(rules, list) else []


def current_denies(settings):
    return _current(settings, "deny")


def current_allows(settings):
    return _current(settings, "allow")


def _union(permissions, key, additions, remove=()):
    raw = permissions.get(key)
    # keep every existing entry verbatim in place, non-strings included —
    # except the cfm-owned rules being retracted
    existing = [r for r in (raw if isinstance(raw, list) else [])
                if not (isinstance(r, str) and r in remove)]
    present = {r for r in existing if isinstance(r, str)}
    merged_rules = existing + sorted(set(additions) - present)
    if merged_rules or isinstance(raw, list):
        permissions[key] = merged_rules


def merged(settings, denies, allows=(), stale=()):
    result = json.loads(json.dumps(settings))  # deep copy, keeps every key
    permissions = result.setdefault("permissions", {})
    _union(permissions, "deny", denies, remove=set(stale))
    _union(permissions, "allow", allows)
    return result


# --- sandbox (opt-in OS-level layer) -----------------------------------------

def sandbox_paths(config):
    """(denyRead, denyWrite) for sandbox.filesystem, project-relative (`./`
    resolves to the project root in project settings). Reads: every secret
    glob at the root and nested. Writes: the config pair and the sidecar —
    the settings files and .claude/agents are already on the sandbox's
    built-in protected list."""
    deny_read = []
    for glob in config.get("secret_globs") or []:
        bare = glob[3:] if glob.startswith("**/") else glob
        for form in (f"./{bare}", f"./**/{bare}"):
            if form not in deny_read:
                deny_read.append(form)
    deny_write = [f"./{cfm_config.CONFIG_FILE}", f"./{cfm_config.LOCAL_CONFIG_FILE}",
                  "./" + MANAGED_REL.replace(os.sep, "/")]
    return deny_read, deny_write


def merged_sandbox(settings, config):
    """settings with the cfm sandbox block unioned in: enabled, and the
    deny lists extended (existing entries kept first, in place)."""
    result = json.loads(json.dumps(settings))
    sandbox = result.setdefault("sandbox", {})
    sandbox["enabled"] = True
    fs = sandbox.setdefault("filesystem", {})
    deny_read, deny_write = sandbox_paths(config)
    for key, additions in (("denyRead", deny_read), ("denyWrite", deny_write)):
        existing = fs.get(key)
        existing = list(existing) if isinstance(existing, list) else []
        fs[key] = existing + [p for p in additions if p not in existing]
    return result


def sandbox_missing(settings, config):
    """The cfm sandbox entries a settings file lacks; [] when the block is
    complete. 'enabled' names the switch itself."""
    sandbox = settings.get("sandbox") if isinstance(settings.get("sandbox"), dict) else {}
    fs = sandbox.get("filesystem") if isinstance(sandbox.get("filesystem"), dict) else {}
    missing = []
    if sandbox.get("enabled") is not True:
        missing.append("enabled")
    deny_read, deny_write = sandbox_paths(config)
    for key, wanted in (("denyRead", deny_read), ("denyWrite", deny_write)):
        present = fs.get(key) if isinstance(fs.get(key), list) else []
        missing.extend(f"{key}: {p}" for p in wanted if p not in present)
    return missing


def sandbox_enabled(settings):
    sandbox = settings.get("sandbox")
    return isinstance(sandbox, dict) and sandbox.get("enabled") is True


# --- status line (opt-in) ----------------------------------------------------

def statusline_command():
    """The absolute path of the plugin's status-line script: settings
    commands do not expand ${CLAUDE_PLUGIN_ROOT}, so the path is resolved
    at write time and the doctor reports it when it stops existing."""
    root = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(os.path.abspath(root), "scripts", "statusline.sh")


def current_statusline(settings):
    """The statusLine command in settings, or None."""
    entry = settings.get("statusLine")
    if isinstance(entry, dict) and isinstance(entry.get("command"), str):
        return entry["command"]
    return None


def read_managed_statusline(path):
    """The status-line command cfm last wrote, or None."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    value = data.get("statusline") if isinstance(data, dict) else None
    return value if isinstance(value, str) and value else None


def statusline_owner(settings, managed):
    """'cfm' when the status line on is cfm's (recorded, or the plugin's
    script by path), 'user' when another one is on, None when none."""
    command = current_statusline(settings)
    if command is None:
        return None
    if command == managed or command.endswith(os.path.join("scripts", "statusline.sh")):
        return "cfm"
    return "user"


def merged_statusline(settings):
    result = json.loads(json.dumps(settings))
    result["statusLine"] = {"type": "command", "command": statusline_command()}
    return result


def without_statusline(settings, managed):
    """settings with cfm's status line removed; a user's own is kept."""
    result = json.loads(json.dumps(settings))
    if statusline_owner(result, managed) == "cfm":
        result.pop("statusLine", None)
    return result


# --- io ----------------------------------------------------------------------

def write_atomic(path, document):
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".settings-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(document, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="cfm — render .claude/settings.json deny rules from config"
    )
    parser.add_argument("--project-dir", default=".", help="project root (default: .)")
    parser.add_argument(
        "--allow-tool", action="append", default=[], metavar="NAME",
        help="exact MCP tool name observed live in this session that tracker "
             "sync calls (e.g. mcp__atlassian__createJiraIssue) — repeatable; "
             "wildcards are rejected",
    )
    parser.add_argument(
        "--sandbox", action="store_true",
        help="also render the sandbox block: enable Claude Code's Bash "
             "sandbox with OS-level denyRead on every secret glob and "
             "denyWrite on the config pair (opt-in third layer)",
    )
    status = parser.add_mutually_exclusive_group()
    status.add_argument(
        "--statusline", action="store_true",
        help="also render the cfm status line (mode and phase in flight) into "
             "the project settings; it replaces a personal statusLine inside "
             "this project only",
    )
    status.add_argument(
        "--remove-statusline", action="store_true",
        help="retract cfm's status line; a statusLine the user wrote is kept",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true",
                      help="exit 0 iff every required deny is present and no "
                           "stale cfm deny remains (with --sandbox: and the "
                           "sandbox block is complete)")
    mode.add_argument("--write", action="store_true",
                      help="write the merged settings file and the sidecar atomically")
    args = parser.parse_args(argv)

    config, errors, warnings = cfm_config.load(args.project_dir)
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    if config is None or errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1

    settings_path = os.path.join(args.project_dir, SETTINGS_REL)
    managed_path = os.path.join(args.project_dir, MANAGED_REL)
    try:
        settings = read_settings(settings_path)
    except (ValueError, OSError) as exc:
        print(
            f"error: {settings_path}: cannot parse existing settings — "
            f"refusing to touch it ({exc})",
            file=sys.stderr,
        )
        return 1

    bad = [t for t in args.allow_tool if not valid_tool_name(t)]
    if bad:
        print(f"error: --allow-tool takes exact mcp__<server>__<tool> names, "
              f"no wildcards: {bad}", file=sys.stderr)
        return 1
    denies = required_denies(config)
    allows = required_allows(config, extra=args.allow_tool)
    stale = stale_denies(config, settings, read_managed(managed_path))

    if args.check:
        # Denies decide the exit code — they are the invariant. Missing
        # allows are reported for visibility but never fail the check.
        present = set(current_denies(settings))
        missing = [d for d in denies if d not in present]
        for entry in missing:
            print(f"missing: {entry}", file=sys.stderr)
        for entry in stale:
            print(f"stale (from an earlier config): {entry}", file=sys.stderr)
        allowed = set(current_allows(settings))
        for entry in (a for a in allows if a not in allowed):
            print(f"advisory (allow, not required): {entry}", file=sys.stderr)
        sandbox_gaps = sandbox_missing(settings, config) if args.sandbox else []
        for entry in sandbox_gaps:
            print(f"sandbox: {entry}", file=sys.stderr)
        statusline_gap = args.statusline and \
            current_statusline(settings) != statusline_command()
        if statusline_gap:
            print(f"statusline: not wired to {statusline_command()}", file=sys.stderr)
        return 1 if (missing or stale or sandbox_gaps or statusline_gap) else 0

    document = merged(settings, denies, allows, stale=stale)
    if args.sandbox:
        document = merged_sandbox(document, config)
    managed_statusline = read_managed_statusline(managed_path)
    if args.statusline:
        document = merged_statusline(document)
    elif args.remove_statusline:
        document = without_statusline(document, managed_statusline)
    if args.write:
        write_atomic(settings_path, document)
        sidecar = {"deny": denies}
        if statusline_owner(document, managed_statusline) == "cfm":
            sidecar["statusline"] = current_statusline(document)
        write_atomic(managed_path, sidecar)
        if stale:
            print(f"retracted {len(stale)} stale den{'y' if len(stale) == 1 else 'ies'}: "
                  + ", ".join(stale))
        return 0

    json.dump(document, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
