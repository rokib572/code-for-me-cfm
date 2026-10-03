"""The graders are the offline half of benchmarks/: pure text ->
(pass, reason). Proving them here means a broken grader is caught without
a model call. Every probe must declare a baseline it expects to FAIL, and
the armed-only material must never leak into the baseline arm."""

from __future__ import annotations

import glob
import importlib.util
import os
import unittest

import yaml

from helpers import ROOT, read

BENCH = os.path.join(ROOT, "benchmarks")


def load_runner():
    spec = importlib.util.spec_from_file_location("cfm_bench_run", os.path.join(BENCH, "run.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Graders(unittest.TestCase):
    def setUp(self):
        import sys
        sys.path.insert(0, BENCH)
        from graders import GRADERS
        self.graders = GRADERS
        self.probes = sorted(glob.glob(os.path.join(BENCH, "probes", "*.yml")))
        self.assertTrue(self.probes)

    def test_fixtures_grade_as_labelled(self):
        # <probe>.pass*.txt grades True, <probe>.fail*.txt grades False
        for probe, fn in sorted(self.graders.items()):
            for arm, want in (("pass", True), ("fail", False)):
                found = sorted(glob.glob(os.path.join(BENCH, "fixtures", f"{probe}.{arm}*.txt")))
                self.assertTrue(found, f"no {arm} fixture for grader '{probe}'")
                for path in found:
                    got, reason = fn(read(path))
                    self.assertIs(got, want, f"{probe} on {os.path.basename(path)}: {reason}")

    def test_probes_reference_graders_and_skills(self):
        named = set()
        for path in self.probes:
            p = yaml.safe_load(read(path))
            named.add(p.get("grader"))
            self.assertIn(p.get("grader"), self.graders, path)
            self.assertTrue(os.path.isfile(os.path.join(ROOT, p.get("skill", ""))), path)
            self.assertEqual((p.get("expect") or {}).get("baseline"), "fail", path)
        self.assertEqual(set(self.graders) - named, set(), "orphan graders")

    def test_arms_differ_and_baseline_is_clean(self):
        mod = load_runner()
        for path in self.probes:
            p = yaml.safe_load(read(path))
            armed, baseline = mod.build_prompt(p, True), mod.build_prompt(p, False)
            self.assertNotEqual(armed, baseline, path)
            self.assertIn(p["task"].strip()[:40], baseline, path)
            for extra in (p.get("context"), "Apply the following engineering discipline"):
                if extra:
                    self.assertNotIn(extra.strip()[:40], baseline, f"{path}: armed-only material leaked")
