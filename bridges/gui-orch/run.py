#!/usr/bin/env python3
"""gui-orch commands for the GUI broker: exactly these verbs, nothing else runs.

    run.py run-ready --plan <plan-ref> --max-items <1..20> [--dry-run]  → orch conduct run --plan P --ready --max-items N
    run.py resume --run <run-id> [--retry <item-ref>]                   → orch conduct resume --run R [--retry I]
    run.py continue --run <run-id>                                      → orch conduct continue --run R
    run.py answer --run R --item I --question Q (--option ID | --text T) → orch conduct answer --run R --item I --question Q ...
    run.py release --run <run-id> --item <item-ref>                     → orch conduct release --run R --item I
    run.py gates-clear --provider <provider>                          → orch conduct gates --clear P

Every value is one argv element checked against its pattern; there is no shell, no list of items in one string (the
pieces of a plan are chosen by ``--ready``), and any other verb, flag, order or extra argument exits 2 without
running anything. The working folder is the trusted project root the broker chose. Exit code 4 of ``resume`` and
``continue`` is not a failure: the run waits for the answer to a question.
"""
from __future__ import annotations

import os
import re
import sys

from adapter import ITEM_REF, OrchError, PLAN_REF, PROVIDERS, RUN_ID, umbrella

QUESTION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
ANSWER_TEXT = re.compile(r"[^\x00-\x1f]{1,2000}")
USAGE = ("usage: run.py run-ready --plan P --max-items N [--dry-run] | run.py resume --run R [--retry I] | "
         "run.py continue --run R | run.py answer --run R --item I --question Q (--option ID | --text T) | "
         "run.py release --run R --item I | run.py gates-clear --provider P")


def fail(code: str, message: str) -> int:
    print(f"{code}: {message}", file=sys.stderr)
    return 2


def build(argv):
    """The orch arguments for ``argv`` (after the verb checks), or an error text."""
    if len(argv) == 3 and argv[:2] == ["gates-clear", "--provider"]:
        if argv[2] not in PROVIDERS:
            return None, "BAD_PROVIDER: provider must be claude-code, codex or grok"
        return ["conduct", "gates", "--clear", argv[2]], None
    if argv[:1] == ["run-ready"] and argv[1:2] == ["--plan"] and argv[3:4] == ["--max-items"] \
            and len(argv) in (5, 6) and argv[5:] in ([], ["--dry-run"]):
        plan, count = argv[2], argv[4]
        if not PLAN_REF.match(plan):
            return None, "BAD_PLAN: --plan is not a plan reference"
        if not (count.isascii() and count.isdigit() and 1 <= int(count) <= 20):
            return None, "BAD_MAX_ITEMS: --max-items is an integer from 1 to 20"
        return ["conduct", "run", "--plan", plan, "--ready", "--max-items", str(int(count)), *argv[5:]], None
    if len(argv) == 3 and argv[0] == "resume" and argv[1] == "--run":
        if not RUN_ID.match(argv[2]):
            return None, "BAD_RUN: --run is not a conductor run id"
        return ["conduct", "resume", "--run", argv[2]], None
    if len(argv) == 5 and argv[0] == "resume" and argv[1] == "--run" and argv[3] == "--retry":
        if not RUN_ID.match(argv[2]):
            return None, "BAD_RUN: --run is not a conductor run id"
        if not ITEM_REF.match(argv[4]):
            return None, "BAD_ITEM: --retry is not an item reference"
        return ["conduct", "resume", "--run", argv[2], "--retry", argv[4]], None
    if len(argv) == 3 and argv[0] == "continue" and argv[1] == "--run":
        if not RUN_ID.match(argv[2]):
            return None, "BAD_RUN: --run is not a conductor run id"
        return ["conduct", "continue", "--run", argv[2]], None
    if len(argv) == 9 and argv[0] == "answer" and argv[1:7:2] == ["--run", "--item", "--question"] \
            and argv[7] in ("--option", "--text"):
        run, item, question, kind, value = argv[2], argv[4], argv[6], argv[7], argv[8]
        if not RUN_ID.match(run):
            return None, "BAD_RUN: --run is not a conductor run id"
        if not ITEM_REF.match(item):
            return None, "BAD_ITEM: --item is not an item reference"
        if not QUESTION_ID.fullmatch(question):
            return None, "BAD_QUESTION: --question is not a question id"
        if not (QUESTION_ID if kind == "--option" else ANSWER_TEXT).fullmatch(value):
            return None, f"BAD_ANSWER: {kind} is not a valid answer"
        # a free text may start with "-": the ``=`` form keeps it one value for the option parser of orch
        chosen = [f"--text={value}"] if kind == "--text" else [kind, value]
        return ["conduct", "answer", "--run", run, "--item", item, "--question", question, *chosen], None
    if len(argv) == 5 and argv[0] == "release" and argv[1] == "--run" and argv[3] == "--item":
        if not RUN_ID.match(argv[2]):
            return None, "BAD_RUN: --run is not a conductor run id"
        if not ITEM_REF.match(argv[4]):
            return None, "BAD_ITEM: --item is not an item reference"
        return ["conduct", "release", "--run", argv[2], "--item", argv[4]], None
    return None, "USAGE: " + USAGE


def main(argv) -> int:
    args, problem = build(argv)
    if args is None:
        code, _, message = problem.partition(": ")
        return fail(code, message)
    command = [umbrella(), "orch", *args]
    sys.stdout.flush()
    os.execv(command[0], command)
    return 1  # not reached


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except OrchError as error:
        print(f"{error.code}: {error.message}", file=sys.stderr)
        sys.exit(1)
