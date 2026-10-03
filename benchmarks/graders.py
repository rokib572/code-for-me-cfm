#!/usr/bin/env python3
"""cfm behavior graders — one pure function per probe.

Each grader takes a response transcript and returns (passed, reason). No
network, no file access, no state: that is what lets tests/run-tests.sh
prove the grader logic offline while only the model calls need credentials.

These are HEURISTICS over text, not ground truth. Each one is tuned to
separate an armed response from a baseline response on the specific
behavior its probe targets, and each states the failure mode it can miss.
A grader disagreeing with a human read is a grader bug — fix it here, and
add the transcript that fooled it to the fixtures.
"""

from __future__ import annotations

import re

# Date-picker libraries an over-building answer reaches for instead of the
# native element. Matched as imports/installs so prose naming one ("you
# could use flatpickr, but") does not trip the grader.
PICKER_LIBS = r"(flatpickr|react-datepicker|air-?datepicker|pikaday|vuejs-datepicker|@mui/x-date-pickers|antd/.*DatePicker)"
INSTALL_RE = re.compile(
    r"(npm i(nstall)?|yarn add|pnpm add|bun add|pip install)\s+[^\n]*" + PICKER_LIBS,
    re.I,
)
IMPORT_RE = re.compile(
    r"(import .*from\s*['\"][^'\"]*" + PICKER_LIBS + r"|require\(\s*['\"][^'\"]*" + PICKER_LIBS + r")",
    re.I,
)
NATIVE_DATE_RE = re.compile(r"""type\s*=\s*['"]date['"]""", re.I)


def grade_simplicity(text):
    """Did it reach for the native element instead of building a picker?

    Misses: an answer that writes a hand-rolled calendar without importing
    anything and without a native input. The no-native check below catches
    the common shape of that, not every shape.
    """
    if INSTALL_RE.search(text) or IMPORT_RE.search(text):
        return False, "pulled in a date-picker dependency"
    if not NATIVE_DATE_RE.search(text):
        return False, "no native date input; built something instead"
    return True, "used the native date input, no dependency"


MOCK_RE = re.compile(
    r"(mock\.patch|@patch\b|jest\.mock|vi\.mock|sinon\.stub|monkeypatch\.setattr|unittest\.mock)",
    re.I,
)
# A tautological assertion recomputes the expected value with the same
# expression the implementation uses, instead of naming an independent one.
TAUTOLOGY_RE = re.compile(
    r"(assert\w*\s*\(?\s*[\w.]+\((?P<args>[^)]*)\)\s*(==|,)\s*[^)\n]*\bsum\s*\(|"
    r"toBe\(\s*[a-z_]\w*\s*[-+*/]\s*[a-z_]\w*\s*\))",
    re.I,
)
LITERAL_EXPECTED_RE = re.compile(
    r"(assert\w*[^\n]*==\s*-?\d+(\.\d+)?|toBe\(\s*-?\d+(\.\d+)?\s*\)|"
    r"toEqual\(\s*-?\d+(\.\d+)?\s*\)|assert\w*\([^,\n]+,\s*-?\d+(\.\d+)?\s*\))"
)


def grade_seams(text):
    """Did it assert through the public interface with independent values?

    Misses: a test that reaches past the interface without a named mocking
    library (hand-rolled fake, direct attribute poke).
    """
    if MOCK_RE.search(text):
        return False, "mocked an internal collaborator instead of asserting through the interface"
    if TAUTOLOGY_RE.search(text):
        return False, "expected value recomputed the way the code computes it"
    if not LITERAL_EXPECTED_RE.search(text):
        return False, "no independent expected value (no known-good literal asserted)"
    return True, "asserted through the interface against a literal expected value"


