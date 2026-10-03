"""Settings generation: the denies mirror the guard, the file is owned
(stale cfm rules retracted, the user's own rules kept), allows are
advisory, and the pre-commit template enforces the same policy for the
human's commits."""

from __future__ import annotations

import json
import os
import subprocess

from helpers import ProjectCase, ROOT, VALID, gen_settings, git, read, write
import gen_settings as g


def proposed(d, *args):
    return json.loads(gen_settings(d, *args).stdout)


class Denies(ProjectCase):
    def test_proposed_denies(self):
        deny = proposed(self.project())["permissions"]["deny"]
        for entry in ("Read(.env*)", "Edit(*.pem)", "Bash(git commit:*)",
                      "Bash(cat *.env*)", "Bash(head *.pem)", "Bash(true)",
                      "Bash(git push -f *)", "Bash(git branch -D *)",
                      "Edit(/.claude/settings.json)", "Edit(/.claude/cfm-denies.json)",
                      "Read(**/.env*)", "Read(id_ed25519*)", "Bash(git pull:*)",
                      "Bash(git checkout:*)", "Bash(gh pr merge:*)", "Bash(git config:*)"):
            self.assertIn(entry, deny)
        # Claude Code never consults Write(...) path rules
        self.assertEqual([e for e in deny if e.startswith("Write(")], [])

    def test_check_and_write(self):
        d = self.project()
        self.assertEqual(gen_settings(d, "--check").returncode, 1)
        self.assertEqual(gen_settings(d, "--write").returncode, 0)
        self.assertEqual(gen_settings(d, "--check").returncode, 0)
        self.assertTrue(os.path.isfile(os.path.join(d, ".claude/cfm-denies.json")))

    def test_merge_preserves_existing(self):
        d = self.project()
        write(os.path.join(d, ".claude/settings.json"), json.dumps({
            "customKey": "keep-me",
            "permissions": {"allow": ["Bash(ls:*)"], "deny": ["WebFetch"]},
        }))
        gen_settings(d, "--write")
        settings = json.loads(read(os.path.join(d, ".claude/settings.json")))
        self.assertEqual(settings["customKey"], "keep-me")
        allow, deny = settings["permissions"]["allow"], settings["permissions"]["deny"]
        self.assertEqual(allow[0], "Bash(ls:*)")
        self.assertFalse(any(a.startswith("Bash(claude mcp") for a in allow))
        self.assertEqual(len(allow), len(set(allow)))
        self.assertEqual(deny[0], "WebFetch")
        for entry in ("Read(.env*)", "Edit(*.pem)", "Bash(git commit:*)"):
            self.assertIn(entry, deny)
        self.assertEqual(len(deny), len(set(deny)))

    def test_level_change_retracts_stale_denies(self):
        # merge-only used to ratchet: L0 → L2 left `git push:*` denied and
        # the level change was silently ineffective at this layer
        d = self.project()
        gen_settings(d, "--write")
        cfg = os.path.join(d, ".cfm-workflow.yml")
        write(cfg, read(cfg).replace("level: L0", "level: L2"))
        proc = gen_settings(d, "--check")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("stale (from an earlier config): Bash(git push:*)", proc.stderr)
        proc = gen_settings(d, "--write")
        self.assertIn("retracted", proc.stdout)
        deny = json.loads(read(os.path.join(d, ".claude/settings.json")))["permissions"]["deny"]
        for gone in ("Bash(git push:*)", "Bash(git checkout:*)", "Bash(git pull:*)", "Bash(git commit:*)"):
            self.assertNotIn(gone, deny)
        for kept in ("Bash(git push * main)", "Bash(git clean:*)", "Bash(git push --force *)"):
            self.assertIn(kept, deny)
        self.assertEqual(gen_settings(d, "--check").returncode, 0)

    def test_stale_custom_ops_and_verify_full_retracted_via_sidecar(self):
        d = self.project()
        cfg = os.path.join(d, ".cfm-workflow.yml")
        write(cfg, read(cfg) + "\nforbidden_ops:\n  - npm publish\n")
        gen_settings(d, "--write")
        deny = json.loads(read(os.path.join(d, ".claude/settings.json")))["permissions"]["deny"]
        self.assertIn("Bash(npm publish:*)", deny)
        write(cfg, read(VALID).replace('verify_full: "true"', 'verify_full: "false"')
              if 'verify_full: "true"' in read(VALID) else read(VALID))
        gen_settings(d, "--write")
        deny = json.loads(read(os.path.join(d, ".claude/settings.json")))["permissions"]["deny"]
        self.assertNotIn("Bash(npm publish:*)", deny)

    def test_no_sidecar_still_retracts_level_shapes(self):
        # a project initialised before the sidecar existed: level-shaped
        # rules are still recognised as cfm's
        d = self.project()
        gen_settings(d, "--write")
        os.remove(os.path.join(d, ".claude/cfm-denies.json"))
        cfg = os.path.join(d, ".cfm-workflow.yml")
        write(cfg, read(cfg).replace("level: L0", "level: L2"))
        self.assertEqual(gen_settings(d, "--check").returncode, 1)
        gen_settings(d, "--write")
        deny = json.loads(read(os.path.join(d, ".claude/settings.json")))["permissions"]["deny"]
        self.assertNotIn("Bash(git push:*)", deny)

    def test_user_rule_in_cfm_shape_family_survives_when_required(self):
        # a rule the user added that cfm also requires stays; one the user
        # added outside cfm's shapes is never touched
        d = self.project()
        write(os.path.join(d, ".claude/settings.json"), json.dumps({
            "permissions": {"deny": ["Bash(rm -rf /)", "Read(./secrets/**)"]}}))
        gen_settings(d, "--write")
        deny = json.loads(read(os.path.join(d, ".claude/settings.json")))["permissions"]["deny"]
        self.assertEqual(deny[:2], ["Bash(rm -rf /)", "Read(./secrets/**)"])

    def test_l2_push_invariants(self):
        d = self.project(config=None)
        write(os.path.join(d, ".cfm-workflow.yml"), read(VALID).replace("level: L0", "level: L2"))
        deny = proposed(d)["permissions"]["deny"]
        for entry in ("Bash(git push * main)", "Bash(git push * main *)", "Bash(git push * *:master)",
                      "Bash(git push * *:refs/heads/main *)", "Bash(git push --force *)"):
            self.assertIn(entry, deny)
        self.assertNotIn("Bash(git push:*)", deny)

    def test_broken_config_exits_1(self):
        d = self.project(config=os.path.join(ROOT, "tests/fixtures/broken-schema.yml"))
        proc = gen_settings(d)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("error", proc.stderr)


