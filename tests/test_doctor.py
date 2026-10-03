"""The doctor must flag a hand-broken config in each check category and
pass a valid one; messages name what is wrong."""

from __future__ import annotations

import json
import os
import shutil

from helpers import (FIXTURES, ProjectCase, VALID, check, doctor, gen_settings,
                     git, read, run, scaffold, write)
import cfm_config


def fixture(name):
    return os.path.join(FIXTURES, name)


class FixtureCases(ProjectCase):
    def test_valid_is_healthy(self):
        self.assert_healthy(self.project())

    def test_broken_schema(self):
        self.assert_unhealthy(self.project(config=fixture("broken-schema.yml")), 1)

    def test_broken_invariant(self):
        self.assert_unhealthy(self.project(config=fixture("broken-invariant.yml")), 1)

    def test_broken_local_override(self):
        d = self.project()
        shutil.copy(fixture("broken-local.yml"), os.path.join(d, ".cfm-workflow.local.yml"))
        self.assert_unhealthy(d, 1)

    def test_broken_paths(self):
        self.assert_unhealthy(self.project(config=fixture("broken-paths.yml")), 2)

    def test_broken_commands(self):
        self.assert_unhealthy(self.project(config=fixture("broken-commands.yml")), 3)

    def test_toothless_rules(self):
        self.assert_unhealthy(self.project(rules="rules-toothless.md"), 6)

    def test_ghost_reviewer_named(self):
        d = self.project(rules="rules-ghost-reviewer.md")
        report = self.assert_unhealthy(d, 6)
        self.assertTrue(any("reviewer 'ghost-agent' which is not an enabled agent" in f
                            for f in check(report, 6)["failures"]))

    def test_broken_roster_both_messages(self):
        d = self.project(config=fixture("broken-roster.yml"))
        report = self.assert_unhealthy(d, 4)
        failures = check(report, 4)["failures"]
        self.assertTrue(any("disabled" in f and "cannot gate" in f for f in failures))
        self.assertTrue(any("shared ownership" in f for f in failures))

    def test_broken_implement(self):
        self.assert_unhealthy(self.project(config=fixture("broken-implement.yml")), 1)

    def test_local_implement_override_is_healthy(self):
        d = self.project()
        shutil.copy(fixture("local-implement.yml"), os.path.join(d, ".cfm-workflow.local.yml"))
        self.assert_healthy(d)


class ConfigSemantics(ProjectCase):
    def plan_gate(self, d):
        proc = run("cfm_config.py", "--project-dir", d, "--json")
        return json.loads(proc.stdout)["implement"]["plan_gate"]

    def test_plan_gate_default_and_override(self):
        # absent from valid.yml, so the DEFAULT (true) must apply; the
        # allowlisted local override must flip it to false
        d = self.project("valid")
        self.assertIs(self.plan_gate(d), True)
        e = self.project("local")
        shutil.copy(fixture("local-implement.yml"), os.path.join(e, ".cfm-workflow.local.yml"))
        self.assertIs(self.plan_gate(e), False)

    def test_additive_invariants(self):
        # the level decides, the config only extends — a config that lists
        # just "git commit" still forbids "git push" at L0, and the secret
        # globs a file omits come back (with a warning), never an error
        d = self.project()
        with open(os.path.join(d, ".cfm-workflow.yml"), "a") as fh:
            fh.write("\nforbidden_ops:\n  - git commit\n  - npm publish\n"
                     "secret_globs:\n  - \".env*\"\n  - \"*.secret\"\n")
        config, errors, warnings = cfm_config.load(d)
        self.assertEqual(errors, [])
        ops = cfm_config.forbidden_ops(config)
        for op in ("git commit", "git push", "git pull", "npm publish", "gh pr merge"):
            self.assertIn(op, ops)
        for g in ("*.secret", "*.pem", "id_ed25519*"):
            self.assertIn(g, config["secret_globs"])
        self.assertTrue(any("re-added default globs" in w for w in warnings))
        self.assertEqual(cfm_config.model_alias("claude-opus-5"), "opus")
        self.assertIsNone(cfm_config.model_alias("gpt-x"))
        l3 = cfm_config.forbidden_ops_for_level("L3")
        self.assertNotIn("git push", l3)
        self.assertNotIn("gh pr create", l3)
        self.assertIn("git clean", l3)

    def test_traversal_config_rejected(self):
        d = self.project(config=fixture("broken-traversal.yml"))
        proc = run("cfm_config.py", "--project-dir", d)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("rules_file: must be a relative path", proc.stderr)
        self.assertIn("progress_log: must be a relative path", proc.stderr)


