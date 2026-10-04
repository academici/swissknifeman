"""Interrupted work preserves its producer identity before successor capture."""
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

try:
    from .fixtures import item_spec_md, write_valid_plan
except ImportError:
    from fixtures import item_spec_md, write_valid_plan

from task import (journal, plan_bundle, plan_context, plan_delivery,
                  plan_item_state, plan_recovery, terminal_policy)


class PlanRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.plan = write_valid_plan(Path(self.tmp.name), "RECOVERY", layout="v2")
        (self.plan / "journal.jsonl").write_text("", encoding="utf-8")
        plan_item_state.build_states(self.plan, item_id="P1.1")
        self.add_successor("P1.2", "P1.1")
        self.add_successor("P1.3", "P1.2")

    def tearDown(self):
        self.tmp.cleanup()

    def add_successor(self, item_id, producer):
        spec = self.plan / "phases" / "P1" / f"{item_id}.md"
        spec.write_text(item_spec_md(item_id).replace(
            "**Inputs:** `lib/pkg/config.py`.",
            f"**Inputs:** `phases/P1/{producer}.state.md` (producer: {producer})."
        ), encoding="utf-8")
        plan_item_state.build_states(self.plan, item_id=item_id)

    def start(self, *, session_id="session-1"):
        # The write-admission predicate itself has separate exhaustive contract
        # tests; this fixture isolates durable position and interruption behavior.
        with patch("task.task_contract.pre_mutation", return_value=None):
            return plan_recovery.start(self.plan, "P1.1", command="plan-run",
                                       actor="implementation/high", session_id=session_id,
                                       contract={"cold_start": {"plan_id": self.plan.name,
                                                                 "item_id": "P1.1"}})

    def terminal(self):
        position = plan_recovery.inspect(self.plan, "P1.1")
        decision = terminal_policy.build_decision(
            self.plan, "P1.1", result="closed-green",
            validation=[{"carrier": "bash test.sh", "status": "green",
                         "evidence_ids": ["test:exit-0"]}])
        journal.append(self.plan, journal.new_entry(
            plan_id=self.plan.name, item_id="P1.1", command="plan-run",
            actor="implementation/high", result="closed-green", session_id="session-1",
            run_id=position["run_id"], attempt=position["attempt"], decision=decision))

    def test_declared_phase_order_overrides_numeric_order_for_path_edges(self):
        phase = self.plan / "phases" / "P1" / "P1.md"
        phase.write_text(phase.read_text() + "\n## Planned Items (outcomes)\n"
                         "- **P1.1 — first**\n- **P1.3 — characterization**\n- **P1.2 — CI integrator**\n")
        items = {"P1.1": {}, "P1.2": {"Files": "`shared.php`"},
                 "P1.3": {"Inputs": "`shared.php`", "Files": "`golden.php`"}}
        self.assertNotIn("P1.2", plan_recovery._dependencies(self.plan, "P1.3", items))
        items["P1.2"]["Inputs"] = "`golden.php`"
        self.assertIn("P1.3", plan_recovery._dependencies(self.plan, "P1.2", items))
        items["P1.3"]["Inputs"] += " (producer: P1.2)"
        self.assertIn("P1.2", plan_recovery._dependencies(self.plan, "P1.3", items))

    def test_complete_dependencies_arrow_order_controls_inferred_edges(self):
        phase = self.plan / "phases/P1/P1.md"
        phase.write_text(phase.read_text() + "\n## Dependencies and order\n\n"
                         "`P1.1` → `P1.3` → `P1.2`. Execution order, not numeric order.\n"
                         "\n### Grouping\n\nP1.3 → P1.2 is a solo continuation.\n")
        items = {"P1.1": {}, "P1.2": {"Files": "`shared.php`", "Inputs": "`golden.php`"},
                 "P1.3": {"Inputs": "`shared.php`", "Files": "`golden.php`"}}
        self.assertNotIn("P1.2", plan_recovery._dependencies(self.plan, "P1.3", items))
        self.assertIn("P1.3", plan_recovery._dependencies(self.plan, "P1.2", items))
        items["P1.3"]["Inputs"] += " (producer: P1.2)"
        self.assertIn("P1.2", plan_recovery._dependencies(self.plan, "P1.3", items))

    def test_arrow_order_requires_complete_unique_declaration_in_order_section(self):
        phase = self.plan / "phases/P1/P1.md"
        original = phase.read_text()
        items = {"P1.1": {}, "P1.2": {}, "P1.3": {}}
        numeric = {item: plan_recovery._key(item) for item in items}
        for heading, declaration in (
                ("Dependencies and order", "`P1.1` → `P1.3`"),
                ("Dependencies and order", "`P1.1` → `P1.3` → `P1.2` → `P1.3`"),
                ("Dependencies and order", "`P1.1` → `P1.3` → `P1.2` → `P1.4`"),
                ("Dependencies and order", "`P1.1` → `P1.3` → `P1.2` → unrelated prose"),
                ("Dependencies and order", "`P1.1` → `P1.3` → `P1.2`\n"
                 "`P1.1` → `P1.2` → `P1.3`"),
                ("Dependencies and order", "Prose mentions P1.1 → P1.3 → P1.2."),
                ("Scope Included", "`P1.1` → `P1.3` → `P1.2`")):
            with self.subTest(heading=heading, declaration=declaration):
                phase.write_text(original + f"\n## {heading}\n\n{declaration}\n")
                self.assertEqual(plan_recovery._execution_ranks(self.plan, items), numeric)

    def test_dependencies_arrow_order_blocks_until_immediate_predecessor_closes(self):
        phase = self.plan / "phases/P1/P1.md"
        phase.write_text(phase.read_text() + "\n## Dependencies and order\n\n"
                         "`P1.1` → `P1.3` → `P1.2`. Frozen order.\n")
        items = {"P1.1": {}, "P1.2": {}, "P1.3": {}}
        positions = {"P1.1": {"result": "closed-green"}}
        with patch("task.plan_downstream._all_items", return_value=items), \
                patch.object(plan_recovery, "_positions", return_value=positions):
            self.assertEqual(plan_recovery._dependencies(self.plan, "P1.2", items), {"P1.3"})
            verdict = plan_recovery.inspect(self.plan, "P1.2")
            self.assertFalse(verdict["allowed"])
            self.assertEqual(verdict["active_item"], "P1.3")
            positions["P1.3"] = {"result": "closed-green"}
            self.assertTrue(plan_recovery.inspect(self.plan, "P1.2")["allowed"])

    def test_materialize_next_ready_uses_declared_order_for_selection_and_cutoff(self):
        phase = self.plan / "phases/P1/P1.md"
        original = phase.read_text()
        items = {"P1.1": {}, "P1.2": {}, "P1.3": {}}
        declarations = (
            "## Planned Items (outcomes)\n"
            "- **P1.1 — first**\n- **P1.3 — producer**\n- **P1.2 — consumer**\n",
            "## Dependencies and order\n\n`P1.1` → `P1.3` → `P1.2`. Frozen order.\n",
        )
        for declaration in declarations:
            for terminal_item, next_item in (("P1.1", "P1.3"), ("P1.3", "P1.2")):
                with self.subTest(declaration=declaration, terminal_item=terminal_item):
                    phase.write_text(original + "\n" + declaration)
                    positions = {"P1.1": {"result": "closed-green"}}
                    positions[terminal_item] = {"result": "closed-green"}
                    expected = self.plan / "bundles" / f"{next_item}.json"
                    with patch.object(plan_recovery, "_positions", return_value=positions), \
                            patch("task.plan_downstream._all_items", return_value=items), \
                            patch.object(plan_bundle, "producer_readiness") as readiness, \
                            patch.object(plan_bundle, "build", return_value=expected) as build:
                        self.assertEqual(plan_recovery.materialize_next_ready(
                            self.plan, terminal_item), expected)
                    readiness.assert_called_once_with(self.plan, next_item)
                    build.assert_called_once_with(self.plan, next_item)

    def test_successor_diagnosis_precedes_missing_bundle_capture(self):
        self.assertFalse((self.plan / "bundles" / "P1.2.json").exists())
        with self.assertRaises(plan_recovery.RecoveryError) as raised:
            plan_context.capture(self.plan, "P1.2")
        self.assertEqual(raised.exception.code, "OUT_OF_ORDER_REQUEST")
        self.assertEqual(raised.exception.active_item, "P1.1")
        self.assertEqual(raised.exception.mode, "start")
        with self.assertRaises(plan_delivery.DeliveryError) as delivery:
            plan_delivery._validate_priority_continuation(
                self.plan, "task:plan-run RECOVERY P1.2")
        self.assertEqual(delivery.exception.code, "OUT_OF_ORDER_REQUEST")
        self.assertEqual(delivery.exception.verdict["active_item"], "P1.1")

    def test_interrupted_product_work_resumes_same_durable_run_once(self):
        started = self.start()
        journal_path = self.plan / "journal.jsonl"
        before = journal_path.read_bytes()
        product = self.plan / "lib" / "pkg" / "new.py"
        product.write_text("PARTIAL = True\n", encoding="utf-8")
        verdict = plan_recovery.inspect(self.plan, "P1.2")
        self.assertEqual((verdict["code"], verdict["active_item"], verdict["mode"]),
                         ("OUT_OF_ORDER_REQUEST", "P1.1", "resume"))
        resumed = self.start(session_id="session-2")
        self.assertEqual(resumed["run_id"], started["run_id"])
        self.assertEqual(resumed["attempt"], started["attempt"])
        self.assertEqual(journal_path.read_bytes(), before)
        self.assertIn("🟡 In progress", (self.plan / "phases/P1/P1.1.state.md").read_text())

    def test_interruption_between_journal_and_state_projection_recovers_without_second_start(self):
        original_builder = plan_item_state.build_states
        calls = [0]
        def interrupt_after_start(*args, **kwargs):
            calls[0] += 1
            if calls[0] == 1:
                raise OSError("interrupted")
            return original_builder(*args, **kwargs)
        with patch("task.plan_item_state.build_states", side_effect=interrupt_after_start):
            with self.assertRaisesRegex(OSError, "interrupted"):
                self.start()
        original = (self.plan / "journal.jsonl").read_bytes()
        resumed = self.start(session_id="new-session")
        self.assertEqual(resumed["mode"], "resume")
        self.assertEqual((self.plan / "journal.jsonl").read_bytes(), original)
        plan_item_state.build_states(self.plan, item_id="P1.1", check=True)

    def test_terminal_projection_materializes_only_next_ready_bundle_and_delivery_passes(self):
        self.start()
        self.terminal()
        self.assertFalse((self.plan / "bundles/P1.2.json").exists())
        plan_item_state.build_states(self.plan, item_id="P1.1")
        self.assertTrue((self.plan / "bundles/P1.2.json").exists())
        self.assertFalse((self.plan / "bundles/P1.3.json").exists())
        plan_bundle.build(self.plan, "P1.2", check=True)
        plan_context.capture(self.plan, "P1.2")
        plan_delivery._validate_priority_continuation(self.plan, "task:plan-run RECOVERY P1.2")

    def test_start_is_refused_before_journal_when_contract_admission_fails(self):
        before = (self.plan / "journal.jsonl").read_bytes()
        with patch("task.task_contract.pre_mutation", return_value="AUTHORITY_BOUNDARY"):
            with self.assertRaisesRegex(plan_recovery.RecoveryError, "AUTHORITY_BOUNDARY"):
                plan_recovery.start(
                    self.plan, "P1.1", command="plan-run", actor="implementation/high",
                    session_id="session-1", contract={})
        self.assertEqual((self.plan / "journal.jsonl").read_bytes(), before)

    def test_revoked_live_authority_refuses_previously_admitted_start_and_resume(self):
        before = (self.plan / "journal.jsonl").read_bytes()
        with patch("task.task_contract.pre_mutation", return_value=None), \
                patch("task.task_contract._resolve_authority", return_value=("owner-gate", False, "revoked")):
            with self.assertRaisesRegex(plan_recovery.RecoveryError, "AUTHORITY_BOUNDARY"):
                self.start()
        self.assertEqual((self.plan / "journal.jsonl").read_bytes(), before)
        self.start()
        started = (self.plan / "journal.jsonl").read_bytes()
        with patch("task.task_contract._resolve_authority", return_value=("owner-gate", False, "revoked")):
            with self.assertRaisesRegex(plan_recovery.RecoveryError, "AUTHORITY_BOUNDARY"):
                self.start(session_id="session-2")
        self.assertEqual((self.plan / "journal.jsonl").read_bytes(), started)

    def test_ready_independent_item_is_not_rejected_by_semantic_next(self):
        spec = self.plan / "phases/P1/P1.2.md"
        spec.write_text(item_spec_md("P1.2").replace("lib/pkg/config.py", "brief/00-brief.md"))
        self.start()
        self.assertTrue(plan_recovery.inspect(self.plan, "P1.2")["allowed"])

    def test_concurrent_restart_admission_durably_starts_only_once(self):
        contract = {"cold_start": {"plan_id": self.plan.name, "item_id": "P1.1"}}
        def invoke(session):
            return plan_recovery.start(self.plan, "P1.1", command="plan-run",
                                       actor="implementation/high", session_id=session,
                                       contract=contract)
        with patch("task.task_contract.pre_mutation", return_value=None):
            with ThreadPoolExecutor(max_workers=2) as pool:
                first, second = list(pool.map(invoke, ("one", "two")))
        self.assertEqual(first["run_id"], second["run_id"])
        self.assertEqual(len((self.plan / "journal.jsonl").read_text().splitlines()), 1)

    def test_resume_repairs_a_missing_deterministic_bundle_before_snapshot(self):
        self.start()
        (self.plan / "bundles/P1.1.json").unlink()
        resumed = self.start(session_id="two")
        self.assertEqual(resumed["mode"], "resume")
        self.assertTrue((self.plan / "bundles/P1.1.json").is_file())
        plan_context.capture(self.plan, "P1.1")

    def test_prepare_names_the_unresolvable_entry_and_recovery_command(self):
        spec = self.plan / "phases/P1/P1.1.md"
        spec.write_text(spec.read_text().replace(
            "**Inputs:** `lib/pkg/config.py`.",
            "**Inputs:** `lib/pkg/config.py`; explanatory policy prose."), encoding="utf-8")
        with self.assertRaises(plan_recovery.RecoveryError) as raised:
            plan_recovery.prepare(self.plan, "P1.1")
        self.assertEqual(raised.exception.code, "PLAN_BUNDLE_UNRESOLVABLE")
        self.assertIn("explanatory policy prose", raised.exception.verdict["entry"])
        self.assertIn("plan-views.py bundle", raised.exception.verdict["recovery_command"])

    def test_start_contract_cannot_be_reused_for_another_item(self):
        with patch("task.task_contract.pre_mutation", return_value=None):
            with self.assertRaisesRegex(plan_recovery.RecoveryError, "RECOVERY_CONTRACT_IDENTITY_MISMATCH"):
                plan_recovery.start(self.plan, "P1.1", command="plan-run",
                                    actor="implementation/high", session_id="one",
                                    contract={"cold_start": {"plan_id": self.plan.name,
                                                              "item_id": "P1.2"}})
        self.assertEqual((self.plan / "journal.jsonl").read_text(), "")
