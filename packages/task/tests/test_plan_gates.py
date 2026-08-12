"""D2/P3 gate tests: v2 refuses, v1 remains silent."""
import copy
import shutil
import tempfile
import unittest
import unittest.mock
from pathlib import Path

try:
    from .fixtures import write_valid_plan
except ImportError:
    from fixtures import write_valid_plan

from task import journal, plan_bundle, plan_gates, plan_item_state, plan_lint, plan_status, plan_weight


DATA = Path(__file__).resolve().parent / "data"


def lint(plan_dir):
    diag = plan_lint.Diagnostics()
    plan_lint.lint_plan(plan_dir, diag)
    return diag


class TestReadBudgetGate(unittest.TestCase):
    def copied_fixture(self, name):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        target = Path(tmp.name) / name
        shutil.copytree(DATA / name, target)
        return target

    def test_v1_is_unconditionally_silent(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_dir = write_valid_plan(Path(tmp), layout=None)
            diag = lint(plan_dir)
        self.assertFalse(any(plan_gates.GATE_ID in row for row in diag.errors), diag.errors)

    def test_v1_phase_candidate_fingerprint_ignores_audit_append_but_tracks_item_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_dir = write_valid_plan(Path(tmp), layout=None)
            before = plan_gates.phase_candidate_fingerprint(plan_dir, "P1")
            phase = plan_dir / "phases" / "P1.md"
            phase.write_text(
                phase.read_text(encoding="utf-8")
                + "\n## Audit P1 — 2026-08-12\n\n**Вердикт: GREEN**\n",
                encoding="utf-8",
            )
            after_audit = plan_gates.phase_candidate_fingerprint(plan_dir, "P1")
            self.assertEqual(after_audit["fingerprint"], before["fingerprint"])

            phase.write_text(
                phase.read_text(encoding="utf-8").replace(
                    "**Intent:** Добавить проверку.",
                    "**Intent:** Добавить проверку и изменённый контракт.",
                ),
                encoding="utf-8",
            )
            after_item_change = plan_gates.phase_candidate_fingerprint(plan_dir, "P1")
            self.assertNotEqual(after_item_change["fingerprint"], before["fingerprint"])

    def test_overweight_v2_item_names_item_weight_threshold_and_unit(self):
        diag = lint(self.copied_fixture("plan-v2-overweight"))
        rows = [row for row in diag.errors if plan_gates.GATE_ID in row]
        self.assertTrue(rows, diag.errors)
        self.assertTrue(any("P1.1" in row and "порога 100" in row
                            and "gpt-5.6-terra" in row for row in rows), rows)

    def test_rebuilt_item_passes_with_frozen_production_threshold(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        plan_dir = write_valid_plan(Path(tmp.name), layout="v2")
        journal.append(plan_dir, journal.new_entry(
            plan_id=plan_dir.name, item_id="P1.1", command="plan-run",
            actor="implementation/high", result="in-progress",
        ))
        plan_item_state.build_states(plan_dir)
        plan_status.build_status(plan_dir)
        contract = plan_dir / "root" / "contracts" / "read-budget-v1.md"
        contract.write_text(contract.read_text(encoding="utf-8").replace(
            "<= 100000", "<= 100"), encoding="utf-8")
        self.assertTrue(any(plan_gates.GATE_ID in row for row in lint(plan_dir).errors))
        contract.write_text(contract.read_text(encoding="utf-8").replace(
            "<= 100", "<= 100000"), encoding="utf-8")
        diag = lint(plan_dir)
        self.assertFalse(any(plan_gates.GATE_ID in row for row in diag.errors), diag.errors)

    def test_oversized_file_names_file_and_both_limits(self):
        plan_dir = self.copied_fixture("plan-v2")
        large = plan_dir / "brief" / "00-brief.md"
        large.write_text("x" * 300000, encoding="utf-8")
        plan_bundle.build(plan_dir, "P1.1")
        diag = lint(plan_dir)
        rows = [row for row in diag.errors if plan_gates.GATE_ID in row]
        self.assertTrue(any("brief/00-brief.md" in row and "262144 байт" in row
                            and "25000 токенов" in row for row in rows), rows)

    def test_missing_contract_fails_closed(self):
        plan_dir = self.copied_fixture("plan-v2")
        (plan_dir / "root" / "contracts" / "read-budget-v1.md").unlink()
        diag = lint(plan_dir)
        self.assertTrue(any("контракт порога" in row for row in diag.errors), diag.errors)

    def test_archived_plan_skips_execution_only_read_budget_gate(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        plan_dir = Path(tmp.name) / "plans" / "archive" / "plan-v2"
        plan_dir.parent.mkdir(parents=True)
        shutil.copytree(DATA / "plan-v2", plan_dir)
        (plan_dir / "root" / "contracts" / "read-budget-v1.md").unlink()
        diag = lint(plan_dir)
        self.assertFalse(any(plan_gates.GATE_ID in row for row in diag.errors), diag.errors)

    def test_archived_plan_skips_execution_only_return_loop_gates(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        plan_dir = Path(tmp.name) / "plans" / "archive" / "plan-v2"
        plan_dir.parent.mkdir(parents=True)
        shutil.copytree(DATA / "plan-v2", plan_dir)
        diag = lint(plan_dir)
        with unittest.mock.patch.object(plan_gates, "_lint_return_escalation_qualification") as qualification, \
                unittest.mock.patch.object(plan_gates, "_lint_return_owner_authorization") as authorization, \
                unittest.mock.patch.object(plan_gates, "_lint_terminal_phase_unresolved_decisions") as unresolved:
            plan_gates.lint_return_loop(plan_dir, "v2", diag)
        qualification.assert_not_called()
        authorization.assert_not_called()
        unresolved.assert_not_called()

    def test_missing_calibration_and_limit_are_errors(self):
        plan_dir = self.copied_fixture("plan-v2")
        for message in ("артефакт калибровки не читается", "артефакт лимита чтения не читается"):
            with self.subTest(message=message), unittest.mock.patch.object(
                    plan_gates.plan_weight, "Measurer",
                    side_effect=plan_weight.PlanWeightError(message)):
                diag = lint(plan_dir)
            self.assertTrue(any(message in row for row in diag.errors), diag.errors)

    def test_clean_v2_bundle_and_views_are_fresh(self):
        diag = lint(self.copied_fixture("plan-v2"))
        self.assertFalse(any(plan_gates.BUNDLE_GATE_ID in row for row in diag.errors), diag.errors)

    def test_future_phase_is_outside_bundle_materialization_scope(self):
        plan_dir = self.copied_fixture("plan-v2")
        (plan_dir / "bundles" / "P1.1.json").unlink()
        status = plan_dir / "status.md"
        status.write_text(status.read_text(encoding="utf-8").replace(
            "| P1 | Фаза раз | 0/1 | 🟡 In progress |",
            "| P1 | Фаза раз | 0/1 | ⬜ Not started |"), encoding="utf-8")
        diag = lint(plan_dir)
        self.assertFalse(any("P1.1: missing_entry" in row for row in diag.errors), diag.errors)

    def test_stale_fixture_reports_every_frozen_bundle_code(self):
        diag = lint(self.copied_fixture("plan-v2-stale"))
        messages = "\n".join((*diag.errors, *diag.warnings))
        for code in ("missing_entry", "stale_vs_spec", "hash_mismatch",
                     "unresolvable_entry", "extraneous_entry"):
            with self.subTest(code=code):
                self.assertIn(code, messages)
        self.assertTrue(any("extraneous_entry" in row for row in diag.warnings), diag.warnings)
        self.assertFalse(any("extraneous_entry" in row for row in diag.errors), diag.errors)

    def test_unilateral_decision_link_names_both_records(self):
        plan_dir = self.copied_fixture("plan-v2")
        old = plan_dir / "decisions" / "D1-fixture.md"
        old.write_text(old.read_text(encoding="utf-8").replace(
            "status: accepted\n", "status: superseded\n").replace(
            "superseded_by: null\n", "superseded_by: D2\n"), encoding="utf-8")
        (plan_dir / "decisions" / "D2-fixture.md").write_text(
            "---\nid: D2\ndate: 2026-07-03\nstatus: accepted\nitem: P1.1\n"
            "items: [P1.1]\nsupersedes: []\nsuperseded_by: null\n---\n"
            "## Решение\n\nFixture.\n\n## Почему\n\nFixture.\n", encoding="utf-8")
        diag = lint(plan_dir)
        rows = [row for row in diag.errors if plan_gates.BUNDLE_GATE_ID in row]
        self.assertTrue(any("D1" in row and "D2" in row for row in rows), rows)

    def test_path_order_and_history_boundary_use_declared_registry(self):
        plan_dir = self.copied_fixture("plan-v2")
        spec = copy.deepcopy(plan_gates.plan_layout.read_path_spec())
        registry = copy.deepcopy(plan_gates.plan_layout.registry())
        executor = spec["paths"]["executor"]["slots"]
        executor[0]["carrier_id"] = "item-state"
        executor[-1]["carrier_id"] = "plan-core"
        executor[2]["carrier_id"] = "history-view"
        with unittest.mock.patch.object(plan_gates.plan_layout, "read_path_spec", return_value=spec), \
                unittest.mock.patch.object(plan_gates.plan_layout, "registry", return_value=registry):
            diag = lint(plan_dir)
        rows = [row for row in diag.errors if plan_gates.PATH_GATE_ID in row]
        self.assertTrue(any("монотонный предикат порядка" in row for row in rows), rows)
        self.assertTrue(any("history" in row and "executor" in row for row in rows), rows)

    def test_terminal_item_input_is_rejected_but_sibling_is_not_a_rule(self):
        plan_dir = self.copied_fixture("plan-v2")
        spec = plan_dir / "phases" / "P1" / "P1.1.md"
        spec.write_text(spec.read_text(encoding="utf-8").replace(
            "`brief/00-brief.md`", "`phases/P0/P0.1.md`", 1), encoding="utf-8")
        diag = lint(plan_dir)
        rows = [row for row in diag.errors if plan_gates.PATH_GATE_ID in row]
        self.assertTrue(any("терминальной фазы" in row and "P1.1" in row for row in rows), rows)


if __name__ == "__main__":
    unittest.main()
