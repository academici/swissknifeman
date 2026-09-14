"""Task's on-demand plan schema stays usable without a separate CORE plugin."""
import importlib.util
import json
from pathlib import Path
import re
import shutil
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "packages/task/scripts/render-provider-commands.py"
spec = importlib.util.spec_from_file_location("task_provider_generator", SCRIPT)
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


class PlanProtocolRuntimeTests(unittest.TestCase):
    def test_relocated_runtime_resolves_schema_and_templates_without_skiller(self):
        projection = generator._plan_protocol_projection(ROOT)
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory)
            for relative, contents in projection.items():
                target = checkout / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(contents)
            self.assertFalse((checkout / "packages/skiller").exists())
            runtime = checkout / generator._PLAN_PROTOCOL_RUNTIME.parent
            body = (runtime / "SKILL.md").read_text()
            references = re.findall(r"\]\(([^)]+)\)", body)
            self.assertIn("references/plan-layout-v2.md", references)
            self.assertIn("snippets/", references)
            for reference in references:
                self.assertTrue((runtime / reference).exists(), reference)
            index = json.loads((runtime / "snippets/index.json").read_text())
            for snippet in index["snippets"]:
                self.assertTrue((runtime / "snippets" / snippet["file"]).is_file(), snippet["file"])
            self.assertIn("Required Reads", (runtime / "references/plan-layout-v2.md").read_text())
            for name in ("journal-template.md", "source-evidence-template.md"):
                template = (runtime / "snippets" / name).read_text()
                self.assertIn('PYTHONPATH="<task-package-root>/lib"', template)
                self.assertNotIn("${CLAUDE_PLUGIN_ROOT}", template)

            self.assertEqual(generator._plan_protocol_runtime_drift(checkout, projection), ())
            victim = runtime / "snippets/plan-template.md"
            victim.write_text("stale template")
            missing = runtime / "references/plan-layout-v2.md"
            missing.unlink()
            self.assertEqual(set(generator._plan_protocol_runtime_drift(checkout, projection)),
                             {victim, missing})

    def test_committed_projection_is_complete_and_does_not_add_discovery_entries(self):
        projection = generator._plan_protocol_projection(ROOT)
        self.assertEqual(generator._plan_protocol_runtime_drift(ROOT, projection), ())
        plugin = json.loads((ROOT / "packages/task/.codex-plugin/plugin.json").read_text())
        self.assertEqual(plugin["skills"], ["./adapters/codex/skills"])
        runtime = ROOT / generator._PLAN_PROTOCOL_RUNTIME.parent
        for discovery in plugin["skills"]:
            self.assertFalse(runtime.is_relative_to(ROOT / "packages/task" / discovery))

    def test_missing_support_canon_is_not_silently_published(self):
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory)
            target = checkout / generator._PLAN_PROTOCOL_SOURCE
            target.parent.mkdir(parents=True)
            shutil.copyfile(ROOT / generator._PLAN_PROTOCOL_SOURCE, target)
            with self.assertRaisesRegex(FileNotFoundError, "support missing"):
                generator._plan_protocol_projection(checkout)
