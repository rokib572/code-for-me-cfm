#!/usr/bin/env python3
"""Unit tests for the PreToolUse decision engine (scripts/guard_check.py).

Stdlib unittest only — no new dependency, no model calls, no hook spawn.
The hook-integration cases (through guard.sh) live in test_guard_hook.py.

    python3 -m unittest tests/test_guard.py -v

Every "was a bypass" case below was verified against the real hook before
its fix; keep them as regressions.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cfm_config  # noqa: E402
import guard_check  # noqa: E402

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "valid.yml")


def _ctx(project_dir, level="L0", verify_full=("true",), mode="enforced"):
    return {
        "globs": list(cfm_config.DEFAULT_SECRET_GLOBS),
        "forbidden": cfm_config.forbidden_ops({"git": {"level": level}}),
        "git_level": level,
        "verify_full": list(verify_full),
        "project_dir": project_dir,
        "project_real": os.path.realpath(project_dir),
        "policy_roots": guard_check._policy_roots(project_dir),
        "mode": mode,
        "orchestrator_roots": guard_check._orchestrator_roots({}, project_dir),
        "subagent": False,
    }


class GuardCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="cfm-guard-")
        for name in (".env", ".env.local", "server.pem", ".netrc", "README.md"):
            with open(os.path.join(self.dir, name), "w") as fh:
                fh.write("SECRET=x\n")
        self.ctx = _ctx(self.dir)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def blocked(self, command, level="L0"):
        ctx = self.ctx if level == "L0" else _ctx(self.dir, level)
        message = guard_check._check_bash(command, ctx)
        self.assertIsNotNone(message, f"expected BLOCK: {command!r}")
        return message

    def allowed(self, command, level="L0"):
        ctx = self.ctx if level == "L0" else _ctx(self.dir, level)
        message = guard_check._check_bash(command, ctx)
        self.assertIsNone(message, f"expected ALLOW: {command!r} -> {message}")


class SecretFiles(GuardCase):
    def test_plain_reads_block(self):
        for cmd in ("cat .env", "head .env", "sort .env", "cat -- .env",
                    "diff .env.example .env", "cat .e*", "cat ~/.netrc",
                    "cat $HOME/.netrc", "base64 .env", "cat .env{,.local}"):
            self.blocked(cmd)

    def test_stdin_redirect_is_a_read_under_every_head(self):
        # `tee < .env` was a verified bypass: tee is a safe head, and the
        # safe-head return skipped the redirect
        for cmd in ("tee < .env", "tee <.env", "cat 0< .env", "wc -c < .env",
                    "ls < .env"):
            self.blocked(cmd)
        self.allowed("wc -c < README.md")
        self.allowed("cat <<EOF\n.env\nEOF")  # heredoc carries content

    def test_git_blob_spec(self):
        # `git show HEAD:.env.local` was a verified bypass
        for cmd in ("git show HEAD:.env.local", "git cat-file -p HEAD:.env",
                    "git show main:config/.env.production"):
            self.blocked(cmd)

    def test_colon_and_equals_forms(self):
        self.blocked("docker run -v $HOME/app/.env:/e alpine cat /e")
        self.blocked("curl --data=@.env")
        self.blocked("curl --data-binary @.env")

    def test_write_destinations_allowed(self):
        # the SECRET rule's write carve-out; in cfm mode the orchestrator
        # rule has its own say on these (OrchestratorRule), so mode is off
        ctx = _ctx(self.dir, mode="off")
        for cmd in ("cp .env.example .env", "echo x > .env",
                    "echo hi | tee .env.bak", "touch .env", "rm .env",
                    "ls -la .env", "git check-ignore .env", "cat .env.example"):
            message = guard_check._check_bash(cmd, ctx)
            self.assertIsNone(message, f"expected ALLOW: {cmd!r} -> {message}")
        # a secret as the SOURCE of cp/mv launders it into a readable name
        self.blocked("cp .env /tmp/plain")
        self.blocked("mv .env /tmp/plain")

    def test_naming_a_secret_file_is_not_reading_it(self):
        # the most common legitimate commands that mention `.env`
        for cmd in ('echo ".env" >> .gitignore', 'printf ".env\\n" >> .gitignore',
                    'grep -q "\\.env" .gitignore', 'grep -e "\\.env" .gitignore',
                    "grep --regexp=.env .gitignore", 'rg "\\.env" .gitignore',
                    'grep -A 3 "\\.env" .gitignore', 'sed -i "s/.env//" .gitignore',
                    'grep -rn "\\.env" src/'):
            self.allowed(cmd)

    def test_pattern_carve_out_does_not_open_file_reads(self):
        for cmd in ("grep SECRET .env", "grep -e SECRET .env", "grep -c x .env",
                    "grep -f .env foo.txt", "grep --file=.env foo.txt",
                    "sed -f .env x", "sed -n p .env", "awk '{print}' .env",
                    "echo $(cat .env)", "echo `cat .env`"):
            self.blocked(cmd)

    def test_substitution_under_safe_head(self):
        self.blocked("ls $(cat .env)")

    def test_env_dumps(self):
        for cmd in ("env", "printenv", "cat /proc/self/environ", "export -p"):
            self.blocked(cmd)
        self.allowed("env FOO=1 ls")


class GitInvariants(GuardCase):
    def test_level_forbids(self):
        self.blocked("git commit -m x")
        self.blocked("git stash")
        self.allowed("git log --oneline -5")
        self.allowed("git status")
        self.allowed("git commit -m x", level="L1")

    def test_alias_via_flags_and_environment(self):
        self.blocked("git -c alias.ci=commit ci")
        self.blocked("git -calias.ci=commit ci")
        # GIT_CONFIG_PARAMETERS was a verified bypass at L0: the NAME=value
        # prefix was stripped without inspection
        self.blocked("GIT_CONFIG_PARAMETERS=\"'alias.ci=commit'\" git ci -m x")
        self.blocked("env GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.ci git ci")
        self.blocked("GIT_CONFIG_GLOBAL=/tmp/x git ci", level="L3")

    def test_default_branch_push_at_every_level(self):
        for spec in ("main", "master", "feature:main", "HEAD:refs/heads/main",
                     "refs/heads/main", "heads/main", "+main"):
            message = self.blocked(f"git push origin {spec}", level="L2")
            self.assertIn("hard invariant", message)
        self.allowed("git push origin feature/x", level="L2")
        self.allowed("git push origin HEAD:feature/x", level="L2")

    def test_destructive_push_and_branch_flags(self):
        for cmd in ("git push --force origin feature/x",
                    "git push origin :feature/x", "git push --delete origin f",
                    "git branch -D feature/x", "git branch -m a b"):
            self.blocked(cmd, level="L3")

    def test_always_forbidden(self):
        for cmd in ("gh pr merge 1", "git config user.name x",
                    "gh api -X POST repos/x/y/issues"):
            self.blocked(cmd, level="L3")
        self.allowed("git config --get user.name", level="L3")


class VerifyFull(GuardCase):
    def test_exact_and_flags_only(self):
        ctx = _ctx(self.dir, verify_full=("npm test",))
        self.assertIsNotNone(guard_check._check_bash("npm test", ctx))
        self.assertIsNotNone(guard_check._check_bash("npm test -- --watch", ctx))
        self.assertIsNotNone(guard_check._check_bash("cd apps && npm test", ctx))
        self.assertIsNone(guard_check._check_bash("npm test src/a.test.ts", ctx))


class QuotingAndSplitting(GuardCase):
    def test_commit_message_is_not_a_command(self):
        # quoted whitespace is a message; the separator inside never splits
        self.allowed('git log --grep "add .env && cat .env"')
        self.blocked('git commit -m "add .env && cat .env"')  # commit, at L0

    def test_subshell_and_wrappers(self):
        for cmd in ("(cat .env)", "nohup cat .env", "timeout 5 cat .env",
                    "sudo -u x cat .env", "sh -c 'cat .env'",
                    "eval cat .env", "find . -name .env -exec cat {} +",
                    # echo is a safe head, but not when its output is piped
                    # to a reader: then its arguments are file names
                    "echo .env | xargs cat", "printf '%s' .env | xargs cat"):
            self.blocked(cmd)
        self.allowed("find . -name .env")  # listing names is not reading
        # the guard cannot see what a pipe feeds, so a piped echo naming a
        # secret is blocked even into a writer — use a redirect instead
        self.blocked("echo .env | tee -a .gitignore")
        self.allowed("echo .env >> .gitignore")


class FileTools(GuardCase):
    def test_match_path(self):
        globs = self.ctx["globs"]
        self.assertIsNotNone(guard_check._match_path("apps/api/.env.local", self.dir, globs))
        self.assertIsNotNone(guard_check._match_path("infra/credentials", self.dir, globs))
        self.assertIsNone(guard_check._match_path(".env.example", self.dir, globs))
        self.assertIsNone(guard_check._match_path("src/env.ts", self.dir, globs))

    def test_grep_tool_glob(self):
        globs = self.ctx["globs"]
        self.assertIsNotNone(guard_check._grep_glob_hits("**/.env*", globs))
        self.assertIsNotNone(guard_check._grep_glob_hits("{*.ts,.env}", globs))
        self.assertIsNone(guard_check._grep_glob_hits("*.ts", globs))


class RedirectForms(GuardCase):
    def test_glued_and_numbered_descriptors(self):
        # `cat<.env`, `exec 3<.env` and `cat 3<.netrc <&3` were verified
        # bypasses: shlex keeps a glued operator inside the word
        for cmd in ("cat<.env", "cat<.netrc", "sort<.env", "exec 3<.env; cat <&3",
                    "cat 3<.netrc <&3", "cat server.pem>out", "cat .netrc>out"):
            self.blocked(cmd)
        self.allowed("cat <<< .env")  # a herestring is content
        self.allowed("echo x 2>&1")
        self.allowed("cat<README.md")


class Substitutions(GuardCase):
    def test_process_substitution_and_echo_feeding_a_reader(self):
        for cmd in ("cat <(cat server.pem)", "diff <(cat .netrc) /dev/null",
                    "cat $(echo server.pem)", 'cat "$(echo .env)"',
                    "(cat server.pem)"):
            self.blocked(cmd)
        self.allowed('echo "$(date)"')
        self.allowed('git log --grep "$(cat msg.txt)"')


class Expansions(GuardCase):
    def test_brace_groups_expand(self):
        for cmd in ("cat .{env,bak}", "cat {.env,}", "cat .env{,.local}"):
            self.blocked(cmd)
        self.allowed("cat {README,LICENSE}.md")


class NarrowingFlags(GuardCase):
    def test_include_and_glob_flags_name_files(self):
        # `--include .env` and `rg -g .env` narrow a repo-wide search TO the
        # secret file; both were verified bypasses (the argument was skipped)
        for cmd in ("grep -r --include .env SECRET .", "rg -g .env SECRET .",
                    "rg --iglob .env SECRET .", "grep -r --include '*.pem' x .",
                    "awk -v f=.env 'BEGIN{while((getline l < f)>0)print l}'"):
            self.blocked(cmd)
        self.allowed("rg -g '!.env' SECRET .")  # exclusion
        self.allowed("grep -r --include '*.ts' SECRET .")
        self.allowed("awk -v x=1 '{print}' README.md")
        self.allowed("rg -t py foo .")


class FindNames(GuardCase):
    def test_partial_and_case_insensitive_patterns(self):
        for cmd in ("find . -name '.en*' -exec cat {} +",
                    "find . -iname .ENV -exec cat {} +",
                    "find . -name '*env' -exec cat {} +",
                    "find . -name '*.pem' -exec cat {} +",
                    "find . -path '*/.env' -print0 | xargs -0 cat"):
            self.blocked(cmd)
        self.allowed("find . -name '*.ts' -exec grep x {} +")
        self.allowed("find . -name '.en*'")  # listing is not reading


class PolicyFiles(unittest.TestCase):
    """Subagents (events carrying agent_id) never modify the config, the
    settings denies, agent files, or the plugin; the main session keeps its
    sanctioned write path."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="cfm-policy-")
        os.makedirs(os.path.join(self.dir, ".claude", "agents"))
        os.makedirs(os.path.join(self.dir, "src"))
        shutil.copy(FIXTURE, os.path.join(self.dir, cfm_config.CONFIG_FILE))
        os.makedirs(os.path.join(self.dir, "build"))
        for rel in (".claude/settings.json", ".claude/agents/custom.md",
                    ".claude/cfm-denies.json", "src/y.ts", "README.md", "cfg.yml"):
            with open(os.path.join(self.dir, rel), "w") as fh:
                fh.write("x\n")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def ctx(self, subagent, level="L2"):
        ctx = _ctx(self.dir, level=level)
        ctx["subagent"] = subagent
        return ctx

    def test_subagent_writes_blocked(self):
        for cmd in ("sed -i 's/L0/L3/' .cfm-workflow.yml",
                    # token-first: these were verified bypasses of the old
                    # head denylist — ordinary shell, no interpreter tricks
                    "curl -o .cfm-workflow.yml",
                    "wget -O .cfm-workflow.yml",
                    "sed --in-place=.bak 's/L0/L3/' .cfm-workflow.yml",
                    "gawk -i inplace '{print}' .cfm-workflow.yml",
                    "sort -o .cfm-workflow.yml cfg.yml", "ed -s .cfm-workflow.yml",
                    "ex -s +'%s/L0/L3/' -cwq .cfm-workflow.yml",
                    "yq -i '.git.level=\"L3\"' .cfm-workflow.yml",
                    "python3 edit.py .cfm-workflow.yml", "touch .claude/cfm-denies.json",
                    "git restore --source=HEAD~3 .cfm-workflow.yml",
                    "git checkout HEAD~3 -- .cfm-workflow.yml", "git checkout -- .",
                    "git restore .", "git stash push .cfm-workflow.yml",
                    "mv .cfm-workflow.yml /tmp/bak",
                    "perl -pi -e s/a/b/ .cfm-workflow.yml",
                    "echo 'git: {level: L3}' >> .cfm-workflow.local.yml",
                    "cat x>.cfm-workflow.yml", "cp x .cfm-workflow.yml",
                    "cp x ./.cfm-workflow.y*", "cp x .cfm-workflow.{yml,bak}",
                    "mv x .cfm-workflow.yml", "rm .cfm-workflow.yml",
                    "rm -rf .", "rm -rf .claude", "rm -rf .*", "mv .claude x",
                    "chmod 000 .cfm-workflow.yml", "truncate -s0 .cfm-workflow.yml",
                    "tee .claude/settings.json < x", "tee -a .claude/settings.local.json",
                    "cp x .claude/agents/custom.md", "ln -sf x .claude/settings.json",
                    "find . -name .cfm-workflow.yml -delete", "find .claude -delete",
                    "find . -name settings.json -exec rm {} +",
                    "git rm .cfm-workflow.yml", "git rm -r .claude",
                    "echo .cfm-workflow.yml | xargs rm",
                    "cp x $CLAUDE_PROJECT_DIR/.cfm-workflow.yml",
                    "cp x sub/.cfm-workflow.yml", "cp x ~/.claude/settings.json",
                    "bash -c 'rm .cfm-workflow.yml'",
                    "cd sub && cp x ../.cfm-workflow.yml",
                    "dd if=x of=.cfm-workflow.yml"):
            message = guard_check._check_bash(cmd, self.ctx(True))
            self.assertIsNotNone(message, f"expected BLOCK: {cmd!r}")
            self.assertIn("workflow policy", message)

    def test_subagent_uninspectable_content_refused(self):
        # a patch, a stash, an archive: the guard cannot see what lands
        for cmd in ("git apply cfg.patch", "git am 0001.patch", "git stash pop",
                    "git stash apply", "unzip -o bundle.zip", "tar -xf bundle.tar",
                    "tar xzf b.tgz", "7z x b.7z"):
            message = guard_check._check_bash(cmd, self.ctx(True))
            self.assertIsNotNone(message, f"expected BLOCK: {cmd!r}")
            self.assertIn("cannot inspect", message)
        for cmd in ("tar -xf b.tar -C build/", "unzip -o b.zip -d build/",
                    "tar czf out.tgz src/", "tar -tf b.tar", "git stash", "git stash list"):
            self.assertIsNone(guard_check._check_bash(cmd, self.ctx(True)), cmd)

    def test_subagent_reads_and_ordinary_writes_allowed(self):
        for cmd in ("cat .cfm-workflow.yml", "grep layers .cfm-workflow.yml",
                    "diff .cfm-workflow.yml cfg.yml", "yq . .cfm-workflow.yml",
                    "jq . .claude/settings.json", "awk '{print}' .cfm-workflow.yml",
                    "sort .cfm-workflow.yml", "cp .cfm-workflow.yml /tmp/backup.yml",
                    "python3 $CLAUDE_PLUGIN_ROOT/scripts/cfm_config.py --project-dir . --json",
                    "cat $CLAUDE_PLUGIN_ROOT/skills/testing/SKILL.md",
                    "git diff HEAD -- .cfm-workflow.yml", "git log -p .cfm-workflow.yml",
                    "wc -l .cfm-workflow.yml", "find . -name .cfm-workflow.yml",
                    "head -5 .claude/agents/custom.md", "test -f .cfm-workflow.yml && echo yes",
                    "git add .", "git commit -m x", "git checkout -b feature/x",
                    "git checkout feature/x", "node scripts/build.js",
                    "sed -n p .cfm-workflow.yml", "cat .claude/settings.json",
                    "ls .claude/agents", "npx prettier --write .", "eslint --fix .",
                    "rm -rf node_modules", "cp x src/y.ts", "sed -i s/a/b/ src/y.ts",
                    "echo x > src/y.ts", "mkdir -p .claude/rules", "git status",
                    "find . -name '*.ts' -exec grep x {} +", "chmod +x scripts/x.sh",
                    "echo .cfm-workflow.yml"):
            message = guard_check._check_bash(cmd, self.ctx(True))
            self.assertIsNone(message, f"expected ALLOW: {cmd!r} -> {message}")

    def test_main_session_keeps_the_sanctioned_path(self):
        for cmd in ("sed -i 's/L0/L3/' .cfm-workflow.yml", "cp x .cfm-workflow.yml",
                    "rm .cfm-workflow.yml", "tar -xf b.tar -C /tmp/x",
                    "curl -o .cfm-workflow.yml",
                    "tee /tmp/x < .cfm-workflow.yml"):
            self.assertIsNone(guard_check._check_bash(cmd, self.ctx(False)), cmd)

    def test_file_tools(self):
        plugin_guard = os.path.join(guard_check._plugin_root(), "scripts", "guard_check.py")
        cases = [
            ("Write", ".cfm-workflow.yml", True, 2),
            ("Edit", ".claude/settings.json", True, 2),
            ("Edit", ".claude/cfm-denies.json", True, 2),
            ("Write", ".claude/agents/new.md", True, 2),
            ("Write", os.path.join(self.dir, ".cfm-workflow.local.yml"), True, 2),
            ("Edit", plugin_guard, True, 2),
            ("Write", "$CLAUDE_PLUGIN_ROOT/hooks/hooks.json", True, 2),
            ("Read", ".cfm-workflow.yml", True, 0),
            ("Write", "src/x.ts", True, 0),
            ("Write", ".cfm-workflow.yml", False, 0),  # the orchestrator
            ("Edit", ".claude/settings.json", False, 0),
        ]
        for tool, path, subagent, expected in cases:
            event = {"tool_name": tool, "tool_input": {"file_path": path}}
            if subagent:
                event["agent_id"] = "agent-1"
            code, _message = guard_check.decide(event, self.dir)
            self.assertEqual(code, expected, f"{tool} {path} subagent={subagent}")


