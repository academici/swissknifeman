#!/usr/bin/env python3
"""gui-orch commands for the GUI broker: exactly four verbs, nothing else runs.

    run.py run-ready --plan <plan-ref> --max-items <1..20> [--dry-run]  → orch conduct run --plan P --ready --max-items N
    run.py resume --run <run-id>                                        → orch conduct resume --run R
    run.py release --run <run-id> --item <item-ref>                     → orch conduct release --run R --item I
    run.py gates-clear --provider <provider>                          → orch conduct gates --clear P

Every value is one argv element checked against its pattern; there is no shell, no list of items in one string (the
pieces of a plan are chosen by ``--ready``), and any other verb, flag, order or extra argument exits 2 without
running anything. The working folder is the trusted project root the broker chose.
"""
from __future__ import annotations

import os
import sys

from adapter import ITEM_REF, OrchError, PLAN_REF, PROVIDERS, RUN_ID, umbrella

USAGE = ("usage: run.py run-ready --plan P --max-items N [--dry-run] | run.py resume --run R | "
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
