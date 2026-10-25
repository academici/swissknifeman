"""Tests of aicore.provider.models and the packaged model catalog."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from aicore.provider import models

EFFORTS = ("low", "medium", "high", "xhigh")
CLASSES = ("economy", "implementation", "frontier")


class TestPackagedCatalog(unittest.TestCase):
    def setUp(self):
        self.catalog = models.load_model_catalog()

    def test_providers_and_order(self):
        self.assertEqual([item.provider_id for item in self.catalog.providers],
                         ["claude-code", "codex", "cursor", "grok"])

    def test_every_provider_has_selectors(self):
        for item in self.catalog.providers:
            for model_class in CLASSES:
                self.assertIsNotNone(models.select_model(self.catalog, item.provider_id, model_class))
            for effort in EFFORTS:
                self.assertIsNotNone(models.select_effort(self.catalog, item.provider_id, effort))

    def test_first_selector_is_the_default(self):
        self.assertEqual(models.select_model(self.catalog, "codex", "frontier"), "gpt-6-astra")
        self.assertEqual(models.select_model(self.catalog, "cursor", "frontier"), "claude-opus-5-thinking-high")
        self.assertEqual(models.select_effort(self.catalog, "claude-code", "xhigh"), "xhigh")

    def test_codex_economy_prefers_verified_gpt_6_luna(self):
        self.assertEqual(models.select_model(self.catalog, "codex", "economy"), "gpt-6-luna")
        self.assertEqual(models.select_model(self.catalog, "codex", "implementation"), "gpt-6-sol")
        inventory = models.inventory(self.catalog, "codex")
        self.assertEqual(inventory["verified_at"], "2026-10-22")
        luna = next(entry for entry in inventory["entries"] if entry["id"] == "gpt-6-luna")
        self.assertEqual(luna["roles"], ["economy", "explore"])
        self.assertEqual(luna["status"], "confirmed")
        self.assertTrue(any(entry["id"] == "gpt-5.6-luna" for entry in inventory["entries"]))
        self.assertNotIn("gork", json.dumps(inventory))

    def test_unknown_provider_class_or_effort_gives_none(self):
        self.assertIsNone(models.select_model(self.catalog, "nope", "frontier"))
        self.assertIsNone(models.select_model(self.catalog, "codex", "huge"))
        self.assertIsNone(models.select_effort(self.catalog, "codex", "max"))
        self.assertIsNone(models.inventory(self.catalog, "nope"))

    def test_inventory_is_a_plain_independent_copy(self):
        first = models.inventory(self.catalog, "cursor")
        self.assertIn("auto_mode", first)
        first["entries"].clear()
        self.assertTrue(models.inventory(self.catalog, "cursor")["entries"])

    def test_catalog_is_read_only(self):
        item = self.catalog.provider("codex")
        with self.assertRaises(TypeError):
            item.class_selectors["economy"] = ("x",)
        with self.assertRaises(AttributeError):
            item.class_selectors["economy"].append("x")


class TestAdmittedClass(unittest.TestCase):
    """The class of a concrete model; the planner's stdlib ``admitted_class`` answers the same for these models."""

    def setUp(self):
        self.catalog = models.load_model_catalog()

    def test_packaged_models_by_id_and_pattern(self):
        for provider, model, expected in [
                ("claude-code", "haiku", "economy"), ("claude-code", "claude-haiku-4-5-20251001", "economy"),
                ("claude-code", "sonnet", "implementation"), ("claude-code", "claude-sonnet-5-5", "implementation"),
                ("claude-code", "claude-opus-5-5", "frontier"),
                ("codex", "gpt-5.6-luna", "economy"), ("codex", "gpt-6-luna", "economy"),
                ("codex", "gpt-6-sol", "implementation"), ("codex", "gpt-6-astra", "frontier"),
                ("codex", "gpt-6.1-sol", "frontier"),
                ("grok", "grok-4.5", "economy"), ("grok", "grok-4.6", "implementation"), ("grok", "grok-4.7", "frontier")]:
            with self.subTest(provider=provider, model=model):
                self.assertEqual(models.admitted_class(self.catalog, provider, model), expected)

    def test_unknown_provider_model_or_roleless_entry_gives_none(self):
        self.assertIsNone(models.admitted_class(self.catalog, "nope", "haiku"))
        self.assertIsNone(models.admitted_class(self.catalog, "claude-code", "mystery-model"))
        self.assertIsNone(models.admitted_class(self.catalog, "claude-code", ""))
        self.assertIsNone(models.admitted_class(self.catalog, "cursor", "auto"))  # routing-assist is no class

    def inventory(self, *entries):
        item = models.ProviderModels("p", {}, {}, models._freeze({"entries": list(entries)}))
        return models.ModelCatalog("1", (item,))

    def test_alias_is_matched_like_an_id_and_shadows_patterns(self):
        catalog = self.inventory({"id": "big", "aliases": ["b"], "roles": ["frontier"], "patterns": ["x.*"]},
                                 {"id": "small", "roles": ["economy"], "patterns": ["b.*"]})
        self.assertEqual(models.admitted_class(catalog, "p", "b"), "frontier")
        self.assertEqual(models.admitted_class(catalog, "p", "big"), "frontier")
        self.assertEqual(models.admitted_class(catalog, "p", "bad"), "economy")  # pattern only without an id match

    def test_retired_entries_are_skipped_and_the_highest_class_wins(self):
        catalog = self.inventory({"id": "old", "roles": ["frontier"], "status": "retired", "patterns": ["m.*"]},
                                 {"id": "m1", "roles": ["economy", "implementation"]},
                                 {"id": "m2", "roles": ["economy"], "patterns": ["m.*"]})
        self.assertIsNone(models.admitted_class(catalog, "p", "old"))
        self.assertEqual(models.admitted_class(catalog, "p", "m1"), "implementation")
        self.assertEqual(models.admitted_class(catalog, "p", "m9"), "economy")  # not the retired frontier pattern

    def test_pattern_must_match_the_whole_model(self):
        catalog = self.inventory({"id": "x", "roles": ["frontier"], "patterns": ["gpt-6"]})
        self.assertIsNone(models.admitted_class(catalog, "p", "gpt-6-luna"))
        self.assertEqual(models.admitted_class(catalog, "p", "gpt-6"), "frontier")


