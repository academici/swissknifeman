import tempfile
import unittest
from pathlib import Path
import sys

_LIB = Path(__file__).resolve().parents[1] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from task import plan_layout
from task import plan_lint
from task import task_contract
try:
    from .fixtures import write_valid_plan
except ImportError:
    from fixtures import write_valid_plan


class PlanLayoutTest(unittest.TestCase):
    def _plan(self, root, layout=None):
        plan = Path(root) / "PLAN"
        (plan / "phases").mkdir(parents=True)
        row = f"| Layout | {layout} |\n" if layout else ""
        (plan / "plan.md").write_text("## 0. Meta\n\n| Поле | Значение |\n" + row, encoding="utf-8")
        return plan

    def test_missing_layout_is_v1_and_resolves_monolith(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._plan(tmp)
            (plan / "phases" / "P1.md").write_text("# P1", encoding="utf-8")
            self.assertEqual(plan_layout.layout_version(plan), "v1")
            self.assertEqual(plan_layout.phase_path(plan, "P1"), plan / "phases" / "P1.md")

    def test_v2_requires_nested_phase_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._plan(tmp, "v2")
            nested = plan / "phases" / "P1"
            nested.mkdir()
            (nested / "P1.md").write_text("# P1", encoding="utf-8")
            self.assertEqual(plan_layout.phase_path(plan, "P1"), nested / "P1.md")
            self.assertEqual(plan_layout.carrier_path(plan, "item-spec", item_id="P1.1"), nested / "P1.1.md")

    def test_unknown_or_mismatched_layout_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._plan(tmp, "v3")
            with self.assertRaises(plan_layout.PlanLayoutError):
                plan_layout.layout_version(plan)

    def test_declared_layout_must_match_phase_tree_in_both_directions(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._plan(tmp, "v1")
            nested = plan / "phases" / "P1"
            nested.mkdir()
            (nested / "P1.md").write_text("# P1", encoding="utf-8")
            with self.assertRaises(plan_layout.PlanLayoutError):
                plan_layout.layout_version(plan)

    def test_linter_keeps_the_same_phase_model_for_v2(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = write_valid_plan(Path(tmp), layout="v2")
            diag = plan_lint.Diagnostics()
            model = plan_lint.lint_plan(plan, diag)
            self.assertFalse(diag.errors)
            self.assertIn("P1", model["phases"])
            self.assertIn("P1.1", model["phases"]["P1"]["items"])

    def test_task_contract_resolves_v2_phase_address(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = write_valid_plan(Path(tmp), layout="v2")
            path = plan / "plan.md"
            text = path.read_text(encoding="utf-8").replace(
                "## 3. Routing\n\n", "## 3. Routing\n\n| Items | Model class/effort | Exec | Почему |\n|:--|:--|:--|:--|\n| P1.1 | implementation/medium | plan-exec | fixture |\n\n")
            path.write_text(text, encoding="utf-8")
            contract = task_contract.build(plan, "P1.1")
            self.assertIn("route", contract)
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._plan(tmp, "v2")
            (plan / "phases" / "P1.md").write_text("# P1", encoding="utf-8")
            with self.assertRaises(plan_layout.PlanLayoutError):
                plan_layout.layout_version(plan)
