# cfm behavior gates

cfm's offline suite (`tests/run-tests.sh`, Python unittest under
`tests/test_*.py`) proves the scripts' behavior, and for the skills it
mostly asserts that files contain strings. That proves the prose is *installed*, never that it
*works*. These probes ask the other question: does a skill's text change
what the model actually does?

The design follows cfm's own standard for the conventions round, where a
rule claimed as lint-enforced is proven by writing a deliberate violation
and watching the linter bite. Same idea, aimed at cfm's own skills.

## The method

Each probe runs one task twice against the same model:

- **armed** — the skill's full text, then the task.
- **baseline** — the task alone.

Both responses go through a grader. **The baseline arm is expected to
fail.** The delta between the arms is the entire result, so a probe the
baseline also passes is reported `VOID`, not a win: it is not
discriminating, and it needs a sharper task or a sharper grader.

The armed arm measures the *skill's prose*, not the full dispatch pipeline.
A probe passing here means the text steers a model; it does not by itself
mean `/cfm:implement-phase` produced better code end to end. That is the
honest limit of a single-shot probe.

## Run it

Needs the `claude` CLI on PATH (guaranteed — cfm is Claude-Code-only) and
PyYAML. No API key, no promptfoo, no new dependency.

```bash
python3 benchmarks/run.py                          # every probe, 1 run each
python3 benchmarks/run.py --probe simplicity       # one probe
python3 benchmarks/run.py --repeat 5 --model claude-haiku-4-5-20251001
python3 benchmarks/run.py --repeat 5 --write --date 2026-09-05
```

Exit code is 1 when any probe is `FAIL` or `ERROR`; `VOID` does not fail
the run, because a non-discriminating probe is a problem with the probe,
not with cfm.

## Probes

| probe | skill under test | the behavior |
|---|---|---|
| `simplicity` | `skills/simplicity` | reaches for `<input type="date">` instead of installing a picker |
| `seams` | `skills/testing` | asserts through the public interface against an independent expected value, rather than mocking internals or recomputing |
| `red-command` | `skills/diagnose` | builds a runnable reproduction **before** naming a cause |
| `glossary` | `skills/domain-modeling` | adopts the seeded `CONTEXT.md` term over its banned synonyms |

## Graders

`graders.py` holds one pure function per probe: text in, `(passed, reason)`
out. No network, no file access, no state — which is what lets
`tests/run-tests.sh` prove the grader logic offline against
`fixtures/<probe>.{pass,fail}.txt` while only the model calls need
credentials. That split is the point: the graders are covered by the
deterministic suite, so a broken grader is caught without spending a token.

They are **heuristics over text**, and each one documents the shape it can
miss. A grader that disagrees with a human read is a grader bug: fix it in
`graders.py`, and add the transcript that fooled it to `fixtures/`.

That workflow is not hypothetical. The first run scored four correct
responses as failures across three separate grader gaps — a repro written
as a test function, a repro written as a bare script, and a glossary answer
whose only banned words were in the sentence explaining that it avoided
them. Every one is now a fixture. Suspect the grader before the skill.

## The one rule when a probe fails

Fixing a FAIL means fixing the **grader** (it misread a correct response),
the **probe** (it tested the skill outside its stated domain), or the
**skill** (its prose genuinely does not carry). Loosening a task or a
grader until the armed arm passes is none of those, and it is the exact
dishonesty the VOID verdict exists to catch. A negative result that
survives an honest fix is worth more than a green table.

## Reading results honestly

Report the measured probe deltas and nothing more. Never derive a per-repo
savings figure from them — the code cfm's agents did not write was never
written, so a live repo has no baseline to subtract from. The only real
per-repo debt number cfm produces is `scripts/debt_scan.py`, which counts
markers that actually exist.
