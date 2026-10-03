"""The scaffold renders workflow files from a valid config, never clobbers,
and never writes through a symlink."""

from __future__ import annotations

import json
import os
import re
import shutil

import yaml

from helpers import ProjectCase, VALID, doctor, check, git, read, run, write


class Scaffold(ProjectCase):
    def bare(self, name, config_text=None):
        d = os.path.join(self.tmp, name)
        os.makedirs(os.path.join(d, "domain/database"))
        os.makedirs(os.path.join(d, "apps/api"))
        write(os.path.join(d, ".cfm-workflow.yml"), config_text or read(VALID))
        return d

    def render(self, d, *args):
        return run("scaffold.py", "--project-dir", d, *args)

    def test_greenfield_render_and_doctor_green(self):
        d = self.bare("g")
        self.assertEqual(self.render(d, "--date", "2026-08-24").returncode, 0)
        md = read(os.path.join(d, "CLAUDE.md"))
        self.assertIn("Test fixture project", md)
        self.assertTrue(any("verify_full" in l and "HUMAN-ONLY" in l for l in md.splitlines()))
        rules = read(os.path.join(d, ".claude/rules/rules.md"))
        self.assertTrue(re.search(r"^## R1\.", rules, re.M))
        self.assertIn("**Enforcement:**", rules)
        gi = [l.strip() for l in read(os.path.join(d, ".gitignore")).splitlines()]
        for line in (".env*", "!.env.example", ".cfm/"):
            self.assertIn(line, gi)
        self.assertTrue(os.path.isfile(os.path.join(d, ".env.example")))
        self.assertIn("## Language", read(os.path.join(d, "CONTEXT.md")))
        self.assertIn("Glossary: `CONTEXT.md`", md)
        self.assertIn("Carried forward", read(os.path.join(d, "docs/PROGRESS.md")))
        self.assertEqual(json.loads(read(os.path.join(d, ".cfm/state.json")))["version"], 1)
        # the rest of the real init flow: the coder's skeleton, then denies
        os.makedirs(os.path.join(d, "domain/database/src"))
        os.makedirs(os.path.join(d, "apps/api/src"))
        report = self.assert_healthy(d)
        for cid in (2, 6, 7, 9):
            self.assertEqual(check(report, cid)["status"], "PASS", cid)

    def test_rules_fallback_owner(self):
        cfg = yaml.safe_load(read(VALID))
        del cfg["agents"]["code-reviewer"]
        cfg["agents"]["arch-reviewer"] = {
            "enabled": True, "purpose": "Reviews architecture conformance",
            "model": "claude-fable-5", "tier": "judgment", "autonomy": "auto",
            "tools": ["Read"], "owns_commands": [], "layers": ["database", "api"]}
        cfg["review_gates"] = ["arch-reviewer"]
        d = self.bare("fb", yaml.safe_dump(cfg))
        os.makedirs(os.path.join(d, "domain/database/src"))
        os.makedirs(os.path.join(d, "apps/api/src"))
        self.render(d)
        self.assertIn("reviewer(arch-reviewer)", read(os.path.join(d, ".claude/rules/rules.md")))
        _rc, report = doctor(d)
        self.assertEqual(check(report, 6)["status"], "PASS")

    def test_never_clobber(self):
        d = self.bare("nc")
        write(os.path.join(d, "CLAUDE.md"), "SENTINEL — hand-written, do not touch\n")
        out = self.render(d).stdout
        self.assertEqual(read(os.path.join(d, "CLAUDE.md")), "SENTINEL — hand-written, do not touch\n")
        self.assertRegex(out, r"kept +CLAUDE.md")

    def test_gitignore_append_only(self):
        d = self.bare("gi")
        write(os.path.join(d, ".gitignore"), "node_modules/\n")
        self.render(d)
        lines = read(os.path.join(d, ".gitignore")).splitlines()
        self.assertEqual(lines[0], "node_modules/")
        for line in (".cfm/", ".env*", "!.env.example"):
            self.assertIn(line, lines)

    def test_dangling_symlink_is_kept_not_followed(self):
        d = self.bare("sy")
        os.makedirs(os.path.join(d, "docs"))
        target = os.path.join(self.tmp, "outside-target.md")
        os.symlink(target, os.path.join(d, "docs/PROGRESS.md"))
        out = self.render(d).stdout
        self.assertFalse(os.path.exists(target))
        self.assertRegex(out, r"kept +docs/PROGRESS.md")

    def test_negation_lands_last(self):
        d = self.bare("gn")
        git(d, "init", "-q")
        write(os.path.join(d, ".gitignore"), "!.env.example\n")
        self.render(d)
        self.assertNotEqual(git(d, "check-ignore", "-q", ".env.example").returncode, 0)
        self.assertEqual(git(d, "check-ignore", "-q", ".env.local").returncode, 0)

    def test_symlinked_gitignore_blocked(self):
        d = self.bare("gl")
        steal = os.path.join(self.tmp, "gitignore-steal.txt")
        os.symlink(steal, os.path.join(d, ".gitignore"))
        proc = self.render(d)
        self.assertEqual(proc.returncode, 1)
        self.assertFalse(os.path.exists(steal))
        self.assertRegex(proc.stdout + proc.stderr, r"\.gitignore.*symlink")

    def test_disabled_agent_owns_nothing(self):
        cfg = yaml.safe_load(read(VALID))
        cfg["agents"]["extra-linter"] = {
            "enabled": False, "purpose": "Disabled linter — must not own slots",
            "model": "claude-haiku-4-5", "tier": "mechanical", "autonomy": "auto",
            "tools": ["Read", "Bash"], "owns_commands": ["lint"], "layers": ["database", "api"]}
        d = self.bare("da", yaml.safe_dump(cfg))
        self.render(d)
        md = read(os.path.join(d, "CLAUDE.md"))
        self.assertRegex(md, r"(?m)^\| lint \|.*\(unassigned\)")
        self.assertNotIn("extra-linter", md)

    def test_state_file_outside_cfm_ignored_by_name(self):
        d = self.bare("sf", read(VALID) + "state_file: docs/cfm-state.json\n")
        git(d, "init", "-q")
        self.render(d)
        self.assertNotEqual(git(d, "check-ignore", "-q", "docs/PROGRESS.md").returncode, 0)
        self.assertEqual(git(d, "check-ignore", "-q", "docs/cfm-state.json").returncode, 0)

    def test_router_layout(self):
        text = read(VALID).replace("layout: single", "layout: router").replace(
            "files: [CLAUDE.md]", "files: [CLAUDE.md, domain/database/CLAUDE.md, apps/api/CLAUDE.md]")
        d = self.bare("rt", text)
        self.render(d)
        for f in ("CLAUDE.md", "domain/database/CLAUDE.md", "apps/api/CLAUDE.md"):
            self.assertTrue(os.path.isfile(os.path.join(d, f)), f)
        root = read(os.path.join(d, "CLAUDE.md"))
        self.assertIn("Routing", root)
        self.assertIn("domain/database/CLAUDE.md", root)
        self.assertIn("domain/database/src/{feature}", read(os.path.join(d, "domain/database/CLAUDE.md")))

    def test_dry_run_writes_nothing(self):
        d = self.bare("dr")
        out = self.render(d, "--dry-run").stdout
        for rel in ("CLAUDE.md", ".env.example", ".gitignore", ".cfm/state.json"):
            self.assertFalse(os.path.exists(os.path.join(d, rel)), rel)
        self.assertIn("would-write", out)
        self.assertIn("CLAUDE.md", out)
