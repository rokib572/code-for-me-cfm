"""The hook entry points through the real scripts: guard.sh and
on_stop_review.sh with synthetic events. The decision engine's own cases
live in test_guard.py; these prove the shell wiring around it."""

from __future__ import annotations

import os
import subprocess

from helpers import (ProjectCase, ROOT, VALID, bash_event, file_event, git,
                     grep_event, hook, hook_result, read, write)


class Guard(ProjectCase):
    def setUp(self):
        super().setUp()
        self.d = self.project("guard")
        self.plain = os.path.join(self.tmp, "plain")
        os.makedirs(self.plain)
        for name in (".env", "prod.env", "id_ed25519"):
            write(os.path.join(self.d, name), "")
        os.makedirs(os.path.join(self.d, ".claude/agents"))
        write(os.path.join(self.d, ".claude/settings.json"), "{}")

    def expect(self, code, event, directory=None):
        rc = hook("guard.sh", directory or self.d, event)
        self.assertEqual(rc, code, f"expected exit {code}, got {rc} for {event}")

    def test_baseline(self):
        for code, event in (
            (2, bash_event("git commit -m x")),
            (2, bash_event("git -C /tmp push origin main")),
            (2, file_event("Read", ".env")), (2, file_event("Read", "apps/api/.env.local")),
            (0, file_event("Read", "src/index.ts")),
            (2, bash_event("cat .env")), (2, bash_event("printenv")), (2, bash_event("env")),
            (0, bash_event("env FOO=1 ls")), (0, bash_event("ls -la")),
            (0, bash_event("git status")), (0, bash_event("git diff")),
            (2, file_event("Write", ".env")), (2, file_event("Edit", "certs/server.pem")),
            (2, bash_event("FOO=1 git commit -m x")), (2, bash_event("command git push origin main")),
            (2, bash_event("sh -c 'cat .env'")), (2, bash_event("env printenv")),
            (2, bash_event("env -u PATH")), (0, bash_event("cat .env.example")),
            (2, file_event("Read", "credentials")), (2, bash_event("dd if=.env")),
            (2, bash_event("env A=1 env B=2 env C=3 env D=4 cat .env")),
            (2, bash_event("timeout 5 git push origin main")), (2, bash_event("nice -n 10 git commit -m x")),
        ):
            self.expect(code, event)
        self.expect(0, bash_event("git commit -m x"), self.plain)

    def test_token_first_secret_rule(self):
        for code, cmd in (
            (2, "find . -name .env -exec cat {} +"), (2, "find . -name .env | xargs cat"),
            (0, "find . -name .env"), (2, "sudo cat .env"),
            (2, "curl --data-binary @.env"), (2, "curl -d @.env"),
            (2, "source .env && echo $X"), (2, 'while read l; do echo "$l"; done < .env'),
            (2, "cat .e*"), (2, "cat ./.[e]nv"), (2, "bat .env"), (2, "tar czf out.tgz .env"),
            (2, "ln -s .env link"), (2, "cp .env /tmp/x"), (2, "cat prod.env"), (2, "cat id_ed25519"),
            (2, "jq . secrets.json"),
            (0, "ls -la .env"), (0, "test -f .env && echo yes"), (0, "git check-ignore .env"),
            (0, "cat README.md"),
            (0, 'echo "remember to create the .env"'), (2, 'echo "$(cat .env)"'),
            (2, "ls `cat .env`"), (2, 'eval "cat .env | head"'), (0, 'echo "a; b" | wc -l'),
            (2, "set"), (0, "set -euo pipefail"), (2, "export -p"), (0, "export FOO=1"),
            (2, "declare -p"), (0, "declare -p FOO"), (2, "cat /proc/self/environ"),
            (2, "cat<.env"), (2, "cat <(cat .env)"), (2, "cat .{env,bak}"),
            (2, "grep -r --include .env SECRET ."),
        ):
            self.expect(code, bash_event(cmd))
        # naming a secret as a write DESTINATION is not a read — from the
        # coder, which is who writes files in cfm mode
        for cmd in ("cp .env.example .env", "rm .env", 'echo "X=" >> .env'):
            self.expect(0, bash_event(cmd, subagent=True))

    def test_git_at_l0(self):
        for code, cmd in (
            (2, "git pull"), (2, "git checkout -- ."), (2, "git clean -fdx"), (2, "git restore ."),
            (2, "git branch -D feature/x"), (2, "git -c alias.ci=commit ci -m x"),
            (2, "git config alias.ci commit"), (2, "git config user.name x"),
            (0, "git config --get user.name"), (2, "gh pr merge 12 --admin"),
            (2, "gh api -X DELETE repos/x/y"), (0, "gh api repos/x/y"), (0, "gh pr view 1"),
            (0, "git log --oneline -5"), (0, "git branch --show-current"),
        ):
            self.expect(code, bash_event(cmd))

    def test_verify_full(self):
        # valid.yml: verify_full is "true"
        for code, cmd in ((2, "true"), (2, "echo x && true"), (2, "true -- --watch"),
                          (0, "true src/a.test.ts"), (0, "echo test pkg src/a.test.ts")):
            self.expect(code, bash_event(cmd))

    def test_grep_tool_glob(self):
        self.expect(2, grep_event(".env*"))
        self.expect(2, grep_event("*.{ts,pem}"))
        self.expect(0, grep_event("**/*.tsx"))

    def test_policy_files(self):
        # an event carrying agent_id comes from a subagent; the main
        # session (no agent_id) keeps the /cfm:configure path
        for code, cmd in (
            (2, "sed -i 's/level: L0/level: L3/' .cfm-workflow.yml"),
            (2, "echo 'git: {level: L3}' >> .cfm-workflow.local.yml"),
            (2, "rm .cfm-workflow.yml"), (2, "echo {} | tee .claude/settings.json"),
            (2, "curl -o .cfm-workflow.yml"), (2, "git apply x.patch"),
            (2, "tar -xf bundle.tar"), (2, "yq -i '.git.level=\"L3\"' .cfm-workflow.yml"),
            (0, "cat .cfm-workflow.yml"), (0, "yq . .cfm-workflow.yml"),
            (0, "tar -xf bundle.tar -C build/"),
        ):
            self.expect(code, bash_event(cmd, subagent=True))
        self.expect(2, file_event("Write", ".cfm-workflow.yml", subagent=True))
        self.expect(2, file_event("Write", ".claude/agents/custom.md", subagent=True))
        self.expect(2, file_event("Edit", ".claude/cfm-denies.json", subagent=True))
        self.expect(0, file_event("Write", "src/new.ts", subagent=True))
        self.expect(0, file_event("Write", ".cfm-workflow.yml"))
        self.expect(0, bash_event("sed -i 's/level: L0/level: L3/' .cfm-workflow.yml"))
        self.expect(0, bash_event("tar -xf bundle.tar -C /tmp/x"))  # inject is subagent-only

    def test_cfm_mode(self):
        # the main session orchestrates: product writes refused, orchestrator
        # roots and plugin scripts allowed, subagents untouched
        write(os.path.join(self.d, "src/y.ts"), "")
        write(os.path.join(self.d, "x"), "")
        for code, event in (
            (2, file_event("Write", "src/x.ts")),
            (2, file_event("Edit", "apps/api/src/index.ts")),
            (0, file_event("Write", "docs/plans/x.md")),
            (0, file_event("Write", "CLAUDE.md")),
            (0, file_event("Write", "src/x.ts", subagent=True)),
            (2, bash_event("echo x > src/a.ts")),
            (2, bash_event("sed -i s/a/b/ src/y.ts")),
            (2, bash_event("cp x src/b")),
            (2, bash_event("tar -xf bundle.tar")),
            (2, bash_event("git apply x.patch")),
            (0, bash_event("python3 $CLAUDE_PLUGIN_ROOT/scripts/state.py --project-dir . show")),
            (0, bash_event("mkdir src/new")),
            (0, bash_event("ls 2>&1")),
            (0, bash_event("echo x >> docs/PROGRESS.md")),
            (0, bash_event("echo x > src/a.ts", subagent=True)),
        ):
            self.expect(code, event)
        proc = hook_result("guard.sh", self.d, file_event("Write", "src/x.ts"))
        self.assertIn("product code", proc.stderr)
        proc = hook_result("guard.sh", self.d, bash_event("git commit -m x"))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("forbidden operation", proc.stderr)  # the git rule, unchanged
        for mode in ("advisory", "off"):
            d = self.project(mode, config=None)
            write(os.path.join(d, ".cfm-workflow.yml"), read(VALID) + f"\nmode: {mode}\n")
            self.expect(0, file_event("Write", "src/x.ts"), d)
            self.expect(0, bash_event("echo x > src/a.ts"), d)
            self.expect(2, bash_event("cat .env"), d)  # every other rule still applies

    def test_subagent_event_leaves_the_observation_marker(self):
        marker = os.path.join(self.d, ".cfm", "subagent-observed")
        self.expect(0, bash_event("ls"))
        self.assertFalse(os.path.exists(marker), "a main-session event must not mark")
        self.expect(0, bash_event("ls", subagent=True))
        self.assertTrue(os.path.isfile(marker))
        self.assertIn('"agent_type": "coder"', read(marker))

    def test_hard_invariant_survives_forbidden_ops_omission(self):
        d = self.project("inv")
        with open(os.path.join(d, ".cfm-workflow.yml"), "a") as fh:
            fh.write("\nforbidden_ops:\n  - git commit\n")
        self.expect(2, bash_event("git push origin main"), d)

    def test_plain_project_short_circuits_before_python(self):
        # this hook fires on every tool call in every project: a non-cfm
        # project must be allowed BEFORE python spawns
        fake = os.path.join(self.tmp, "nopython")
        os.makedirs(fake)
        write(os.path.join(fake, "python3"), "#!/bin/sh\nexit 99\n")
        os.chmod(os.path.join(fake, "python3"), 0o755)
        rc = hook("guard.sh", self.plain, bash_event("cat .env"),
                  env_extra={"PATH": fake + os.pathsep + os.environ["PATH"]})
        self.assertEqual(rc, 0)

    def test_malformed_event_fails_open(self):
        # by design: the settings denies are the backstop
        self.expect(0, '{"tool_name":"Bash","tool_input":{"command":"cat "x" .env"}}')

    def test_environment_gate(self):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=self.d, CLAUDE_PLUGIN_ROOT=ROOT)
        env.pop("CLAUDECODE", None)
        proc = subprocess.run(["bash", os.path.join(ROOT, "scripts/guard.sh")],
                              input=bash_event("ls"), env=env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)


