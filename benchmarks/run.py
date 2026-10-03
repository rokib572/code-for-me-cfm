#!/usr/bin/env python3
"""cfm behavior gates — does a skill's prose change what the model does?

cfm's offline suite (tests/run-tests.sh) mostly asserts that files contain strings. This asks the
question those cannot: run the same task twice, once with a skill's text in
the prompt and once without, and grade both. The armed arm should pass, the
BASELINE ARM SHOULD FAIL. A probe both arms pass is measuring nothing, and
the runner says so rather than reporting a win.

Opt-in and run by hand: it makes real model calls. tests/run-tests.sh stays
offline and covers the graders against fixtures instead.

Usage:
  python3 benchmarks/run.py                     # every probe
  python3 benchmarks/run.py --probe simplicity  # one
  python3 benchmarks/run.py --repeat 3 --write  # 3 runs each, save a report
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from graders import GRADERS  # noqa: E402

try:
    import yaml
except ImportError:
    yaml = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
TIMEOUT = 300


def strip_frontmatter(text):
    """Drop the YAML block; the probe tests the discipline, not the manifest."""
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    return text[end + 4:].lstrip("\n") if end != -1 else text


# `claude -p` is an agent, not a completion endpoint: without this it goes
# looking at the filesystem and answers "which repo did you mean?" instead of
# the question. Identical in both arms, so the delta stays the skill text.
FRAMING = (
    "Answer the task below directly and completely from the information "
    "given. It is self-contained: do not read files, search the filesystem, "
    "or ask a clarifying question. Show the code.\n\n### Task\n\n"
)


def build_prompt(probe, armed):
    """Baseline gets the task. Armed gets the same task behind the skill text.

    The delta is exactly the skill's prose, which is the claim under test.
    """
    parts = []
    if armed:
        skill = os.path.join(ROOT, probe["skill"])
        with open(skill, encoding="utf-8") as fh:
            parts.append(
                "Apply the following engineering discipline when you answer.\n\n"
                + strip_frontmatter(fh.read())
                + "\n---\n"
            )
        # Armed-only, and that is the whole point of the glossary probe: cfm's
        # claim is that a glossary in the brief makes cold-started agents name
        # things the same way. Handing it to the baseline too made the control
        # not a control, and the probe went VOID because both arms complied.
        if probe.get("context"):
            parts.append(
                "The project glossary (CONTEXT.md) defines:\n\n"
                + probe["context"] + "\n---\n"
            )
    parts.append(FRAMING + probe["task"])
    return "\n".join(parts)


def ask(prompt, model=None):
    # Prompt goes on stdin, never argv: a skill body opens with `---`, which
    # argv parses as a flag, and prompts outgrow argv limits anyway.
    cmd = ["claude", "-p"]
    if model:
        cmd += ["--model", model]
    # A neutral empty cwd: run inside the cfm repo and the agent reads its
    # CLAUDE.md and skills, which contaminates the BASELINE arm with the very
    # discipline it is the control for.
    try:
        with tempfile.TemporaryDirectory(prefix="cfm-probe-") as sandbox:
            done = subprocess.run(
                cmd, input=prompt, capture_output=True, text=True,
                timeout=TIMEOUT, cwd=sandbox,
            )
    except subprocess.TimeoutExpired:
        return None, f"timed out after {TIMEOUT}s"
    if done.returncode != 0:
        return None, (done.stderr or "").strip()[:400] or f"exit {done.returncode}"
    return done.stdout, None


def run_probe(probe, repeat, model):
    grader = GRADERS[probe["grader"]]
    arms = {}
    for arm, armed in (("armed", True), ("baseline", False)):
        prompt = build_prompt(probe, armed)
        runs = []
        for _ in range(repeat):
            text, error = ask(prompt, model)
            if error:
                runs.append({"passed": None, "reason": f"run failed: {error}"})
                continue
            passed, reason = grader(text)
            runs.append({"passed": passed, "reason": reason})
        graded = [r for r in runs if r["passed"] is not None]
        arms[arm] = {
            "runs": runs,
            "passed": sum(1 for r in graded if r["passed"]),
            "graded": len(graded),
            "expected": probe["expect"][arm],
        }
    return arms


def verdict(arms):
    """The delta is the result, so a probe both arms pass proves nothing."""
    armed, baseline = arms["armed"], arms["baseline"]
    if not armed["graded"] or not baseline["graded"]:
        return "ERROR", "a run failed; no verdict"
    armed_rate = armed["passed"] / armed["graded"]
    baseline_rate = baseline["passed"] / baseline["graded"]
    if baseline_rate == 1.0:
        return "VOID", (
            "the baseline passed too — this probe does not discriminate, so it "
            "measures nothing. Sharpen the task or the grader."
        )
    if armed_rate > baseline_rate:
        return "PASS", f"armed {armed_rate:.0%} vs baseline {baseline_rate:.0%}"
    return "FAIL", (
        f"armed {armed_rate:.0%} vs baseline {baseline_rate:.0%} — the skill's "
        "prose did not change the behavior it claims to change"
    )


def report(results, model, repeat):
    lines = [
        "# cfm behavior gates",
        "",
        f"model: `{model or 'default'}` · runs per arm: {repeat}",
        "",
        "Each probe runs one task twice: **armed** (the skill's text in the",
        "prompt) and **baseline** (the task alone). The delta is the result.",
        "A probe the baseline also passes is VOID, not a win.",
        "",
        "| probe | verdict | armed | baseline | note |",
        "|---|---|--:|--:|---|",
    ]
    for name, arms in results.items():
        status, note = verdict(arms)
        a, b = arms["armed"], arms["baseline"]
        lines.append(
            f"| {name} | **{status}** | {a['passed']}/{a['graded']} | "
            f"{b['passed']}/{b['graded']} | {note} |"
        )
    lines += [
        "",
        "## What a verdict means",
        "",
        "- **PASS** — the armed arm beat the baseline. The prose moved the model.",
        "- **FAIL** — no delta. Either the prose does not carry in a single-shot",
        "  prompt, or this model already resists the behavior.",
        "- **VOID** — the baseline passed too, so the probe is not discriminating",
        "  and proves nothing either way. The model may simply be good at this",
        "  task already, which is a fine reason to retire or sharpen the probe.",
        "",
        "## Reading this honestly",
        "",
        "**A FAIL is not proof the skill is useless in cfm.** These probes paste",
        "a skill's text into one prompt and grade one reply. That is the weakest",
        "form of every claim, and it is not how cfm uses the text: in the real",
        "workflow the orchestrator enforces ordering through phase gates and a",
        "state file, dispatches the discipline in a scoped brief, and re-runs a",
        "failed gate. A skill can fail here and still hold there. What this",
        "harness rules out is the opposite claim, that the prose alone is",
        "sufficient.",
        "",
        "These are measured probe deltas and nothing more. They do not imply a",
        "per-repo figure: the version cfm's agents did not build was never",
        "written, so there is no baseline in a live repo to subtract from.",
        "The graders are text heuristics with stated blind spots (see",
        "`graders.py`); a grader disagreeing with a human read is a grader bug,",
        "so fix it there and add the transcript that fooled it to `fixtures/`.",
        "",
        "Run counts this low are noisy. Treat a single run as a smoke test and",
        "raise `--repeat` before drawing a conclusion from any row.",
        "",
    ]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="cfm behavior gates")
    parser.add_argument("--probe", help="run one probe by name")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--model", help="model id passed to claude -p")
    parser.add_argument("--write", action="store_true",
                        help="save the report under benchmarks/results/")
    parser.add_argument("--date", help="report date (YYYY-MM-DD) for --write")
    args = parser.parse_args(argv)

    if yaml is None:
        print("PyYAML is required: pip install pyyaml", file=sys.stderr)
        return 2
    if shutil.which("claude") is None:
        print("SKIP: the `claude` CLI is not on PATH — behavior gates need it "
              "to run either arm.", file=sys.stderr)
        return 0

    probes = {}
    for path in sorted(glob.glob(os.path.join(HERE, "probes", "*.yml"))):
        with open(path, encoding="utf-8") as fh:
            probe = yaml.safe_load(fh)
        if probe["grader"] not in GRADERS:
            print(f"unknown grader '{probe['grader']}' in {path}", file=sys.stderr)
            return 2
        probes[probe["name"]] = probe

    if args.probe:
        if args.probe not in probes:
            print(f"no such probe: {args.probe} (have: {', '.join(probes)})",
                  file=sys.stderr)
            return 2
        probes = {args.probe: probes[args.probe]}

    results = {}
    for name, probe in probes.items():
        print(f"running {name}...", file=sys.stderr)
        results[name] = run_probe(probe, args.repeat, args.model)

    text = report(results, args.model, args.repeat)
    print(text)

    if args.write:
        if not args.date:
            print("--write needs --date YYYY-MM-DD", file=sys.stderr)
            return 2
        slug = args.probe or "all"
        out = os.path.join(HERE, "results", f"{args.date}-{slug}.md")
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"\nwrote {os.path.relpath(out, ROOT)}", file=sys.stderr)

    statuses = [verdict(a)[0] for a in results.values()]
    return 1 if ("FAIL" in statuses or "ERROR" in statuses) else 0


if __name__ == "__main__":
    sys.exit(main())
