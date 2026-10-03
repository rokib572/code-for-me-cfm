"""The ledger is written by scripts/state.py at every boundary: a full
phase through the script stays schema-valid, doctor-green, and renders the
phase-gate table with honest totals."""

from __future__ import annotations

import json
import os

from helpers import ProjectCase, run, read, write


class Lifecycle(ProjectCase):
    def setUp(self):
        super().setUp()
        self.d = self.project()

    def state(self, *args):
        return run("state.py", "--project-dir", self.d, *args)

    def ledger(self):
        return json.loads(read(os.path.join(self.d, ".cfm/state.json")))

    def test_diagnose_completes_with_its_own_gate(self):
        # a diagnosis leaves no diff, so it completes with `plan-fix` instead of
        # the implementation gates, and its notes survive for /cfm:plan to read
        self.state("init", "--id", "diagnose-slow-login", "--description", "login is slow", "--layers", "api")
        self.state("note", "--key", "root_cause", "--value", "N+1 in session lookup")
        self.assertEqual(self.state("complete", "--gates", "plan-fix").returncode, 0)
        d = self.ledger()
        self.assertEqual(d["phase"]["status"], "complete")
        self.assertEqual(d["pending_gates"], ["plan-fix"])
        self.assertEqual(d["notes"]["root_cause"], "N+1 in session lookup")
        self.assertEqual(self.state("validate").returncode, 0)
        # plain `complete` still sets the default implementation gates
        self.state("init", "--id", "p2", "--description", "again", "--layers", "api")
        self.state("complete")
        self.assertEqual(self.ledger()["pending_gates"], ["run-verify_full", "git-per-level", "next-phase-approval"])
        self.assert_healthy(self.d)

    def test_full_phase(self):
        steps = [
            ("init", "--id", "p1", "--description", "first", "--layers", "database", "api"),
            ("dispatch", "--agent", "coder", "--layer", "database"),
            ("record", "--agent", "coder", "--layer", "database", "--purpose", "schema",
             "--model", "claude-sonnet-5", "--total", "54200", "--input", "50000",
             "--output", "4200", "--duration-ms", "260000", "--files", "domain/database/src/a.ts"),
            ("record", "--agent", "e2e-test", "--layer", "database", "--purpose", "tests",
             "--model", "claude-sonnet-5", "--tests-written", "t/a.test.ts",
             "--tests-passed", "t/a.test.ts"),
            ("gate", "--agent", "code-reviewer", "--verdict", "pass"),
            ("question", "--ask", "tracker?", "--asked-by", "cfm:plan"),
            ("question", "--ask", "tracker?", "--asked-by", "cfm:plan"),
            ("question", "--resolve", "--asked-by", "cfm:plan", "--outcome", "declined"),
            ("tracker", "--provider", "jira", "--last-sync", "ok",
             "--bind", "docs/plans/x.md#p1=jira:PROJ-1"),
            ("carry", "AC-3 deferred"),
        ]
        for step in steps:
            p = self.state(*step)
            self.assertEqual(p.returncode, 0, f"{step[0]}: {p.stderr}")
        s = self.ledger()
        layer = s["cursor"]["layers"]["database"]
        self.assertEqual(layer["coder"], "done")
        self.assertEqual(layer["tests"]["passed"], ["t/a.test.ts"])
        self.assertEqual(s["tokens"]["phase_total"], 54200)
        self.assertEqual(s["files_touched"], ["domain/database/src/a.ts"])
        self.assertEqual(s["cursor"]["phase_gates"], {"code-reviewer": "pass"})
        self.assertEqual(s["deferred_questions"],
                         [{"question": "tracker?", "asked_by": "cfm:plan", "outcome": "declined"}])
        self.assertEqual(s["tracker"]["tasks"], {"docs/plans/x.md#p1": "jira:PROJ-1"})
        self.assertEqual(s["tracker"]["last_sync"]["outcome"], "ok")
        self.assertEqual(s["carried_forward"], ["AC-3 deferred"])

        # refusals: a second init while in flight; a gate for an unknown agent
        p = self.state("init", "--id", "p2", "--description", "dup", "--layers", "api")
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(self.ledger()["phase"]["id"], "p1")
        p = self.state("gate", "--agent", "nobody", "--verdict", "pass")
        self.assertNotEqual(p.returncode, 0)
        self.assertNotIn("nobody", self.ledger()["cursor"]["phase_gates"])

        # rollback resets the layer and every gate verdict
        p = self.state("rollback", "--layer", "database", "--to", "coder-pending")
        s = self.ledger()
        self.assertEqual(p.returncode, 0)
        self.assertEqual(s["cursor"]["layers"]["database"]["coder"], "pending")
        self.assertEqual(s["cursor"]["phase_gates"], {"code-reviewer": "pending"})

        # unknown fields survive every rewrite
        s["future_field"] = {"kept": True}
        write(os.path.join(self.d, ".cfm/state.json"), json.dumps(s))
        self.state("carry", "second")
        self.assertEqual(self.ledger().get("future_field"), {"kept": True})

        p = self.state("complete")
        s = self.ledger()
        self.assertEqual(p.returncode, 0)
        self.assertEqual(s["phase"]["status"], "complete")
        self.assertTrue(s["phase"]["completed"])
        self.assertEqual(s["pending_gates"], ["run-verify_full", "git-per-level", "next-phase-approval"])

        report = self.state("report").stdout
        lines = report.splitlines()
        self.assertEqual((lines[0], lines[-1]), ("```", "```"))
        coder = next(l for l in lines if l.startswith("coder · database"))
        # one dispatch is the scale, so its bar is full width: 18 input + 2 output
        self.assertIn("\U0001F7E6" * 18 + "\U0001F7E7" * 2 + "  54.2k  (in 50.0k · out 4.2k)", coder)
        self.assertIn("claude-sonnet-5 · 4m 20s", coder)
        e2e = next(l for l in lines if l.startswith("e2e-test · database"))
        self.assertIn("no token data  claude-sonnet-5 · —", e2e)
        totals = next(l for l in lines if l.startswith("Totals"))
        self.assertIn("54.2k+  (in 50.0k+ · out 4.2k+)  2 dispatches", totals)
        self.assertEqual(self.state("validate").returncode, 0)
        self.assert_healthy(self.d)
