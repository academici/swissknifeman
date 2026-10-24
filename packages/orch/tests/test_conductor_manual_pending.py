"""A manual procedure check without a reported verdict is pending, not red: no correction spends budget on it."""
import unittest
from types import SimpleNamespace

from orch.conductor.stages import checks_stage


class _Stage:
    """The members of the conductor the checks stage calls before the correction loop."""

    def _blocked(self, report, code, message):
        return {"status": "blocked", "code": code, "message": message}

    def _red_signature(self, rows):
        raise AssertionError("a pending verdict is not a red signature")

    def _allowance(self, *args, **kwargs):
        raise AssertionError("no correction may be spent on a pending verdict")


class ManualPendingTests(unittest.TestCase):
    def test_a_procedure_without_a_verdict_stops_with_manual_pending(self):
        rows = [{"id": "V1", "procedure": "observe the fix", "verdict": None, "evidence": None, "green": False}]
        item = SimpleNamespace(state={"check_fixes_at": []})
        out_rows, blocked, round_no = checks_stage.green(_Stage(), item, rows, {}, 3, "")
        self.assertIs(out_rows, rows)
        self.assertEqual(blocked["code"], "MANUAL_PENDING")
        self.assertIn("V1", blocked["message"])
        self.assertEqual(round_no, 3)
        self.assertEqual(item.state["check_fixes_at"], [])

    def test_a_pending_procedure_with_a_red_command_is_not_stopped_as_pending(self):
        rows = [{"id": "V1", "procedure": "observe", "verdict": None, "evidence": None, "green": False},
                {"id": "V2", "cmd": "false", "exit": 1, "green": False}]
        item = SimpleNamespace(state={"check_fixes_at": []})
        stage = _Stage()
        stage._red_signature = lambda rows: ("V2",)
        stage._allowance = lambda *args, **kwargs: "limit reached"
        stage._advise_red = lambda *args, **kwargs: None
        _, blocked, _ = checks_stage.green(stage, item, rows, {}, 1, "")
        self.assertEqual(blocked["code"], "CHECKS_RED")


if __name__ == "__main__":
    unittest.main()
