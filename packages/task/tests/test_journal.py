"""unittest для task.journal — append-only писатель пер-планового журнала (P1.1).
Запуск: cd packages/task && python3 -m unittest discover -s tests"""
import json
import hashlib
import tempfile
import unittest
from pathlib import Path

from task.journal import (  # noqa: E402
    JournalValidationError, append, append_exception, main, new_entry, validate_entry,
    validate_exceptions,
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


class TestHistoricalExceptions(TmpDirTestCase):
    def setUp(self):
        super().setUp()
        self.plan_id = "2026.07.19-DEMO"
        self.plan_dir = self.plan_dir / self.plan_id
        self.plan_dir.mkdir()
        (self.plan_dir / "plan.md").write_text(
            "# План\n\n## 5. Decision Log\n\n| D# | Дата | Решение | Почему |\n"
            "|:--|:--|:--|:--|\n| D51 | 2026-07-20 | owner | test |\n",
            encoding="utf-8")
        entry = new_entry(plan_id=self.plan_id, item_id="P0.1", command="plan-design",
                          actor="owner", result="no-op")
        entry["friction"] = "legacy"
        raw = json.dumps(entry, ensure_ascii=False, sort_keys=True)
        (self.plan_dir / "journal.jsonl").write_text(raw + "\n", encoding="utf-8")
        self.raw = raw

    def _record(self, **overrides):
        record = {
            "ts": "2026-07-20T00:00:00Z", "plan_id": self.plan_id,
            "target_line": 1,
            "target_sha256": hashlib.sha256(self.raw.encode("utf-8")).hexdigest(),
            "invalid_fields": ["friction"], "owner_decision": "D51",
            "actor": "owner", "reason": "preserve historical evidence",
        }
        record.update(overrides)
        return record

    def _write(self, *records):
        path = self.plan_dir / "journal-exceptions.jsonl"
        path.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n"
                               for r in records), encoding="utf-8")

    def test_exact_valid_exception_is_accepted(self):
        self._write(self._record())
        records, errors = validate_exceptions(self.plan_dir, self.plan_id)
        self.assertEqual(errors, [])
        self.assertEqual(records[1]["invalid_fields"], ["friction"])

    def test_duplicate_target_fails_closed(self):
        record = self._record()
        self._write(record, record)
        _, errors = validate_exceptions(self.plan_dir, self.plan_id)
        self.assertTrue(any("duplicate" in error for error in errors), errors)

    def test_raw_hash_mismatch_fails_closed(self):
        self._write(self._record(target_sha256="0" * 64))
        _, errors = validate_exceptions(self.plan_dir, self.plan_id)
        self.assertTrue(any("SHA-256" in error for error in errors), errors)

    def test_valid_or_malformed_target_fails_closed(self):
        valid = new_entry(plan_id=self.plan_id, item_id="P0.1", command="plan-design",
                          actor="owner", result="no-op")
        raw = json.dumps(valid, ensure_ascii=False, sort_keys=True)
        (self.plan_dir / "journal.jsonl").write_text(raw + "\n", encoding="utf-8")
        self.raw = raw
        self._write(self._record(target_sha256=hashlib.sha256(raw.encode()).hexdigest()))
        _, errors = validate_exceptions(self.plan_dir, self.plan_id)
        self.assertTrue(any("уже валидна" in error for error in errors), errors)
        (self.plan_dir / "journal.jsonl").write_text("{bad\n", encoding="utf-8")
        self._write(self._record(target_sha256=hashlib.sha256(b"{bad").hexdigest()))
        _, errors = validate_exceptions(self.plan_dir, self.plan_id)
        self.assertTrue(any("не JSON" in error for error in errors), errors)

    def test_missing_owner_and_foreign_plan_fail_closed(self):
        self._write(self._record(owner_decision="D52"))
        _, errors = validate_exceptions(self.plan_dir, self.plan_id)
        self.assertTrue(any("D52" in error for error in errors), errors)
        self._write(self._record(plan_id="2026.07.19-FOREIGN"))
        _, errors = validate_exceptions(self.plan_dir, self.plan_id)
        self.assertTrue(any("plan_id" in error for error in errors), errors)
        entry = json.loads(self.raw)
        entry["plan_id"] = "2026.07.19-FOREIGN"
        self.raw = json.dumps(entry, ensure_ascii=False, sort_keys=True)
        (self.plan_dir / "journal.jsonl").write_text(self.raw + "\n", encoding="utf-8")
        self._write(self._record(target_sha256=hashlib.sha256(self.raw.encode()).hexdigest()))
        _, errors = validate_exceptions(self.plan_dir, self.plan_id)
        self.assertTrue(any("target event" in error for error in errors), errors)

    def test_inexact_invalid_field_set_fails_closed(self):
        self._write(self._record(invalid_fields=["friction", "note"]))
        _, errors = validate_exceptions(self.plan_dir, self.plan_id)
        self.assertTrue(any("invalid_fields" in error for error in errors), errors)

    def test_exception_cli_appends_valid_record(self):
        rc = main([
            "exception", "--plan-dir", str(self.plan_dir), "--target-line", "1",
            "--invalid-fields", "friction", "--owner-decision", "D51",
            "--actor", "owner", "--reason", "preserve historical evidence",
        ])
        self.assertEqual(rc, 0)
        self.assertTrue((self.plan_dir / "journal-exceptions.jsonl").is_file())


if __name__ == "__main__":
    unittest.main()
