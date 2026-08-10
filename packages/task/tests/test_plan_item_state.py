import tempfile
import unittest
from pathlib import Path

try:
    from .fixtures import write_valid_plan
except ImportError:
    from fixtures import write_valid_plan
from task import journal, plan_item_state

class PlanItemStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.plan = write_valid_plan(Path(self.tmp.name), "DEMO-V2", layout="v2")
        (self.plan / "journal.jsonl").write_text("", encoding="utf-8")
    def tearDown(self): self.tmp.cleanup()
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

    def test_blocked_event_projects_required_escalation(self):
        journal.append(self.plan, journal.new_entry(
            plan_id="DEMO-V2", item_id="P1.1", command="plan-run",
            actor="implementation/high", result="blocked",
        ))
        text = plan_item_state.render_state(self.plan, "P1.1")
        self.assertIn("**Status:** 🔴 Blocked", text)
        self.assertIn("**Escalation Needed:** yes", text)

    def test_design_event_is_history_but_not_execution_position(self):
        journal.append(self.plan, journal.new_entry(
            plan_id="DEMO-V2", item_id="P1.1", command="plan-design",
            actor="frontier/high", result="in-progress",
        ))
        model, _note, _friction = plan_item_state.state_model(self.plan, "P1.1")
        self.assertEqual(model["state"]["position"], {
            "status": "⬜ Not started", "attempt": 0, "last_result": None,
        })

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
