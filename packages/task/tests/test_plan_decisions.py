import tempfile
import unittest
from pathlib import Path
import sys

_LIB = Path(__file__).resolve().parents[1] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from task import plan_decisions


def decision(identifier, *, status="accepted", supersedes="[]", superseded_by="null",
             date_value="2026-08-08"):
    return f"""---
id: {identifier}
date: {date_value}
status: {status}
item: P2.2
items: [P2.2]
supersedes: {supersedes}
superseded_by: {superseded_by}
---
## Solution

{identifier} solution.

## Why

Verification.
""" + ("\n## Consequences\n\nReplacement.\n" if supersedes != "[]" else "")


class PlanDecisionsTest(unittest.TestCase):
    def test_date_is_calendar_valid_without_imposing_monotonic_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._plan(tmp)
            path = plan / "decisions" / "D1-first.md"
            for invalid in ("2026-99-99", "2025-02-29"):
                path.write_text(decision("D1", date_value=invalid), encoding="utf-8")
                with self.subTest(invalid=invalid), self.assertRaisesRegex(
                        plan_decisions.DecisionError, "calendar-valid"):
                    plan_decisions.load_decisions(plan)
            path.write_text(decision("D1", date_value="2024-02-29"), encoding="utf-8")
            self.assertEqual(plan_decisions.load_decisions(plan)[0].date, "2024-02-29")
    def _plan(self, root):
        plan = Path(root) / "plan"
        (plan / "decisions").mkdir(parents=True)
        (plan / "phases" / "P2").mkdir(parents=True)
        (plan / "plan.md").write_text("## 0. Meta\n\n| Field | Meaning |\n|:--|:--|\n| Layout | v2 |\n", encoding="utf-8")
        (plan / "phases" / "P2" / "P2.md").write_text("# P2\n", encoding="utf-8")
        return plan

    def test_builds_four_deterministic_views_and_check_detects_edit(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._plan(tmp)
            (plan / "decisions" / "D1-first.md").write_text(
                decision("D1", status="superseded", superseded_by="D2"), encoding="utf-8")
            (plan / "decisions" / "D2-second.md").write_text(
                decision("D2", supersedes="[D1]"), encoding="utf-8")
            (plan / "decisions" / "D3-question.md").write_text(
                decision("D3", status="proposed"), encoding="utf-8")
            outputs = plan_decisions.build_views(plan)
            self.assertEqual(len(outputs), 4)
            self.assertIn("D2", (plan / "decisions" / "_current.md").read_text(encoding="utf-8"))
            self.assertIn("D1", (plan / "decisions" / "_archive.md").read_text(encoding="utf-8"))
            self.assertIn("D3", (plan / "open-questions.md").read_text(encoding="utf-8"))
            plan_decisions.build_views(plan, check=True)
            with (plan / "decisions" / "_current.md").open("a", encoding="utf-8") as target:
                target.write("manual edit\n")
            with self.assertRaises(plan_decisions.plan_projection.ProjectionError):
                plan_decisions.build_views(plan, check=True)

    def test_rejects_nonreciprocal_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._plan(tmp)
            (plan / "decisions" / "D1-first.md").write_text(
                decision("D1", status="superseded", superseded_by="D2"), encoding="utf-8")
            (plan / "decisions" / "D2-second.md").write_text(decision("D2"), encoding="utf-8")
            with self.assertRaisesRegex(plan_decisions.DecisionError, "non-reciprocal"):
                plan_decisions.load_decisions(plan)

    def test_rejects_unknown_status_and_missing_history_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._plan(tmp)
            source = decision("D1", status="draft").replace("item: P2.2\n", "")
            (plan / "decisions" / "D1-first.md").write_text(source, encoding="utf-8")
            with self.assertRaises(plan_decisions.DecisionError):
                plan_decisions.load_decisions(plan)
