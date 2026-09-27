import tempfile
import unittest
from pathlib import Path

try:
    from .fixtures import write_valid_plan
except ImportError:
    from fixtures import write_valid_plan
from task import journal, plan_item_state, plan_lint, terminal_policy

class PlanItemStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.plan = write_valid_plan(Path(self.tmp.name), "DEMO-V2", layout="v2")
        (self.plan / "journal.jsonl").write_text("", encoding="utf-8")
    def tearDown(self): self.tmp.cleanup()
    def decision(self, result="closed-green"):
        return terminal_policy.build_decision(
            self.plan, "P1.1", result=result,
            validation=[{"carrier": "bash test.sh", "status": "green",
                         "evidence_ids": ["test:exit-0"]}],
            repair_exhausted=(
                {"classifier": "recoverable-validation-gap/v1",
                 "failed_carrier": "bash test.sh", "verdict": "outside-scope",
                 "reason": "fixture deviation", "continuation": "follow-up: fixture",
                 "evidence_ids": ["test:deviation"]}
                if result == "closed-deviations" else None),
        )
    def test_result_mapping_covers_sealed_enum(self):
        self.assertEqual(set(plan_item_state.RESULT_STATUS), set(journal.RESULT_VALUES))
    def test_generate_and_drift_check(self):
        targets = plan_item_state.build_states(self.plan)
        text = targets[0].read_text(encoding="utf-8")
        self.assertIn("projection: item-state", text)
        self.assertNotIn("routing", text.lower())
        self.assertEqual(plan_item_state.build_states(self.plan, check=True), targets)
        targets[0].write_text(text + "drift\n", encoding="utf-8")
        with self.assertRaises(plan_item_state.ItemStateError): plan_item_state.build_states(self.plan, check=True)

    def test_history_pointer_has_a_complete_canonical_cli(self):
        model, _note, _friction = plan_item_state.state_model(self.plan, "P1.1")
        self.assertEqual(
            model["state"]["history_pointer"]["command"],
            "python3 packages/task/scripts/plan-views.py history --plan-dir <plan> --item P1.1",
        )

    def test_blocked_event_projects_required_escalation(self):
        journal.append(self.plan, journal.new_entry(
            plan_id="DEMO-V2", item_id="P1.1", command="plan-run",
            actor="implementation/high", result="blocked",
            decision={"signal_class": "authority-boundary", "scope_class": "authority",
                      "action": "approval-required", "recovered": False, "terminal": True},
        ))
        text = plan_item_state.render_state(self.plan, "P1.1")
        self.assertIn("**Status:** 🔴 Blocked", text)
        self.assertIn("**Escalation Needed:** yes", text)
        self.assertIn("> 🔴 ESCALATION P1.1:", text)
        plan_item_state.build_states(self.plan)
        diagnostics = plan_lint.Diagnostics()
        plan_lint.lint_plan(self.plan, diagnostics)
        self.assertFalse(any("рассогласованы" in error for error in diagnostics.errors),
                         diagnostics.errors)

    def test_design_event_is_history_but_not_execution_position(self):
        journal.append(self.plan, journal.new_entry(
            plan_id="DEMO-V2", item_id="P1.1", command="plan-design",
            actor="frontier/high", result="in-progress",
        ))
        model, _note, _friction = plan_item_state.state_model(self.plan, "P1.1")
        self.assertEqual(model["state"]["position"], {
            "status": "⬜ Not started", "attempt": 0, "last_result": None,
        })

    def test_explicit_design_continuation_reopens_terminal_item(self):
        journal.append(self.plan, journal.new_entry(
            plan_id="DEMO-V2", item_id="P1.1", command="plan-run",
            actor="implementation/high", result="blocked",
            decision={"signal_class": "authority-boundary", "scope_class": "authority",
                      "action": "approval-required", "recovered": False, "terminal": True},
        ))
        journal.append(self.plan, journal.new_entry(
            plan_id="DEMO-V2", item_id="P1.1", command="plan-design",
            actor="frontier/high", result="in-progress", attempt=2,
        ))

        model, _note, _friction = plan_item_state.state_model(self.plan, "P1.1")
        self.assertEqual(model["state"]["position"], {
            "status": "🟡 In progress", "attempt": 2, "last_result": "in-progress",
        })

    def test_no_op_does_not_erase_a_closed_execution_position(self):
        journal.append(self.plan, journal.new_entry(
            plan_id="DEMO-V2", item_id="P1.1", command="plan-run",
            actor="implementation/high", result="closed-green", decision=self.decision(),
        ))
        journal.append(self.plan, journal.new_entry(
            plan_id="DEMO-V2", item_id="P1.1", command="plan-run",
            actor="implementation/high", result="no-op",
        ))
        model, _note, _friction = plan_item_state.state_model(self.plan, "P1.1")
        self.assertEqual(model["state"]["position"]["status"], "🟢 Done")

    def test_routing_rejection_is_provenance_without_execution_attempt(self):
        journal.append(self.plan, journal.new_entry(
            plan_id="DEMO-V2", item_id="P1.1", command="plan-run",
            actor="implementation/medium", result="routing-rejected",
            friction=["routing-blocked"],
        ))
        model, _note, _friction = plan_item_state.state_model(self.plan, "P1.1")
        self.assertEqual(model["state"]["position"], {
            "status": "⬜ Not started", "attempt": 0, "last_result": None,
        })
        self.assertEqual(
            model["state"]["next_step"],
            "Retry the same command after route correction.",
        )

    def test_observations_do_not_replace_live_execution_position_or_attempt(self):
        journal.append(self.plan, journal.new_entry(
            plan_id="DEMO-V2", item_id="P1.1", command="plan-run",
            actor="implementation/high", result="in-progress",
        ))
        for result in ("decision-pending", "local-repair", "rag-pending", "block-candidate"):
            journal.append(self.plan, journal.new_entry(
                plan_id="DEMO-V2", item_id="P1.1", command="plan-run",
                actor="implementation/high", result=result,
            ))
        model, _note, _friction = plan_item_state.state_model(self.plan, "P1.1")
        self.assertEqual(model["state"]["position"], {
            "status": "🟡 In progress", "attempt": 1, "last_result": "in-progress",
        })
        self.assertEqual(model["state"]["next_step"],
                         "Run isolated block confirmation; do not terminalize.")

    def test_rag_pending_is_provenance_without_execution_attempt(self):
        journal.append(self.plan, journal.new_entry(
            plan_id="DEMO-V2", item_id="P1.1", command="plan-run",
            actor="implementation/high", result="rag-pending",
        ))
        model, _note, _friction = plan_item_state.state_model(self.plan, "P1.1")
        self.assertEqual(model["state"]["position"], {
            "status": "⬜ Not started", "attempt": 0, "last_result": None,
        })
        self.assertEqual(model["state"]["next_step"],
                         "Gather required RAG evidence; do not terminalize.")

    def test_rag_pending_after_start_preserves_live_attempt(self):
        journal.append(self.plan, journal.new_entry(
            plan_id="DEMO-V2", item_id="P1.1", command="plan-run",
            actor="implementation/high", result="in-progress",
        ))
        journal.append(self.plan, journal.new_entry(
            plan_id="DEMO-V2", item_id="P1.1", command="plan-run",
            actor="implementation/high", result="rag-pending",
        ))
        model, _note, _friction = plan_item_state.state_model(self.plan, "P1.1")
        self.assertEqual(model["state"]["position"], {
            "status": "🟡 In progress", "attempt": 1, "last_result": "in-progress",
        })
        self.assertEqual(model["state"]["next_step"],
                         "Gather required RAG evidence; do not terminalize.")

    def test_write_site_local_repair_projects_without_reopening_terminal_item(self):
        journal.append(self.plan, journal.new_entry(
            plan_id="DEMO-V2", item_id="P1.1", command="plan-run",
            actor="implementation/high", result="closed-green", note="summary",
            decision=self.decision(),
        ))
        before, _note, _friction = plan_item_state.state_model(self.plan, "P1.1")
        journal.append(self.plan, journal.new_entry(
            plan_id="DEMO-V2", item_id="P1.1", command="plan-run",
            actor="implementation/high", result="local-repair",
            friction=["local-repair"],
            note="write-site: pre_mutation: allow · pre_final: allow",
        ))
        after, _note, _friction = plan_item_state.state_model(self.plan, "P1.1")
        self.assertEqual(after["state"]["position"], before["state"]["position"])
        text = plan_item_state.render_state(self.plan, "P1.1")
        self.assertIn(
            "**Completion Notes:** summary\n"
            "write-site: pre_mutation: allow · pre_final: allow",
            text,
        )
        self.assertIn("**Known Deviations:** —", text)

    def test_item_event_does_not_stale_another_items_state(self):
        first_spec = self.plan / "phases" / "P1" / "P1.1.md"
        second_spec = first_spec.with_name("P1.2.md")
        second_spec.write_text(
            first_spec.read_text(encoding="utf-8").replace("P1.1", "P1.2"),
            encoding="utf-8",
        )
        plan_item_state.build_states(self.plan)
        second_state = second_spec.with_name("P1.2.state.md")
        before = second_state.read_bytes()

        journal.append(self.plan, journal.new_entry(
            plan_id="DEMO-V2", item_id="P1.1", command="plan-design",
            actor="frontier/high", result="in-progress",
        ))

        with self.assertRaises(plan_item_state.ItemStateError):
            plan_item_state.build_states(self.plan, item_id="P1.1", check=True)
        self.assertEqual(
            plan_item_state.build_states(self.plan, item_id="P1.2", check=True),
            (second_state,),
        )
        self.assertEqual(second_state.read_bytes(), before)

    def test_audit_and_execution_events_keep_their_execution_semantics(self):
        journal.append(self.plan, journal.new_entry(
            plan_id="DEMO-V2", item_id="P1.1", command="plan-design",
            actor="frontier/high", result="in-progress",
        ))
        journal.append(self.plan, journal.new_entry(
            plan_id="DEMO-V2", item_id="P1.1", command="plan-audit",
            actor="frontier/xhigh", result="audit-red",
        ))
        journal.append(self.plan, journal.new_entry(
            plan_id="DEMO-V2", item_id="P1.1", command="plan-run",
            actor="implementation/high", result="in-progress",
        ))
        model, _note, _friction = plan_item_state.state_model(self.plan, "P1.1")
        self.assertEqual(model["state"]["position"], {
            "status": "🟡 In progress", "attempt": 2, "last_result": "in-progress",
        })
