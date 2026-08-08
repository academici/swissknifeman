"""D2 read-budget gate tests: v2 refuses, v1 remains silent."""
import shutil
import tempfile
import unittest
import unittest.mock
from pathlib import Path

try:
    from .fixtures import write_valid_plan
except ImportError:
    from fixtures import write_valid_plan

from task import plan_gates, plan_lint, plan_weight


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

    def test_overweight_v2_item_names_item_weight_threshold_and_unit(self):
        diag = lint(self.copied_fixture("plan-v2-overweight"))
        rows = [row for row in diag.errors if plan_gates.GATE_ID in row]
        self.assertTrue(rows, diag.errors)
        self.assertTrue(any("P1.1" in row and "порога 100" in row
                            and "gpt-5.6-terra" in row for row in rows), rows)

    def test_rebuilt_item_passes_with_frozen_production_threshold(self):
        plan_dir = self.copied_fixture("plan-v2-overweight")
        contract = plan_dir / "root" / "contracts" / "read-budget-v1.md"
        contract.write_text(contract.read_text(encoding="utf-8").replace("<= 100", "<= 100000"),
                            encoding="utf-8")
        diag = lint(plan_dir)
        self.assertFalse(any(plan_gates.GATE_ID in row for row in diag.errors), diag.errors)

    def test_oversized_file_names_file_and_both_limits(self):
        plan_dir = self.copied_fixture("plan-v2")
        large = plan_dir / "brief" / "00-brief.md"
        large.write_text("x" * 300000, encoding="utf-8")
        diag = lint(plan_dir)
        rows = [row for row in diag.errors if plan_gates.GATE_ID in row]
        self.assertTrue(any("brief/00-brief.md" in row and "262144 байт" in row
                            and "25000 токенов" in row for row in rows), rows)

    def test_missing_contract_fails_closed(self):
        plan_dir = self.copied_fixture("plan-v2")
        (plan_dir / "root" / "contracts" / "read-budget-v1.md").unlink()
        diag = lint(plan_dir)
        self.assertTrue(any("контракт порога" in row for row in diag.errors), diag.errors)

    def test_missing_calibration_and_limit_are_errors(self):
        plan_dir = self.copied_fixture("plan-v2")
        for message in ("артефакт калибровки не читается", "артефакт лимита чтения не читается"):
            with self.subTest(message=message), unittest.mock.patch.object(
                    plan_gates.plan_weight, "Measurer",
                    side_effect=plan_weight.PlanWeightError(message)):
                diag = lint(plan_dir)
            self.assertTrue(any(message in row for row in diag.errors), diag.errors)


if __name__ == "__main__":
    unittest.main()
