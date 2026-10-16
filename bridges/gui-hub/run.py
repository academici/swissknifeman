#!/usr/bin/env python3
"""gui-hub commands for the GUI broker: exactly two verbs, nothing else runs.

    run.py doctor                    → swissknifeman doctor
    run.py sync <cap> [--dry-run]    → swissknifeman hub sync --project <maind id> --only <cap> [--dry-run]

The project is the working folder the broker chose (a trusted project root); its maind id is the fleet project with
the same real path. A cap outside the allowlist, another verb or extra arguments exit 2 without running anything.
"""
from __future__ import annotations

import os
import sys

from adapter import CAPS, HubError, find_project, hub_json, umbrella

USAGE = "usage: run.py doctor | run.py sync <cap> [--dry-run]"


def fail(code: str, message: str) -> int:
    print(f"{code}: {message}", file=sys.stderr)
    return 2


def main(argv) -> int:
    if argv == ["doctor"]:
        command = [umbrella(), "doctor"]
    elif len(argv) in (2, 3) and argv[0] == "sync" and argv[2:] in ([], ["--dry-run"]):
        cap = argv[1]
        if cap not in CAPS:
            return fail("UNKNOWN_CAP", f"{cap!r} is not one of {', '.join(CAPS)}")
        project = find_project(hub_json(["status", "--all", "--json"], 60), os.getcwd())
        if project is None:
            return fail("PROJECT_NOT_IN_MAIND", f"{os.path.realpath(os.getcwd())} is not a project of the maind fleet")
        command = [umbrella(), "hub", "sync", "--project", project["id"], "--only", cap, *argv[2:]]
    else:
        return fail("USAGE", USAGE)
    sys.stdout.flush()
    os.execv(command[0], command)
    return 1  # not reached


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except HubError as error:
        print(f"{error.code}: {error.message}", file=sys.stderr)
        sys.exit(1)
