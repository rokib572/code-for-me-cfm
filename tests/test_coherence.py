"""Plugin self-coherence: the roster, the agent files, the skills and the
references must agree with each other and with the scripts. These are
string assertions on shipped files — they prove the prose is installed,
never that it works (benchmarks/ asks that question)."""

from __future__ import annotations

import glob
import os
import re
import unittest

import yaml

from helpers import ROOT, read
import cfm_config

REFERENCE_SKILLS = {"testing", "domain-modeling", "simplicity"}


def skill(name):
    return read(os.path.join(ROOT, "skills", name, "SKILL.md"))


def agent(name):
    return read(os.path.join(ROOT, "agents", f"{name}.md"))


class Roster(unittest.TestCase):
    def setUp(self):
        self.roster = yaml.safe_load(read(os.path.join(ROOT, "templates", "roster.yml")))

    def test_fields_and_single_owner(self):
        required = {"enabled", "purpose", "model", "tier", "autonomy", "tools",
                    "owns_commands", "layers"}
        owners = {}
        for name, entry in self.roster.items():
            self.assertEqual(required - set(entry), set(), f"roster {name}: missing fields")
            for slot in entry.get("owns_commands") or []:
                owners.setdefault(slot, []).append(name)
        shared = {s: o for s, o in owners.items() if len(o) > 1}
        self.assertEqual(shared, {})
        self.assertFalse({"Write", "Edit"} & set(self.roster["mechanical-gate"]["tools"]),
                         "mechanical-gate must have no write tools (by design)")

    def test_agent_files_match_roster(self):
        files = {os.path.basename(p)[:-3] for p in glob.glob(os.path.join(ROOT, "agents", "*.md"))}
        self.assertEqual(files, set(self.roster))
        for name in sorted(files):
            text = agent(name)
            self.assertTrue(text.startswith("---"), f"{name}: missing frontmatter")
            fm = yaml.safe_load(text.split("---")[1])
            self.assertEqual(fm.get("name"), name)
            fm_tools = {t.strip() for t in str(fm.get("tools", "")).split(",") if t.strip()}
            self.assertEqual(fm_tools, set(self.roster[name]["tools"]), name)
            self.assertEqual(fm.get("model"), self.roster[name]["model"], name)
            self.assertIn(".cfm-workflow.yml", text, f"{name}: missing read-config-first")
            self.assertIn("secret_globs", text, f"{name}: missing secrets discipline")


