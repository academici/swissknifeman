"""Fail the first attempt on each event id (exit 3), succeed and record the event in OUT (argv[1]) later."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))  # the aicore package folder
from tests.ext.fixtures.subscribers._record import record  # noqa: E402

event = json.load(sys.stdin)
tries = sys.argv[1] + ".tries"
failed = set()
if os.path.exists(tries):
    with open(tries, encoding="utf-8") as handle:
        failed = set(handle.read().split())
if event["id"] not in failed:
    with open(tries, "a", encoding="utf-8") as handle:
        handle.write(event["id"] + "\n")
    sys.stderr.write("failing once on purpose\n")
    sys.exit(3)
record(sys.argv[1], event)
