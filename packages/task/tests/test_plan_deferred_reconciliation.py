"""Deferred reconciliation keeps its active run without requiring future outputs."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from .fixtures import item_spec_md, write_valid_plan
except ImportError:
    from fixtures import item_spec_md, write_valid_plan

from task import (plan_bundle, plan_gates, plan_item_state, plan_lint,
                  plan_recovery, plan_status)
from task.plan_lint_checks.engine import _lint_next_runnable_bundle


class DeferredReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.plan = write_valid_plan(Path(self.tmp.name), "RECONCILE")
        (self.plan / "journal.jsonl").write_text("")
        plan_item_state.build_states(self.plan, item_id="P1.1")
        with patch("task.task_contract.pre_mutation", return_value=None):
            self.started = plan_recovery.start(
                self.plan, "P1.1", command="plan-run", actor="test/high",
                session_id="test", contract={"cold_start": {
                    "plan_id": self.plan.name, "item_id": "P1.1"}})
        producer = self.plan / "phases/P1/P1.2.md"
        producer.write_text(item_spec_md("P1.2").replace("lib/pkg/config.py", "brief/00-brief.md").replace(
            "**Files:** brief/00-brief.md",
            "**Files:** `findings/repair.md`").replace(
            "**Deliverables:** валидация + тест.",
            "**Deliverables:** `findings/repair.md`.") )
        consumer = self.plan / "phases/P1/P1.1.md"
        consumer.write_text(consumer.read_text().replace(
            "**Inputs:** `lib/pkg/config.py`.",
            "**Inputs:** `lib/pkg/config.py`; `findings/repair.md` (producer: P1.2)."))
        for item in ("P1.1", "P1.2"):
            plan_item_state.build_states(self.plan, item_id=item, materialize_successor=False)
        plan_bundle.build(self.plan, "P1.2")
        plan_status.build_status(self.plan)
        self.journal_before = (self.plan / "journal.jsonl").read_bytes()
        self.phases = {"P1": {"path": self.plan / "phases/P1/P1.md",
                               "items": {"P1.1": {}, "P1.2": {}}}}
        self.items = {"P1.1": {"status": "🟡 In progress"},
                      "P1.2": {"status": "⬜ Not started"}}

    def bundle_diagnostics(self):
        diag = plan_lint.Diagnostics()
        _lint_next_runnable_bundle(self.plan, "v2", self.phases, self.items, diag)
        return diag

    def test_deferred_active_consumer_does_not_require_unproduced_bundle(self):
        self.assertFalse(plan_recovery.inspect(self.plan, "P1.1")["allowed"])
        self.assertTrue(plan_recovery.inspect(self.plan, "P1.2")["allowed"])
        self.assertFalse(self.bundle_diagnostics().errors)
        diag = plan_lint.Diagnostics()
        plan_gates.lint_read_budget(self.plan, "v2", diag)
        self.assertFalse(diag.errors, diag.errors)
        self.assertFalse((self.plan / "findings/repair.md").exists())
        self.assertEqual((self.plan / "journal.jsonl").read_bytes(), self.journal_before)
        position = plan_recovery._positions(self.plan)["P1.1"]
        self.assertEqual(position["run_id"], self.started["run_id"])
        self.assertEqual(position["attempt"], self.started["attempt"])

    def test_actual_ready_producer_still_requires_fresh_bundle(self):
        (self.plan / "bundles/P1.2.json").write_text("{}")
        self.assertTrue(any("P1.2 устарел" in row
                            for row in self.bundle_diagnostics().errors))

    def test_undeclared_missing_input_still_fails(self):
        spec = self.plan / "phases/P1/P1.2.md"
        spec.write_text(spec.read_text().replace(
            "**Inputs:** `brief/00-brief.md`.", "**Inputs:** `missing/own.md`."))
        self.assertTrue(any("unresolvable_entry" in row
                            for row in self.bundle_diagnostics().errors))

    def test_dependency_cycle_is_not_silently_deferred(self):
        spec = self.plan / "phases/P1/P1.2.md"
        spec.write_text(spec.read_text().replace(
            "**Inputs:** `brief/00-brief.md`.",
            "**Inputs:** `phases/P1/P1.1.state.md` (producer: P1.1)."))
        self.assertTrue(any("PLAN_DEPENDENCY_CYCLE" in row
                            for row in self.bundle_diagnostics().errors))
        diag = plan_lint.Diagnostics()
        plan_gates.lint_read_budget(self.plan, "v2", diag)
        self.assertTrue(any("PLAN_DEPENDENCY_CYCLE" in row for row in diag.errors))

    def test_unknown_producer_is_not_silently_deferred(self):
        spec = self.plan / "phases/P1/P1.1.md"
        spec.write_text(spec.read_text().replace("producer: P1.2", "producer: P9.9"))
        self.assertTrue(any("PLAN_DEPENDENCY_UNKNOWN" in row
                            for row in self.bundle_diagnostics().errors))


if __name__ == "__main__":
    unittest.main()