class CustomAgents(ProjectCase):
    def add_custom(self, d):
        path = os.path.join(d, ".cfm-workflow.yml")
        text = read(path).replace("review_gates:", """  perf-reviewer:
    enabled: true
    purpose: "Reviews hot paths for allocation and query count"
    model: claude-opus-5
    tier: judgment
    autonomy: auto
    tools: [Read, Grep, Glob]
    owns_commands: []
    layers: [database, api]

review_gates:""")
        write(path, text)

    def test_custom_agent_lifecycle(self):
        # no project agent file → check 4 FAIL (tool limits unenforced);
        # agent_file.py renders one → healthy; drifted tools → FAIL again;
        # a re-render keeps the body and realigns the frontmatter
        d = self.project()
        self.add_custom(d)
        self.assert_unhealthy(d, 4)
        self.assertEqual(run("agent_file.py", "--project-dir", d, "--agent",
                             "perf-reviewer", "--write").returncode, 0)
        self.assert_healthy(d)
        agent_md = os.path.join(d, ".claude/agents/perf-reviewer.md")
        text = read(agent_md)
        for line in ("tools: Read, Grep, Glob\n", "model: opus\n", "name: perf-reviewer\n"):
            self.assertIn(line, text)
        with open(agent_md, "a") as fh:
            fh.write("\nUser-added paragraph.\n")
        cfg = os.path.join(d, ".cfm-workflow.yml")
        write(cfg, read(cfg).replace("tools: [Read, Grep, Glob]", "tools: [Read, Grep, Glob, Bash]"))
        self.assert_unhealthy(d, 4)
        run("agent_file.py", "--project-dir", d, "--agent", "perf-reviewer", "--write")
        text = read(agent_md)
        self.assertIn("tools: Read, Grep, Glob, Bash\n", text)
        self.assertIn("User-added paragraph", text)
        self.assert_healthy(d)

    def test_agent_file_refuses_shipped(self):
        d = self.project()
        proc = run("agent_file.py", "--project-dir", d, "--agent", "coder", "--write")
        self.assertEqual(proc.returncode, 1)

    def test_shipped_agent_understating_tools_fails(self):
        d = self.project(config=None)
        write(os.path.join(d, ".cfm-workflow.yml"),
              read(VALID).replace("tools: [Read, Write, Edit, Bash]", "tools: [Read, Grep]"))
        self.assert_unhealthy(d, 4)

    def test_shipped_agent_readonly_drift_warns(self):
        _rc, report = doctor(self.project())
        self.assertTrue(any("omits read-only" in w for w in check(report, 4)["warnings"]))

    def test_verify_full_owner(self):
        d = self.project(config=None)
        write(os.path.join(d, ".cfm-workflow.yml"),
              read(VALID).replace("owns_commands: []", "owns_commands: [verify_full]", 1))
        report = self.assert_unhealthy(d, 4)
        self.assertTrue(any("no agent may own it" in f for f in check(report, 4)["failures"]))

    def test_shared_ack_nags(self):
        # acknowledged shared ownership: healthy overall, check #4 WARN
        report = self.assert_healthy(self.project(config=fixture("shared-ack.yml")))
        c4 = check(report, 4)
        self.assertEqual(c4["status"], "WARN")
        self.assertTrue(any("acknowledged" in w and "keep nagging" in w for w in c4["warnings"]))


class Rules(ProjectCase):
    def test_disabled_reviewer_has_no_teeth(self):
        # disable 'coder' (first enabled: true; not in review_gates) and
        # point R2 at it — with spaces inside the parens
        d = self.project(config=None)
        write(os.path.join(d, ".cfm-workflow.yml"), read(VALID).replace("enabled: true", "enabled: false", 1))
        write(os.path.join(d, ".claude/rules/rules.md"),
              read(fixture("rules-valid.md")).replace("reviewer(code-reviewer)", "reviewer( coder )"))
        self.assert_unhealthy(d, 6)

    def test_compound_enforcement_accepted(self):
        d = self.project()
        write(os.path.join(d, ".claude/rules/rules.md"),
              read(fixture("rules-valid.md")).replace("reviewer(code-reviewer)", "reviewer(ghost) + lint(x)"))
        self.assert_healthy(d)

    def test_lint_without_slot_warns(self):
        d = self.project(config=None)
        write(os.path.join(d, ".cfm-workflow.yml"),
              "".join(l for l in read(VALID).splitlines(True) if not l.startswith("  lint:")))
        report = self.assert_healthy(d)
        self.assertTrue(any("R1: enforcement claims lint(...) but" in w
                            for w in check(report, 6)["warnings"]))

    def test_lint_with_slot_no_warning(self):
        _rc, report = doctor(self.project())
        self.assertFalse(any("enforcement claims lint(...) but" in w
                             for w in check(report, 6)["warnings"]))


