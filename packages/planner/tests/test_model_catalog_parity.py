"""The model selectors in command-routing.json are a transitional copy of the aicore model catalog."""
import json
from pathlib import Path
import unittest

from core.provider.models import load_model_catalog

ROUTING_PATH = Path(__file__).resolve().parents[1] / "configs" / "command-routing.json"
FIELDS = ("class_selectors", "effort_selectors", "model_inventory")
HINT = "update packages/aicore/configs/model-catalog.json and the transitional copy together"


class ModelCatalogParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mappings = json.loads(ROUTING_PATH.read_text(encoding="utf-8"))["mappings"]
        cls.catalog = load_model_catalog()

    def test_same_providers_in_the_same_order(self):
        self.assertEqual([item.provider_id for item in self.catalog.providers], list(self.mappings), HINT)

    def test_selectors_and_inventory_are_equal_per_provider(self):
        for provider in self.catalog.providers:
            expected = {
                "class_selectors": {key: list(value) for key, value in provider.class_selectors.items()},
                "effort_selectors": {key: list(value) for key, value in provider.effort_selectors.items()},
                "model_inventory": provider.inventory_dict(),
            }
            for field in FIELDS:
                with self.subTest(provider=provider.provider_id, field=field):
                    self.assertEqual(self.mappings[provider.provider_id][field], expected[field],
                                     f"{field} of {provider.provider_id} differs: {HINT}")


if __name__ == "__main__":
    unittest.main()
