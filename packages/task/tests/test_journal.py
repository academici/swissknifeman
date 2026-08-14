"""unittest для task.journal — append-only писатель пер-планового журнала (P1.1).
Запуск: cd packages/task && python3 -m unittest discover -s tests"""
import json
import tempfile
import unittest
from pathlib import Path

try:
    from . import fixtures  # noqa: F401
except ImportError:
    import fixtures  # noqa: F401,E402
from task.journal import (  # noqa: E402
    JournalValidationError, append, append_exception, append_idempotent_terminal,
    derive_run_id, line_sha256, main,
    new_entry, new_exception, validate_entry, validate_exception, validate_exception_target,
)
from task import terminal_policy


def _validation_decision(plan_dir, item_id="P1.3", result="closed-green"):
    plan_dir = Path(plan_dir)
    if not (plan_dir / "plan.md").exists():
        (plan_dir / "plan.md").write_text(
            "## 0. Meta\n\n| Поле | Значение |\n|:--|:--|\n| Layout | v2 |\n",
            encoding="utf-8")
    phase = plan_dir / "phases" / "P1"
    phase.mkdir(parents=True, exist_ok=True)
    (phase / "P1.md").write_text("# P1\n", encoding="utf-8")
    spec = phase / f"{item_id}.md"
    if not spec.exists():
        spec.write_text(f"# {item_id}\n", encoding="utf-8")
    return terminal_policy.build_decision(
        plan_dir, item_id, result=result,
        validation=[{"carrier": "bash test.sh", "status": "green",
                     "evidence_ids": ["test:exit-0"]}],
        repair_exhausted=(
            {"classifier": "recoverable-validation-gap/v1",
             "failed_carrier": "bash test.sh", "verdict": "outside-scope",
             "reason": "fixture deviation", "continuation": "follow-up: fixture",
             "evidence_ids": ["test:deviation"]}
            if result == "closed-deviations" else None),
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

    def test_continue_first_observations_are_not_terminal_results(self):
        from task.journal import RESULT_VALUES, TERMINAL_CLOSE_RESULTS
        observations = {
            "routing-rejected", "decision-pending", "local-repair", "rag-pending", "block-candidate",
        }
        self.assertLessEqual(observations, set(RESULT_VALUES))
        self.assertTrue(observations.isdisjoint(TERMINAL_CLOSE_RESULTS))

    def test_rag_pending_and_candidate_accept_decision_evidence(self):
        for result, action in (("rag-pending", "gather-rag"),
                               ("block-candidate", "request-isolated-review")):
            entry = new_entry(
                plan_id="P", item_id="P1.1", command="plan-run",
                actor="model/high", result=result,
                decision={
                    "signal_class": "external-dependency",
                    "scope_class": "external",
                    "action": action,
                    "recovered": False,
                    "terminal": False,
                },
            )
            validate_entry(entry)


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
    def test_start_and_terminal_share_deterministic_run_id(self):
        kwargs = dict(plan_id="P", item_id="P1.3", attempt=2, session_id="session-1")
        self.assertEqual(derive_run_id(**kwargs), derive_run_id(**kwargs))
        self.assertEqual(len(derive_run_id(**kwargs)), 64)

    def test_duplicate_terminal_returns_pointer_without_appending(self):
        run_id = derive_run_id(
            plan_id="P", item_id="P1.3", attempt=1, session_id="session-1")
        start = new_entry(
            plan_id="P", item_id="P1.3", command="plan-run", actor="model/high",
            result="in-progress", session_id="session-1", run_id=run_id)
        terminal = new_entry(
            plan_id="P", item_id="P1.3", command="plan-run", actor="model/high",
            result="closed-green", session_id="session-1", run_id=run_id,
            fingerprint="a" * 64, decision=_validation_decision(self.plan_dir))
        append(self.plan_dir, start)
        first = append_idempotent_terminal(self.plan_dir, terminal)
        before = (self.plan_dir / "journal.jsonl").read_bytes()
        second = append_idempotent_terminal(self.plan_dir, terminal)
        self.assertEqual(first[2], True)
        self.assertEqual(second[1:], (2, False))
        self.assertEqual((self.plan_dir / "journal.jsonl").read_bytes(), before)

    def test_attention_is_distinct_from_audit_red(self):
        entry = new_entry(
            plan_id="P", item_id="P1", command="plan-audit", actor="model/high",
            result="audit-attention", fingerprint="b" * 64)
        validate_entry(entry)
        self.assertEqual(entry["result"], "audit-attention")

    def test_phase_audit_non_green_cannot_be_appended_without_reducer_evidence(self):
        for result in ("audit-attention", "audit-red"):
            with self.subTest(result=result):
                entry = new_entry(
                    plan_id="P", item_id="P1 — режим фазы", command="plan-audit",
                    actor="model/high", result=result, fingerprint="b" * 64)
                with self.assertRaisesRegex(
                        JournalValidationError,
                        "AUDIT_(ATTENTION_NONTERMINAL|TERMINAL_EVIDENCE_REQUIRED)"):
                    append(self.plan_dir, entry)

    def test_phase_audit_confirmed_boundary_can_be_appended(self):
        entry = new_entry(
            plan_id="P", item_id="P1", command="plan-audit", actor="model/high",
            result="audit-red", fingerprint="b" * 64,
            decision={
                "signal_class": "safety", "scope_class": "phase",
                "action": "terminal-block", "recovered": False, "terminal": True,
                "reason_code": "BLOCK_CONFIRMED", "evidence_ids": ["block:fixture"],
                "continuation": "terminal: confirmed-block block:fixture",
            })
        path = append(self.plan_dir, entry)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["result"], "audit-red")

    def test_red_validation_cannot_be_terminalized(self):
        decision = _validation_decision(self.plan_dir)
        decision["terminal_evidence"]["validation"][0]["status"] = "red"
        entry = new_entry(
            plan_id="P", item_id="P1.3", command="plan-run", actor="model/high",
            result="closed-green", decision=decision)
        with self.assertRaisesRegex(JournalValidationError, "TERMINAL_VALIDATION_RED"):
            append(self.plan_dir, entry)

    def test_audit_item_close_checks_current_spec_digest(self):
        decision = _validation_decision(self.plan_dir)
        spec = self.plan_dir / "phases" / "P1" / "P1.3.md"
        spec.write_text("# changed after decision\n", encoding="utf-8")
        entry = new_entry(
            plan_id="P", item_id="P1.3", command="plan-audit",
            actor="frontier/xhigh", result="closed-green", decision=decision)

        with self.assertRaisesRegex(JournalValidationError, "TERMINAL_SPEC_STALE"):
            append(self.plan_dir, entry)

    def test_deviation_requires_repair_exhausted_evidence(self):
        decision = _validation_decision(self.plan_dir)
        decision["action"] = "close-deviations"
        entry = new_entry(
            plan_id="P", item_id="P1.3", command="plan-run", actor="model/high",
            result="closed-deviations", decision=decision)
        with self.assertRaisesRegex(JournalValidationError, "REPAIR_EXHAUSTED_REQUIRED"):
            append(self.plan_dir, entry)

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
                            actor="sonnet/high", result="closed-green",
                            decision=_validation_decision(self.plan_dir))
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

    def test_overlong_note_is_schema_valid_but_writer_rejects_before_io(self):
        entry = new_entry(plan_id="P", item_id="P1.3", command="plan-exec",
                          actor="sonnet/high", result="closed-green", note="x" * 301)
        validate_entry(entry)  # sealed v1 schema still accepts historical rows
        with self.assertRaisesRegex(JournalValidationError, "301 символов > 300"):
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
            decision = None
            if result == "closed-deviations":
                decision = _validation_decision(self.plan_dir, result=result)
            elif result == "escalated":
                decision = {
                    "signal_class": "authority-boundary", "scope_class": "authority",
                    "action": "approval-required", "recovered": False, "terminal": True,
                }
            append(self.plan_dir, new_entry(
                plan_id="P", item_id="P1.3", command="plan-exec",
                actor="sonnet/high", result=result, decision=decision))
        path = self.plan_dir / "journal.jsonl"
        for ln in path.read_text(encoding="utf-8").splitlines():
            json.loads(ln)  # не бросает — валидный NDJSON построчно


