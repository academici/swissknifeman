"""Terminal continuity and handoff recommendation receipts."""
import json
import tempfile
import unittest
from pathlib import Path

try:
    from .fixtures import write_valid_plan
except ImportError:
    from fixtures import write_valid_plan
from task import journal, plan_delivery, plan_item_state, terminal_policy


class PlanDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _terminal_plan(self, *, layout="v2", result="closed-green", root=None):
        plan = write_valid_plan(root or self.root, "DEMO-DELIVERY", layout=layout)
        (plan / "journal.jsonl").write_text("", encoding="utf-8")
        handoff = plan / "handoff.md"
        handoff.write_text(handoff.read_text(encoding="utf-8").replace(
            "/task:plan-exec DEMO-DELIVERY P1.1",
            "/task:plan-audit DEMO-DELIVERY P1"), encoding="utf-8")
        decision = terminal_policy.build_decision(
            plan, "P1.1", result=result,
            validation=[{"carrier": "bash test.sh", "status": "green",
                         "evidence_ids": ["test:exit-0"]}],
            repair_exhausted=(
                {"classifier": "recoverable-validation-gap/v1",
                 "failed_carrier": "bash test.sh", "verdict": "outside-scope",
                 "reason": "fixture deviation", "continuation": "follow-up: fixture",
                 "evidence_ids": ["test:deviation"]}
                if result == "closed-deviations" else None),
        )
        journal.append(plan, journal.new_entry(
            plan_id=plan.name,
            item_id="P1.1",
            command="plan-run",
            actor="implementation/high",
            result=result,
            session_id="session-1",
            run_id="run-1",
            fingerprint="a" * 64,
            decision=decision,
        ))
        plan_item_state.build_states(plan, item_id="P1.1")
        return plan

    def test_terminal_item_receipt_binds_state_journal_and_exact_recommendation(self):
        plan = self._terminal_plan()
        receipt = plan_delivery.build_terminal_receipt(plan, "P1.1")
        self.assertEqual(receipt["schema_version"], "terminal-delivery-receipt/v1")
        self.assertEqual(receipt["status"], "🟢 Done")
        self.assertEqual(receipt["next_exact"], "/task:plan-audit DEMO-DELIVERY P1")
        self.assertIn("| Model | sonnet |", receipt["recommendation"])
        self.assertEqual(receipt["journal"]["run_id"], "run-1")
        self.assertEqual(receipt["journal"]["line"], 1)
        self.assertEqual(receipt["adapter_attestation"]["version"], "0.13.2")
        self.assertEqual(receipt["adapter_attestation"]["command_id"], "task:plan-run")
        self.assertRegex(
            receipt["adapter_attestation"]["canonical_command_sha256"],
            r"^sha256:[0-9a-f]{64}$")
        self.assertRegex(receipt["digests"]["state"], r"^sha256:[0-9a-f]{64}$")
        self.assertTrue(plan_delivery.verify_receipt(plan, receipt))

    def test_nonterminal_item_forbids_terminal_receipt(self):
        plan = write_valid_plan(self.root, "DEMO-LIVE", layout="v2")
        (plan / "journal.jsonl").write_text("", encoding="utf-8")
        journal.append(plan, journal.new_entry(
            plan_id=plan.name, item_id="P1.1", command="plan-run",
            actor="implementation/high", result="in-progress",
            session_id="session-1", run_id="run-1",
        ))
        plan_item_state.build_states(plan, item_id="P1.1")
        with self.assertRaisesRegex(plan_delivery.DeliveryError, "FINAL_BEFORE_TERMINAL_FORBIDDEN"):
            plan_delivery.build_terminal_receipt(plan, "P1.1")

    def test_handoff_receipt_is_available_for_nonterminal_design_delivery(self):
        plan = write_valid_plan(self.root, "DEMO-HANDOFF", layout="v2")
        receipt = plan_delivery.build_handoff_receipt(plan, "design")
        self.assertEqual(receipt["schema_version"], "handoff-recommendation-receipt/v1")
        self.assertEqual(receipt["status"], "handoff-persisted")
        self.assertEqual(receipt["next_exact"], "/task:plan-exec DEMO-HANDOFF P1.1")

    def test_handoff_receipt_preserves_visible_batch(self):
        plan = write_valid_plan(self.root, "DEMO-BATCH-HANDOFF", layout="v2")
        handoff = plan / "handoff.md"
        handoff.write_text(handoff.read_text(encoding="utf-8").replace(
            "| Model | sonnet |", "| Batch | B1 |\n| Model | sonnet |"), encoding="utf-8")
        receipt = plan_delivery.build_handoff_receipt(plan, "design")
        self.assertEqual(receipt["route"]["batch"], "B1")

    def test_phase_audit_receipt_rejects_repair_successor_without_terminal_evidence(self):
        plan = write_valid_plan(self.root, "DEMO-AUDIT", layout="v2")
        phase = plan / "phases" / "P1" / "P1.md"
        phase.write_text(
            phase.read_text(encoding="utf-8")
            + "\n## Audit P1 — 2026-08-12\n\n**Вердикт: RED**\n\n"
            "### Что запускать\n\n"
            "| Batch | Model | Thinking | Context | Суть | Команда |\n"
            "|:--|:--|:--|:--|:--|:--|\n"
            "| repair | frontier | high | `cold-start-root: audit-root-terminal` | fix | "
            "`$ task:plan-run DEMO-AUDIT P1.1` |\n\n"
            "```text\n$ task:plan-run DEMO-AUDIT P1.1\n\n"
            "РЕЖИМ: bounded audit repair-forward\nВХОД: audit\nСКОУП: fix\nНЕ ТРОГАТЬ: other\n```\n",
            encoding="utf-8",
        )
        journal.append(plan, journal.new_entry(
            plan_id=plan.name, item_id="P1", command="plan-audit",
            actor="frontier/xhigh", result="audit-green", session_id="session-audit",
            fingerprint="a" * 64,
        ))
        with self.assertRaisesRegex(
                plan_delivery.DeliveryError, "AUDIT_VERDICT_EVENT_MISMATCH"):
            plan_delivery.build_handoff_receipt(plan, "P1")

    def test_phase_audit_green_receipt_binds_close_successor(self):
        plan = write_valid_plan(self.root, "DEMO-AUDIT-GREEN", layout="v2")
        phase = plan / "phases" / "P1" / "P1.md"
        phase.write_text(
            phase.read_text(encoding="utf-8")
            + "\n## Audit P1 — 2026-08-13\n\n**Вердикт: GREEN**\n\n"
            "### Что запускать\n\n"
            "Semantic Next: `close: task:plan-close DEMO-AUDIT-GREEN P1`.\n\n"
            "| Batch | Model | Thinking | Context | Суть | Команда |\n"
            "|:--|:--|:--|:--|:--|:--|\n"
            "| n/a | implementation | high | `cold-start-root: audit-root-terminal` | close | "
            "`$ task:plan-close DEMO-AUDIT-GREEN P1` |\n",
            encoding="utf-8",
        )
        journal.append(plan, journal.new_entry(
            plan_id=plan.name, item_id="P1 — режим фазы", command="plan-audit",
            actor="frontier/xhigh", result="audit-green", session_id="session-audit",
            fingerprint="b" * 64,
        ))
        receipt = plan_delivery.build_handoff_receipt(plan, "P1")
        self.assertEqual(
            receipt["next_exact"], "close: task:plan-close DEMO-AUDIT-GREEN P1")
        self.assertEqual(receipt["digests"]["handoff"], plan_delivery.file_digest(phase))

    def test_stale_handoff_recommendation_is_rejected(self):
        plan = self._terminal_plan()
        receipt = plan_delivery.build_terminal_receipt(plan, "P1.1")
        handoff = plan / "handoff.md"
        handoff.write_text(
            handoff.read_text(encoding="utf-8").replace("P1.1", "P1.2"),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(plan_delivery.DeliveryError,
                                    "FINAL_BEFORE_TERMINAL_FORBIDDEN"):
            plan_delivery.verify_receipt(plan, receipt)

    def test_terminal_item_rejects_stale_subject_handoff(self):
        plan = self._terminal_plan()
        handoff = plan / "handoff.md"
        handoff.write_text(
            handoff.read_text(encoding="utf-8").replace("after P1.1", "after P1.0"),
            encoding="utf-8")
        with self.assertRaisesRegex(
                plan_delivery.DeliveryError, "FINAL_BEFORE_TERMINAL_FORBIDDEN"):
            plan_delivery.build_terminal_receipt(plan, "P1.1")

    def test_v2_receipt_uses_generated_item_state_digest(self):
        plan = self._terminal_plan(layout="v2")
        receipt = plan_delivery.build_terminal_receipt(plan, "P1.1")
        state = plan / "phases" / "P1" / "P1.1.state.md"
        self.assertEqual(receipt["digests"]["state"], plan_delivery.file_digest(state))

    def test_terminal_receipt_survives_bookkeeping_head_change(self):
        plan = self._terminal_plan()
        receipt = plan_delivery.build_terminal_receipt(plan, "P1.1")
        original = plan_delivery._git_commit
        plan_delivery._git_commit = lambda _plan: "f" * 40
        try:
            self.assertTrue(plan_delivery.verify_receipt(plan, receipt))
        finally:
            plan_delivery._git_commit = original

    def test_terminal_phase_and_archive_receipts_are_supported(self):
        phase_plan = self._terminal_plan()
        journal.append(phase_plan, journal.new_entry(
            plan_id=phase_plan.name, item_id="P1", command="plan-close",
            actor="implementation/high", result="closed-green", session_id="session-phase",
            run_id="run-phase", fingerprint="c" * 64,
        ))
        phase_receipt = plan_delivery.build_terminal_receipt(phase_plan, "P1")
        self.assertEqual(phase_receipt["status"], "🟢 Done")
        self.assertEqual(phase_receipt["journal"]["run_id"], "run-phase")

        archive_plan = write_valid_plan(self.root, "DEMO-ARCHIVE")
        archived_path = archive_plan.parent / "archive" / archive_plan.name
        archived_path.parent.mkdir()
        archive_plan.rename(archived_path)
        archive_plan = archived_path
        journal.append(archive_plan, journal.new_entry(
            plan_id=archive_plan.name, item_id="archive", command="plan-close",
            actor="implementation/high", result="closed-green", session_id="session-archive",
            run_id="run-archive", fingerprint="d" * 64,
        ))
        archive_receipt = plan_delivery.build_terminal_receipt(archive_plan, "archive")
        self.assertEqual(archive_receipt["status"], "archived")
        self.assertEqual(archive_receipt["journal"]["run_id"], "run-archive")

    def test_terminal_receipt_refuses_missing_carrier_and_run_id(self):
        plan = self._terminal_plan(root=self.root / "missing-carrier")
        (plan / "phases" / "P1" / "P1.1.state.md").unlink()
        with self.assertRaisesRegex(plan_delivery.DeliveryError, "DELIVERY_CARRIER_MISSING"):
            plan_delivery.build_terminal_receipt(plan, "P1.1")

        plan = self._terminal_plan(root=self.root / "missing-run-id-terminal")
        journal_path = plan / "journal.jsonl"
        entry = json.loads(journal_path.read_text(encoding="utf-8"))
        entry.pop("run_id")
        journal_path.write_text(json.dumps(entry, ensure_ascii=False) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(plan_delivery.DeliveryError, "TERMINAL_RUN_ID_MISSING"):
            plan_delivery.build_terminal_receipt(plan, "P1.1")

    def test_terminal_receipt_skips_historical_missing_run_id_when_latest_is_valid(self):
        plan = self._terminal_plan(root=self.root / "historical-missing-run-id")
        journal_path = plan / "journal.jsonl"
        latest = json.loads(journal_path.read_text(encoding="utf-8"))
        historical = {**latest, "run_id": None, "ts": "2026-08-12T00:00:00Z"}
        journal_path.write_text(
            json.dumps(historical, ensure_ascii=False) + "\n"
            + json.dumps(latest, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        plan_item_state.build_states(plan, item_id="P1.1")

        receipt = plan_delivery.build_terminal_receipt(plan, "P1.1")

        self.assertEqual(receipt["journal"]["line"], 2)
        self.assertEqual(receipt["journal"]["run_id"], "run-1")

    def test_terminal_receipt_skips_historical_invalid_terminal_when_recovered_close_is_valid(self):
        plan = self._terminal_plan(root=self.root / "historical-invalid-terminal")
        journal_path = plan / "journal.jsonl"
        latest = json.loads(journal_path.read_text(encoding="utf-8"))
        historical = {
            **latest,
            "result": "blocked",
            "decision": None,
            "ts": "2026-08-12T00:00:00Z",
        }
        journal_path.write_text(
            json.dumps(historical, ensure_ascii=False) + "\n"
            + json.dumps(latest, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        plan_item_state.build_states(plan, item_id="P1.1")

        receipt = plan_delivery.build_terminal_receipt(plan, "P1.1")

        self.assertEqual(receipt["journal"]["line"], 2)
        self.assertEqual(receipt["journal"]["run_id"], "run-1")

    def test_terminal_receipt_still_refuses_only_invalid_terminal(self):
        plan = self._terminal_plan(root=self.root / "only-invalid-terminal")
        path = plan / "journal.jsonl"
        event = json.loads(path.read_text(encoding="utf-8"))
        event["result"] = "blocked"
        event["decision"] = None
        path.write_text(json.dumps(event, ensure_ascii=False) + "\n", encoding="utf-8")
        plan_item_state.build_states(plan, item_id="P1.1")

        with self.assertRaisesRegex(plan_delivery.DeliveryError, "TERMINAL_EVIDENCE_REQUIRED"):
            plan_delivery.build_terminal_receipt(plan, "P1.1")

    def test_terminal_receipt_refuses_journal_state_result_mismatch(self):
        plan = self._terminal_plan(result="closed-deviations")
        state = plan / "phases" / "P1" / "P1.1.state.md"
        state.write_text(
            state.read_text(encoding="utf-8").replace("🟠 Done with deviations", "🟢 Done"),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(plan_delivery.DeliveryError, "STALE_TERMINAL_RECEIPT"):
            plan_delivery.build_terminal_receipt(plan, "P1.1")

    def test_terminal_receipt_rejects_tampered_red_validation(self):
        plan = self._terminal_plan()
        path = plan / "journal.jsonl"
        event = json.loads(path.read_text(encoding="utf-8"))
        event["decision"]["terminal_evidence"]["validation"][0]["status"] = "red"
        path.write_text(json.dumps(event, ensure_ascii=False) + "\n", encoding="utf-8")
        plan_item_state.build_states(plan, item_id="P1.1")
        with self.assertRaisesRegex(plan_delivery.DeliveryError, "TERMINAL_VALIDATION_RED"):
            plan_delivery.build_terminal_receipt(plan, "P1.1")

    def test_atomic_write_round_trips_receipt(self):
        plan = self._terminal_plan()
        receipt = plan_delivery.build_terminal_receipt(plan, "P1.1")
        target = plan / "artifacts" / "receipt.json"
        plan_delivery.write_receipt(target, receipt)
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), receipt)
        self.assertEqual(list(target.parent.glob(".receipt.json.*.tmp")), [])

    def test_all_canonical_commands_require_a_delivery_receipt(self):
        command_dir = Path(__file__).resolve().parents[1] / "commands"
        expected_kinds = {
            "plan-design.md": "--kind handoff",
            "plan-exec.md": "--kind terminal",
            "plan-audit.md": "--kind handoff",
            "plan-close.md": "--kind terminal",
        }
        for name, kind in expected_kinds.items():
            source = (command_dir / name).read_text(encoding="utf-8")
            self.assertIn("plan-delivery.py", source, name)
            self.assertIn(kind, source, name)
            self.assertTrue("exact recommendation" in source or
                            "Рекомендация следующего шага:" in source, name)

        plan_run = (command_dir / "plan-run.md").read_text(encoding="utf-8")
        self.assertIn('task.command_catalog.package_command_path("task:plan-exec")', plan_run)
        self.assertIn("with these three differences", plan_run)


if __name__ == "__main__":
    unittest.main()
