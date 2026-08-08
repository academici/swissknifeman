"""unittest для task.journal — append-only писатель пер-планового журнала (P1.1).
Запуск: cd packages/task && python3 -m unittest discover -s tests"""
import json
import tempfile
import unittest
from pathlib import Path

from task.journal import (  # noqa: E402
    JournalValidationError, append, append_exception, line_sha256, main,
    new_entry, new_exception, validate_entry, validate_exception, validate_exception_target,
)


class TmpDirTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.plan_dir = self.root / "P"
        self.plan_dir.mkdir()

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


class TestTraceRef(TmpDirTestCase):
    """P3.1 (`root/contracts/unified-agent-trace-v1.md` § Journal reference):
    `trace_ref` is additive — omitted by default, present only when passed."""

    def test_omitted_by_default_entry_unchanged(self):
        entry = new_entry(plan_id="P", item_id="P1.1", command="plan-exec",
                           actor="sonnet/high", result="in-progress")
        self.assertNotIn("trace_ref", entry)
        validate_entry(entry)  # не бросает — trace_ref не входит в REQUIRED_FIELDS

    def test_supplied_trace_ref_is_carried_and_appended(self):
        entry = new_entry(plan_id="P", item_id="P1.1", command="plan-exec",
                           actor="sonnet/high", result="in-progress",
                           trace_ref="a" * 64)
        self.assertEqual(entry["trace_ref"], "a" * 64)
        validate_entry(entry)  # extra key — не отклоняется схемой P1.1
        path = append(self.plan_dir, entry)
        written = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(written["trace_ref"], "a" * 64)


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

    def test_foreign_plan_id_not_written(self):
        entry = new_entry(
            plan_id="FOREIGN", item_id="P1.3", command="plan-exec",
            actor="sonnet/high", result="in-progress",
        )
        with self.assertRaisesRegex(JournalValidationError, "FOREIGN.*P"):
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


class TestHistoricalSchemaException(TmpDirTestCase):
    def _invalid_target(self, *, plan_id="P", invalid_command=False):
        entry = new_entry(
            plan_id=plan_id, item_id="design", command="plan-audit",
            actor="opus/xhigh", result="audit-red",
            friction=["Major: historical free-form value"],
        )
        if invalid_command:
            entry["command"] = "plan-nope"
        raw = json.dumps(entry, ensure_ascii=False, sort_keys=True)
        (self.plan_dir / "journal.jsonl").write_text(raw + "\n", encoding="utf-8")
        (self.plan_dir / "plan.md").write_text(
            "| D51 | 2026-07-19 | owner gate | reason |\n", encoding="utf-8")
        return raw

    def _exception(self, raw):
        return new_exception(
            plan_id="P", target_line=1, target_sha256=line_sha256(raw),
            invalid_fields=["friction"], owner_decision="D51",
            actor="owner", reason="preserve historical bytes",
            ts="2026-07-19T20:00:00Z",
        )

    def test_exception_is_valid_sidecar_and_keeps_journal_bytes(self):
        raw = self._invalid_target()
        exception = self._exception(raw)
        validate_exception(exception)
        path = append_exception(self.plan_dir, exception)
        self.assertEqual(path, self.plan_dir / "journal-exceptions.jsonl")
        self.assertEqual(
            (self.plan_dir / "journal.jsonl").read_text(encoding="utf-8"), raw + "\n")
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), exception)

    def test_exception_requires_existing_owner_decision(self):
        raw = self._invalid_target()
        exception = self._exception(raw)
        exception["owner_decision"] = "D52"
        with self.assertRaisesRegex(JournalValidationError, "отсутствует"):
            append_exception(self.plan_dir, exception)

    def test_exception_rejects_unknown_fields(self):
        raw = self._invalid_target()
        exception = self._exception(raw)
        exception["future"] = True
        with self.assertRaisesRegex(JournalValidationError, "неизвестные поля"):
            append_exception(self.plan_dir, exception)

    def test_exception_rejects_duplicate_target(self):
        raw = self._invalid_target()
        exception = self._exception(raw)
        append_exception(self.plan_dir, exception)
        with self.assertRaisesRegex(JournalValidationError, "уже существует"):
            append_exception(self.plan_dir, exception)

    def test_exception_rejects_valid_target(self):
        raw = self._invalid_target()
        valid = json.loads(raw)
        valid["friction"] = ["deviation"]
        raw = json.dumps(valid, ensure_ascii=False, sort_keys=True)
        (self.plan_dir / "journal.jsonl").write_text(raw + "\n", encoding="utf-8")
        exception = self._exception(raw)
        with self.assertRaisesRegex(JournalValidationError, "уже проходит"):
            append_exception(self.plan_dir, exception)

    def test_exception_rejects_foreign_event_plan_id(self):
        raw = self._invalid_target(plan_id="FOREIGN")
        exception = self._exception(raw)
        with self.assertRaisesRegex(JournalValidationError, "target.*FOREIGN.*P"):
            append_exception(self.plan_dir, exception)

    def test_exception_rejects_foreign_sidecar_plan_id(self):
        raw = self._invalid_target(plan_id="FOREIGN")
        exception = self._exception(raw)
        exception["plan_id"] = "FOREIGN"
        with self.assertRaisesRegex(JournalValidationError, "exception.*FOREIGN.*P"):
            append_exception(self.plan_dir, exception)

    def test_exception_requires_exact_invalid_field_set(self):
        raw = self._invalid_target(invalid_command=True)
        exception = self._exception(raw)
        with self.assertRaisesRegex(
                JournalValidationError, r"\['command', 'friction'\]"):
            append_exception(self.plan_dir, exception)


