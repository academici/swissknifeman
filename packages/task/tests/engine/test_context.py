"""Context pack (dossier §7): golden pack, section extraction, reads, lessons, decisions, start integration."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_LIB = Path(__file__).resolve().parents[2] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from task.plan import context, lifecycle, ops, store  # noqa: E402
from task.plan.model import PlanError  # noqa: E402

try:
    from . import test_lifecycle
except ImportError:  # run as `discover -s tests/engine` (no parent package)
    import test_lifecycle

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "plan.py"
DOC = """# Title

## 1. Overview

Intro.

## 2. Validation

Body line.

```text
## fenced, not a heading
```

### 2.1 Error format

Nested body.

## 3. `Out` of scope

Last.

## Empty

## Tail
tail text
"""


class SectionTests(unittest.TestCase):
    def test_numbered_and_named_headings(self):
        self.assertEqual(context.extract_section(DOC, "§1"), "Intro.")
        self.assertEqual(context.extract_section(DOC, "§2.1"), "Nested body.")
        self.assertEqual(context.extract_section(DOC, "§2 Validation").splitlines()[0], "Body line.")  # N alone decides
        self.assertEqual(context.extract_section(DOC, "validation").splitlines()[0], "Body line.")  # case-insensitive
        self.assertEqual(context.extract_section(DOC, "Error format"), "Nested body.")  # substring tier
        self.assertEqual(context.extract_section(DOC, "out of scope"), "Last.")  # markup ignored in headings

    def test_a_section_runs_to_the_next_heading_of_the_same_or_higher_level(self):
        body = context.extract_section(DOC, "§2")
        self.assertIn("### 2.1 Error format", body)  # a deeper heading stays inside
        self.assertIn("Nested body.", body)
        self.assertNotIn("Last.", body)
        self.assertIn("## fenced, not a heading", body)  # fenced lines are never headings

    def test_missing_empty_and_last_sections(self):
        self.assertIsNone(context.extract_section(DOC, "§9"))
        self.assertIsNone(context.extract_section(DOC, "Nonexistent"))
        self.assertEqual(context.extract_section(DOC, "Empty"), "")
        self.assertEqual(context.extract_section(DOC, "Tail"), "tail text")


class JsonContextTests(test_lifecycle.LifeCase):
    def test_complete_context_is_json_and_deterministic(self):
        text = context.render(self.load(), "P1.1")
        value = json.loads(text)
        self.assertEqual(value["item"]["id"], "P1.1")
        self.assertEqual(value["brief"]["messages"][0]["text"], "m")
        path = context.build(self.load(), "P1.1")
        self.assertEqual(path.name, "P1.1.json")
        self.assertEqual(path.read_text(), text)
        self.assertEqual(context.render(self.load(), "P1.1"), text)

    def test_all_lessons_survive_without_a_read_budget(self):
        for n in range(12):
            lifecycle.log(self.root, "P1.1", "difficulty", f"problem {n}")
        lessons = context.collect(self.load(), "P1.1")["lessons"]
        self.assertEqual([e["summary"] for e in lessons], [f"problem {n}" for n in range(12)])

    def test_long_supporting_sections_are_not_truncated(self):
        text = "\n".join(f"line {n}" for n in range(501))
        (self.root.parent.parent / "runbook.md").write_text("## Runbook\n" + text)
        ops.patch(self.root, "P1.1", {"reads": [{"path": "runbook.md", "section": "Runbook", "why": "steps", "required": True}]})
        self.assertEqual(context.collect(self.load(), "P1.1")["reads"][0]["content"], text)

    def test_knowledge_sections_and_provenance_are_preserved(self):
        ops.add_document(self.root, {"id": "design", "title": "Design", "applies_to": ["P1.1"],
            "sections": [{"id": "steps", "title": "Steps", "text": "do everything\n" * 400}]})
        ops.patch(self.root, "P1.1", {"reads": [{"path": "@plan/knowledge/design.json", "section": "steps", "why": "steps", "required": True}]})
        value = context.collect(self.load(), "P1.1")
        self.assertEqual(value["reads"][0]["content"]["sections"], value["documents"][0]["sections"])
        self.assertEqual(context.collect(self.load(), "P1.2")["documents"], [])

    def test_views_never_supply_agent_input(self):
        ops.patch(self.root, "P1.1", {"reads": [{"path": "@plan/views/plan.md", "section": "Goal", "why": "bad", "required": False}]})
        self.refused("HUMAN_VIEW", lambda root: lifecycle.start(root, ["P1.1"], test_lifecycle.OPUS))
        self.assertEqual(self.load().items["P1.1"]["status"], "todo")

    def test_missing_required_input_is_refused_without_mutation(self):
        ops.patch(self.root, "P1.1", {"reads": [{"path": "gone.py", "why": "needed", "required": True}]})
        self.refused("READ_MISSING", lambda root: lifecycle.start(root, ["P1.1"], test_lifecycle.OPUS))

    def test_authored_plan_markdown_is_not_an_execution_source(self):
        (self.root / "notes.md").write_text("Private old plan notes")
        ops.patch(self.root, "P1.1", {"reads": [{"path": "@plan/notes.md", "why": "bad", "required": True}]})
        self.refused("HUMAN_VIEW", lambda root: lifecycle.start(root, ["P1.1"], test_lifecycle.OPUS))

    def test_upstream_results_and_foreign_decisions_remain_structured(self):
        self.start("P1.1")
        self.finish("P1.1", "done_with_deviations", notes="result", deviations=["slow"], pending=["docs"])
        ops.patch(self.root, "P1.2", {"decisions": ["PLAN3.D4"]})
        value = context.collect(self.load(), "P1.2")
        self.assertEqual(value["upstream"][0]["result"]["deviations"], ["slow"])
        entry, = value["decisions"]  # superset of the former {"ref", "loaded": False}; the resolver adds a reason
        self.assertEqual((entry["ref"], entry["loaded"]), ("PLAN3.D4", False))
        self.assertTrue(entry["reason"].startswith("PLAN_NOT_FOUND: "))

    def test_start_and_resume_build_json_inputs(self):
        started = self.start("P1.1", "P1.2")
        self.assertEqual([p.name for p in started.packs], ["P1.1.json", "P1.2.json"])
        started.packs[0].write_text("stale")
        self.start("P1.1")
        self.assertEqual(json.loads(started.packs[0].read_text())["item"]["status"], "in_progress")

    def test_cli_stdout_is_json_and_does_not_write_a_pack(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "context", str(self.root), "P1.1", "--stdout"],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["item"]["id"], "P1.1")
        self.assertFalse((self.root / "context").exists())


if __name__ == "__main__":
    unittest.main()
