#!/usr/bin/env python3
"""cfm PreToolUse decision engine.

Reads one hook-event JSON object from stdin: {"tool_name": ..., "tool_input": ...,
"agent_id": ... (subagents only)}. Exit 0 allows the tool call; exit 2 blocks
it with the reason on stderr. Only projects with a .cfm-workflow.yml are
governed. A broken config must not disable the guard: enforcement falls back
to the cfm_config defaults for any field that is unreadable.

Secret files: any token of any command that names a secret-glob file blocks
the call (a token-first rule, not a reader-command denylist), except under a
short list of heads that cannot print contents (ls, rm, stat, echo, ...),
the pattern argument of grep/sed/awk, and the write-only destination of
cp/mv/tee/redirects. A secret file on stdin (`tee < .env`, `cat<.env`,
`exec 3<.env`) is a read under every head. A token is also split on ':' and
'=', so `HEAD:.env.local`, `--data=@.env` and `-v $PWD/.env:/x` are judged by
the file they name. Shell globs and brace groups in tokens are expanded
against the project so `cat .e*` and `cat .{env,bak}` are judged by what
they would read; `$(...)`, backticks and `<(...)` are scanned as commands of
their own, and an echo/printf whose output feeds another command is treated
as naming files for it.

Policy files: the config (.cfm-workflow.yml and its .local), the generated
settings denies (.claude/settings*.json, .claude/cfm-denies.json), project
agent files (.claude/agents/), and the plugin itself are what the guard
enforces FROM. A subagent — any event carrying agent_id — never modifies
them, and the rule is token-first like the secret rule: Edit/Write on those
paths and any command naming one are blocked unless the head only reads
(cat, grep, diff, sed without -i, yq without -i, ...); output redirects
into one are blocked under every head; rm/mv/chmod and tree-writing git
subcommands also match a directory above one; `git apply`, `git am`,
`git stash pop|apply` and archive extraction into the project are refused
because the guard cannot see what they land. The main session keeps its
sanctioned path (/cfm:init and /cfm:configure write the config there, with
the human approving the diff).

cfm mode (config `mode`, default `enforced`): the main session — any event
WITHOUT agent_id — orchestrates and never writes product code. It may write
only the orchestrator roots: the config pair, .claude/, .cfm/, .git/,
docs/, CLAUDE.md and every claude_md.files entry, the configured
rules_file, context_file, progress_log and state_file, .gitignore and
.env.example. Everything else inside the project is product: Edit/Write
there is refused, and so is a command whose head writes what it names —
an output redirect under any head, cp/install/ln destinations, rm/mv/chmod
targets, sed -i and friends, tee/touch/truncate, curl -o/wget -O/dd of=,
tree-writing git subcommands naming a path, `git apply`/`am`/`stash pop`,
and archive extraction into the project. Unlike the two rules above this
one is head-first, not token-first: an unknown head is execution
(pytest, tsc, make, npm ci), and so is any interpreter, because the rule
protects the whole tree and a token-first fallback would refuse most
legitimate commands. It is a discipline rule for a trusted party, not a
security boundary — the interpreter, variable and script-file shapes, a
`cd`, a pipe feeding a writer, a formatter or package manager rewriting
the tree, and content arriving from git history all pass, and the
settings deny layer cannot mirror it because the permission layer does
not see agent_id. Subagents are untouched. `advisory` and `off` silence
the rule; everything else in this module still applies.

Git: the effective forbidden set is cfm_config.forbidden_ops(config) — the
level's list, extended by the config, plus the always-forbidden ops. Pushes
that would land on the default branch (by refspec target, or by the
checked-out branch when the push names none) and destructive push/branch
flags are blocked at every level. The default branch is whatever
origin/HEAD points at, plus main and master always. GIT_CONFIG* environment
assignments are blocked outright: they can define an alias the guard
cannot see. verify_full is the human's command and is blocked for every
agent — the exact command, or the command with only flags appended
(`npm test -- --watch`); a path argument makes it a scoped run.

Command text is split into segments on ||, &&, ;, |, & and newlines
OUTSIDE quotes, so a separator inside a commit message never starts a
second command. A token containing whitespace is a quoted message, not a
file name, and is skipped — after any substitution inside it has been
scanned as a command of its own.

The config is parsed on every call (PyYAML import plus parse is a few
milliseconds); there is deliberately no cache, because a cache file inside
the project is policy an agent could rewrite.
"""

from __future__ import annotations

import fnmatch
import glob as globmod
import json
import os
import re
import shlex
import sys

FILE_PATH_TOOLS = ("Read", "Edit", "MultiEdit", "Write", "NotebookEdit")
FILE_WRITE_TOOLS = ("Edit", "MultiEdit", "Write", "NotebookEdit")

