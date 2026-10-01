"""Post-terminal reconciliation resumes from journal truth without duplicate events."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from .fixtures import handoff_md, item_spec_md, write_valid_plan
except ImportError:
    from fixtures import handoff_md, item_spec_md, write_valid_plan

from task import (journal, plan_item_state, plan_reconcile, terminal_policy)


class TerminalReconciliationTests(unittest.TestCase):
    def test_terminal_journal_repairs_stale_views_and_materializes_one_successor(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = write_valid_plan(Path(tmp), "RECONCILE", layout="v2")
            successor = plan / "phases/P1/P1.2.md"
            successor.write_text(item_spec_md("P1.2").replace(
                "**Inputs:** `lib/pkg/config.py`.",
                "**Inputs:** `phases/P1/P1.1.state.md` (producer: P1.1)."),
                encoding="utf-8")
            (plan / "journal.jsonl").write_text("", encoding="utf-8")
            plan_item_state.build_states(plan, item_id="P1.1", materialize_successor=False)
            plan_item_state.build_states(plan, item_id="P1.2", materialize_successor=False)
            run_id = "run-reconcile"
            journal.append(plan, journal.new_entry(
                plan_id=plan.name, item_id="P1.1", command="plan-run",
                actor="implementation/high", result="in-progress", session_id="session-1",
                run_id=run_id, attempt=1))
            decision = terminal_policy.build_decision(
                plan, "P1.1", result="closed-green",
                validation=[{"carrier": "fixture", "status": "green",
                             "evidence_ids": ["test:green"]}])
            journal.append(plan, journal.new_entry(
                plan_id=plan.name, item_id="P1.1", command="plan-run",
                actor="implementation/high", result="closed-green", session_id="session-1",
                run_id=run_id, attempt=1, decision=decision))
            # The journal is terminal while owner views intentionally remain stale.
            self.assertIn("⬜ Not started", (plan / "phases/P1/P1.1.state.md").read_text())
            handoff = handoff_md(plan.name, item_id="P1.1").replace(
                f"/task:plan-run {plan.name} P1.1",
                f"/task:plan-run {plan.name} P1.2")
            (plan / "handoff.md").write_text(handoff, encoding="utf-8")

            before = (plan / "journal.jsonl").read_bytes()
            with patch.object(plan_reconcile.plan_status, "build_status",
                              side_effect=OSError("interrupted")):
                with self.assertRaises(plan_reconcile.ReconciliationError) as raised:
                    plan_reconcile.reconcile_terminal(plan, "P1.1")
            self.assertEqual((raised.exception.code, raised.exception.stage),
                             ("PLAN_RECONCILIATION_INCOMPLETE", "owner-views"))
            self.assertEqual((plan / "journal.jsonl").read_bytes(), before)

            first = plan_reconcile.reconcile_terminal(plan, "P1.1")
            second = plan_reconcile.reconcile_terminal(plan, "P1.1")

            self.assertEqual(first["receipt"], second["receipt"])
            self.assertEqual((plan / "journal.jsonl").read_bytes(), before)
            self.assertIn("🟢 Done", (plan / "phases/P1/P1.1.state.md").read_text())
            self.assertEqual(first["next_bundle"], "bundles/P1.2.json")
            self.assertTrue((plan / "bundles/P1.2.json").is_file())


if __name__ == "__main__":
    unittest.main()