class Skills(unittest.TestCase):
    def test_frontmatter_and_step0_gate(self):
        for path in sorted(glob.glob(os.path.join(ROOT, "skills", "*", "SKILL.md"))):
            name = os.path.basename(os.path.dirname(path))
            text = read(path)
            self.assertTrue(text.startswith("---") and "description:" in text.split("---")[1], name)
            if name in REFERENCE_SKILLS:
                # pure discipline read by Bash-less agents: no step-0 gate
                self.assertNotIn("require-claude-code.sh", text, name)
            else:
                self.assertIn("require-claude-code.sh", text, f"{name}: missing step-0 gate")

    def test_help_lists_every_command(self):
        # /cfm:help renders a fixed table; a new command missing from it
        # (or a removed one left in) is drift
        listed = set(re.findall(r"^\| `/cfm:([a-z-]+)", skill("help"), re.M))
        commands = {os.path.basename(os.path.dirname(p))
                    for p in glob.glob(os.path.join(ROOT, "skills", "*", "SKILL.md"))} - REFERENCE_SKILLS
        self.assertEqual(listed, commands)

    def test_redaction_single_source(self):
        for rel in ("skills/plan/SKILL.md", "skills/create-task/SKILL.md",
                    "skills/implement-phase/SKILL.md", "skills/connect-tracker/SKILL.md",
                    "skills/diagnose/SKILL.md", "CONNECTORS.md"):
            text = read(os.path.join(ROOT, rel))
            for marker in ("AKIA", "ghp_"):
                self.assertNotIn(marker, text, f"{rel}: inline redaction pattern")
            self.assertIn("redact.py", text, rel)

    def test_routes(self):
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "skills/add-agent/SKILL.md")))
        configure, init = skill("configure"), skill("init")
        self.assertIn("add-agent", configure)
        self.assertNotIn("guided flow — name", configure)
        self.assertIn("add-agent", init)
        conv = os.path.join(ROOT, "skills/init/references/conventions-round.md")
        self.assertTrue(os.path.isfile(conv))
        for text in (init, configure):
            self.assertIn("conventions-round", text)
            self.assertNotIn("Symbol naming", text)
        conv_round = read(conv)
        for marker in ("Prove the lint teeth", "mechanical-gate", "coder"):
            self.assertIn(marker, conv_round)
        self.assertIn("demote", conv_round.lower())
        scaf = read(os.path.join(ROOT, "skills/init/references/scaffold.md"))
        self.assertIn("2.5", scaf)
        self.assertIn("Prove the lint teeth", scaf)
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "skills/connect-tracker/SKILL.md")))
        for name in ("plan", "configure"):
            self.assertIn("connect-tracker", skill(name))
            self.assertNotIn("tracker-shaped", skill(name))

    def test_review_command_name(self):
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "skills/code-review/SKILL.md")))
        self.assertFalse(os.path.isdir(os.path.join(ROOT, "skills", "review")))
        stale = re.compile(r"\bcfm" ":review\\b")  # split so this file never self-matches
        for dirpath, dirnames, filenames in os.walk(ROOT):
            dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__")]
            for fn in filenames:
                path = os.path.join(dirpath, fn)
                try:
                    text = read(path)
                except (OSError, UnicodeDecodeError):
                    continue
                rel = os.path.relpath(path, ROOT)
                self.assertFalse(stale.search(text) or "skills/" "review/" in text,
                                 f"{rel}: stale review-command reference")

    def test_craft_references(self):
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "skills/testing/SKILL.md")))
        for text, rel in ((skill("plan"), "plan"), (skill("implement-phase"), "implement-phase"),
                          (agent("e2e-test"), "e2e-test"), (agent("coder"), "coder")):
            self.assertIn("seam", text.lower(), rel)
        for name in ("e2e-test", "coder"):
            self.assertIn("skills/testing/SKILL.md", agent(name))
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "skills/domain-modeling/SKILL.md")))
        for text, rel in ((skill("implement-phase"), "implement-phase"), (skill("code-review"), "code-review"),
                          (agent("code-reviewer"), "code-reviewer"), (agent("architect"), "architect")):
            self.assertIn("context_file", text, rel)
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "skills/simplicity/SKILL.md")))
        for name in ("coder", "ui-design"):
            self.assertIn("skills/simplicity/SKILL.md", agent(name))
        self.assertIn("YAGNI pass", skill("plan"))
        self.assertIn("Lean already. Ship.", agent("simplicity-check"))
        self.assertIn("net: -", agent("simplicity-check"))

    def test_debt_and_diagnose(self):
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "scripts/debt_scan.py")))
        for name in ("status", "implement-phase"):
            self.assertIn("debt_scan.py", skill(name))
        diag = skill("diagnose")
        self.assertIn("No red command, no phase 2", diag)
        self.assertIn("skills/testing/SKILL.md", diag)
        # diagnose ends at the finding: it asks whether to plan a fix, never applies one
        for marker in ("AskUserQuestion", "complete --gates plan-fix", "`cfm:plan`",
                       "Never applies a fix, and never dispatches the coder, e2e-test, or any"):
            self.assertIn(marker, diag, marker)
        for marker in ("Dispatch the **coder** with the fix", "review pipeline", "review_gates",
                       "Dispatch **e2e-test**"):
            self.assertNotIn(marker, diag, marker)
        self.assertIn("diagnose-<slug>", skill("plan"))

    def test_plan_mode_gate(self):
        for name, extra in (("plan", ()), ("implement-phase", ("implement.plan_gate",))):
            text = skill(name)
            for marker in ("EnterPlanMode", "ExitPlanMode") + extra:
                self.assertIn(marker, text, name)

    def test_one_state_writer(self):
        for name in ("implement-phase", "diagnose", "status", "plan", "init",
                     "connect-tracker", "create-task", "code-review"):
            self.assertIn("scripts/state.py", skill(name), name)
        hand_written = ("Write of the full JSON", "UPDATE the entry's", "record it in\n  `.cfm/state.json`")
        for path in sorted(glob.glob(os.path.join(ROOT, "skills", "*", "SKILL.md"))
                           + glob.glob(os.path.join(ROOT, "skills", "*", "references", "*.md"))):
            text = read(path)
            for marker in hand_written:
                self.assertNotIn(marker, text, os.path.relpath(path, ROOT))


