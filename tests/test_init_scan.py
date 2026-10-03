"""The init scanner must classify each repo scenario correctly and surface
existing ledger/rules files, strong candidates first."""

from __future__ import annotations

import json
import os
import shutil

from helpers import ProjectCase, VALID, run, write


class Scenarios(ProjectCase):
    def scenario(self, d):
        return json.loads(run("init_scan.py", "--project-dir", d).stdout)

    def test_greenfield(self):
        d = os.path.join(self.tmp, "g"); os.makedirs(d)
        self.assertEqual(self.scenario(d)["scenario"], "greenfield")
        self.assertEqual(self.scenario(d)["signals"]["doc_candidates"], {"progress": [], "rules": []})

    def test_scaffolded(self):
        d = os.path.join(self.tmp, "s")
        write(os.path.join(d, "package.json"), '{"scripts": {"lint": "eslint ."}}')
        write(os.path.join(d, "src/index.ts"), "console.log(1)")
        self.assertEqual(self.scenario(d)["scenario"], "scaffolded")

    def test_existing(self):
        d = os.path.join(self.tmp, "e")
        write(os.path.join(d, "package.json"), "{}")
        for i in range(1, 21):
            write(os.path.join(d, f"src/mod{i}.ts"), f"export const x{i} = {i}")
        self.assertEqual(self.scenario(d)["scenario"], "existing")

    def test_adoption_wins_over_maturity(self):
        d = os.path.join(self.tmp, "a")
        write(os.path.join(d, "CLAUDE.md"), "# My project")
        write(os.path.join(d, ".claude/agents/coder.md"), "agent")
        write(os.path.join(d, "package.json"), "{}")
        os.makedirs(os.path.join(d, "src"))
        self.assertEqual(self.scenario(d)["scenario"], "adoption")

    def test_already_initialized(self):
        d = os.path.join(self.tmp, "d"); os.makedirs(d)
        shutil.copy(VALID, os.path.join(d, ".cfm-workflow.yml"))
        self.assertEqual(self.scenario(d)["scenario"], "already-initialized")

    def test_doc_candidates_strong_first(self):
        d = os.path.join(self.tmp, "m")
        write(os.path.join(d, "docs/STATUS.md"), "# Status")
        write(os.path.join(d, "coding-rules.md"), "# Rules")
        write(os.path.join(d, "CHANGELOG.md"), "# Changelog")
        write(os.path.join(d, "CONTRIBUTING.md"), "# Contributing")
        dc = self.scenario(d)["signals"]["doc_candidates"]
        self.assertEqual(dc["progress"][0], "docs/STATUS.md")
        self.assertEqual(dc["progress"][-1], "CHANGELOG.md")
        self.assertLess(dc["rules"].index("coding-rules.md"), dc["rules"].index("CONTRIBUTING.md"))
