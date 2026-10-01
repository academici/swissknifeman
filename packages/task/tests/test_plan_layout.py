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
        (plan / "plan.md").write_text("## 0. Meta\n\n| Field | Meaning |\n" + row, encoding="utf-8")
        return plan

    def test_missing_layout_is_rejected_as_retired(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._plan(tmp)
            (plan / "phases" / "P1.md").write_text("# P1", encoding="utf-8")
            with self.assertRaisesRegex(plan_layout.PlanLayoutError, "PLAN_LAYOUT_V1_RETIRED"):
                plan_layout.layout_version(plan)

    def test_v2_requires_nested_phase_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._plan(tmp, "v2")
            nested = plan / "phases" / "P1"
            nested.mkdir()
            (nested / "P1.md").write_text("# P1", encoding="utf-8")
            self.assertEqual(plan_layout.phase_path(plan, "P1"), nested / "P1.md")
            self.assertEqual(plan_layout.carrier_path(plan, "item-spec", item_id="P1.1"), nested / "P1.1.md")
            (nested / "P1.1.md").write_text("### P1.1 — item\n", encoding="utf-8")
            self.assertEqual(plan_layout.item_spec_paths(plan, "P1"), [nested / "P1.1.md"])

    def test_v2_phase_directory_without_index_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._plan(tmp, "v2")
            (plan / "phases" / "P1").mkdir()

            with self.assertRaisesRegex(
                plan_layout.PlanLayoutError,
                r"phases/P1/P1\.md",
            ):
                plan_layout.phase_paths(plan)

    def test_unknown_or_mismatched_layout_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._plan(tmp, "v3")
            with self.assertRaises(plan_layout.PlanLayoutError):
                plan_layout.layout_version(plan)

    def test_declared_v1_is_rejected_before_tree_inspection(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._plan(tmp, "v1")
            nested = plan / "phases" / "P1"
            nested.mkdir()
            (nested / "P1.md").write_text("# P1", encoding="utf-8")
            with self.assertRaisesRegex(plan_layout.PlanLayoutError, "PLAN_LAYOUT_V1_RETIRED"):
                plan_layout.layout_version(plan)

    def test_retired_layout_cannot_enter_phase_status_resolution(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._plan(tmp)
            (plan / "phases" / "P1.md").write_text("# P1", encoding="utf-8")
            plan_md = plan / "plan.md"
            plan_md.write_text(plan_md.read_text(encoding="utf-8") + """
## 4. Phase Index & Status Board

| Phase | Title | Items 🟢/total | Status |
|:--|:--|:--|:--|
| P1 | Finished phase | 1/1 | 🟢 Done |
""", encoding="utf-8")
            with self.assertRaisesRegex(plan_layout.PlanLayoutError, "PLAN_LAYOUT_V1_RETIRED"):
                plan_layout.phase_statuses(plan)

    def test_linter_keeps_the_same_phase_model_for_v2(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = write_valid_plan(Path(tmp), layout="v2")
            diag = plan_lint.Diagnostics()
            model = plan_lint.lint_plan(plan, diag)
            self.assertFalse(diag.errors)
            self.assertIn("P1", model["phases"])
            self.assertIn("P1.1", model["phases"]["P1"]["items"])

    def test_linter_requires_v2_decision_pointer_and_no_discussion_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = write_valid_plan(Path(tmp), layout="v2")
            plan_md = plan / "plan.md"
            text = plan_md.read_text(encoding="utf-8").replace(
                "Solutions catalog: `decisions/`; collect: "
                "`python3 packages/task/scripts/plan-views.py decisions`.",
                "| D# | Date | Solution | Why |\n|:--|:--|:--|:--|\n| D1 | 2026-01-01 | old | old |")
            plan_md.write_text(text + "\n## Discussion\n\nOld media.\n", encoding="utf-8")
            diag = plan_lint.Diagnostics()
            plan_lint.lint_plan(plan, diag)
            joined = "\n".join(str(entry) for entry in diag.errors)
            self.assertIn("Decision Log must be a pointer string", joined)
            self.assertIn("«## Discussion» prohibited", joined)

    def test_task_contract_resolves_v2_phase_address(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = write_valid_plan(Path(tmp), layout="v2")
            path = plan / "plan.md"
            text = path.read_text(encoding="utf-8").replace(
                "## 3. Routing\n\n", "## 3. Routing\n\n| Items | Model class/effort | Exec | Why |\n|:--|:--|:--|:--|\n| P1.1 | implementation/medium | run | fixture |\n\n")
            path.write_text(text, encoding="utf-8")
            contract = task_contract.build(plan, "P1.1")
            self.assertIn("route", contract)
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._plan(tmp, "v2")
            (plan / "phases" / "P1.md").write_text("# P1", encoding="utf-8")
            with self.assertRaises(plan_layout.PlanLayoutError):
                plan_layout.layout_version(plan)