class OrchestratorRule(unittest.TestCase):
    """cfm mode: a main-session event (no agent_id) never writes product;
    the orchestrator roots stay writable; subagents are untouched."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="cfm-orch-")
        for rel in ("src", "docs/plans", ".claude/rules", ".cfm", "build", "sub"):
            os.makedirs(os.path.join(self.dir, rel))
        shutil.copy(FIXTURE, os.path.join(self.dir, cfm_config.CONFIG_FILE))
        for rel in ("src/y.ts", "README.md", "package.json", "CLAUDE.md",
                    ".gitignore", "docs/PROGRESS.md", ".claude/rules/rules.md",
                    "x", "b.tar", "nb.ipynb", "scripts/x.sh"):
            path = os.path.join(self.dir, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as fh:
                fh.write("x\n")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def ctx(self, subagent=False, mode="enforced", level="L0"):
        ctx = _ctx(self.dir, level=level, mode=mode)
        ctx["subagent"] = subagent
        return ctx

    def test_main_session_product_writes_blocked(self):
        for cmd in (
            "echo x > src/a.ts", "echo x >> README.md", "cat x > newfile.ts",
            "ls > listing.txt", "echo x > src/y.ts 2>&1", "cat x &> src/a.ts",
            "sed -i s/a/b/ src/y.ts", "perl -pi -e s/a/b/ src/y.ts",
            "gawk -i inplace '{print}' src/y.ts", "yq -i '.a=1' package.json",
            "sort -o src/y.ts x", "cp x src/b", "cp -r build src/vendor",
            "install x src/b", "ln -s x src/link", "mv src/y.ts src/z.ts",
            "rm src/y.ts", "rm -rf src", "rm -rf .", "rm -rf build",
            "chmod +x src/y.ts", "tee src/y.ts < x", "echo x | tee -a src/y.ts",
            "touch src/new.ts", "truncate -s0 README.md",
            "curl -o src/y.ts", "wget -O src/y.ts",
            "dd if=x of=src/y.ts", "ed -s src/y.ts",
            "git checkout -- src/y.ts", "git restore src/", "git checkout -- .",
            "git rm src/y.ts", "git stash push src/y.ts",
            "git apply x.patch", "git am 0001.patch", "git stash pop",
            "tar -xf b.tar", "unzip -o b.zip", "tar -xf b.tar -C build/",
            "find src -name '*.ts' -exec sed -i s/a/b/ {} +", "find build -delete",
            "bash -c 'echo x > src/a.ts'", "sh -c 'rm src/y.ts'",
            "eval 'echo x > src/a.ts'", "cd src && echo x > a.ts",
            "cp x $CLAUDE_PROJECT_DIR/src/b", "cp x ./src/../src/b",
            "echo x > sub/deep/file.ts",
        ):
            message = guard_check._check_bash(cmd, self.ctx(level="L2"))
            self.assertIsNotNone(message, f"expected BLOCK: {cmd!r}")
            self.assertIn("main session orchestrates", message)

    def test_main_session_orchestration_allowed(self):
        for cmd in (
            # orchestrator roots
            "echo x > docs/plans/feature.md", "sed -i s/a/b/ CLAUDE.md",
            "cp x .cfm-workflow.yml", "cp x sub/.cfm-workflow.yml",
            "echo x >> .gitignore", "cp x .env.example", "mkdir -p .claude/rules",
            "echo '{}' > .cfm/state.json", "echo x >> docs/PROGRESS.md",
            "rm -rf docs/plans", "rm .cfm/subagent-observed", "git checkout -- docs/",
            "tee .claude/rules/rules.md < x", "touch docs/plans/x.md",
            "tar -xf b.tar -C docs/",
            # outside the project
            "echo x > /tmp/scratch", "cp src/y.ts /tmp/y.ts", "tee ~/.claude/notes < x",
            "tar -xf b.tar -C /tmp/x", "sort -o /tmp/out src/y.ts",
            "echo x > /dev/null",
            # execution, reads, unknown heads
            "python3 $CLAUDE_PLUGIN_ROOT/scripts/state.py --project-dir . show",
            "python3 scripts/foo.py src/y.ts", "node scripts/build.js",
            "bash setup.sh", "npx prettier --check src", "pytest tests/test_x.py",
            "ruff check src/", "tsc -p apps/api", "tree src", "ls src > /dev/null",
            "cat src/y.ts", "grep -rn foo src/", "sed -n p src/y.ts",
            "awk '{print}' src/y.ts", "yq . package.json", "wc -l src/y.ts",
            "diff src/y.ts x", "cp src/y.ts /tmp/x", "sort src/y.ts",
            "echo hello | wc -c", "echo src/y.ts", "printf '%s\\n' a b | sort",
            "ls 2>&1", "make 2>&1 | tail", "cmd >&2", "curl --version",
            "curl -d @src/y.ts", "npm install left-pad",
            "pip install -r requirements.txt", "mkdir src/new",
            "chmod 755 nonexistent", "rm nonexistent",
            "git status", "git diff", "git log -p src/y.ts", "git add .",
            "git add src/y.ts", "git checkout -b feature/x", "git checkout feature/x",
            "git merge feature/x", "git rebase main", "git stash", "git stash list",
            "git commit -m x",
        ):
            message = guard_check._check_bash(cmd, self.ctx(level="L2"))
            self.assertIsNone(message, f"expected ALLOW: {cmd!r} -> {message}")
        # at L0 the git rule still speaks, in its own words
        self.assertIn("forbidden operation",
                      guard_check._check_bash("git commit -m x", self.ctx()))
        self.assertIn("verify_full",
                      guard_check._check_bash("true", self.ctx()))

    def test_mode_advisory_and_off_skip_the_rule(self):
        for mode in ("advisory", "off"):
            for cmd in ("echo x > src/a.ts", "rm -rf src", "git apply x.patch",
                        "tar -xf b.tar", "sed -i s/a/b/ src/y.ts"):
                self.assertIsNone(
                    guard_check._check_bash(cmd, self.ctx(mode=mode, level="L2")), cmd)

    def test_subagent_untouched(self):
        for cmd in ("echo x > src/a.ts", "sed -i s/a/b/ src/y.ts", "rm -rf src",
                    "cp x src/b", "tar -xf b.tar -C build/", "npm install x"):
            self.assertIsNone(guard_check._check_bash(cmd, self.ctx(True, level="L2")), cmd)
        self.assertIn("workflow policy",
                      guard_check._check_bash("cp x .cfm-workflow.yml", self.ctx(True)))

    def test_file_tools(self):
        cases = [
            ("Write", "src/x.ts", False, 2),
            ("Edit", "README.md", False, 2),
            ("MultiEdit", os.path.join(self.dir, "package.json"), False, 2),
            ("Write", "$CLAUDE_PROJECT_DIR/src/x.ts", False, 2),
            ("Write", "docs/plans/x.md", False, 0),
            ("Write", "CLAUDE.md", False, 0),
            ("Write", ".claude/rules/rules.md", False, 0),
            ("Edit", ".cfm-workflow.yml", False, 0),
            ("Write", ".cfm/state.json", False, 0),
            ("Write", "docs/PROGRESS.md", False, 0),
            ("Write", ".gitignore", False, 0),
            ("Write", ".env.example", False, 0),
            ("Write", "/tmp/cfm-scratch.md", False, 0),
            ("Write", os.path.expanduser("~/.claude/plans/p.md"), False, 0),
            ("Read", "src/x.ts", False, 0),
            ("Write", "src/x.ts", True, 0),
        ]
        for tool, path, subagent, expected in cases:
            event = {"tool_name": tool, "tool_input": {"file_path": path}}
            if subagent:
                event["agent_id"] = "agent-1"
            code, message = guard_check.decide(event, self.dir)
            self.assertEqual(code, expected, f"{tool} {path} subagent={subagent} {message}")
            if expected == 2:
                self.assertIn("product code", message)
        event = {"tool_name": "NotebookEdit", "tool_input": {"notebook_path": "nb.ipynb"}}
        self.assertEqual(guard_check.decide(event, self.dir)[0], 2)
        # the secret rule speaks first
        code, message = guard_check.decide(
            {"tool_name": "Write", "tool_input": {"file_path": ".env"}}, self.dir)
        self.assertEqual(code, 2)
        self.assertIn("secret glob", message)

    def test_mode_from_config_and_derived_roots(self):
        config_path = os.path.join(self.dir, cfm_config.CONFIG_FILE)
        with open(FIXTURE) as fh:
            base = fh.read()
        for mode in ("advisory", "off"):
            with open(config_path, "w") as fh:
                fh.write(base + f"\nmode: {mode}\n")
            event = {"tool_name": "Write", "tool_input": {"file_path": "src/x.ts"}}
            self.assertEqual(guard_check.decide(event, self.dir)[0], 0, mode)
        with open(config_path, "w") as fh:
            fh.write(base + "\nmode: bogus\n")
        ctx = guard_check.load_context(self.dir)
        self.assertEqual(ctx["mode"], "enforced")  # a broken value never disables
        with open(config_path, "w") as fh:
            fh.write(base.replace("  layout: single\n  files: [CLAUDE.md]",
                                  "  layout: router\n"
                                  "  files: [CLAUDE.md, apps/api/CLAUDE.md]")
                     + "\nrules_file: rules/x.md\n")
        os.makedirs(os.path.join(self.dir, "apps", "api"))
        for path, expected in (("apps/api/CLAUDE.md", 0), ("apps/api/index.ts", 2),
                               ("rules/x.md", 0)):
            event = {"tool_name": "Write", "tool_input": {"file_path": path}}
            self.assertEqual(guard_check.decide(event, self.dir)[0], expected, path)


class BrokenConfig(unittest.TestCase):
    def test_broken_config_still_enforces(self):
        directory = tempfile.mkdtemp(prefix="cfm-broken-")
        try:
            with open(os.path.join(directory, cfm_config.CONFIG_FILE), "w") as fh:
                fh.write("layers: [\n")  # unparseable
            ctx = guard_check.load_context(directory)
            self.assertIn(".env*", ctx["globs"])
            self.assertIn("git commit", ctx["forbidden"])
            self.assertFalse(ctx["subagent"])
            self.assertEqual(ctx["mode"], "enforced")
            self.assertIn(os.path.realpath(os.path.join(directory, "docs")),
                          ctx["orchestrator_roots"])
        finally:
            shutil.rmtree(directory, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