# heads that can name a secret file without printing its contents (echo and
# printf print their ARGUMENTS — `echo .env >> .gitignore` names a file
# without reading it; a `$(cat .env)` inside is scanned separately)
SAFE_WITH_SECRET_PATH = frozenset((
    "ls", "test", "[", "stat", "file", "rm", "unlink", "shred", "touch",
    "mkdir", "rmdir", "chmod", "chown", "realpath", "readlink", "basename",
    "dirname", "du", "wc", "md5sum", "sha1sum", "sha256sum", "sha512sum",
    "tee", "truncate", "echo", "printf",
))
# heads whose first positional is a PATTERN, not a file — unless -e/--regexp
# supplies it, in which case every positional is a file
PATTERN_HEADS = frozenset((
    "grep", "egrep", "fgrep", "rg", "sed", "awk", "gawk", "mawk", "nawk",
))
AWK_HEADS = frozenset(("awk", "gawk", "mawk", "nawk"))
PATTERN_FLAGS = frozenset(("-e", "--regexp", "--expression"))
# flags whose argument is a FILE the command reads (patterns/script from a
# file) — it stays checked, and it means every positional is a file
PATTERN_FILE_FLAGS = frozenset(("-f", "--file", "--exclude-from"))
# flags whose argument NARROWS the files searched: `--include .env` or
# `rg -g .env` turns a repo-wide grep into a reader of that file, so the
# argument is checked as a file glob (a leading '!' excludes, and is skipped)
PATTERN_NARROW_FLAGS = frozenset(("--include", "-g", "--glob", "--iglob"))
# flags whose argument is neither a pattern nor a file
PATTERN_SKIP_FLAGS = frozenset((
    "-A", "-B", "-C", "-m", "-d", "-D", "--max-count", "--exclude",
    "--exclude-dir", "--label", "--color", "--colour", "-t", "--type", "-T",
    "--type-not",
))
# git subcommands that may take a secret path without reading it
SAFE_GIT_WITH_SECRET_PATH = frozenset(("check-ignore", "rm", "ls-files", "status"))
# git flags whose argument is a separate token (git -C <dir> commit ...)
ARG_FLAGS = frozenset(("-C", "-c", "--git-dir", "--work-tree", "--namespace"))
# words that wrap another command without changing what it does
WRAPPER_WORDS = frozenset((
    "command", "exec", "nohup", "time", "nice", "stdbuf", "setsid",
    "ionice", "timeout", "sudo", "doas", "busybox", "chronic", "unbuffer",
    "caffeinate", "builtin",
))
# wrapper flags whose argument is a separate token (nice -n 10, sudo -u x)
WRAPPER_ARG_FLAGS = frozenset((
    "-n", "-c", "-t", "-p", "-k", "-s", "-i", "-o", "-e", "-u", "-g", "-C",
    "-D", "-h", "-r", "-U", "--signal", "--kill-after", "--adjustment",
    "--user", "--group", "--chdir",
))
SHELL_WORDS = frozenset(("sh", "bash", "zsh", "dash", "ksh"))
# env flags whose argument is a separate token
ENV_ARG_FLAGS = frozenset(("-u", "--unset", "-C", "--chdir", "-S", "--split-string"))
FIND_NAME_FLAGS = frozenset((
    "-name", "-iname", "-path", "-ipath", "-wholename", "-iwholename",
    "-regex", "-iregex", "-lname", "-ilname",
))
FIND_ACTION_FLAGS = frozenset((
    "-exec", "-execdir", "-ok", "-okdir", "-delete", "-print0", "-fprint",
    "-fprint0", "-ls", "-fls",
))
FIND_MUTATING_FLAGS = frozenset(("-exec", "-execdir", "-ok", "-okdir", "-delete"))
GIT_CONFIG_READ_FLAGS = frozenset((
    "--get", "--get-all", "--get-regexp", "--list", "-l", "--show-origin",
    "--show-scope", "--get-urlmatch",
))
GH_API_MUTATING = frozenset((
    "-X", "--method", "-f", "--raw-field", "-F", "--field", "--input",
))
PUSH_ARG_FLAGS = frozenset((
    "-o", "--push-option", "--repo", "--receive-pack", "--exec",
))
PUSH_DESTRUCTIVE_FLAGS = frozenset((
    "-f", "--force", "--force-with-lease", "--force-if-includes",
    "--mirror", "--all", "--delete", "-d", "--prune",
))
BRANCH_DESTRUCTIVE_FLAGS = frozenset((
    "-D", "-d", "--delete", "-M", "-m", "--move", "-f", "--force",
))
# policy files a subagent never modifies — the config pair by NAME (so a
# `cd` the guard cannot track still cannot reach them), the rest by path
PROTECTED_BASENAMES = frozenset((".cfm-workflow.yml", ".cfm-workflow.local.yml"))
PROTECTED_PROJECT_PATHS = (
    ".cfm-workflow.yml", ".cfm-workflow.local.yml",
    os.path.join(".claude", "settings.json"),
    os.path.join(".claude", "settings.local.json"),
    os.path.join(".claude", "cfm-denies.json"),
    os.path.join(".claude", "agents"),
)
PROTECTED_HOME_PATHS = (os.path.join(".claude", "settings.json"),)
# The policy rule is token-first, like the secret rule: a subagent command
# naming a policy file is a write unless its head is one of these, which
# read what they name and change nothing.
POLICY_READ_HEADS = frozenset((
    "cat", "head", "tail", "less", "more", "bat", "wc", "diff", "cmp", "comm",
    "stat", "ls", "file", "du", "md5sum", "sha1sum", "sha256sum", "sha512sum",
    "cksum", "realpath", "readlink", "basename", "dirname", "test", "[",
    "grep", "egrep", "fgrep", "rg", "ag", "strings", "od", "xxd", "hexdump",
    "nl", "tac", "cut", "tr", "uniq", "column", "fold", "paste", "expand",
    "jq", "git-lfs",
))
# read heads that become writers under one flag
IN_PLACE_HEADS = frozenset(("sed", "perl"))
AWK_INPLACE_HEADS = frozenset(("awk", "gawk", "mawk", "nawk"))
# heads whose LAST positional is the destination; the sources are reads
DEST_LAST_HEADS = frozenset(("cp", "mv", "install", "ln"))
# heads that create or truncate every non-flag positional
CREATE_HEADS = frozenset(("tee", "touch", "truncate"))
# line editors: the positionals are files they may write
EDITOR_HEADS = frozenset(("ed", "ex"))
# heads whose output file is a flag's argument
OUTPUT_FLAG_HEADS = {
    "curl": ("-o", "--output"),
    "wget": ("-O", "--output-document"),
}
# heads that remove or move whatever they name, including a parent directory
DESTROY_HEADS = frozenset((
    "rm", "rmdir", "unlink", "shred", "mv", "rename", "chmod", "chown", "chattr",
))
# heads that execute a script: a plugin script run by a subagent is a read
# of the plugin, not a write (`python3 <plugin>/scripts/cfm_config.py`)
INTERPRETER_HEADS = frozenset((
    "python", "python3", "node", "bash", "sh", "zsh", "dash", "ksh", "perl",
    "ruby", "deno", "bun", "npx",
))
# git subcommands that rewrite the working tree from a ref or a path
GIT_TREE_WRITERS = frozenset((
    "checkout", "switch", "restore", "reset", "merge", "rebase", "pull",
    "cherry-pick", "revert", "clean", "rm", "mv", "worktree", "submodule",
    "stash",
))
# git subcommands that land content the guard cannot inspect in the tree
GIT_INJECT_SUBCOMMANDS = frozenset(("apply", "am"))
GIT_STASH_INJECT = frozenset(("pop", "apply", "branch"))
# archive extraction lands files wherever it is pointed — the project root
# by default, which is above every policy file
EXTRACT_HEADS = frozenset(("tar", "bsdtar", "unzip", "7z", "7za", "7zr", "unrar"))
# what the main session may write in cfm mode, by project-relative path;
# the config's own path fields and claude_md.files join at runtime
ORCHESTRATOR_PROJECT_PATHS = (
    ".cfm-workflow.yml", ".cfm-workflow.local.yml", ".claude", ".cfm", ".git",
    "docs", "CLAUDE.md", ".gitignore", ".env.example",
)
ORCHESTRATOR_CONFIG_PATH_FIELDS = (
    "rules_file", "context_file", "progress_log", "state_file",
)
# once a subagent event is seen, the guard records it here so the doctor
# can prove the agent_id branch fires on real events, not just probes
SUBAGENT_OBSERVED_REL = os.path.join(".cfm", "subagent-observed")
MAX_DEPTH = 3
MAX_BRACE_EXPANSIONS = 64

_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
# GIT_CONFIG_PARAMETERS, GIT_CONFIG_COUNT/KEY_n/VALUE_n, GIT_CONFIG_GLOBAL…
_GIT_CONFIG_ENV_RE = re.compile(r"^GIT_CONFIG[A-Z0-9_]*=\S*$")
_DURATION_RE = re.compile(r"^\d+(\.\d+)?[smhd]?$")
_GLOB_CHARS_RE = re.compile(r"[*?\[]")
_BRACE_RE = re.compile(r"\{([^{}]*,[^{}]*)\}")
_SEPARATORS = ("||", "&&", ";", "|", "&", "\n")
# $(...) and `...` (one level of nested parens inside), plus process
# substitution <(...) / >(...) — each is a command of its own
_SUBST_RE = re.compile(
    r"\$\(((?:[^()]|\([^()]*\))*)\)|`([^`]*)`|[<>]\(((?:[^()]|\([^()]*\))*)\)"
)
# redirect operators glued to a word: `cat<.env`, `3<.env`, `cmd>out`, `2>&1`
# — split off so every operator is its own token (`<(` and `>(` are process
# substitution, not redirects)
_REDIRECT_SPLIT_RE = re.compile(
    r"(\d*(?:<<<|<<-|<<|<>|<&|>&|&>>|&>|>>|>\||<(?!\()|>(?!\()))"
)
_INPUT_REDIRECT_RE = re.compile(r"^\d*<>?$")      # <, 0<, 3<, <>
_OUTPUT_REDIRECT_RE = re.compile(r"^\d*(?:>>|>\||>&|&>>|&>|>|<>)$")
_PROC_ENVIRON_RE = re.compile(r"(^|/)proc/[^/\s]+/environ$")
_WHITESPACE_RE = re.compile(r"\s")
_VAR_RE = re.compile(r"\$\{?(HOME|PWD|CLAUDE_PROJECT_DIR|CLAUDE_PLUGIN_ROOT)\}?")