class Secrets(ProjectCase):
    def test_env_example_with_value(self):
        d = self.project()
        write(os.path.join(d, ".env.example"), "FOO=realvalue\nBAR=\n")
        self.assert_unhealthy(d, 7)

    def test_raw_token_never_leaks(self):
        d = self.project()
        write(os.path.join(d, ".env.example"), "sk-live-FAKEFAKEFAKE\n")
        gen_settings(d, "--write")
        proc = run("doctor.py", "--project-dir", d, "--json")
        report = json.loads(proc.stdout)
        self.assertEqual(check(report, 7)["status"], "FAIL")
        self.assertNotIn("FAKEFAKEFAKE", proc.stdout)
        self.assertTrue(any("content not shown" in f for f in check(report, 7)["failures"]))

    def test_bare_env_gitignore(self):
        d = self.project()
        write(os.path.join(d, ".gitignore"), ".env\n!.env.example\n")
        write(os.path.join(d, ".env.local"), "")
        self.assert_unhealthy(d, 7)

    def test_negation_order_warns(self):
        d = self.project()
        write(os.path.join(d, ".gitignore"), "!.env.example\n.env*\n")
        write(os.path.join(d, ".env.local"), "")
        _rc, report = doctor(d)
        c7 = check(report, 7)
        self.assertEqual(c7["status"], "WARN")
        self.assertTrue(any("overridden by later rules" in w for w in c7["warnings"]))

    def test_gitignore_rule_deferred(self):
        # no .git, no .env* files, no .gitignore — check #7 must not FAIL
        d = os.path.join(self.tmp, "defer")
        for rel in ("domain/database/src", "apps/api/src", ".claude/rules", "docs"):
            os.makedirs(os.path.join(d, rel))
        write(os.path.join(d, "CLAUDE.md"), "# fixture\n")
        shutil.copy(fixture("rules-valid.md"), os.path.join(d, ".claude/rules/rules.md"))
        shutil.copy(VALID, os.path.join(d, ".cfm-workflow.yml"))
        self.assert_healthy(d)

    def test_committed_secret_instructs_rotation(self):
        d = self.project()
        git(d, "init", "-q")
        write(os.path.join(d, "server.pem"), "not-a-real-cert\n")
        git(d, "add", "server.pem")
        git(d, "commit", "-q", "-m", "fixture")
        report = self.assert_unhealthy(d, 7)
        self.assertTrue(any("server.pem" in f and "rotate" in f for f in check(report, 7)["failures"]))

    def test_stale_denies_fail(self):
        # a git level raised after the denies were written leaves the old
        # `git push:*` deny behind — the permission layer contradicts the
        # config, and the doctor must say so
        d = self.project()
        gen_settings(d, "--write")
        cfg = os.path.join(d, ".cfm-workflow.yml")
        write(cfg, read(cfg).replace("level: L0", "level: L2"))
        report = self.assert_unhealthy(d, 7, settings=False)
        self.assertTrue(any("stale deny" in f for f in check(report, 7)["failures"]))
        gen_settings(d, "--write")
        self.assert_healthy(d, settings=False)

    def test_sandbox_status_reported(self):
        d = self.project()
        _rc, report = doctor(d)
        self.assertTrue(any("sandbox off" in n for n in check(report, 7)["notes"]))
        gen_settings(d, "--sandbox", "--write")
        _rc, report = doctor(d, settings=False)
        self.assertTrue(any("sandbox OS-level denies present" in n for n in check(report, 7)["notes"]))
        # a hand-trimmed sandbox block warns
        path = os.path.join(d, ".claude/settings.json")
        settings = json.loads(read(path))
        settings["sandbox"]["filesystem"]["denyWrite"] = []
        write(path, json.dumps(settings))
        _rc, report = doctor(d, settings=False)
        self.assertTrue(any("sandbox is enabled but" in w for w in check(report, 7)["warnings"]))