class Allows(ProjectCase):
    def test_only_observed_exact_names(self):
        for provider in (None, "clickup", "jira"):
            self.assertEqual(g.required_allows({"tracker": {"provider": provider}}), [])
        observed = g.required_allows({"tracker": {"provider": "trello"}}, extra=[
            "mcp__claude_ai_Trello__trelloWriteCard", "mcp__claude_ai_Trello__trelloWriteCard",
            "mcp__atlassian__*", "mcp__*__create", "Bash(claude mcp add *)", "mcp__x"])
        self.assertEqual(observed, ["mcp__claude_ai_Trello__trelloWriteCard"])

    def test_cli_rejects_wildcard(self):
        self.assertEqual(gen_settings(self.project(), "--allow-tool", "mcp__atlassian__*").returncode, 1)

    def test_allows_are_advisory(self):
        d = self.project()
        gen_settings(d, "--write")
        path = os.path.join(d, ".claude/settings.json")
        settings = json.loads(read(path))
        settings["permissions"]["allow"] = []
        write(path, json.dumps(settings))
        self.assertEqual(gen_settings(d, "--check").returncode, 0)


class Sandbox(ProjectCase):
    def test_opt_in_block(self):
        d = self.project()
        self.assertNotIn("sandbox", proposed(d))
        sandbox = proposed(d, "--sandbox")["sandbox"]
        self.assertIs(sandbox["enabled"], True)
        fs = sandbox["filesystem"]
        for entry in ("./.env*", "./**/.env*", "./**/credentials", "./*.pem"):
            self.assertIn(entry, fs["denyRead"])
        self.assertEqual(fs["denyWrite"], ["./.cfm-workflow.yml", "./.cfm-workflow.local.yml",
                                           "./.claude/cfm-denies.json"])

    def test_merge_keeps_existing_sandbox_entries(self):
        d = self.project()
        write(os.path.join(d, ".claude/settings.json"), json.dumps({
            "sandbox": {"enabled": False, "filesystem": {"allowWrite": ["~/.kube"], "denyRead": ["~/.ssh"]}}}))
        gen_settings(d, "--sandbox", "--write")
        sandbox = json.loads(read(os.path.join(d, ".claude/settings.json")))["sandbox"]
        self.assertIs(sandbox["enabled"], True)
        self.assertEqual(sandbox["filesystem"]["allowWrite"], ["~/.kube"])
        self.assertEqual(sandbox["filesystem"]["denyRead"][0], "~/.ssh")
        self.assertEqual(gen_settings(d, "--sandbox", "--check").returncode, 0)
        self.assertEqual(gen_settings(d, "--check").returncode, 0)

    def test_check_with_sandbox_flags_gaps(self):
        d = self.project()
        gen_settings(d, "--write")
        proc = gen_settings(d, "--sandbox", "--check")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("sandbox: enabled", proc.stderr)