SECRET_MESSAGE = (
    "cfm: blocked — '{target}' matches secret glob '{glob}'. The secrets "
    "policy is a hard invariant: never read secret files, even on an "
    "explicit user request."
)
ENV_DUMP_MESSAGE = (
    "cfm: blocked — '{cmd}' dumps the environment "
    "(Claude Code loads project .env into it)."
)
VERIFY_FULL_MESSAGE = (
    "cfm: blocked — that is the verify_full command. The full test suite is "
    "the human's command; agents run tests only by explicit file path "
    "(test_scoped)."
)
GIT_CONFIG_ENV_MESSAGE = (
    "cfm: blocked — '{token}' configures git through the environment, which "
    "can define an alias the guard cannot see. Use plain git commands."
)
POLICY_MESSAGE = (
    "cfm: blocked — '{target}' is workflow policy (the cfm config, the "
    "generated settings denies, an agent file, or the plugin itself). "
    "Subagents never modify it; config changes go through /cfm:configure "
    "in the main session, with the human approving the diff."
)
POLICY_INJECT_MESSAGE = (
    "cfm: blocked — '{cmd}' lands content the guard cannot inspect in the "
    "working tree, which can rewrite workflow policy (the cfm config, the "
    "settings denies, agent files). Subagents never run it; the human "
    "applies patches, stashes and archives."
)
ORCHESTRATOR_MESSAGE = (
    "cfm: blocked — '{target}' is product code; in cfm mode the main "
    "session orchestrates and never writes it. Dispatch the coder (or "
    "/cfm:implement-phase, /cfm:diagnose) instead."
)
ORCHESTRATOR_INJECT_MESSAGE = (
    "cfm: blocked — '{cmd}' lands content the guard cannot inspect in the "
    "project tree; in cfm mode the main session orchestrates and never "
    "writes product code. Dispatch the coder (or /cfm:implement-phase, "
    "/cfm:diagnose) instead."
)


def _cfm_config():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import cfm_config
    return cfm_config


def _secret_globs(config):
    cfm_config = _cfm_config()
    globs = []
    raw = config.get("secret_globs")
    if isinstance(raw, list):
        globs = [g for g in raw if isinstance(g, str)]
    # hard invariant: a broken config never shrinks the glob set
    globs.extend(g for g in cfm_config.DEFAULT_SECRET_GLOBS if g not in globs)
    return globs


def _glob_match(value, glob):
    if fnmatch.fnmatch(value, glob):
        return True
    # fnmatch gives '**/' no special meaning, so '**/credentials' misses a
    # root-level 'credentials' — also try the glob with the prefix removed
    return glob.startswith("**/") and fnmatch.fnmatch(value, glob[3:])


def _match_path(path, project_dir, globs):
    """Return the first glob matching the path (relative to project root) or
    its basename, so `.env*` catches apps/api/.env.local and `**/credentials`
    catches nested paths."""
    absolute = path if os.path.isabs(path) else os.path.join(project_dir, path)
    try:
        rel = os.path.relpath(absolute, project_dir)
    except ValueError:
        rel = path
    base = os.path.basename(absolute.rstrip("/"))
    if base == ".env.example":  # the sanctioned no-values env file
        return None
    for glob in globs:
        if _glob_match(rel, glob) or _glob_match(base, glob):
            return glob
    return None


def _match_name(token, globs):
    base = os.path.basename(token.rstrip("/"))
    if base == ".env.example":  # the sanctioned no-values env file
        return None
    for glob in globs:
        if _glob_match(base, glob) or _glob_match(token, glob):
            return glob
    return None


def _candidate_names(token):
    """The file names a token may denote: itself, the value after '=' for
    option=value / if=/of= forms, and either side of a ':' for git blob
    specs (`HEAD:.env.local`) and mount specs (`$PWD/.env:/x`), with a
    curl-style '@' prefix stripped."""
    parts = [token]
    if "=" in token:
        parts.append(token.partition("=")[2])
    for part in list(parts):
        if ":" in part:
            before, _sep, after = part.partition(":")
            parts.extend((before, after))
    names = []
    for part in parts:
        part = part.lstrip("@")
        if part and not part.startswith("-") and part not in names:
            names.append(part)
    return names


def _expand_vars(token, project_dir):
    """Substitute the handful of variables whose values the guard knows
    ($HOME, $PWD, $CLAUDE_PROJECT_DIR, $CLAUDE_PLUGIN_ROOT, a leading ~)."""
    values = {
        "HOME": os.path.expanduser("~"),
        "PWD": project_dir,
        "CLAUDE_PROJECT_DIR": project_dir,
        "CLAUDE_PLUGIN_ROOT": os.environ.get("CLAUDE_PLUGIN_ROOT") or _plugin_root(),
    }
    token = _VAR_RE.sub(lambda m: values[m.group(1)], token)
    if token == "~" or token.startswith("~/"):
        token = os.path.expanduser("~") + token[1:]
    return token


def _brace_expand(token):
    """`.{env,bak}` -> `.env`, `.bak`; `{.env,}` -> `.env`, ``. Innermost
    group first, recursively, capped so a hostile token cannot explode."""
    match = _BRACE_RE.search(token)
    if not match:
        return [token]
    out = []
    for alt in match.group(1).split(","):
        out.extend(_brace_expand(token[:match.start()] + alt + token[match.end():]))
        if len(out) >= MAX_BRACE_EXPANSIONS:
            break
    return out[:MAX_BRACE_EXPANSIONS]


def _expand(token, project_dir):
    """Brace-expand and shell-glob a token against the project so `.e*` and
    `.{env,bak}` are judged by the files they would actually name.
    Unexpandable tokens return themselves."""
    out = []
    for alt in _brace_expand(_expand_vars(token, project_dir)):
        if not alt:
            continue
        if not _GLOB_CHARS_RE.search(alt):
            out.append(alt)
            continue
        pattern = alt if os.path.isabs(alt) else os.path.join(project_dir, alt)
        try:
            matches = globmod.glob(pattern)
        except (OSError, ValueError):
            matches = []
        out.extend(
            [os.path.relpath(m, project_dir) if not os.path.isabs(alt) else m
             for m in matches] or [alt]
        )
    return out


def _cleaned(name):
    """A token that came from `$(cat x)` or `(cat x)` carries the shell's
    parens: judge the name inside them too."""
    stripped = name.lstrip("$({").rstrip(")};")
    return (name, stripped) if stripped != name else (name,)


def _match_token(token, globs, project_dir="."):
    # a token with whitespace came from a quoted string: a commit message
    # or an echo, not a file name (substitutions inside it are scanned
    # separately by _check_secret_tokens)
    if _WHITESPACE_RE.search(token):
        return None
    # a bare flag names nothing; `--data=@.env` names a file after the '='
    if token.startswith("-") and "=" not in token:
        return None
    for name in _candidate_names(token):
        for expanded in _expand(name, project_dir):
            for candidate in _cleaned(expanded):
                glob = _match_name(candidate, globs)
                if glob:
                    return glob
    return None


def _split_redirects(tokens):
    """Every redirect operator becomes its own token: `cat<.env` ->
    `cat`, `<`, `.env`; `3<.env` -> `3<`, `.env`; `cmd>out` -> `cmd`, `>`,
    `out`. Heredoc and herestring operators split the same way and are
    recognised (not treated as file redirects) downstream."""
    out = []
    for token in tokens:
        if "<" not in token and ">" not in token or _WHITESPACE_RE.search(token):
            # a token with whitespace is a quoted message or a script
            # (`sh -c 'cat < .env'`) — the script branch scans it whole
            out.append(token)
            continue
        out.extend(p for p in _REDIRECT_SPLIT_RE.split(token) if p)
    return out


