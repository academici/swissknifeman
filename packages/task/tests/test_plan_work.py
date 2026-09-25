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

    def add_supporting_artifacts(self):
        phase = "P1"
        normative = (
            f"research/{phase}-design.md",
            f"research/{phase}-design-rag.md",
            f"artifacts/{phase}-design/examples.md",
        )
        for relative in (*normative, f"artifacts/{phase}-design-rag/capture.md"):
            path = self.plan / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"# {relative}\n\nConcrete design evidence.\n")
        phase_path = self.plan / "phases/P1/P1.md"
        phase_path.write_text(phase_path.read_text() + "\n" + "\n".join(normative)
                              + f"\nartifacts/{phase}-design-rag/capture.md\n")
        spec = self.plan / "phases/P1/P1.1.md"
        spec.write_text(spec.read_text().replace(
            "**Inputs:** `lib/pkg/config.py`.",
            "**Inputs:** `lib/pkg/config.py` · " + " · ".join(
                f"`{relative}`" for relative in normative) + "."))
        (self.plan / "roadmap.md").write_text(
            "# Execution sheet\n\n<!-- execution-sheet/v1 -->\n\n"
            "| Command | Unified route | Review |\n"
            "|:--|:--|:--|\n"
            "| `task:plan-run WORK P1.1` | `implementation/medium` | `light` |\n")

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

    def test_design_finish_reports_and_enforces_supporting_artifacts(self):
        capsule = plan_work.design_context(self.plan, finish=True)
        self.assertTrue(capsule["supporting_artifacts"]["complete"])
        self.assertEqual(capsule["supporting_artifacts"]["phases"]["P1"]["present"], [])
        partial = self.plan / "research/P1-design.md"
        partial.parent.mkdir(parents=True, exist_ok=True)
        partial.write_text("# Chosen dossier\n")
        with self.assertRaisesRegex(plan_work.WorkError,
                                    "PLAN_SUPPORTING_ARTIFACTS_INCOMPLETE"):
            plan_work.finalize_design(self.plan, finish=True, actor="test/high",
                                      session_id="test")
        self.add_supporting_artifacts()
        handoff = self.plan / "handoff.md"
        handoff.write_text(handoff.read_text().replace(
            "/task:plan-exec WORK P1.1", "/task:plan-audit WORK design"))
        capsule = plan_work.design_context(self.plan, finish=True)
        self.assertTrue(capsule["supporting_artifacts"]["complete"])
        self.assertTrue(capsule["execution_sheet"]["complete"])
        result = plan_work.finalize_design(self.plan, finish=True, actor="test/high",
                                           session_id="test")
        self.assertEqual(result["phase_id"], "finish")
        self.assertTrue(result["supporting_artifacts"]["complete"])
        self.assertTrue(result["execution_sheet"]["complete"])

    def test_design_finish_can_rebind_an_unchanged_terminal_phase(self):
        from task import journal, terminal_policy

        self.add_supporting_artifacts()
        handoff = self.plan / "handoff.md"
        handoff.write_text(handoff.read_text().replace(
            "/task:plan-exec WORK P1.1", "/task:plan-audit WORK design"))
        decision = terminal_policy.build_decision(
            self.plan, "P1.1", result="closed-green",
            validation=[{"carrier": "fixture", "evidence_ids": ["fixture:green"],
                         "status": "green"}],
        )
        journal.append(self.plan, journal.new_entry(
            plan_id="WORK", item_id="P1.1", command="plan-run",
            actor="test/high", result="closed-green", decision=decision,
            note="Fixture complete.",
        ))
        journal.append(self.plan, journal.new_entry(
            plan_id="WORK", item_id="P1.1", command="plan-run",
            actor="test/high", result="no-op",
            note="write-site: pre_mutation: allow · pre_final: allow",
        ))
        plan_item_state.build_states(self.plan, item_id="P1.1")
        plan_status.build_status(self.plan)

        capsule = plan_work.design_context(self.plan, finish=True)
        self.assertEqual(capsule["phase_id"], "finish")
        result = plan_work.finalize_design(
            self.plan, finish=True, actor="test/high", session_id="design")
        self.assertEqual(result["phase_id"], "finish")

    def test_execution_sheet_requires_finished_design_and_matching_green_audit(self):
        from task import journal, plan_readiness

        self.add_supporting_artifacts()
        bundle = self.plan / "bundles/P1.1.json"
        bundle.unlink()
        with self.assertRaisesRegex(plan_work.WorkError, "PLAN_DESIGN_GATE_BLOCKED"):
            self.prepare()
        handoff = self.plan / "handoff.md"
        handoff.write_text(handoff.read_text().replace(
            "/task:plan-exec WORK P1.1", "/task:plan-audit WORK design"))
        finished = plan_work.finalize_design(
            self.plan, finish=True, actor="test/high", session_id="design")
        self.assertEqual(finished["phase_id"], "finish")
        self.assertFalse(bundle.exists())
        fingerprint = plan_readiness.design_snapshot(self.plan)["fingerprint"]
        with self.assertRaisesRegex(journal.JournalValidationError, "PLAN_DESIGN_AUDIT_STALE"):
            journal.append(self.plan, journal.new_entry(
                plan_id="WORK", item_id="design", command="plan-audit",
                actor="test/xhigh", result="audit-green", fingerprint="0" * 64))
        journal.append(self.plan, journal.new_entry(
            plan_id="WORK", item_id="design", command="plan-audit",
            actor="test/xhigh", result="audit-green", fingerprint=fingerprint))
        self.assertTrue(plan_readiness.design_gate(self.plan)["allowed"])
        self.prepare()
        self.assertTrue(bundle.is_file())
        spec = self.plan / "phases/P1/P1.1.md"
        spec.write_text(spec.read_text().replace("Добавить проверку.", "Добавить проверку ключа."))
        self.assertEqual(plan_readiness.design_gate(self.plan)["code"],
                         "PLAN_DESIGN_FINISH_MISSING")

    def test_early_execution_next_is_rejected_before_design_journal(self):
        from task import plan_readiness

        self.add_supporting_artifacts()
        phase_dir = self.plan / "phases/P2"
        phase_dir.mkdir()
        (phase_dir / "P2.md").write_text(
            "# P2\n\n## Phase Context\n\n> СКЕЛЕТ — не детализирован\n\n"
            "## Phase Handoff\n\nСначала уточнить.\n")
        self.assertEqual(plan_readiness.design_gate(self.plan)["code"],
                         "PLAN_DESIGN_INCOMPLETE")
        with self.assertRaisesRegex(plan_work.WorkError, "PLAN_DESIGN_GATE_BLOCKED"):
            self.prepare()
        with self.assertRaisesRegex(plan_recovery.RecoveryError, "PLAN_DESIGN_GATE_BLOCKED"):
            plan_recovery.start(
                self.plan, "P1.1", command="plan-exec", actor="test/medium",
                session_id="test", contract={"cold_start": {"plan_id": "WORK",
                                                        "item_id": "P1.1"}})
        with self.assertRaisesRegex(plan_delivery.DeliveryError, "PLAN_DESIGN_GATE_BLOCKED"):
            plan_delivery.build_handoff_receipt(self.plan, "P1")
        self.assertEqual((self.plan / "journal.jsonl").read_text(), "")

    def test_dated_plan_cannot_disable_gate_by_removing_sheet_marker(self):
        from task import plan_readiness

        historical = self.plan.parent / "2026.09.22-EXISTING"
        historical.mkdir()
        (historical / "roadmap.md").write_text("# ordinary roadmap\n")
        self.assertFalse(plan_readiness.design_gate_enabled(historical))
        dated = self.plan.parent / "2026.09.24-NEW"
        dated.mkdir()
        (dated / "roadmap.md").write_text("# ordinary roadmap\n")
        self.assertTrue(plan_readiness.design_gate_enabled(dated))

    def test_invalid_history_is_not_reported_as_missing_audit(self):
        from task import journal, plan_readiness

        self.add_supporting_artifacts()
        event = journal.new_entry(plan_id="WORK", item_id="P1.1",
                                  command="plan-exec", actor="test/medium",
                                  result="in-progress")
        event["result"] = "pending-validation"
        (self.plan / "journal.jsonl").write_text(json.dumps(event) + "\n")
        self.assertEqual(plan_readiness.design_gate(self.plan)["code"],
                         "PLAN_JOURNAL_INVALID")

    def test_unreadable_authored_design_has_typed_refusal(self):
        from task import plan_readiness

        self.add_supporting_artifacts()
        (self.plan / "plan.md").write_bytes(b"\xff")
        self.assertEqual(plan_readiness.design_gate(self.plan)["code"],
                         "PLAN_DESIGN_INCOMPLETE")

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
            self.assertEqual(capsule["foreign_error_summary"]["count"], 1)
            self.assertEqual(capsule["local_errors"], [])
            result = plan_work.finalize_design(self.plan, "P1", actor="test/high", session_id="test")
            self.assertEqual(result["foreign_error_summary"]["count"], 1)
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
