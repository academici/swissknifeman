"""Terminal continuity and handoff recommendation receipts."""
import json
import tempfile
import unittest
from pathlib import Path

try:
    from .fixtures import write_valid_plan
except ImportError:
    from fixtures import write_valid_plan
from task import journal, plan_delivery, plan_item_state


class PlanDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _terminal_plan(self, *, layout="v2", result="closed-green", root=None):
        plan = write_valid_plan(root or self.root, "DEMO-DELIVERY", layout=layout)
        (plan / "journal.jsonl").write_text("", encoding="utf-8")
        journal.append(plan, journal.new_entry(
            plan_id=plan.name,
            item_id="P1.1",
            command="plan-run",
            actor="implementation/high",
            result=result,
            session_id="session-1",
            run_id="run-1",
            fingerprint="a" * 64,
        ))
        plan_item_state.build_states(plan, item_id="P1.1")
        return plan

    def test_terminal_item_receipt_binds_state_journal_and_exact_recommendation(self):
        plan = self._terminal_plan()
        receipt = plan_delivery.build_terminal_receipt(plan, "P1.1")
        self.assertEqual(receipt["schema_version"], "terminal-delivery-receipt/v1")
        self.assertEqual(receipt["status"], "🟢 Done")
        self.assertEqual(receipt["next_exact"], "/task:plan-exec DEMO-DELIVERY P1.1")
        self.assertIn("| Model | sonnet |", receipt["recommendation"])
        self.assertEqual(receipt["journal"]["run_id"], "run-1")
        self.assertEqual(receipt["journal"]["line"], 1)
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

    def test_phase_audit_receipt_prefers_latest_audit_launch_block(self):
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
            actor="frontier/xhigh", result="audit-red", session_id="session-audit",
            fingerprint="b" * 64,
        ))
        receipt = plan_delivery.build_handoff_receipt(plan, "P1")
        self.assertEqual(receipt["next_exact"], "$ task:plan-run DEMO-AUDIT P1.1")
        self.assertEqual(receipt["route"]["batch"], "repair")
        self.assertEqual(receipt["route"]["model"], "frontier")
        self.assertIn("РЕЖИМ: bounded audit repair-forward", receipt["recommendation"])
        self.assertEqual(receipt["digests"]["handoff"], plan_delivery.file_digest(phase))

    def test_stale_handoff_recommendation_is_rejected(self):
        plan = self._terminal_plan()
        receipt = plan_delivery.build_terminal_receipt(plan, "P1.1")
        handoff = plan / "handoff.md"
        handoff.write_text(
            handoff.read_text(encoding="utf-8").replace("P1.1", "P1.2"),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(plan_delivery.DeliveryError, "HANDOFF_RECOMMENDATION_MISSING"):
            plan_delivery.verify_receipt(plan, receipt)

    def test_v2_receipt_uses_generated_item_state_digest(self):
        plan = self._terminal_plan(layout="v2")
        receipt = plan_delivery.build_terminal_receipt(plan, "P1.1")
        state = plan / "phases" / "P1" / "P1.1.state.md"
        self.assertEqual(receipt["digests"]["state"], plan_delivery.file_digest(state))

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

    def test_terminal_receipt_refuses_journal_state_result_mismatch(self):
        plan = self._terminal_plan(result="closed-deviations")
        state = plan / "phases" / "P1" / "P1.1.state.md"
        state.write_text(
            state.read_text(encoding="utf-8").replace("🟠 Done with deviations", "🟢 Done"),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(plan_delivery.DeliveryError, "STALE_TERMINAL_RECEIPT"):
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
            self.assertIn("Рекомендация следующего шага:", source, name)

        plan_run = (command_dir / "plan-run.md").read_text(encoding="utf-8")
        self.assertIn("packages/task/commands/plan-exec.md", plan_run)
        self.assertIn("Всё остальное", plan_run)


if __name__ == "__main__":
    unittest.main()
