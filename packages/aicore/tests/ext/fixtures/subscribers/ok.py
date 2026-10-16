"""Succeed: record the event in OUT (argv[1]); with argv[2], answer {"status": argv[2]} on stdout."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))  # the aicore package folder
from tests.ext.fixtures.subscribers._record import record  # noqa: E402

record(sys.argv[1], json.load(sys.stdin))
if len(sys.argv) > 2:
    json.dump({"status": sys.argv[2]}, sys.stdout)
