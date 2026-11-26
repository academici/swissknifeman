"""The self-check a completion report must show: a command with a note in parentheses is the command."""
from __future__ import annotations

from types import SimpleNamespace
import unittest

from orch.conductor.stages import execute

COMMANDS = ["python3 scripts/affected-tests.py --run", "ruff check ."]


def gap(rows, issues=()) -> list:
    item = SimpleNamespace(options={"checks": {"self_check": COMMANDS, "executor_runs_checks": False}})
    report = {"status": "done", "self_check": rows, "open_issues": list(issues)}
    return execute.self_check_gap(item, report)


class SelfCheckGapTests(unittest.TestCase):
    def test_a_command_with_a_note_in_parentheses_counts(self):
        rows = [{"cmd": "python3 scripts/affected-tests.py --run", "exit": 0},
                {"cmd": "ruff check . (run as /snap/bin/ruff)", "exit": 0}]
        self.assertEqual(gap(rows), [])

    def test_another_command_or_extra_arguments_do_not_count(self):
        rows = [{"cmd": "python3 scripts/affected-tests.py --run", "exit": 0},
                {"cmd": "ruff check . --fix", "exit": 0}, {"cmd": "ruff check src", "exit": 0}]
        self.assertEqual(gap(rows), ["ruff check ."])

    def test_a_red_noted_command_needs_a_deviation(self):
        rows = [{"cmd": "python3 scripts/affected-tests.py --run", "exit": 0},
                {"cmd": "ruff check . (sandbox: no permission)", "exit": 1}]
        self.assertEqual(gap(rows), ["ruff check ."])
        deviation = {"kind": "deviation", "text": "ruff cannot start in the sandbox"}
        self.assertEqual(gap(rows, [deviation]), [])

    def test_a_deviation_that_names_a_missing_command_accounts_for_it(self):
        rows = [{"cmd": "ruff check .", "exit": 0}]
        deviation = {"kind": "deviation", "text": "python3 scripts/affected-tests.py --run cannot write /tmp here"}
        self.assertEqual(gap(rows, [deviation]), [])
        self.assertEqual(gap([], [deviation]), ["ruff check ."])


if __name__ == "__main__":
    unittest.main()
