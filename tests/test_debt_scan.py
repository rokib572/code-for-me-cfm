"""The debt ledger counts what is really there: markers behind a comment
prefix, the ceiling/trigger split, no_trigger for the rotting ones,
secret files skipped, prose about the convention left out."""

from __future__ import annotations

import json
import os

from helpers import ProjectCase, run, write


class DebtScan(ProjectCase):
    def setUp(self):
        super().setUp()
        self.d = os.path.join(self.tmp, "ds")
        write(os.path.join(self.d, "src/lock.py"),
              "def acquire():\n    # cfm-debt: global lock, per-account locks if throughput matters\n"
              "    return _GLOBAL\n\ndef scan(items):\n    # cfm-debt: O(n^2) scan\n    return sorted(items)\n")
        write(os.path.join(self.d, "src/app.js"), "// cfm-debt: in-memory cache, swap to redis on a second node\n")
        write(os.path.join(self.d, ".env"), "SECRET_TOKEN=real\n# cfm-debt: never read, secret file\n")
        write(os.path.join(self.d, "README.md"), "The cfm-debt: convention is documented here, in prose.\n")
        write(os.path.join(self.d, "node_modules/dep.js"), "// cfm-debt: vendored, ignore me\n")

    def scan(self, *args):
        return json.loads(run("debt_scan.py", "--project-dir", self.d, *args).stdout)

    def test_repo_ledger(self):
        d = self.scan()
        self.assertEqual(d["total"], 3)
        self.assertEqual(d["no_trigger"], 1)
        files = {(m["file"], m["line"]): m for m in d["markers"]}
        self.assertFalse(any(m["file"] in (".env", "README.md") or m["file"].startswith("node_modules/")
                             for m in d["markers"]))
        lock = files[("src/lock.py", 2)]
        self.assertEqual(lock["ceiling"], "global lock")
        self.assertTrue(lock["upgrade"].startswith("per-account"))
        self.assertTrue(files[("src/lock.py", 6)]["no_trigger"])

    def test_scoped_to_paths(self):
        d = self.scan("--paths", "src/app.js", ".env")
        self.assertEqual(d["total"], 1)
        self.assertEqual(d["scanned"], "paths")
        self.assertFalse(any(m["file"] == ".env" for m in d["markers"]))