# Anything that can actually go red on the bug. A shell invocation is one
# shape; a failing test or a bare assert is another, and the discipline lists
# "failing test" as the FIRST way to build a loop — so a grader that only
# accepted shell commands scored a correct answer as wrong.
COMMAND_RE = re.compile(
    r"((^|\n)\s*(\$|>)?\s*(pytest|python3?|node|npm (run |test)|pnpm |yarn |go test|curl|"
    r"cargo test|jest|vitest|(?:ba)?sh |\./)\S*"
    r"|(^|\n)\s*def test_\w*\s*\("
    r"|(^|\n)\s*(it|test)\s*\(\s*['\"]"
    r"|(^|\n)\s*assert\b)",
    re.I | re.M,
)
# Naming a cause. Ordering against the first command is what the probe tests.
HYPOTHESIS_RE = re.compile(
    r"(root cause|the (bug|problem|issue) is|this (is|happens) because|caused by|"
    r"the culprit|likely cause|probably (because|due)|it fails because)",
    re.I,
)


# A fenced block of runnable script is a reproduction too, even with no test
# harness and no shell line around it. Requiring a recognised runner scored
# three correct answers wrong before this existed.
SCRIPT_BLOCK_RE = re.compile(r"```(?:py|python|js|javascript|sh|bash)?\r?\n(.*?)```", re.S)
EXECUTABLE_RE = re.compile(r"^\s*[\w.\[\]]+\s*=\s*[^=\n]+\(|^\s*\w+\(", re.M)


def first_repro(text):
    """Offset of the earliest thing that could be run, or None."""
    offsets = []
    match = COMMAND_RE.search(text)
    if match:
        offsets.append(match.start())
    for block in SCRIPT_BLOCK_RE.finditer(text):
        body = block.group(1)
        # A snippet merely quoting the buggy source is not a reproduction; a
        # block that constructs something and calls it is.
        if EXECUTABLE_RE.search(body) and "def " + "parse" not in body[:40]:
            offsets.append(block.start())
            break
    return min(offsets) if offsets else None


def grade_red_command(text):
    """Did it build a runnable reproduction BEFORE naming a cause?

    Ordering is the whole test: a response may hypothesise freely once a red
    command exists. Misses: the skill's stricter bar is a command ALREADY RUN
    with its output shown, and this grader accepts one merely written. A
    hand-simulated trace in comments therefore still scores as a repro.
    """
    repro = first_repro(text)
    hypothesis = HYPOTHESIS_RE.search(text)
    if repro is None:
        return False, "no runnable reproduction anywhere in the response"
    if hypothesis and hypothesis.start() < repro:
        return False, "named a cause before building a reproduction"
    return True, "built a reproduction before naming any cause"


GLOSSARY_TERM = "Order"
GLOSSARY_BANNED = ("purchase", "transaction", "basket")
FENCE_RE = re.compile(r"```[a-zA-Z0-9_+-]*\r?\n(.*?)```", re.S)


def code_only(text):
    """The fenced blocks, or the whole text when nothing is fenced.

    Naming is what the glossary governs, so the grader judges the code. Prose
    is not just noise here, it actively inverts the signal: a response that
    correctly explains "I used Order rather than purchase, transaction or
    basket" names every banned word while doing exactly the right thing.
    """
    blocks = FENCE_RE.findall(text)
    return "\n".join(blocks) if blocks else text


def grade_glossary(text):
    """Did it adopt the seeded glossary's term over the banned synonyms?

    Misses: a banned synonym used as a string literal or comment inside a
    code block, which still counts against the response here.
    """
    code = code_only(text)
    if not re.search(r"\b" + GLOSSARY_TERM + r"s?\b", code, re.I):
        return False, f"code never uses the glossary term '{GLOSSARY_TERM}'"
    used = [w for w in GLOSSARY_BANNED if re.search(r"\b" + w + r"s?\b", code, re.I)]
    if used:
        return False, f"code uses glossary-banned synonym(s): {', '.join(used)}"
    return True, f"code names things '{GLOSSARY_TERM}' and avoids every banned synonym"


GRADERS = {
    "simplicity": grade_simplicity,
    "seams": grade_seams,
    "red-command": grade_red_command,
    "glossary": grade_glossary,
}
