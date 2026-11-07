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
        self.assertIn("not reported  claude-sonnet-5 · —", e2e)
        totals = next(l for l in lines if l.startswith("Totals"))
        self.assertIn("54.2k+  (in 50.0k+ · out 4.2k+)  2 dispatches", totals)
        self.assertIn("\u26A0 1 of 2 dispatches have no usage", report)
        self.assertEqual(self.state("validate").returncode, 0)
        self.assert_healthy(self.d)

    def test_usage_backfills_a_dispatch_recorded_before_its_notification(self):
        # a dispatch recorded at launch has no usage yet; the task-notification
        # that lands later fills the oldest null entry for that agent and layer
        self.state("init", "--id", "p1", "--description", "first", "--layers", "api")
        for purpose in ("first", "re-dispatch"):
            self.state("record", "--agent", "coder", "--layer", "api",
                       "--purpose", purpose, "--model", "claude-opus-5")
        self.state("record", "--agent", "code-reviewer", "--purpose", "review: phase",
                   "--model", "claude-opus-5")
        report = self.state("report").stdout
        totals = next(l for l in report.splitlines() if l.startswith("Totals"))
        self.assertIn("not reported  3 dispatches", totals)
        self.assertNotIn("0+", report)
        self.assertIn("\u26A0 3 of 3 dispatches have no usage", report)
        self.assertIn("\u2B1C total (input/output split not reported)", report)

        usage = "<usage><subagent_tokens>40000</subagent_tokens><duration_ms>90000</duration_ms></usage>"
        p = self.state("usage", "--agent", "coder", "--layer", "api", "--usage", usage)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.state("usage", "--agent", "coder", "--layer", "api", "--total", "10000")
        self.state("usage", "--agent", "code-reviewer", "--total", "5000")
        first, second, review = self.ledger()["tokens"]["dispatches"]
        self.assertEqual((first["purpose"], first["total_tokens"], first["duration_ms"]),
                         ("first", 40000, 90000))
        self.assertEqual((second["total_tokens"], second["duration_ms"]), (10000, None))
        self.assertEqual(review["total_tokens"], 5000)
        self.assertEqual(self.ledger()["tokens"]["phase_total"], 55000)
        report = self.state("report").stdout
        self.assertIn("55.0k  3 dispatches", report)
        self.assertNotIn("\u26A0", report)

        # nothing left to fill: refused, and a reported number is never overwritten
        p = self.state("usage", "--agent", "coder", "--layer", "api", "--total", "1")
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(self.ledger()["tokens"]["phase_total"], 55000)
        p = self.state("usage", "--agent", "coder", "--layer", "api")
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(self.state("validate").returncode, 0)
        self.assert_healthy(self.d)

    def test_report_harvests_usage_from_the_session_transcript(self):
        # records made before their notification landed, plus a run never
        # recorded at all, are filled from the task-notifications on disk
        self.state("init", "--id", "p1", "--description", "first", "--layers", "api")
        self.state("record", "--agent", "coder", "--layer", "api", "--purpose", "build",
                   "--model", "claude-opus-5")
        config_dir = os.path.join(self.d, "claude-home")
        session = os.path.join(config_dir, "projects",
                               "".join(c if c.isalnum() else "-" for c in os.path.abspath(self.d)),
                               "s1")
        rows = []
        for task, kind, total, stamp in (("a1", "cfm:coder", 71747, "2999-01-01T00:00:01.5Z"),
                                         ("a2", "cfm:code-reviewer", 41070, "2999-01-01T00:00:02Z"),
                                         ("a3", "Explore", 9999, "2999-01-01T00:00:03Z"),
                                         ("a0", "cfm:coder", 1, "2000-01-01T00:00:00Z")):
            write(os.path.join(session, "subagents", f"agent-{task}.meta.json"),
                  json.dumps({"agentType": kind}))
            rows.append({"toolUseResult": {"agentId": task, "resolvedModel": "claude-opus-5-5",
                                           "description": f"run {task}"}})
            rows.append({"timestamp": stamp, "attachment": {
                "commandMode": "task-notification",
                "prompt": f"<task-notification>\n<task-id>{task}</task-id>",
                "usage": {"totalTokens": total, "durationMs": 60000}}})
        write(session + ".jsonl", "".join(json.dumps(r) + "\n" for r in rows))

        env = dict(os.environ, CLAUDE_CONFIG_DIR=config_dir)
        p = run("state.py", "--project-dir", self.d, "report", env=env)
        self.assertEqual(p.returncode, 0, p.stderr)
        coder, review = self.ledger()["tokens"]["dispatches"]
        self.assertEqual((coder["purpose"], coder["total_tokens"], coder["agent_id"]),
                         ("build", 71747, "a1"))
        self.assertEqual((review["agent"], review["purpose"], review["model"], review["total_tokens"]),
                         ("code-reviewer", "run a2", "claude-opus-5-5", 41070))
        self.assertEqual(self.ledger()["tokens"]["phase_total"], 112817)
        self.assertNotIn("⚠", p.stdout)
        # a second report claims nothing twice
        run("state.py", "--project-dir", self.d, "report", env=env)
        self.assertEqual(len(self.ledger()["tokens"]["dispatches"]), 2)
        self.assertEqual(self.state("validate").returncode, 0)

    def test_record_reads_task_notification_usage(self):
        self.state("init", "--id", "p1", "--description", "first", "--layers", "api")
        usage = ("<usage><subagent_tokens>64609</subagent_tokens><tool_uses>21</tool_uses>"
                 "<duration_ms>174078</duration_ms></usage>")
        self.state("record", "--agent", "coder", "--layer", "api", "--purpose", "x",
                   "--model", "claude-opus-5", "--usage", usage)
        self.state("record", "--agent", "coder", "--layer", "api", "--purpose", "y",
                   "--model", "claude-opus-5", "--usage", usage, "--total", "100")
        first, second = self.ledger()["tokens"]["dispatches"]
        self.assertEqual((first["total_tokens"], first["duration_ms"]), (64609, 174078))
        self.assertIsNone(first["input_tokens"])
        self.assertEqual((second["total_tokens"], second["duration_ms"]), (100, 174078))
        self.assertEqual(self.ledger()["tokens"]["phase_total"], 64709)
        self.assertIn("64.6k  claude-opus-5 · 2m 54s", self.state("report").stdout)
