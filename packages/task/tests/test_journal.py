"""unittest для task.journal — append-only писатель пер-планового журнала (P1.1).
Запуск: cd packages/task && python3 -m unittest discover -s tests"""
import json
import tempfile
import unittest
from pathlib import Path

from task.journal import (  # noqa: E402
    JournalValidationError, append, main, new_entry, validate_entry,
)


class TmpDirTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.plan_dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()


class TestNewEntryAndValidate(TmpDirTestCase):
    def test_new_entry_has_all_required_fields_and_validates(self):
        entry = new_entry(
            plan_id="2026.07.18-FOREMAN", item_id="P1.3", command="plan-exec",
            actor="sonnet/high", result="in-progress",
        )
        validate_entry(entry)  # не бросает
        for field in ("ts", "plan_id", "item_id", "command", "session_id", "run_id",
                      "attempt", "actor", "friction", "result", "cost_usd", "num_turns",
                      "duration_ms", "note"):
            self.assertIn(field, entry)
        self.assertEqual(entry["session_id"], None)
        self.assertEqual(entry["run_id"], None)
        self.assertEqual(entry["attempt"], 1)
        self.assertEqual(entry["friction"], [])
        self.assertTrue(entry["ts"].endswith("Z"))

    def test_missing_field_rejected(self):
        entry = new_entry(plan_id="P", item_id="P1.1", command="plan-exec",
                           actor="sonnet/high", result="in-progress")
        del entry["cost_usd"]
        with self.assertRaises(JournalValidationError):
            validate_entry(entry)

    def test_bad_command_rejected(self):
        entry = new_entry(plan_id="P", item_id="P1.1", command="plan-exec",
                           actor="sonnet/high", result="in-progress")
        entry["command"] = "plan-nope"
        with self.assertRaises(JournalValidationError):
            validate_entry(entry)

    def test_bad_result_rejected(self):
        entry = new_entry(plan_id="P", item_id="P1.1", command="plan-exec",
                           actor="sonnet/high", result="in-progress")
        entry["result"] = "not-an-enum-value"
        with self.assertRaises(JournalValidationError):
            validate_entry(entry)

    def test_bad_friction_value_rejected(self):
        entry = new_entry(plan_id="P", item_id="P1.1", command="plan-exec",
                           actor="sonnet/high", result="in-progress",
                           friction=["deviation", "не-из-списка"])
        with self.assertRaises(JournalValidationError):
            validate_entry(entry)

    def test_attempt_must_be_positive_int(self):
        entry = new_entry(plan_id="P", item_id="P1.1", command="plan-exec",
                           actor="sonnet/high", result="in-progress")
        entry["attempt"] = 0
        with self.assertRaises(JournalValidationError):
            validate_entry(entry)

    def test_numeric_fields_reject_non_number(self):
        entry = new_entry(plan_id="P", item_id="P1.1", command="plan-exec",
                           actor="sonnet/high", result="in-progress")
        entry["cost_usd"] = "1.83"
        with self.assertRaises(JournalValidationError):
            validate_entry(entry)

    def test_numeric_fields_accept_none(self):
        entry = new_entry(plan_id="P", item_id="P1.1", command="plan-exec",
                           actor="sonnet/high", result="in-progress")
        validate_entry(entry)  # cost_usd/num_turns/duration_ms — None по дефолту

    def test_all_result_and_friction_enum_values_accepted(self):
        from task.journal import FRICTION_VALUES, RESULT_VALUES
        for result in RESULT_VALUES:
            entry = new_entry(plan_id="P", item_id="P1.1", command="plan-exec",
                               actor="sonnet/high", result=result, friction=FRICTION_VALUES)
            validate_entry(entry)  # не бросает ни на одном каноническом значении


class TestAppend(TmpDirTestCase):
    def test_append_writes_one_valid_json_line(self):
        entry = new_entry(plan_id="P", item_id="P1.3", command="plan-exec",
                           actor="sonnet/high", result="in-progress")
        path = append(self.plan_dir, entry)
        self.assertEqual(path, self.plan_dir / "journal.jsonl")
        lines = path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0]), entry)

    def test_append_is_append_only_existing_lines_untouched(self):
        first = new_entry(plan_id="P", item_id="P1.3", command="plan-exec",
                           actor="sonnet/high", result="in-progress")
        second = new_entry(plan_id="P", item_id="P1.3", command="plan-exec",
                            actor="sonnet/high", result="closed-green")
        append(self.plan_dir, first)
        append(self.plan_dir, second)
        lines = (self.plan_dir / "journal.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[0])["result"], "in-progress")
        self.assertEqual(json.loads(lines[1])["result"], "closed-green")

    def test_invalid_entry_not_written(self):
        entry = new_entry(plan_id="P", item_id="P1.3", command="plan-exec",
                           actor="sonnet/high", result="in-progress")
        entry["result"] = "garbage"
        with self.assertRaises(JournalValidationError):
            append(self.plan_dir, entry)
        self.assertFalse((self.plan_dir / "journal.jsonl").exists())

    def test_every_line_is_parseable_ndjson(self):
        for result in ("in-progress", "closed-deviations", "escalated"):
            append(self.plan_dir, new_entry(
                plan_id="P", item_id="P1.3", command="plan-exec",
                actor="sonnet/high", result=result))
        path = self.plan_dir / "journal.jsonl"
        for ln in path.read_text(encoding="utf-8").splitlines():
            json.loads(ln)  # не бросает — валидный NDJSON построчно


class TestCli(TmpDirTestCase):
    def test_main_append_writes_entry(self):
        rc = main([
            "append", "--plan-dir", str(self.plan_dir), "--plan", "2026.07.18-FOREMAN",
            "--item", "P1.3", "--command", "plan-run", "--actor", "sonnet/high",
            "--result", "closed-green", "--friction", "deviation,retry",
            "--attempt", "2", "--note", "test stub",
        ])
        self.assertEqual(rc, 0)
        lines = (self.plan_dir / "journal.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        entry = json.loads(lines[0])
        self.assertEqual(entry["plan_id"], "2026.07.18-FOREMAN")
        self.assertEqual(entry["item_id"], "P1.3")
        self.assertEqual(entry["command"], "plan-run")
        self.assertEqual(entry["friction"], ["deviation", "retry"])
        self.assertEqual(entry["attempt"], 2)

    def test_main_rejects_invalid_command_choice(self):
        with self.assertRaises(SystemExit):
            main([
                "append", "--plan-dir", str(self.plan_dir), "--plan", "P",
                "--item", "P1.1", "--command", "plan-nope", "--actor", "sonnet/high",
                "--result", "in-progress",
            ])

    def test_main_returns_1_on_validation_error(self):
        # attempt по схеме требует int≥1 — argparse не ловит это (валидация в append()),
        # значит смоделируем несогласованность через невалидный --friction-элемент.
        rc = main([
            "append", "--plan-dir", str(self.plan_dir), "--plan", "P",
            "--item", "P1.1", "--command", "plan-exec", "--actor", "sonnet/high",
            "--result", "in-progress", "--friction", "не-из-enum",
        ])
        self.assertEqual(rc, 1)
        self.assertFalse((self.plan_dir / "journal.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