def _tokens(segment):
    try:
        tokens = shlex.split(segment, posix=True)
    except ValueError:  # unbalanced quotes — degrade to whitespace split
        tokens = segment.split()
    return _split_redirects(tokens)


def _strip_prefix(tokens):
    """Strip leading NAME=value assignments, wrapper words (command, exec,
    nohup, time, nice, sudo, ...) plus their own option tokens, and
    subshell/group openers glued to the head, so the real command is what
    gets analyzed."""
    out = list(tokens)
    while out:
        head = out[0].lstrip("({")
        if not head:
            out = out[1:]
            continue
        if head != out[0]:
            out = [head] + out[1:]
        if _ASSIGN_RE.match(head):
            out = out[1:]
            continue
        word = os.path.basename(head)
        if word in WRAPPER_WORDS:
            out = out[1:]
            # skip the wrapper's option tokens before re-deriving the head
            while out:
                token = out[0]
                if token.startswith("-"):
                    if token in WRAPPER_ARG_FLAGS and len(out) > 1:
                        out = out[2:]
                    else:
                        out = out[1:]
                    continue
                if word == "timeout" and _DURATION_RE.match(token):
                    out = out[1:]
                    continue
                break
            continue
        break
    return out


def _matches_op(tokens, head, op_words):
    """True when the segment runs op_words as a command + subcommand sequence,
    tolerating flags in between (git -C x commit). Tokenization gives word
    boundaries, so 'git commitish' or a quoted mention never matches."""
    if not op_words or head != op_words[0]:
        return False
    rest = op_words[1:]
    if not rest:
        return True
    matched = 0
    skip_next = False
    for token in tokens[1:]:
        if skip_next:
            skip_next = False
            continue
        if token.startswith("-"):
            skip_next = token in ARG_FLAGS
            continue
        if token == rest[matched]:
            matched += 1
            if matched == len(rest):
                return True
        else:
            return False
    return False


def _git_positionals(tokens, arg_flags):
    """Positional tokens after the git subcommand, skipping flags and the
    arguments of flags that take one."""
    out = []
    skip = False
    for token in tokens[1:]:
        if skip:
            skip = False
            continue
        if token == "--":
            continue
        if token.startswith("-"):
            skip = token in arg_flags or token in ARG_FLAGS
            continue
        out.append(token)
    return out


