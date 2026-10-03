"""Shared fixtures for the cfm test suite (stdlib unittest, no dependency).

Every test builds a throwaway project under a temp dir, renders what
/cfm:init would (the settings denies), and runs the real scripts as
subprocesses — the same entry points the skills call.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
FIXTURES = os.path.join(ROOT, "tests", "fixtures")
VALID = os.path.join(FIXTURES, "valid.yml")

sys.path.insert(0, SCRIPTS)

# tests exercise check logic, not the environment gate — check #0 must pass
os.environ["CLAUDECODE"] = "1"


def script(name):
    return os.path.join(SCRIPTS, name)


def run(name, *args, cwd=None, input=None, env=None):
    """Run scripts/<name> with python3; returns CompletedProcess."""
    return subprocess.run(
        [sys.executable, script(name), *args], cwd=cwd, input=input,
        capture_output=True, text=True, env=env,
    )


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def write(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def git(directory, *args):
    return subprocess.run(
        ["git", "-C", directory, "-c", "user.email=cfm@test", "-c", "user.name=cfm",
         *args], capture_output=True, text=True,
    )


def scaffold(directory, config=VALID, rules="rules-valid.md"):
    """The tree the valid fixture expects, plus the config and rules."""
    for rel in ("domain/database/src", "apps/api/src", ".claude/rules", "docs"):
        os.makedirs(os.path.join(directory, rel), exist_ok=True)
    write(os.path.join(directory, "CLAUDE.md"), "# fixture\n")
    shutil.copy(os.path.join(FIXTURES, rules),
                os.path.join(directory, ".claude/rules/rules.md"))
    # doctor check #7 compliance — the env glob family, example negated
    write(os.path.join(directory, ".gitignore"), ".env*\n!.env.example\n")
    if config:
        shutil.copy(config, os.path.join(directory, ".cfm-workflow.yml"))
    return directory


def gen_settings(directory, *args):
    """Render the settings denies as init would — best effort: a broken
    config exits 1, and check 7 then only warns because check 1 owns it."""
    return run("gen_settings.py", "--project-dir", directory, *args)


def doctor(directory, settings=True):
    """(rc, report dict). Renders the settings denies first unless told
    not to, because an initialized project always carries them."""
    if settings:
        gen_settings(directory, "--write")
    proc = run("doctor.py", "--project-dir", directory, "--json")
    return proc.returncode, json.loads(proc.stdout)


def check(report, check_id):
    return next(c for c in report["checks"] if c["id"] == check_id)


def failing_ids(report):
    return [c["id"] for c in report["checks"] if c["status"] == "FAIL"]


class ProjectCase(unittest.TestCase):
    """A temp dir per test, removed afterwards."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cfm-test-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def project(self, name="p", config=VALID, rules="rules-valid.md"):
        return scaffold(os.path.join(self.tmp, name), config, rules)

    def assert_healthy(self, directory, settings=True):
        rc, report = doctor(directory, settings)
        self.assertTrue(report["ok"], f"expected healthy, failing: "
                        f"{[c for c in report['checks'] if c['status'] == 'FAIL']}")
        self.assertEqual(rc, 0)
        return report

    def assert_unhealthy(self, directory, check_id, settings=True):
        rc, report = doctor(directory, settings)
        self.assertFalse(report["ok"], "expected unhealthy, doctor reported ok")
        self.assertNotEqual(rc, 0)
        target = check(report, check_id)
        self.assertEqual(target["status"], "FAIL",
                         f"expected check #{check_id} to FAIL, got {target['status']}")
        others = [i for i in failing_ids(report) if i != check_id]
        self.assertEqual(others, [], f"unexpected extra failing checks: {others}")
        return report


# --- hook events -----------------------------------------------------------

def bash_event(command, subagent=False):
    event = {"tool_name": "Bash", "tool_input": {"command": command}}
    if subagent:
        event.update({"agent_id": "t-1", "agent_type": "coder"})
    return json.dumps(event)


def file_event(tool, path, subagent=False):
    event = {"tool_name": tool, "tool_input": {"file_path": path}}
    if tool == "Write":
        event["tool_input"]["content"] = "x"
    if subagent:
        event.update({"agent_id": "t-1", "agent_type": "coder"})
    return json.dumps(event)


def grep_event(glob):
    return json.dumps({"tool_name": "Grep",
                       "tool_input": {"pattern": "=", "path": ".", "glob": glob}})


def hook_result(name, directory, event, env_extra=None):
    """Run scripts/<name>.sh with the event on stdin; returns the
    CompletedProcess (exit code, stdout JSON if any, stderr reason)."""
    env = dict(os.environ, CLAUDECODE="1", CLAUDE_PROJECT_DIR=directory,
               CLAUDE_PLUGIN_ROOT=ROOT)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(["bash", script(name)], input=event, env=env,
                          capture_output=True, text=True)


def hook(name, directory, event, env_extra=None):
    """Run scripts/<name>.sh with the event on stdin; returns the exit code."""
    return hook_result(name, directory, event, env_extra).returncode
