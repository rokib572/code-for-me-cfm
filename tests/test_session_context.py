"""cfm mode's prose half: the session-context hook through the real entry
script (session_context.sh) and the status line. The guard's orchestrator
rule — the mechanism — is covered in test_guard.py / test_guard_hook.py."""

from __future__ import annotations

import json
import os
import subprocess

from helpers import ProjectCase, ROOT, VALID, read, run, write

ROUTES_MUST_NAME = ("plan", "implement-phase", "diagnose", "code-review", "status")


def context(proc):
    return json.loads(proc.stdout)["hookSpecificOutput"]


class SessionStart(ProjectCase):
    def setUp(self):
        super().setUp()
        self.d = self.project("ctx")
        self.plain = os.path.join(self.tmp, "plain")
        os.makedirs(self.plain)

    def start(self, directory, reason="startup"):
        event = json.dumps({"hook_event_name": "SessionStart", "session_start_reason": reason})
        return subprocess.run(
            ["bash", os.path.join(ROOT, "scripts", "session_context.sh"), "SessionStart"],
            input=event, capture_output=True, text=True,
            env=dict(os.environ, CLAUDECODE="1", CLAUDE_PROJECT_DIR=directory,
                     CLAUDE_PLUGIN_ROOT=ROOT))

    def test_plain_project_is_silent(self):
        proc = self.start(self.plain)
        self.assertEqual((proc.returncode, proc.stdout), (0, ""))

    def test_enforced_context(self):
        proc = self.start(self.d)
        self.assertEqual(proc.returncode, 0)
        out = context(proc)
        self.assertEqual(out["hookEventName"], "SessionStart")
        text = out["additionalContext"]
        self.assertIn("cfm mode: ENFORCED", text)
        self.assertIn("ORCHESTRATOR", text)
        self.assertIn("guard", text)
        for name in ROUTES_MUST_NAME:
            self.assertIn(f"/cfm:{name}", text)
        self.assertIn("No phase in flight", text)
        self.assertIn("git level L0", text)

    def test_state_summary_and_compact(self):
        run("state.py", "--project-dir", self.d, "init", "--id", "p2",
            "--description", "billing api", "--layers", "database")
        proc = self.start(self.d, reason="compact")
        text = context(proc)["additionalContext"]
        self.assertIn("'p2'", text)
        self.assertIn("IN-FLIGHT", text)
        self.assertIn("resumes it", text)

    def test_advisory_and_off(self):
        adv = self.project("adv", config=None)
        write(os.path.join(adv, ".cfm-workflow.yml"), read(VALID) + "\nmode: advisory\n")
        text = context(self.start(adv))["additionalContext"]
        self.assertIn("cfm mode: ADVISORY", text)
        self.assertIn("advisory", text)
        self.assertNotIn("guard enforces this", text)
        off = self.project("off", config=None)
        write(os.path.join(off, ".cfm-workflow.yml"), read(VALID) + "\nmode: off\n")
        proc = self.start(off)
        self.assertEqual((proc.returncode, proc.stdout), (0, ""))

    def test_broken_config_still_informs(self):
        write(os.path.join(self.d, ".cfm-workflow.yml"), read(VALID) + "\nmode: bogus\n")
        text = context(self.start(self.d))["additionalContext"]
        self.assertIn("cfm mode: ENFORCED", text)  # the default enforces
        self.assertIn("validation error", text)

    def test_malformed_event_fails_open(self):
        proc = subprocess.run(
            ["bash", os.path.join(ROOT, "scripts", "session_context.sh"), "SessionStart"],
            input="not json", capture_output=True, text=True,
            env=dict(os.environ, CLAUDECODE="1", CLAUDE_PROJECT_DIR=self.d,
                     CLAUDE_PLUGIN_ROOT=ROOT))
        self.assertEqual(proc.returncode, 0)
        self.assertIn("cfm mode: ENFORCED", context(proc)["additionalContext"])

    def test_outside_claude_code_is_silent_not_blocking(self):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=self.d, CLAUDE_PLUGIN_ROOT=ROOT)
        env.pop("CLAUDECODE", None)
        proc = subprocess.run(
            ["bash", os.path.join(ROOT, "scripts", "session_context.sh"), "SessionStart"],
            input="{}", capture_output=True, text=True, env=env)
        self.assertEqual((proc.returncode, proc.stdout), (0, ""))


class PromptSubmit(ProjectCase):
    def submit(self, directory, prompt):
        event = json.dumps({"hook_event_name": "UserPromptSubmit", "prompt": prompt})
        return subprocess.run(
            ["bash", os.path.join(ROOT, "scripts", "session_context.sh"), "UserPromptSubmit"],
            input=event, capture_output=True, text=True,
            env=dict(os.environ, CLAUDECODE="1", CLAUDE_PROJECT_DIR=directory,
                     CLAUDE_PLUGIN_ROOT=ROOT))

    def test_plain_prompt_gets_the_router(self):
        d = self.project()
        proc = self.submit(d, "add a null check to the login handler")
        out = context(proc)
        self.assertEqual(out["hookEventName"], "UserPromptSubmit")
        self.assertIn("cfm mode (enforced)", out["additionalContext"])
        self.assertIn("/cfm:diagnose", out["additionalContext"])
        self.assertIn("never an edit", out["additionalContext"])

    def test_slash_commands_and_off_are_silent(self):
        d = self.project()
        for prompt in ("/cfm:status", "  /clear", "/cfm:implement-phase 2"):
            proc = self.submit(d, prompt)
            self.assertEqual((proc.returncode, proc.stdout), (0, ""), prompt)
        off = self.project("off", config=None)
        write(os.path.join(off, ".cfm-workflow.yml"), read(VALID) + "\nmode: off\n")
        proc = self.submit(off, "add a null check")
        self.assertEqual((proc.returncode, proc.stdout), (0, ""))


class StatusLine(ProjectCase):
    def line(self, directory, payload=None):
        event = json.dumps(payload if payload is not None else {
            "model": {"display_name": "Fable"},
            "workspace": {"project_dir": directory, "current_dir": directory},
            "cwd": directory})
        env = dict(os.environ, CLAUDE_PLUGIN_ROOT=ROOT)
        env.pop("CLAUDE_PROJECT_DIR", None)
        return subprocess.run(["bash", os.path.join(ROOT, "scripts", "statusline.sh")],
                              input=event, capture_output=True, text=True, env=env)

    def test_mode_and_phase(self):
        d = self.project()
        proc = self.line(d)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), "cfm ▸ enforced ▸ no phase ▸ [Fable]")
        run("state.py", "--project-dir", d, "init", "--id", "p1",
            "--description", "x", "--layers", "database")
        self.assertIn("phase p1 in-flight", self.line(d).stdout)
        write(os.path.join(d, ".cfm/state.json"), "{ not json")
        self.assertIn("state unreadable", self.line(d).stdout)

    def test_plain_project_and_empty_input(self):
        plain = os.path.join(self.tmp, "plain")
        os.makedirs(plain)
        self.assertEqual(self.line(plain).stdout.strip(), "[Fable] plain")
        proc = self.line(plain, payload={})
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(proc.stdout.strip())
