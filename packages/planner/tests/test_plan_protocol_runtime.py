"""Planner owns a portable, on-demand plan canon without a separate plugin."""
import json
from pathlib import Path
import re
import shutil
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
RUNTIME = ROOT / "packages/planner/skills/plan-protocol"


class PlanProtocolRuntimeTests(unittest.TestCase):
    def test_relocated_runtime_resolves_references_in_planner_only_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory)
            runtime = checkout / "packages/planner/skills/plan-protocol"
            shutil.copytree(RUNTIME, runtime)
            self.assertEqual({path.name for path in (checkout / "packages").iterdir()}, {"planner"})
            body = (runtime / "SKILL.md").read_text()
            references = re.findall(r"\]\(([^)]+)\)", body)
            self.assertIn("references/work-references.md", references)
            for reference in references:
                self.assertTrue((runtime / reference).is_file(), reference)
            self.assertTrue((runtime / "evals/evals.json").is_file())
            self.assertFalse((runtime / "provenance.json").exists())

    def test_task_skill_is_registered_with_the_marketplace_plugin(self):
        plugin = json.loads((ROOT / "packages/planner/.codex-plugin/plugin.json").read_text())
        self.assertEqual(plugin["skills"], ["./adapters/codex/skills", "./skills"])
        self.assertTrue(RUNTIME.is_relative_to(ROOT / "packages/planner/skills"))
        claude = json.loads((ROOT / "packages/planner/.claude-plugin/plugin.json").read_text())
        self.assertEqual(claude["skills"], ["./skills"])
        self.assertFalse((RUNTIME / "provenance.json").exists())
