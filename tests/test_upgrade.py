"""The upgrade report is a pure read that finds what the doctor does not:
retired keys, settings left on a default, roster agents added since init,
and a min_version stamp behind the plugin."""

from __future__ import annotations

import json
import os

import yaml

from helpers import ProjectCase, VALID, read, run, write


class Upgrade(ProjectCase):
    def report(self, d):
        proc = run("upgrade.py", "--project-dir", d, "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def test_finds_drift_and_writes_nothing(self):
        cfg = yaml.safe_load(read(VALID))
        cfg["legacy_flag"] = True
        cfg["review"]["old_key"] = 1
        cfg["agents"]["coder"]["color"] = "blue"
        cfg["agents"]["e2e-test"] = dict(cfg["agents"]["coder"], enabled=False, color="red")
        d = self.project(config=None)
        path = os.path.join(d, ".cfm-workflow.yml")
        write(path, yaml.safe_dump(cfg))
        before = read(path)

        report = self.report(d)
        self.assertEqual(set(report["unknown_keys"]),
                         {"legacy_flag", "review.old_key", "agents.coder.color"})
        defaulted = {item["key"] for item in report["defaulted_keys"]}
        self.assertIn("review.scope", defaulted)
        self.assertNotIn("review.trigger", defaulted)  # the file sets it
        new = {item["agent"]: item["entry"] for item in report["new_agents"]}
        self.assertIn("security-check", new)
        self.assertNotIn("coder", new)
        self.assertNotIn("e2e-test", new)  # disabled on purpose, not a gap
        self.assertNotIn("e2e-test", report["models"])
        self.assertNotIn("ui-design", new)  # no web/frontend layer here
        self.assertEqual(new["security-check"]["layers"], ["api", "database"])
        self.assertTrue(report["stamp_behind"])  # fixture pins 0.1.0
        self.assertEqual(report["schema"], {"file": 2, "latest": 2})
        self.assertEqual(read(path), before)

    def test_repo_rescan(self):
        d = self.project()
        for rel in ("apps/api", "packages/new-lib", "node_modules/dep"):
            write(os.path.join(d, rel, "package.json"), "{}")
        write(os.path.join(d, "package.json"),
              json.dumps({"scripts": {"lint": "eslint .", "lint:arch": "x", "dev": "vite"}}))
        write(os.path.join(d, ".cfm-workflow.yml"),
              read(VALID).replace('lint: ["true"]', 'lint: ["pnpm lint:arch"]'))
        repo = self.report(d)["repo"]
        self.assertEqual(repo["unlayered_packages"], ["packages/new-lib"])
        self.assertEqual(repo["unused_scripts"], ["lint", "dev"])

    def test_missing_config_exits_1(self):
        proc = run("upgrade.py", "--project-dir", self.tmp)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("/cfm:init", proc.stderr)