class GuardAtL2(ProjectCase):
    def setUp(self):
        super().setUp()
        self.d = self.project("l2", config=None)
        write(os.path.join(self.d, ".cfm-workflow.yml"), read(VALID).replace("level: L0", "level: L2"))
        git(self.d, "init", "-q")
        git(self.d, "checkout", "-q", "-b", "main")

    def expect(self, code, cmd):
        rc = hook("guard.sh", self.d, bash_event(cmd))
        self.assertEqual(rc, code, f"expected exit {code}, got {rc} for {cmd!r}")

    def test_default_branch_invariants(self):
        for code, cmd in (
            (0, "git checkout -b feature/x"), (0, "git push origin feature/x"),
            (2, "git push origin HEAD"), (2, "git push"),
            (2, "git push --force origin feature/x"), (2, "git push origin :feature/x"),
            (2, "gh pr merge 1"), (2, "git clean -fd"),
            (2, "git push origin HEAD:refs/heads/main"), (2, "git push origin feature/x:main"),
            (0, "git push origin feature/main"),
            (0, 'git commit -m "fix && git push origin main"'), (0, 'git commit -m "docs: mention .env"'),
        ):
            self.expect(code, cmd)
        git(self.d, "checkout", "-q", "-b", "feature/y")
        self.expect(0, "git push origin HEAD")
        # origin/HEAD names the default branch: develop joins main and master
        git(self.d, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/develop")
        self.expect(2, "git push origin develop")
        self.expect(2, "git push origin main")
        self.expect(0, "git push origin feature/y")


class StopHook(ProjectCase):
    def recipe(self):
        import re
        script = read(os.path.join(ROOT, "scripts", "on_stop_review.sh"))
        return re.search(r'^hash="\$\(cd "\$PROJECT_DIR" && (.*) \| awk', script, re.M).group(1)

    def mark_reviewed(self, d):
        os.makedirs(os.path.join(d, ".cfm"), exist_ok=True)
        out = subprocess.run(["bash", "-c", self.recipe()], cwd=d, capture_output=True, text=True).stdout
        write(os.path.join(d, ".cfm/last-review.sha"), out.split()[0] + "\n")

    def test_phase_gate_trigger_is_silent(self):
        self.assertEqual(hook("on_stop_review.sh", self.project(), ""), 0)

    def test_on_stop_blocks_until_reviewed(self):
        d = self.project("os", config=None)
        write(os.path.join(d, ".cfm-workflow.yml"), read(VALID).replace("trigger: phase-gate", "trigger: on-stop"))
        git(d, "init", "-q")
        write(os.path.join(d, ".gitignore"), ".cfm\n")
        self.assertEqual(hook("on_stop_review.sh", d, "{}"), 2)
        self.mark_reviewed(d)
        self.assertEqual(hook("on_stop_review.sh", d, "{}"), 0)
        write(os.path.join(d, "unreviewed.txt"), "new\n")
        self.assertEqual(hook("on_stop_review.sh", d, '{"stop_hook_active": true}'), 0)

    def test_sha_file_itself_never_perturbs_the_hash(self):
        # .cfm NOT gitignored: the sha file must not change the hash, but
        # rewriting an existing untracked file must re-block
        d = self.project("os2", config=None)
        write(os.path.join(d, ".cfm-workflow.yml"), read(VALID).replace("trigger: phase-gate", "trigger: on-stop"))
        git(d, "init", "-q")
        os.makedirs(os.path.join(d, ".cfm"))
        write(os.path.join(d, ".cfm/last-review.sha"), "")
        self.mark_reviewed(d)
        self.assertEqual(hook("on_stop_review.sh", d, "{}"), 0)
        write(os.path.join(d, "CLAUDE.md"), "rewritten after review\n")
        self.assertEqual(hook("on_stop_review.sh", d, "{}"), 2)