class TestHistoricalSchemaException(TmpDirTestCase):
    def _invalid_target(self, *, plan_id="P", invalid_command=False):
        (self.plan_dir / "phases" / "P1").mkdir(parents=True, exist_ok=True)
        (self.plan_dir / "phases" / "P1" / "P1.md").write_text("# P1\n", encoding="utf-8")
        (self.plan_dir / "decisions").mkdir(exist_ok=True)
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
            "## 0. Meta\n\n| Поле | Значение |\n|:--|:--|\n| Layout | v2 |\n",
            encoding="utf-8")
        (self.plan_dir / "decisions" / "D51-owner-gate.md").write_text(
            "# D51\n", encoding="utf-8")
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
        (plan_dir / "plan.md").write_text(
            "## 0. Meta\n\n| Поле | Значение |\n|:--|:--|\n| Layout | v2 |\n", encoding="utf-8")
        (plan_dir / "phases" / "P1").mkdir(parents=True)
        (plan_dir / "phases" / "P1" / "P1.3.md").write_text("# P1.3\n", encoding="utf-8")
        decision = json.dumps(_validation_decision(plan_dir), ensure_ascii=False)
        rc = main([
            "append", "--plan-dir", str(plan_dir), "--plan", "2026.07.18-FOREMAN",
            "--item", "P1.3", "--command", "plan-run", "--actor", "sonnet/high",
            "--result", "closed-green", "--friction", "deviation,retry",
            "--attempt", "2", "--note", "test stub", "--decision-json", decision,
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
        (plan_dir / "plan.md").write_text(
            "## 0. Meta\n\n| Поле | Значение |\n|:--|:--|\n| Layout | v2 |\n", encoding="utf-8")
        (plan_dir / "phases" / "P1").mkdir(parents=True)
        (plan_dir / "phases" / "P1" / "P1.3.md").write_text("# P1.3\n", encoding="utf-8")
        decision = json.dumps(_validation_decision(plan_dir), ensure_ascii=False)
        rc = main([
            "append", "--plan-dir", str(plan_dir), "--plan", "2026.07.18-FOREMAN",
            "--item", "P1.3", "--command", "plan-run", "--actor", "sonnet/high",
            "--result", "closed-green", "--trace-ref", "b" * 64,
            "--decision-json", decision,
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
        (self.plan_dir / "phases" / "P1").mkdir(parents=True)
        (self.plan_dir / "phases" / "P1" / "P1.md").write_text("# P1\n", encoding="utf-8")
        (self.plan_dir / "plan.md").write_text(
            "## 0. Meta\n\n| Поле | Значение |\n|:--|:--|\n| Layout | v2 |\n",
            encoding="utf-8")
        decisions = self.plan_dir / "decisions"
        decisions.mkdir()
        (decisions / "D51-owner-gate.md").write_text("# D51\n", encoding="utf-8")
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
