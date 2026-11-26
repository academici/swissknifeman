"""Models of agent packs come from the aicore model catalog by class: no second table of models in harness."""
import glob
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from aicore.provider.models import load_model_catalog, select_model
from harness import agentpacks

PACKS = Path(__file__).resolve().parents[1] / "configs" / "claude-code" / "agent-packs"


class ModelClassTests(unittest.TestCase):
    def test_every_class_resolves_through_the_catalog_for_both_providers(self):
        catalog = load_model_catalog()
        for provider in ("claude-code", "codex"):
            for model_class in agentpacks.MODEL_CLASSES:
                self.assertEqual(agentpacks.model_for_class(provider, model_class),
                                 select_model(catalog, provider, model_class))

    def test_codex_models_are_the_catalog_ones_not_a_private_table(self):
        self.assertEqual(agentpacks.model_for_class("codex", "implementation"), "gpt-6-sol")
        self.assertFalse(hasattr(agentpacks, "_MODEL_SELECTORS"))

    def test_an_unknown_class_or_provider_is_named(self):
        for provider, model_class in (("codex", "ultra"), ("nobody", "frontier")):
            with self.assertRaises(ValueError) as caught:
                agentpacks.model_for_class(provider, model_class)
            self.assertTrue(str(caught.exception).startswith("HARNESS_MODEL_CLASS_UNKNOWN"), caught.exception)

    def test_a_class_answer_renders_as_the_claude_model_of_the_class(self):
        text = "model: {{MODEL_REVIEWER}}\nmodel: {{MODEL_BUILDER}}\nmodel: {{MODEL_ORCHESTRATOR}}\nname: {{OTHER}}"
        answers = {"MODEL_REVIEWER": "frontier", "MODEL_BUILDER": "sonnet", "MODEL_ORCHESTRATOR": "inherit",
                   "OTHER": "frontier"}
        self.assertEqual(agentpacks._render_template_text(text, answers),
                         "model: opus\nmodel: sonnet\nmodel: inherit\nname: frontier")

    def test_every_pack_model_question_takes_classes_and_names_and_defaults_to_a_class(self):
        found = 0
        for path in sorted(glob.glob(str(PACKS / "*" / "pack.json"))):
            for entry in json.loads(Path(path).read_text(encoding="utf-8")).get("interview", []):
                if not entry["id"].startswith("MODEL_"):
                    continue
                found += 1
                where = f"{path}: {entry['id']}"
                self.assertTrue({"economy", "implementation", "frontier", "opus", "sonnet", "haiku", "inherit"}
                                <= set(entry["enum"]), where)
                if "_common" not in path:
                    self.assertIn(entry["default"], agentpacks.MODEL_CLASSES, where)
        self.assertGreaterEqual(found, 21)


if __name__ == "__main__":
    unittest.main()