class TestBrokenCatalogs(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.good = json.loads(models.default_model_catalog_path().read_text(encoding="utf-8"))

    def load(self, doc):
        path = Path(self._tmp.name) / "catalog.json"
        path.write_text(doc if isinstance(doc, str) else json.dumps(doc), encoding="utf-8")
        return models.load_model_catalog(path)

    def test_extra_field_names_the_path_and_code(self):
        doc = copy.deepcopy(self.good)
        doc["providers"][0]["extra"] = 1
        with self.assertRaises(models.ModelCatalogError) as caught:
            self.load(doc)
        self.assertEqual((caught.exception.path, caught.exception.code), ("/providers/0/extra", "additional"))

    def test_other_defects(self):
        cases = {}
        doc = copy.deepcopy(self.good)
        del doc["providers"][1]["effort_selectors"]["xhigh"]
        cases["missing"] = doc
        doc = copy.deepcopy(self.good)
        doc["providers"][1]["class_selectors"]["economy"] = []
        cases["empty"] = doc
        doc = copy.deepcopy(self.good)
        doc["providers"].append(copy.deepcopy(doc["providers"][0]))
        cases["duplicate"] = doc
        cases["not json"] = "{"
        for name, doc in cases.items():
            with self.subTest(name=name):
                with self.assertRaises(models.ModelCatalogError):
                    self.load(doc)

    def test_missing_file(self):
        with self.assertRaises(models.ModelCatalogError):
            models.load_model_catalog(Path(self._tmp.name) / "none.json")


if __name__ == "__main__":
    unittest.main()
