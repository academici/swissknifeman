"""One-call work preparation/finalization preserves the owning admission gates."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from .fixtures import item_spec_md, write_valid_plan
except ImportError:
    from fixtures import item_spec_md, write_valid_plan

from task import (plan_bundle, plan_delivery, plan_item_state, plan_recovery,
                  plan_status, plan_work, route_evidence)


class PlanWorkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.plan = write_valid_plan(Path(self.tmp.name), "WORK")
        (self.plan / "journal.jsonl").write_text("")
        plan_item_state.build_states(self.plan, item_id="P1.1")
        plan_status.build_status(self.plan)
        core = self.plan / "plan.md"
        core.write_text(core.read_text().replace("## 3. Routing", """## 3. Routing

| Batch | Items | Model class/effort | Exec | Review | Почему |
|:--|:--|:--|:--|:--|:--|
| solo | P1.1 | implementation/medium | manual | light | recommended: bounded work |
"""))
        self.actual = route_evidence.capture_actual(
            "implementation", "medium", source="provider-thread-state", model="test")
        self.actual.update(thread_id="test-session", source_version="test",
                           cwd=self.tmp.name, invocation="task:plan-exec WORK P1.1")

    def prepare(self):
        return plan_work.prepare(self.plan, "P1.1", command="plan-exec",
                                 actor="test/medium", session_id="test-session",
                                 actual_route=self.actual)

    def test_prepare_returns_selected_context_and_one_durable_start_with_route(self):
        first = self.prepare()
        self.assertEqual(set(first["context"]), {"item-spec"})
        self.assertNotIn("bundle", first["context"])
        self.assertEqual(len(first["snapshot"]["members"]), 5)
        receipt = route_evidence.run_receipt_from_journal(
            self.plan, first["position"]["run_id"])
        self.assertEqual(receipt["session_id"], "test-session")
        before = (self.plan / "journal.jsonl").read_bytes()
        resumed = self.prepare()
        self.assertEqual(resumed["position"]["mode"], "resume")
        self.assertEqual(resumed["position"]["run_id"], first["position"]["run_id"])
        self.assertEqual((self.plan / "journal.jsonl").read_bytes(), before)

    def test_route_failure_does_not_create_an_attempt(self):
        state = (self.plan / "phases/P1/P1.1.state.md").read_bytes()
        bundle = (self.plan / "bundles/P1.1.json").read_bytes()
        self.actual["model_class"] = "economy"
        with self.assertRaisesRegex(plan_work.WorkError, "ROUTE_UNDERSHOOT"):
            self.prepare()
        self.assertEqual((self.plan / "journal.jsonl").read_text(), "")
        self.assertEqual((self.plan / "phases/P1/P1.1.state.md").read_bytes(), state)
        self.assertEqual((self.plan / "bundles/P1.1.json").read_bytes(), bundle)

    def test_prepare_captures_context_once(self):
        from task import plan_context

        with patch("task.plan_context.capture", wraps=plan_context.capture) as capture:
            self.prepare()
        self.assertEqual(capture.call_count, 1)

    def test_explicit_plan_run_passes_its_inherited_carrier_to_contract(self):
        core = self.plan / "plan.md"
        core.write_text(core.read_text().replace("| manual |", "| plan-exec |"))
        self.actual.update(model_class="frontier", effort="high",
                           invocation="task:plan-run WORK P1.1")
        result = plan_work.prepare(self.plan, "P1.1", command="plan-run",
                                   actor="test/high", session_id="test-session",
                                   actual_route=self.actual)
        self.assertEqual(result["position"]["code"], "START_ITEM")

    def test_out_of_order_stays_typed_before_start(self):
        successor = self.plan / "phases/P1/P1.2.md"
        successor.write_text(item_spec_md("P1.2").replace(
            "**Inputs:** `lib/pkg/config.py`.",
            "**Inputs:** `phases/P1/P1.1.state.md` (producer: P1.1)."))
        plan_item_state.build_states(self.plan, item_id="P1.2")
        with self.assertRaisesRegex(plan_recovery.RecoveryError, "OUT_OF_ORDER_REQUEST"):
            plan_work.prepare(self.plan, "P1.2", command="plan-exec",
                              actor="test/medium", session_id="test-session",
                              actual_route=self.actual)
        self.assertEqual((self.plan / "journal.jsonl").read_text(), "")

    def test_missing_validation_prerequisite_is_reported_for_local_repair(self):
        spec = self.plan / "phases/P1/P1.1.md"
        spec.write_text(spec.read_text().replace("**Validation:**", "**Validation:** `make absent`;"))
        result = self.prepare()
        self.assertEqual(result["validation"]["disposition"], "local-repair")

    def test_design_capsule_reads_no_generated_bundle_payload(self):
        capsule = plan_work.design_context(self.plan, "P1")
        self.assertIn("Validation", capsule["schema"]["item_fields"])
        self.assertIn("P1.1", capsule["items"])
        self.assertEqual(capsule["routing"]["P1.1"]["route"]["effort"], "medium")
        self.assertNotIn("bundle", capsule)

    def test_design_route_budget_is_checked_before_baseline_write(self):
        with self.assertRaisesRegex(plan_work.WorkError, "ECONOMY_ROUTE_OVERSHOOT"):
            plan_work.design_context(self.plan, "P1", actual_route={"model_class": "frontier", "effort": "xhigh"})
        self.assertFalse((self.plan / ".plan-cache/design-P1-baseline.json").exists())
        result = plan_work.design_context(self.plan, "P1",
            actual_route={"model_class": "frontier", "effort": "xhigh"}, owner_accepts_overshoot=True)
        self.assertEqual(result["phase_id"], "P1")

    def test_captured_foreign_baseline_is_visible_but_new_errors_block(self):
        from task import plan_lint
        original = plan_lint.lint_plan
        new_error = []

        def lint(root, diagnostics):
            value = original(root, diagnostics)
            diagnostics.error(Path(root) / "phases/P9/P9.md", 1, "historical defect")
            if new_error:
                diagnostics.error(Path(root) / "phases/P1/P1.md", 2, "new defect")
            return value

        with patch("task.plan_lint.lint_plan", side_effect=lint):
            capsule = plan_work.design_context(self.plan, "P1")
            self.assertTrue(capsule["baseline_errors"])
            result = plan_work.finalize_design(self.plan, "P1", actor="test/high", session_id="test")
            self.assertIn("historical defect", result["baseline_errors"][0])
            new_error.append(True)
            with self.assertRaisesRegex(plan_work.WorkError, "new defect"):
                plan_work.finalize_design(self.plan, "P1", actor="test/high", session_id="test")

    def test_selected_phase_defect_cannot_be_accepted_as_baseline(self):
        from task import plan_lint
        original = plan_lint.lint_plan

        def lint(root, diagnostics):
            value = original(root, diagnostics)
            diagnostics.error(Path(root) / "phases/P1/P1.md", 1, "existing target defect")
            return value

        with patch("task.plan_lint.lint_plan", side_effect=lint):
            plan_work.design_context(self.plan, "P1")
            with self.assertRaisesRegex(plan_work.WorkError, "existing target defect"):
                plan_work.finalize_design(self.plan, "P1", actor="test/high", session_id="test")

    def test_finalize_design_is_repeatable_and_does_not_start_execution(self):
        first = plan_work.finalize_design(self.plan, "P1", actor="test/high",
                                          session_id="design-session")
        before = (self.plan / "journal.jsonl").read_bytes()
        second = plan_work.finalize_design(self.plan, "P1", actor="test/high",
                                           session_id="design-session")
        self.assertEqual((self.plan / "journal.jsonl").read_bytes(), before)
        self.assertEqual(first["receipt"], second["receipt"])
        self.assertTrue(plan_delivery.verify_receipt(self.plan, second["receipt"]))
        events = [json.loads(line) for line in before.splitlines()]
        self.assertEqual([(row["command"], row["result"]) for row in events],
                         [("plan-design", "no-op")])
        plan_bundle.build(self.plan, "P1.1", check=True)
        plan_item_state.build_states(self.plan, item_id="P1.1", check=True)
        self.assertEqual(plan_recovery.inspect(self.plan, "P1.1")["mode"], "start")

    def test_bad_handoff_cannot_be_finalized_or_journaled(self):
        path = self.plan / "handoff.md"
        path.write_text(path.read_text().replace("/task:plan-exec WORK P1.1", "nonsense"))
        with self.assertRaises(ValueError):
            plan_work.finalize_design(self.plan, "P1", actor="test/high", session_id="test")
        self.assertEqual((self.plan / "journal.jsonl").read_text(), "")
        self.assertFalse((self.plan / ".plan-cache/design-receipt.json").exists())

    def test_finalize_cannot_invent_a_terminal_event(self):
        with self.assertRaisesRegex(ValueError, "PLAN_RECONCILIATION_INCOMPLETE"):
            plan_work.finalize(self.plan, "P1.1")


if __name__ == "__main__":
    unittest.main()