class State(ProjectCase):
    def broken(self, text, name):
        d = self.project(name)
        write(os.path.join(d, ".cfm/state.json"), text)
        self.assert_unhealthy(d, 9)

    def test_orphaned_in_flight(self):
        self.broken('{"phase": {"status": "in-flight", "plan": "docs/plans/ghost.md"}}\n', "a")

    def test_unparseable(self):
        self.broken('{"phase": not json\n', "b")

    def test_non_dict(self):
        self.broken('[1, 2]\n', "c")

    def test_schema_drift(self):
        self.broken('{"version":1,"phase":{"id":"x","status":"in-flight","started":"2026-01-01T00:00:00Z"},'
                    '"cursor":{"layers":{"database":{"coder":"bogus","tests":{"written":[],"passed":[]},"gates":{}}}}}\n', "d")


class Pipeline(ProjectCase):
    def test_pre_commit_trigger_without_hook(self):
        d = self.project(config=None)
        write(os.path.join(d, ".cfm-workflow.yml"), read(VALID).replace("trigger: phase-gate", "trigger: pre-commit"))
        git(d, "init", "-q")
        self.assert_unhealthy(d, 8)

    def test_guard_self_test_reported(self):
        _rc, report = doctor(self.project())
        self.assertTrue(any("guard self-test: secret read" in n for n in check(report, 8)["notes"]))

    def test_subagent_observation(self):
        # no dispatches yet: a note. Dispatches without the marker: WARN.
        # The marker present: a note saying the layer fired for real.
        d = self.project()
        _rc, report = doctor(d)
        self.assertTrue(any("not yet observed" in n for n in check(report, 8)["notes"]))
        run("state.py", "--project-dir", d, "init", "--id", "p1", "--description", "x", "--layers", "database")
        run("state.py", "--project-dir", d, "record", "--agent", "coder", "--layer", "database",
            "--purpose", "x", "--model", "claude-sonnet-5")
        _rc, report = doctor(d, settings=False)
        self.assertTrue(any("no subagent event ever reached the guard" in w
                            for w in check(report, 8)["warnings"]))
        write(os.path.join(d, ".cfm/subagent-observed"), "{}\n")
        _rc, report = doctor(d, settings=False)
        self.assertTrue(any("subagent events observed live" in n for n in check(report, 8)["notes"]))
        self.assertEqual(check(report, 8)["status"], "PASS")


class Mode(ProjectCase):
    def test_bogus_mode_fails_schema(self):
        d = self.project(config=None)
        write(os.path.join(d, ".cfm-workflow.yml"), read(VALID) + "\nmode: bogus\n")
        report = self.assert_unhealthy(d, 1)
        self.assertTrue(any("mode: 'bogus' is not one of" in f for f in check(report, 1)["failures"]))

    def test_mode_is_a_team_setting(self):
        d = self.project()
        write(os.path.join(d, ".cfm-workflow.local.yml"), "mode: advisory\n")
        report = self.assert_unhealthy(d, 1)
        self.assertTrue(any("override of 'mode' is not permitted" in f
                            for f in check(report, 1)["failures"]))

    def test_off_is_a_string_not_a_boolean(self):
        d = self.project(config=None)
        write(os.path.join(d, ".cfm-workflow.yml"), read(VALID) + "\nmode: off\n")
        proc = run("cfm_config.py", "--project-dir", d, "--json")
        self.assertEqual(json.loads(proc.stdout)["mode"], "off")
        self.assert_healthy(d)

    def test_check_8_reports_mode_and_probes(self):
        d = self.project()
        _rc, report = doctor(d)
        notes = check(report, 8)["notes"]
        self.assertTrue(any(n.startswith("cfm mode: enforced") for n in notes))
        self.assertTrue(any("main session's product writes (Write, redirect, copy) blocked" in n
                            for n in notes))
        self.assertTrue(any("status line off" in n for n in notes))
        self.assertTrue(any("session context" in n for n in notes))
        gen_settings(d, "--write", "--statusline")
        _rc, report = doctor(d, settings=False)
        self.assertTrue(any("cfm status line on" in n for n in check(report, 8)["notes"]))
        adv = self.project("adv", config=None)
        write(os.path.join(adv, ".cfm-workflow.yml"), read(VALID) + "\nmode: advisory\n")
        report = self.assert_healthy(adv)
        notes = check(report, 8)["notes"]
        self.assertTrue(any(n.startswith("cfm mode: advisory") for n in notes))
        self.assertTrue(any("cfm mode is advisory, so the main session's product writes pass" in n
                            for n in notes))
        off = self.project("off", config=None)
        write(os.path.join(off, ".cfm-workflow.yml"), read(VALID) + "\nmode: off\n")
        report = self.assert_healthy(off)
        self.assertTrue(any(n.startswith("cfm mode: off") for n in check(report, 8)["notes"]))
