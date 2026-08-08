"""P3.6: every plan-lint check declares its layout-v2 disposition."""
import inspect
import json
import sys
import tempfile
import unittest
from pathlib import Path

_LIB = Path(__file__).resolve().parents[1] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from task import plan_gates, plan_lint  # noqa: E402
from task.plan_lint_checks import common, engine, parsing, policy  # noqa: E402

try:
    from .fixtures import write_valid_plan  # noqa: E402
except ImportError:
    from fixtures import write_valid_plan  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "configs" / "lint-check-dispositions.json"
VALUES = {"unchanged", "migrated", "n/a-with-reason"}
MODULES = (common, policy, parsing, engine, plan_gates)


def _checks():
    return {
        f"{module.__name__}.{name}"
        for module in MODULES
        for name, value in inspect.getmembers(module, inspect.isfunction)
        if value.__module__ == module.__name__ and name.startswith("_lint_")
    }


class TestLintCheckDispositions(unittest.TestCase):
    def test_registry_covers_exact_introspected_check_set(self):
        data = json.loads(REGISTRY.read_text(encoding="utf-8"))
        checks = data["checks"]
        self.assertEqual(set(checks), _checks())
        for name, record in checks.items():
            self.assertIn(record.get("disposition"), VALUES, name)
            if record["disposition"] == "n/a-with-reason":
                self.assertTrue(record.get("reason", "").strip(), name)

    def test_v2_decision_rag_and_journal_note_keep_v1_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_dir = write_valid_plan(Path(tmp), "2026.08.08-DEMO", layout="v2")
            decisions = plan_dir / "decisions"
            for index in range(1, 4):
                (decisions / f"D{index}-demo.md").write_text(
                    "---\n"
                    f"id: D{index}\n"
                    "date: 2026-08-08\nstatus: accepted\nitem: ''\nitems: []\n"
                    "supersedes: []\nsuperseded_by: null\n---\n"
                    "## Решение\n\nБез RAG-маркера.\n\n## Почему\n\nТест.\n",
                    encoding="utf-8")
            journal = plan_dir / "journal.jsonl"
            entry = json.loads(journal.read_text(encoding="utf-8"))
            entry["note"] = "x" * 301
            journal.write_text(json.dumps(entry, ensure_ascii=False) + "\n", encoding="utf-8")
            diag = plan_lint.Diagnostics()
            plan_lint.lint_plan(plan_dir, diag)
            self.assertTrue(any("Decision Log: 3 решений" in warning for warning in diag.warnings),
                            diag.warnings)
            self.assertTrue(any("Update Log: запись «Что» 301 символов" in warning
                                for warning in diag.warnings), diag.warnings)

    def test_v2_consequences_uses_record_frontmatter_and_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_dir = write_valid_plan(Path(tmp), "2026.08.08-DEMO", layout="v2")
            plan_md = plan_dir / "plan.md"
            plan_md.write_text(plan_md.read_text(encoding="utf-8").replace(
                "| visibility | private |", "| visibility | private |\n| Closure Protocol | v1 |"),
                encoding="utf-8")
            (plan_dir / "decisions" / "D98-replacement.md").write_text(
                "---\nid: D98\ndate: 2026-08-08\nstatus: accepted\nitem: ''\nitems: []\n"
                "supersedes: []\nsuperseded_by: null\n---\n"
                "## Решение\n\nsupersedes D30 в части объёма.\n\n## Почему\n\nТест.\n",
                encoding="utf-8")
            diag = plan_lint.Diagnostics()
            plan_lint.lint_plan(plan_dir, diag)
            self.assertTrue(any("Decision Log D98" in error for error in diag.errors), diag.errors)
