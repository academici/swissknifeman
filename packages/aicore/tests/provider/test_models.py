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