class Templates(unittest.TestCase):
    def test_pre_commit_glob_copies_in_sync(self):
        # templates/pre-commit.sh runs from .git/hooks/ where cfm_config does
        # not import, so it carries the default globs twice; both copies
        # must equal cfm_config.DEFAULT_SECRET_GLOBS
        hook = read(os.path.join(ROOT, "templates", "pre-commit.sh"))
        match = re.search(r"globs = \[(.*?)\]", hook, re.S)
        py_copy = [g.strip().strip('"') for g in match.group(1).replace("\n", " ").split(",") if g.strip()]
        self.assertEqual(py_copy, cfm_config.DEFAULT_SECRET_GLOBS)
        match = re.search(r"case \"\$base\" in\s*\n\s*([^\n]*?)\)", hook)
        expected = [g[3:] if g.startswith("**/") else g for g in cfm_config.DEFAULT_SECRET_GLOBS]
        self.assertEqual(match.group(1).split("|"), expected)

    def test_stop_hook_recipe_matches_skill(self):
        # the hash recipe is defined ONCE in on_stop_review.sh; the skill
        # must carry the byte-identical copy
        script = read(os.path.join(ROOT, "scripts", "on_stop_review.sh"))
        recipe = re.search(r'^hash="\$\(cd "\$PROJECT_DIR" && (.*) \| awk', script, re.M).group(1)
        self.assertTrue(recipe)
        self.assertIn(recipe, skill("code-review"))

    def test_offline_suite_never_calls_the_model(self):
        # the suite may IMPORT benchmarks/run.py (to check arm isolation)
        # but never execute it or call an entry point that makes model calls
        for path in glob.glob(os.path.join(ROOT, "tests", "*.py")) + [
                os.path.join(ROOT, "tests", "run-tests.sh")]:
            text = read(path)
            rel = os.path.relpath(path, ROOT)
            self.assertIsNone(re.search(r"(python3?|bash|sh)[^\n]*benchmarks/run\.py", text), rel)
            self.assertIsNone(re.search(r"^[^#\n]*mod\.(ask|run_probe|main)\(", text, re.M), rel)


class CfmMode(unittest.TestCase):
    def test_routes_name_shipped_skills(self):
        import session_context
        skills = {os.path.basename(os.path.dirname(p))
                  for p in glob.glob(os.path.join(ROOT, "skills", "*", "SKILL.md"))}
        for _shape, name in session_context.ROUTES:
            self.assertIn(name, skills, f"session context routes to /cfm:{name}, which does not exist")
            self.assertNotIn(name, REFERENCE_SKILLS, f"/cfm:{name} is model-invoked, not a command")
        self.assertIn("mode", skills)

    def test_hooks_json_wires_every_event(self):
        import json
        hooks = json.loads(read(os.path.join(ROOT, "hooks", "hooks.json")))["hooks"]
        commands = {event: [h["command"] for entry in entries for h in entry["hooks"]]
                    for event, entries in hooks.items()}
        self.assertEqual(set(commands), {"SessionStart", "UserPromptSubmit", "PreToolUse", "Stop"})
        self.assertTrue(any("session_context.sh SessionStart" in c for c in commands["SessionStart"]))
        self.assertTrue(any("session_context.sh UserPromptSubmit" in c
                            for c in commands["UserPromptSubmit"]))
        for script in ("session_context.sh", "statusline.sh", "guard.sh", "on_stop_review.sh"):
            self.assertTrue(os.access(os.path.join(ROOT, "scripts", script), os.X_OK), script)

    def test_mode_prose_installed(self):
        for name in ("implement-phase", "diagnose", "init"):
            self.assertIn("cfm mode", skill(name), f"{name}: orchestrator doctrine lacks the guard's teeth")
        self.assertIn("mode", skill("configure"))
        self.assertIn("**Mode**", skill("status"))
        mode = skill("mode")
        for value in cfm_config.MODES:
            self.assertIn(f"`{value}`", mode)
        self.assertIn("never in `.cfm-workflow.local.yml`", mode)
        self.assertNotIn("mode", cfm_config.LOCAL_OVERRIDE_ALLOWLIST)
