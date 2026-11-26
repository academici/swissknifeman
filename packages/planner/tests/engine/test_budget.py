"""``budget.measure`` / ``plan.py context --budget``: size report of a context pack, read-only."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

_LIB = Path(__file__).resolve().parents[2] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from planner.plan import budget, context, ops  # noqa: E402

try:
    from . import test_context, test_lifecycle
except ImportError:  # run as `discover -s tests/engine` (no parent package)
    import test_context
    import test_lifecycle

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "plan.py"
SECTIONS = [{"id": "s", "title": "S", "text": "t" * 2000}]


class BudgetTests(test_lifecycle.LifeCase):
    def setUp(self):
        super().setUp()
        ops.add_document(self.root, {"id": "loose", "title": "Loose", "sections": SECTIONS})
        ops.add_document(self.root, {"id": "bound", "title": "Bound", "applies_to": ["P1.1"], "sections": SECTIONS})

    def set_mode(self, mode):
        ops.patch(self.load(), "plan", {"settings": {"context_pack": mode}})

    def read_bound(self):
        test_context.force_patch(self.root, "P1.1", {"reads": [
            {"path": "@plan/knowledge/bound.json", "why": "w", "required": True}]})

    def test_legacy_reports_unbound_content_and_a_smaller_scoped_preview(self):
        self.set_mode("legacy")
        report = budget.measure(self.load(), "P1.1")
        loose = next(s for s in report["sources"] if s["ref"] == "knowledge/loose")
        self.assertEqual(loose["reason"], "unbound")
        self.assertEqual(report["unbound"]["documents"], 1)
        self.assertEqual(report["unbound"]["bytes"], loose["bytes"])
        self.assertLess(report["scoped_preview_bytes"], report["bytes"])
        self.assertEqual(report["bytes"], len(context.render(self.load(), "P1.1", with_scout=False).encode()))
        self.assertEqual(self.load().plan["settings"]["context_pack"], "legacy")

    def test_a_read_of_a_bound_document_is_a_duplicate(self):
        self.set_mode("legacy")
        self.read_bound()
        report = budget.measure(self.load(), "P1.1")
        self.assertEqual(report["duplicates"]["reads"], 1)
        read = next(s for s in report["sources"] if s["key"] == "reads")
        self.assertEqual(read["duplicate_of"], "documents")

    def test_scoped_has_no_preview_and_no_unbound_bytes(self):
        self.read_bound()
        report = budget.measure(self.load(), "P1.1")
        self.assertEqual(report["mode"], "scoped")
        self.assertNotIn("scoped_preview_bytes", report)
        self.assertEqual(report["unbound"], {"documents": 0, "decisions": 0, "bytes": 0})
        self.assertEqual(next(s for s in report["sources"] if s["key"] == "reads")["duplicate_of"], "documents")

    def test_budget_threshold_and_deterministic_order(self):
        self.assertFalse(budget.measure(self.load(), "P1.1")["over_budget"])
        ops.patch(self.load(), "plan", {"settings": {"context_budget_kb": 1}})
        report = budget.measure(self.load(), "P1.1")
        self.assertTrue(report["over_budget"])
        keys = [(-s["bytes"], s["key"], s["ref"]) for s in report["sources"]]
        self.assertEqual(keys, sorted(keys))
        self.assertIn("OVER", budget.text(report))

    def test_text_names_the_fix_for_unbound_content(self):
        self.set_mode("legacy")
        lines = budget.text(budget.measure(self.load(), "P1.1"))
        self.assertIn("unbound: 1 document(s)", lines)
        self.assertIn("scoped preview:", lines)

    def test_measure_writes_nothing(self):
        budget.measure(self.load(), "P1.1")
        self.assertFalse((self.root / "context").exists())

    def run_cli(self, *extra):
        return subprocess.run([sys.executable, str(SCRIPT), "context", str(self.root), "P1.1", *extra],
                              capture_output=True, text=True, timeout=30)

    def test_cli_json_report_writes_no_pack(self):
        result = self.run_cli("--budget", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["item"], "P1.1")
        self.assertFalse((self.root / "context").exists())
        self.assertIn("P1.1", self.run_cli("--budget").stdout)

    def test_cli_budget_refuses_stdout(self):
        self.assertEqual(self.run_cli("--budget", "--stdout").returncode, 2)


if __name__ == "__main__":
    unittest.main()