class PreCommit(ProjectCase):
    def repo(self, name):
        d = os.path.join(self.tmp, name)
        os.makedirs(d)
        git(d, "init", "-q")
        git(d, "commit", "-q", "--allow-empty", "-m", "init")
        return d

    def hook_rc(self, d, installed=False):
        cmd = ["./.git/hooks/pre-commit"] if installed else ["sh", os.path.join(ROOT, "templates/pre-commit.sh")]
        return subprocess.run(cmd, cwd=d, capture_output=True, text=True).returncode

    def stage(self, d, name, content):
        git(d, "reset", "-q")
        write(os.path.join(d, name), content + "\n")
        git(d, "add", "-f", name)

    def test_template(self):
        d = self.repo("pc")
        self.stage(d, ".env", "API_KEY=hunter2")
        self.assertEqual(self.hook_rc(d), 1)
        self.stage(d, "app.ts", "export const x = 1")
        self.assertEqual(self.hook_rc(d), 0)
        self.stage(d, ".env.example", "API_KEY=")
        self.assertEqual(self.hook_rc(d), 0)

    def test_installed_honors_project_globs_and_lint(self):
        d = self.repo("pci")
        write(os.path.join(d, ".cfm-workflow.yml"), read(VALID) + """
secret_globs:
  - ".env*"
  - "*.pem"
  - "*.supersecret"
""")
        hook = os.path.join(d, ".git/hooks/pre-commit")
        write(hook, read(os.path.join(ROOT, "templates/pre-commit.sh")))
        os.chmod(hook, 0o755)
        self.stage(d, "deploy.supersecret", "token")
        self.assertEqual(self.hook_rc(d, installed=True), 1)
        git(d, "reset", "-q")
        os.remove(os.path.join(d, "deploy.supersecret"))
        self.stage(d, "notes.txt", "clean")
        self.assertEqual(self.hook_rc(d, installed=True), 0)
        cfg = os.path.join(d, ".cfm-workflow.yml")
        write(cfg, read(cfg).replace('lint: ["true"]', 'lint: ["false"]'))
        self.assertEqual(self.hook_rc(d, installed=True), 1)


class StatusLine(ProjectCase):
    def settings(self, d):
        return json.loads(read(os.path.join(d, ".claude/settings.json")))

    def test_opt_in_write_check_and_remove(self):
        d = self.project()
        gen_settings(d, "--write")
        self.assertNotIn("statusLine", self.settings(d))
        self.assertEqual(gen_settings(d, "--check").returncode, 0)
        proc = gen_settings(d, "--check", "--statusline")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("statusline: not wired", proc.stderr)
        gen_settings(d, "--write", "--statusline")
        entry = self.settings(d)["statusLine"]
        self.assertEqual(entry["type"], "command")
        self.assertTrue(entry["command"].endswith(os.path.join("scripts", "statusline.sh")))
        self.assertTrue(os.path.isfile(entry["command"]))
        sidecar = json.loads(read(os.path.join(d, ".claude/cfm-denies.json")))
        self.assertEqual(sidecar["statusline"], entry["command"])
        self.assertEqual(gen_settings(d, "--check", "--statusline").returncode, 0)
        # sticky: a later plain --write leaves it in place
        gen_settings(d, "--write")
        self.assertIn("statusLine", self.settings(d))
        gen_settings(d, "--write", "--remove-statusline")
        self.assertNotIn("statusLine", self.settings(d))
        self.assertNotIn("statusline", json.loads(read(os.path.join(d, ".claude/cfm-denies.json"))))

    def test_user_status_line_is_never_touched(self):
        d = self.project()
        write(os.path.join(d, ".claude/settings.json"), json.dumps({
            "statusLine": {"type": "command", "command": "~/.claude/mine.sh"}}))
        gen_settings(d, "--write")
        self.assertEqual(self.settings(d)["statusLine"]["command"], "~/.claude/mine.sh")
        gen_settings(d, "--write", "--remove-statusline")
        self.assertEqual(self.settings(d)["statusLine"]["command"], "~/.claude/mine.sh")
        self.assertNotIn("statusline", json.loads(read(os.path.join(d, ".claude/cfm-denies.json"))))
        self.assertEqual(g.statusline_owner(self.settings(d), None), "user")
        # opting in replaces it inside this project — the documented trade
        gen_settings(d, "--write", "--statusline")
        self.assertEqual(g.statusline_owner(self.settings(d), None), "cfm")