def _default_branches(project_dir):
    """main and master always, plus whatever origin/HEAD points at — so a
    repo whose default is develop or trunk is covered too."""
    import subprocess  # lazy: only push checks need it
    names = {"main", "master"}
    try:
        result = subprocess.run(
            ["git", "-C", project_dir, "symbolic-ref", "-q", "--short",
             "refs/remotes/origin/HEAD"],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return names
    ref = result.stdout.strip() if result.returncode == 0 else ""
    if ref:
        names.add(ref.split("/", 1)[1] if "/" in ref else ref)
    return names


def _refspec_target(spec):
    """The branch a push refspec lands on: `main`, `feature:main`,
    `HEAD:refs/heads/main` and `+main` all resolve to `main`."""
    spec = spec.lstrip("+")
    target = spec.partition(":")[2] if ":" in spec else spec
    # git resolves both `refs/heads/main` and the `heads/main` shorthand
    for prefix in ("refs/heads/", "heads/"):
        if target.startswith(prefix):
            target = target[len(prefix):]
            break
    return target


def _current_branch(project_dir):
    import subprocess  # lazy: only push checks need it
    try:
        result = subprocess.run(
            ["git", "-C", project_dir, "symbolic-ref", "--short", "-q", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _check_git(tokens, head, ctx):
    """Hard invariants first (every level), then the level's forbidden set."""
    if head == "git":
        # aliases would let `git ci` stand in for `git commit`
        for token in tokens[1:]:
            if token.startswith("alias.") or token.startswith("-c") and \
                    "alias." in token:
                return ("cfm: blocked — git aliases are not allowed "
                        "(they hide the real operation from the guard).")
        sub = _git_positionals(tokens, ())
        subcommand = sub[0] if sub else None
        if subcommand == "config":
            read_only = any(t in GIT_CONFIG_READ_FLAGS for t in tokens)
            if any(t.startswith("alias.") for t in tokens) or not read_only:
                return ("cfm: blocked — 'git config' writes are not allowed; "
                        "read forms (--get, --list) are fine.")
            return None
        if subcommand == "push":
            for token in tokens[1:]:
                if token in PUSH_DESTRUCTIVE_FLAGS:
                    return (f"cfm: blocked — hard invariant: destructive push "
                            f"flag '{token}'. This holds at every git level.")
            positionals = _git_positionals(tokens, PUSH_ARG_FLAGS)[1:]
            refspecs = positionals[1:]  # after the remote
            for spec in refspecs:
                if spec.startswith(":") or spec.startswith("+"):
                    return ("cfm: blocked — hard invariant: refspec "
                            f"'{spec}' deletes or force-updates a remote ref.")
            defaults = _default_branches(ctx["project_dir"])
            for spec in refspecs:
                if _refspec_target(spec) in defaults:
                    return (
                        f"cfm: blocked — hard invariant: never push directly to "
                        f"the default branch ('{spec}'). This holds at every "
                        f"git level."
                    )
            # no refspec, or HEAD: the push lands on the checked-out branch
            if not refspecs or any(s == "HEAD" or s.startswith("HEAD:HEAD")
                                   for s in refspecs):
                branch = _current_branch(ctx["project_dir"])
                if branch and branch in defaults:
                    return (
                        f"cfm: blocked — hard invariant: the checked-out "
                        f"branch is '{branch}', so this push lands on the "
                        f"default branch. This holds at every git level."
                    )
        if subcommand == "branch":
            for token in tokens[1:]:
                if token in BRANCH_DESTRUCTIVE_FLAGS:
                    return (f"cfm: blocked — 'git branch {token}' deletes or "
                            f"renames a branch; that is the human's call.")
    if head == "gh":
        sub = _git_positionals(tokens, ())
        if sub[:1] == ["api"] and any(t in GH_API_MUTATING for t in tokens):
            return "cfm: blocked — 'gh api' with a mutating method or body."
    for op in ctx["forbidden"]:
        if _matches_op(tokens, head, op.split()):
            return (
                f"cfm: blocked — '{op}' is a forbidden operation. "
                f"Git mutations are the human's per the configured "
                f"git level ({ctx['git_level']})."
            )
    return None


def _check_verify_full(tokens, ctx):
    """The verify_full command, or it plus flags only (`npm test -- --ci`).
    A non-flag extra token — a file path, a keyword — makes it a scoped
    run, which is the agents' legitimate test shape."""
    for command in ctx["verify_full"]:
        try:
            full = shlex.split(command)
        except ValueError:
            full = command.split()
        if not full or tokens[:len(full)] != full:
            continue
        if all(t.startswith("-") for t in tokens[len(full):]):
            return VERIFY_FULL_MESSAGE
    return None


def _input_redirect_targets(tokens):
    """Files a command reads on stdin or another descriptor: `< .env`,
    `0< .env`, `3< .env`, `<> .env` (operators are already split into their
    own tokens). A heredoc (<<), herestring (<<<) or descriptor dup (<&)
    carries no file name."""
    targets = []
    for i, token in enumerate(tokens):
        if _INPUT_REDIRECT_RE.match(token) and i + 1 < len(tokens):
            targets.append(tokens[i + 1])
    return targets


def _check_secret_tokens(tokens, head, ctx, piped=False):
    globs, project_dir = ctx["globs"], ctx["project_dir"]
    for token in tokens:
        if _PROC_ENVIRON_RE.search(token):
            return ENV_DUMP_MESSAGE.format(cmd=token)
    # a secret file on stdin is a read whatever the head does with it —
    # `tee < .env` prints it, so this runs BEFORE the safe-head exemption
    for target in _input_redirect_targets(tokens):
        glob = _match_token(target, globs, project_dir)
        if glob:
            return SECRET_MESSAGE.format(target=f"< {target}", glob=glob)
    # echo/printf print their arguments — unless those arguments are piped
    # onward (`echo .env | xargs cat`), in which case they are file names
    # handed to a reader and are checked like any other
    if head in SAFE_WITH_SECRET_PATH and not (
        piped and head in ("echo", "printf")
    ):
        return None
    if head == "git":
        sub = _git_positionals(tokens, ())
        if sub and sub[0] in SAFE_GIT_WITH_SECRET_PATH:
            return None
    body = tokens[1:]
    if head in DEST_LAST_HEADS:
        # the last positional is the destination — a write, not a read
        positionals = [i for i, t in enumerate(body) if not t.startswith("-")]
        if len(positionals) >= 2:
            body = body[:positionals[-1]] + body[positionals[-1] + 1:]
    if head in PATTERN_HEADS:
        body = _drop_pattern_argument(body, head)
    skip = False
    for token in body:
        if skip:
            skip = False
            continue
        if _OUTPUT_REDIRECT_RE.match(token) or token in ("<<", "<<-", "<<<"):
            # a redirect target is written, never read; a heredoc delimiter
            # or herestring is content, not a file name
            skip = True
            continue
        glob = _match_token(token, globs, project_dir)
        if glob:
            return SECRET_MESSAGE.format(target=token, glob=glob)
    return None


def _drop_pattern_argument(body, head):
    """grep/sed/awk: the pattern is not a file. With -e/--regexp the pattern
    is that flag's argument and every positional is a file; otherwise the
    first positional is the pattern. `-f .env` (patterns FROM a file) is a
    read and stays checked, as is a narrowing `--include .env` / `-g .env`
    and an awk `-v f=.env` assignment."""
    out, files, skip, keep_next, explicit = [], [], False, False, False
    for token in body:
        if keep_next:
            keep_next = False
            if not token.startswith("!"):  # a '!' glob EXCLUDES files
                files.append(token)  # a file or file glob: still checked
            continue
        if skip:
            skip = False
            continue  # the -e argument (a pattern) or a count/label
        if token in PATTERN_FLAGS:
            skip = explicit = True
            continue
        if token in PATTERN_FILE_FLAGS:
            keep_next = explicit = True
            continue
        if token in PATTERN_NARROW_FLAGS or (head in AWK_HEADS and token == "-v"):
            keep_next = True
            continue
        if token in PATTERN_SKIP_FLAGS and token != "-v":
            skip = True
            continue
        if token.startswith(("--regexp=", "--expression=")):
            explicit = True
            continue  # a pattern
        if token.startswith(("--file=", "--exclude-from=")):
            explicit = True
            out.append(token)  # --file=.env names a file; _match_token sees '='
            continue
        out.append(token)
    if explicit:
        return out + files
    for i, token in enumerate(out):
        if not token.startswith("-"):
            return out[:i] + out[i + 1:] + files
    return out + files


def _find_name_samples(globs):
    """Concrete file names each secret glob stands for (`.env*` -> `.env`,
    `.envx`; `*.pem` -> `.pem`, `x.pem`), so a find pattern like `.en*`,
    `*env` or `-iname .ENV` is judged by whether it would match one."""
    samples = set()
    for glob in globs:
        bare = glob[3:] if glob.startswith("**/") else glob
        for fill in ("", "x"):
            sample = bare.replace("*", fill).replace("?", "x")
            if sample:
                samples.add(sample)
    return samples


def _find_name_hits(pattern, globs):
    if _match_name(pattern, globs):
        return True
    lowered = pattern.lower()
    for sample in _find_name_samples(globs):
        for shaped in (sample, f"x/{sample}", f"./x/{sample}"):
            if fnmatch.fnmatchcase(shaped.lower(), lowered):
                return True
    return False


def _check_find(tokens, ctx, piped):
    names = []
    for i, token in enumerate(tokens):
        if token in FIND_NAME_FLAGS and i + 1 < len(tokens):
            names.append(tokens[i + 1])
    if not names:
        return None
    acts = piped or any(t in FIND_ACTION_FLAGS for t in tokens)
    if not acts:
        return None  # listing names is not reading contents
    for name in names:
        if _find_name_hits(name, ctx["globs"]):
            return SECRET_MESSAGE.format(target=f"find {name}",
                                         glob="(a find pattern matching one)")
    return None


# --- policy files (subagents) ------------------------------------------------

def _plugin_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _policy_roots(project_dir):
    roots = [os.path.join(project_dir, rel) for rel in PROTECTED_PROJECT_PATHS]
    home = os.path.expanduser("~")
    roots.extend(os.path.join(home, rel) for rel in PROTECTED_HOME_PATHS)
    roots.append(os.environ.get("CLAUDE_PLUGIN_ROOT") or _plugin_root())
    return [os.path.realpath(r) for r in roots]


def _under_plugin(name, ctx):
    plugin = ctx["policy_roots"][-1]
    name = _expand_vars(name, ctx["project_dir"])
    absolute = name if os.path.isabs(name) else os.path.join(ctx["project_dir"], name)
    real = os.path.realpath(absolute)
    return real == plugin or real.startswith(plugin + os.sep)


def _policy_hit(name, ctx, ancestor=False):
    """The protected path `name` denotes, or None. With `ancestor`, a
    directory above a protected path counts too (rm -rf . / .claude)."""
    project_dir = ctx["project_dir"]
    for candidate in _cleaned(name):
        if not candidate:
            continue
        if os.path.basename(candidate.rstrip("/")) in PROTECTED_BASENAMES:
            return candidate
        absolute = candidate if os.path.isabs(candidate) \
            else os.path.join(project_dir, candidate)
        real = os.path.realpath(absolute)
        for root in ctx["policy_roots"]:
            if real == root or real.startswith(root + os.sep):
                return candidate
            if ancestor and root.startswith(real + os.sep):
                return candidate
    return None


def _policy_token(token, ctx, ancestor=False):
    if _WHITESPACE_RE.search(token):
        return None
    if token.startswith("-") and "=" not in token:
        return None
    for name in _candidate_names(token):
        for expanded in _expand(name, ctx["project_dir"]):
            hit = _policy_hit(expanded, ctx, ancestor)
            if hit:
                return hit
    return None


# --- product files (the main session, in cfm mode) --------------------------

def _orchestrator_roots(config, project_dir):
    """What the main session may write: the fixed workflow paths plus the
    config's own path fields (falling back to the defaults when a field is
    missing or garbage, so a broken config never widens the writable set)
    and every claude_md.files entry. A path that escapes the project is a
    validation error, not a root."""
    cfm_config = _cfm_config()
    rels = list(ORCHESTRATOR_PROJECT_PATHS)
    for field in ORCHESTRATOR_CONFIG_PATH_FIELDS:
        value = config.get(field)
        rels.append(value if isinstance(value, str) and value
                    else cfm_config.DEFAULTS[field])
    files = (config.get("claude_md") or {}).get("files") \
        if isinstance(config.get("claude_md"), dict) else None
    if isinstance(files, list):
        rels.extend(f for f in files if isinstance(f, str) and f)
    roots = []
    for rel in rels:
        parts = rel.replace("\\", "/").split("/")
        if os.path.isabs(rel) or ".." in parts:
            continue
        roots.append(os.path.realpath(os.path.join(project_dir, rel)))
    return roots


def _orchestrator_hit(name, ctx, must_exist=False):
    """The product path `name` denotes, or None. Product = inside the
    project and under none of the orchestrator roots; the config pair is
    never product wherever it sits. Paths outside the project (/tmp,
    ~/.claude) are not the guard's to govern. `must_exist` filters
    positionals that only look like paths (chmod 755, git checkout
    feature/x, a sed pattern). Symlinks resolve like the policy rule: a
    link inside the project pointing out is outside."""
    project = ctx["project_real"]
    for candidate in _cleaned(name):
        if not candidate:
            continue
        if os.path.basename(candidate.rstrip("/")) in PROTECTED_BASENAMES:
            continue
        absolute = candidate if os.path.isabs(candidate) \
            else os.path.join(ctx["project_dir"], candidate)
        real = os.path.realpath(absolute)
        if real != project and not real.startswith(project + os.sep):
            continue
        if any(real == root or real.startswith(root + os.sep)
               for root in ctx["orchestrator_roots"]):
            continue
        if must_exist and not os.path.lexists(absolute):
            continue
        return candidate
    return None


def _orchestrator_token(token, ctx, must_exist=False):
    if _WHITESPACE_RE.search(token):
        return None
    if token.startswith("-") and "=" not in token:
        return None
    for name in _candidate_names(token):
        for expanded in _expand(name, ctx["project_dir"]):
            hit = _orchestrator_hit(expanded, ctx, must_exist)
            if hit:
                return hit
    return None


def _find_mutates(body):
    """find -delete, or -exec/-ok running a head that is not a plain reader
    (`-exec grep x {} +` is a read and does not count)."""
    if "-delete" in body:
        return True
    for i, token in enumerate(body):
        if token in ("-exec", "-execdir", "-ok", "-okdir") and i + 1 < len(body):
            sub = _strip_prefix(body[i + 1:])
            sub_head = os.path.basename(sub[0]) if sub else ""
            if sub_head and sub_head not in POLICY_READ_HEADS:
                return True
    return False


def _sed_in_place(body):
    return any(t.startswith("-i") or t.startswith("--in-place") or
               (t.startswith("-") and not t.startswith("--") and "i" in t[1:])
               for t in body)


def _awk_in_place(body):
    return any(t == "-i" or t.startswith("--in-place") or t.startswith("-i")
               for t in body)


def _yq_in_place(body):
    return any(t == "-i" or t == "--inplace" or
               (t.startswith("-") and not t.startswith("--") and "i" in t[1:])
               for t in body)


def _sort_output(body):
    return any(t == "-o" or t.startswith("--output") or
               (t.startswith("-o") and not t.startswith("--")) for t in body)


def _extract_dest(head, body):
    """Where an extraction lands, or None when the command does not
    extract. The default is the working directory."""
    if head in ("tar", "bsdtar"):
        first = body[0] if body else ""
        extracting = "--extract" in body or any(
            t.startswith("-") and not t.startswith("--") and "x" in t[1:]
            for t in body) or (first and not first.startswith("-") and "x" in first)
        if not extracting:
            return None
        for i, t in enumerate(body):
            if t in ("-C", "--directory") and i + 1 < len(body):
                return body[i + 1]
            if t.startswith("--directory="):
                return t.partition("=")[2]
            if t.startswith("-C") and len(t) > 2:
                return t[2:]
        return "."
    if head == "unzip":
        for i, t in enumerate(body):
            if t == "-d" and i + 1 < len(body):
                return body[i + 1]
        return "."
    if head in ("7z", "7za", "7zr"):
        if not body or body[0] not in ("x", "e"):
            return None
        for t in body:
            if t.startswith("-o") and len(t) > 2:
                return t[2:]
        return "."
    if head == "unrar":
        if not body or body[0] not in ("x", "e"):
            return None
        positionals = [t for t in body[2:] if not t.startswith("-")]
        return positionals[-1] if positionals and positionals[-1].endswith("/") else "."
    return None


def _without_redirects(body):
    """The body with every redirect operator and its target removed, so a
    head's positionals are judged without `< in` or `> out` among them."""
    out, skip = [], False
    for token in body:
        if skip:
            skip = False
            continue
        if _OUTPUT_REDIRECT_RE.match(token) or _INPUT_REDIRECT_RE.match(token) \
                or token in ("<<", "<<-", "<<<"):
            skip = True
            continue
        out.append(token)
    return out


def _output_flag_targets(head, body):
    flags = OUTPUT_FLAG_HEADS.get(head, ())
    out = []
    for i, token in enumerate(body):
        if token in flags and i + 1 < len(body):
            out.append(body[i + 1])
        elif any(token.startswith(f + "=") for f in flags if f.startswith("--")):
            out.append(token.partition("=")[2])
        elif any(token.startswith(f) and len(token) > len(f)
                 for f in flags if not f.startswith("--")):
            out.append(token[len(next(f for f in flags if token.startswith(f))):])
    if head == "dd":
        out.extend(t.partition("=")[2] for t in body if t.startswith("of="))
    return out


def _write_targets(tokens, head, ctx, piped):
    """The tokens a command may write, each tagged (token, ancestor, kind),
    plus an inject label when the command lands content the guard cannot
    inspect. Kinds: `redirect` (the target of >, >>, &>), `dest` (an
    explicit destination — cp/install/ln last positional, sort -o, curl
    -o, wget -O, dd of=, tee/touch/truncate positionals, an extraction
    directory), `path` (rm/mv/chmod, sed -i and friends, ed/ex, find start
    directories and -name patterns, tree-writing git positionals — a path
    only if it exists), `piped` (an echo/printf feeding a pipe),
    `interpreter` (arguments of python3/node/bash/…) and `default`
    (positionals of a head the tables do not know). Each rule decides
    which kinds it honors. The inject label is (cmd, conditional):
    unconditional for git apply/am/stash pop, conditional on a `dest` hit
    for archive extraction."""
    out = []
    for i, token in enumerate(tokens):
        if _OUTPUT_REDIRECT_RE.match(token) and i + 1 < len(tokens):
            target = tokens[i + 1]
            if target.isdigit() or target == "-":
                continue  # a descriptor dup (2>&1, >&2), not a file
            out.append((target, False, "redirect"))
    body = _without_redirects(tokens[1:])
    positional = [t for t in body if not t.startswith("-")]

    def tag(items, kind, ancestor=False):
        out.extend((t, ancestor, kind) for t in items)

    if head in ("echo", "printf"):
        if piped:
            # `echo .cfm-workflow.yml | xargs rm` — the guard cannot see what
            # a pipe feeds, so a piped echo's arguments are candidates
            tag(body, "piped")
        return out, None
    if head in POLICY_READ_HEADS:
        return out, None
    if head in IN_PLACE_HEADS:
        if _sed_in_place(body):
            tag(_drop_pattern_argument(body, head), "path")
        return out, None
    if head in AWK_INPLACE_HEADS:
        if _awk_in_place(body):
            tag(_drop_pattern_argument(body, head), "path")
        return out, None
    if head == "yq":
        if _yq_in_place(body):
            tag(_drop_pattern_argument(body, head), "path")
        return out, None
    if head == "sort":
        if not _sort_output(body):
            return out, None
        for i, token in enumerate(body):
            if token == "-o" and i + 1 < len(body):
                tag([body[i + 1]], "dest")
            elif token.startswith("--output="):
                tag([token.partition("=")[2]], "dest")
            elif token.startswith("-o") and not token.startswith("--"):
                tag([token[2:]], "dest")
        tag(positional, "default")
        return out, None
    if head in OUTPUT_FLAG_HEADS or head == "dd":
        tag(_output_flag_targets(head, body), "dest")
        tag(body, "default")
        return out, None
    if head in CREATE_HEADS:
        tag(body, "dest")
        return out, None
    if head in EDITOR_HEADS:
        tag(body, "path")
        return out, None
    if head in DEST_LAST_HEADS and head != "mv":
        if len(positional) >= 2:
            tag([positional[-1]], "dest")
        else:
            tag(body, "path")
        return out, None
    if head in DESTROY_HEADS:
        tag(body, "path", ancestor=True)
        return out, None
    if head == "find":
        if not _find_mutates(body):
            return out, None
        names = []
        for i, token in enumerate(body):
            if token in FIND_NAME_FLAGS and i + 1 < len(body):
                names.append(body[i + 1])
        # the start directories: everything before the first predicate
        for token in body:
            if token.startswith("-") or token in ("(", "!"):
                break
            names.append(token)
        tag(names, "path", ancestor=True)
        return out, None
    if head == "git":
        sub = _git_positionals(tokens, ())
        if not sub:
            return out, None
        if sub[0] in GIT_INJECT_SUBCOMMANDS or (
            sub[0] == "stash" and sub[1:2] and sub[1] in GIT_STASH_INJECT
        ):
            return out, ("git " + " ".join(sub[:2]), False)
        if sub[0] in GIT_TREE_WRITERS:
            tag(sub[1:], "path", ancestor=True)
        return out, None
    if head in EXTRACT_HEADS:
        dest = _extract_dest(head, body)
        if dest is not None:
            tag([dest], "dest", ancestor=True)
            return out, (f"{head} into {dest}", True)
        return out, None
    if head in INTERPRETER_HEADS:
        tag(body, "interpreter")
        return out, None
    tag(body, "default")
    return out, None


def _check_writes(tokens, head, ctx, piped, hit, message, inject_message):
    """Run one write rule over the command: `hit(token, ancestor, kind)`
    returns the protected path a candidate denotes, or None."""
    candidates, inject = _write_targets(tokens, head, ctx, piped)
    if inject and not inject[1]:
        return inject_message.format(cmd=inject[0])
    for token, ancestor, kind in candidates:
        target = hit(token, ancestor, kind)
        if target:
            if inject and kind == "dest":
                return inject_message.format(cmd=inject[0])
            return message.format(target=target)
    return None


def _check_policy(tokens, head, ctx, piped):
    """Subagents never modify policy files. Token-first: any candidate of
    any kind naming one blocks the call unless the head only reads what it
    names; a plugin script handed to an interpreter is execution."""
    def hit(token, ancestor, kind):
        if kind == "interpreter" and _under_plugin(token, ctx):
            return None
        return _policy_token(token, ctx, ancestor)
    return _check_writes(tokens, head, ctx, piped, hit,
                         POLICY_MESSAGE, POLICY_INJECT_MESSAGE)


def _check_orchestrator(tokens, head, ctx, piped):
    """cfm mode: the main session never writes product code. Head-first:
    only a head whose semantics write the candidate counts, an unknown
    head or an interpreter is execution, and a piped echo names nothing —
    the rule protects the whole tree, so a token-first fallback would
    refuse most legitimate commands."""
    def hit(token, ancestor, kind):
        if kind in ("interpreter", "default", "piped"):
            return None
        return _orchestrator_token(token, ctx, must_exist=(kind == "path"))
    return _check_writes(tokens, head, ctx, piped, hit,
                         ORCHESTRATOR_MESSAGE, ORCHESTRATOR_INJECT_MESSAGE)


# --- command analysis --------------------------------------------------------

def _analyze_command(tokens, ctx, depth, piped=False):
    # before the NAME=value prefix is discarded: GIT_CONFIG_PARAMETERS and
    # friends can define `alias.ci=commit`, turning `git ci` into a commit
    for token in tokens:
        if _GIT_CONFIG_ENV_RE.match(token):
            return GIT_CONFIG_ENV_MESSAGE.format(token=token.partition("=")[0])
    tokens = _strip_prefix(tokens)
    # env unwraps iteratively (no depth cost): strip env's own flags and
    # NAME=value tokens; no command left means env prints the environment
    while tokens and os.path.basename(tokens[0]) == "env":
        rest = tokens[1:]
        i = 0
        while i < len(rest):
            token = rest[i]
            if token == "--":
                i += 1
                continue
            if token in ENV_ARG_FLAGS:
                i += 2
                continue
            if token.startswith("-"):
                i += 1
                continue
            if _ASSIGN_RE.match(token):
                i += 1
                continue
            break
        if i >= len(rest):
            return ENV_DUMP_MESSAGE.format(cmd="env")
        tokens = _strip_prefix(rest[i:])
    if not tokens:
        return None
    head = os.path.basename(tokens[0])

    if ctx.get("subagent"):
        message = _check_policy(tokens, head, ctx, piped)
    elif ctx.get("mode") == "enforced":
        message = _check_orchestrator(tokens, head, ctx, piped)
    else:
        message = None
    if message:
        return message
    if head == "printenv":
        return ENV_DUMP_MESSAGE.format(cmd="printenv")
    # shell builtins that print every variable when given no name
    if head == "set" and len(tokens) == 1:
        return ENV_DUMP_MESSAGE.format(cmd="set")
    if head == "export" and all(t == "-p" for t in tokens[1:]):
        return ENV_DUMP_MESSAGE.format(cmd="export -p")
    if head in ("declare", "typeset") and "-p" in tokens[1:] \
            and all(t.startswith("-") for t in tokens[1:]):
        return ENV_DUMP_MESSAGE.format(cmd=f"{head} -p")
    if head == "eval" and depth < MAX_DEPTH:
        # eval runs its arguments as a script — analyze them as one
        message = _scan_command(" ".join(tokens[1:]), ctx, depth + 1)
        if message:
            return message
    # the depth cap only limits true recursion — an exhausted depth still
    # runs every direct check below on the current tokens
    if head in SHELL_WORDS and depth < MAX_DEPTH:
        # sh -c '<script>' — analyze the script like a top-level command
        for i in range(1, len(tokens) - 1):
            token = tokens[i]
            if token == "-c" or (token.startswith("-")
                                 and not token.startswith("--")
                                 and token.endswith("c")):
                return _scan_command(tokens[i + 1], ctx, depth + 1)
    if head == "xargs" and depth < MAX_DEPTH:
        rest = tokens[1:]
        i = 0
        while i < len(rest) and rest[i].startswith("-"):
            i += 2 if rest[i] in ("-I", "-a", "-d", "-E", "-L", "-n", "-P", "-s") else 1
        if i < len(rest):
            message = _analyze_command(rest[i:], ctx, depth + 1)
            if message:
                return message
    if head == "find":
        message = _check_find(tokens, ctx, piped)
        if message:
            return message
        if depth < MAX_DEPTH:
            for i, token in enumerate(tokens):
                if token in ("-exec", "-execdir", "-ok", "-okdir"):
                    sub = []
                    for t in tokens[i + 1:]:
                        if t in (";", "+"):
                            break
                        sub.append(t)
                    if sub:
                        message = _analyze_command(sub, ctx, depth + 1)
                        if message:
                            return message
        return None

    message = _check_verify_full(tokens, ctx)
    if message:
        return message
    message = _check_git(tokens, head, ctx)
    if message:
        return message
    return _check_secret_tokens(tokens, head, ctx, piped)


def _split_segments(command):
    """Split on the shell separators outside quotes. Returns a list of
    (segment, separator-that-followed-it); the last separator is ''."""
    segments, buf, quote, i, n = [], [], None, 0, len(command)
    while i < n:
        ch = command[i]
        if quote:
            if ch == "\\" and quote == '"' and i + 1 < n:
                buf.append(command[i:i + 2])
                i += 2
                continue
            if ch == quote:
                quote = None
            buf.append(ch)
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            buf.append(ch)
            i += 1
            continue
        if ch == "\\" and i + 1 < n:
            buf.append(command[i:i + 2])
            i += 2
            continue
        for sep in _SEPARATORS:
            if command.startswith(sep, i):
                segments.append(("".join(buf), sep))
                buf = []
                i += len(sep)
                break
        else:
            buf.append(ch)
            i += 1
    segments.append(("".join(buf), ""))
    return segments


def _scan_command(command, ctx, depth, tail_piped=False):
    """`tail_piped`: the text is a substitution whose output becomes the
    enclosing command's arguments, so its last segment is treated like a
    command feeding a pipe (`$(echo .env)` names a file for `cat`)."""
    segments = _split_segments(command)
    for index, (segment, separator) in enumerate(segments):
        # a $(...), `...` or <(...) anywhere in the segment — inside a quoted
        # echo, under a safe head like ls — is a command of its own; scan it
        # on the raw text, since shlex does not treat backticks as quotes
        if depth < MAX_DEPTH:
            for match in _SUBST_RE.finditer(segment):
                inner = next(g for g in match.groups() if g is not None)
                message = _scan_command(inner, ctx, depth + 1, tail_piped=True)
                if message:
                    return message
        tokens = _tokens(segment)
        if not tokens:
            continue
        piped = separator == "|" or (tail_piped and index == len(segments) - 1)
        message = _analyze_command(tokens, ctx, depth, piped=piped)
        if message:
            return message
    return None


def _context(config, project_dir):
    cfm_config = _cfm_config()
    git_level = (config.get("git") or {}).get("level")
    if not isinstance(git_level, str):
        git_level = cfm_config.DEFAULTS["git"]["level"]
    mode = config.get("mode")
    if mode not in cfm_config.MODES:
        mode = cfm_config.DEFAULTS["mode"]  # a broken value never disables the rule
    return {
        "globs": _secret_globs(config),
        "forbidden": cfm_config.forbidden_ops(config),
        "git_level": git_level,
        "verify_full": cfm_config.slot_commands(config, "verify_full"),
        "project_dir": project_dir,
        "project_real": os.path.realpath(project_dir),
        "policy_roots": _policy_roots(project_dir),
        "mode": mode,
        "orchestrator_roots": _orchestrator_roots(config, project_dir),
        "subagent": False,
    }


def load_context(project_dir):
    """The decision context for a project, parsed from the config on every
    call. A broken or unparseable config still yields a context — the
    defaults enforce."""
    config, _errors, _warnings = _cfm_config().load(project_dir)
    if not isinstance(config, dict):
        config = {}  # unparseable config still enforces via defaults
    return _context(config, project_dir)


def _check_bash(command, ctx):
    stripped = command.strip()
    # the whole command as written, before any splitting
    for full in ctx["verify_full"]:
        if stripped == full.strip():
            return VERIFY_FULL_MESSAGE
    return _scan_command(command, ctx, 0)


def _grep_glob_hits(glob_param, globs):
    """Grep's glob narrows the files searched; a glob that names secret
    files turns Grep into a reader of them. Brace groups and comma lists
    are checked per alternative."""
    if not isinstance(glob_param, str) or not glob_param:
        return None
    alternatives = [glob_param]
    while any("{" in a for a in alternatives):  # expand braces first
        expanded = []
        for alt in alternatives:
            brace = re.match(r"^(.*?)\{([^{}]*)\}(.*)$", alt)
            if brace:
                for inner in brace.group(2).split(","):
                    expanded.append(brace.group(1) + inner.strip() + brace.group(3))
            else:
                expanded.append(alt)
        alternatives = expanded
    alternatives = [p.strip() for a in alternatives for p in a.split(",")]
    for alt in alternatives:
        glob = _match_name(alt, globs)
        if glob:
            return alt, glob
    return None


def _note_subagent_observed(project_dir, event):
    """Record, once, that a real subagent event reached the guard. Doctor
    check 8 reads this: a phase that dispatched agents without the marker
    means the agent_id branch never fired, and the policy-file layer is
    inert. Evidence only — never policy — so a write failure is ignored."""
    if os.environ.get("CFM_GUARD_SELFTEST"):
        return  # the doctor's synthetic probes are not evidence
    path = os.path.join(project_dir, SUBAGENT_OBSERVED_REL)
    if os.path.exists(path):
        return
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            import datetime
            fh.write(json.dumps({
                "observed": datetime.datetime.now(datetime.timezone.utc)
                .strftime("%Y-%m-%dT%H:%M:%SZ"),
                "agent_type": event.get("agent_type"),
                "fields": sorted(k for k in event if k.startswith("agent_")),
            }) + "\n")
    except OSError:
        pass


def decide(event, project_dir):
    """(exit code, message) for one hook event."""
    tool_name = event.get("tool_name", "")
    tool_input = event.get("tool_input") or {}
    ctx = load_context(project_dir)
    # Claude Code sets agent_id (and agent_type) only when the hook fires
    # inside a subagent — documented hook-input fields
    ctx["subagent"] = bool(event.get("agent_id") or event.get("agent_type"))
    if ctx["subagent"]:
        _note_subagent_observed(project_dir, event)
    globs = ctx["globs"]

    if tool_name in FILE_PATH_TOOLS or tool_name == "Grep":
        if tool_name == "Grep":
            path = tool_input.get("path")
            hit = _grep_glob_hits(tool_input.get("glob"), globs)
            if hit:
                return 2, SECRET_MESSAGE.format(target=f"glob {hit[0]}", glob=hit[1])
        else:
            path = tool_input.get("file_path") or tool_input.get("notebook_path")
        if isinstance(path, str) and path:
            glob = _match_path(path, project_dir, globs)
            if glob:
                return 2, SECRET_MESSAGE.format(target=path, glob=glob)
            if tool_name in FILE_WRITE_TOOLS:
                expanded = _expand_vars(path, project_dir)
                if ctx["subagent"]:
                    if _policy_hit(expanded, ctx):
                        return 2, POLICY_MESSAGE.format(target=path)
                elif ctx["mode"] == "enforced" and _orchestrator_hit(expanded, ctx):
                    return 2, ORCHESTRATOR_MESSAGE.format(target=path)
    elif tool_name == "Bash":
        command = tool_input.get("command")
        if isinstance(command, str) and command:
            message = _check_bash(command, ctx)
            if message:
                return 2, message
    return 0, None


def main():
    event = json.load(sys.stdin)
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    if not os.path.exists(os.path.join(project_dir, ".cfm-workflow.yml")):
        return 0  # not a cfm project — the guard only governs cfm projects
    code, message = decide(event, project_dir)
    if message:
        print(message, file=sys.stderr)
    return code


if __name__ == "__main__":
    # Fail-open on unexpected errors: the generated settings.json deny rules
    # are the second enforcement layer, so a crash here must never break hooks.
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"cfm guard: internal error, allowing tool call ({exc})", file=sys.stderr)
        sys.exit(0)