class TestCli(TmpDirTestCase):
    def test_main_append_writes_entry(self):
        plan_dir = self.root / "2026.07.18-FOREMAN"
        plan_dir.mkdir()
        rc = main([
            "append", "--plan-dir", str(plan_dir), "--plan", "2026.07.18-FOREMAN",
            "--item", "P1.3", "--command", "plan-run", "--actor", "sonnet/high",
            "--result", "closed-green", "--friction", "deviation,retry",
            "--attempt", "2", "--note", "test stub",
        ])
        self.assertEqual(rc, 0)
        lines = (plan_dir / "journal.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        entry = json.loads(lines[0])
        self.assertEqual(entry["plan_id"], "2026.07.18-FOREMAN")
        self.assertEqual(entry["item_id"], "P1.3")
        self.assertEqual(entry["command"], "plan-run")
        self.assertEqual(entry["friction"], ["deviation", "retry"])
        self.assertEqual(entry["attempt"], 2)

    def test_main_append_with_trace_ref_writes_it(self):
        plan_dir = self.root / "2026.07.18-FOREMAN"
        plan_dir.mkdir()
        rc = main([
            "append", "--plan-dir", str(plan_dir), "--plan", "2026.07.18-FOREMAN",
            "--item", "P1.3", "--command", "plan-run", "--actor", "sonnet/high",
            "--result", "closed-green", "--trace-ref", "b" * 64,
        ])
        self.assertEqual(rc, 0)
        entry = json.loads((plan_dir / "journal.jsonl").read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(entry["trace_ref"], "b" * 64)

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

    def test_main_exception_appends_sidecar(self):
        entry = new_entry(
            plan_id="P", item_id="design", command="plan-audit",
            actor="opus/xhigh", result="audit-red", friction=["Major: legacy"],
        )
        (self.plan_dir / "journal.jsonl").write_text(
            json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        (self.plan_dir / "plan.md").write_text(
            "| D51 | 2026-07-19 | owner gate | reason |\n", encoding="utf-8")
        rc = main([
            "exception", "--plan-dir", str(self.plan_dir), "--plan", "P",
            "--target-line", "1", "--invalid-fields", "friction",
            "--owner-decision", "D51", "--actor", "owner",
            "--reason", "preserve historical bytes",
        ])
        self.assertEqual(rc, 0)
        self.assertTrue((self.plan_dir / "journal-exceptions.jsonl").is_file())


class TestV2DecisionCarrier(TmpDirTestCase):
    def test_exception_owner_decision_resolves_from_v2_decisions_carrier(self):
        (self.plan_dir / "phases" / "P1").mkdir(parents=True)
        (self.plan_dir / "plan.md").write_text(
            "## 0. Meta\n\n| Поле | Значение |\n|:--|:--|\n| Layout | v2 |\n",
            encoding="utf-8")
        (self.plan_dir / "phases" / "P1" / "P1.md").write_text("# P1\n", encoding="utf-8")
        decisions = self.plan_dir / "decisions"
        decisions.mkdir()
        (decisions / "D42-owner-gate.md").write_text("# D42\n", encoding="utf-8")
        entry = new_entry(plan_id="P", item_id="P1.1", command="plan-run",
                          actor="implementation/high", result="in-progress")
        del entry["friction"]
        raw = json.dumps(entry, ensure_ascii=False, sort_keys=True)
        (self.plan_dir / "journal.jsonl").write_text(raw + "\n", encoding="utf-8")
        exception = new_exception(
            plan_id="P", target_line=1, target_sha256=line_sha256(raw),
            invalid_fields=["friction"], owner_decision="D42", actor="owner",
            reason="v2 carrier fixture")
        validate_exception_target(self.plan_dir, exception)


if __name__ == "__main__":
    unittest.main()
