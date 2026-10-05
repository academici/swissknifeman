"""Task owns a portable, on-demand plan canon without a separate Skiller plugin."""
import json
from pathlib import Path
import re
import shutil
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
RUNTIME = ROOT / "packages/task/runtime/plan-protocol"


class PlanProtocolRuntimeTests(unittest.TestCase):
    def test_relocated_runtime_resolves_references_without_skiller(self):
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory)
            runtime = checkout / "packages/task/runtime/plan-protocol"
            shutil.copytree(RUNTIME, runtime)
            self.assertFalse((checkout / "packages/skiller").exists())
            body = (runtime / "SKILL.md").read_text()
            references = re.findall(r"\]\(([^)]+)\)", body)
            self.assertIn("references/work-references.md", references)
            for reference in references:
                self.assertTrue((runtime / reference).is_file(), reference)
            self.assertTrue((runtime / "evals/evals.json").is_file())
            self.assertFalse((runtime / "provenance.json").exists())

    def test_task_canon_is_outside_native_skill_discovery(self):
        plugin = json.loads((ROOT / "packages/task/.codex-plugin/plugin.json").read_text())
        self.assertEqual(plugin["skills"], ["./adapters/codex/skills"])
        for discovery in plugin["skills"]:
            self.assertFalse(RUNTIME.is_relative_to(ROOT / "packages/task" / discovery))
        self.assertFalse((ROOT / "packages/skiller/skills/general/plan-protocol").exists())
        self.assertFalse((RUNTIME / "provenance.json").exists())
