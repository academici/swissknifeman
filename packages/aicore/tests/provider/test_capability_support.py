"""The capability-support/v1 enums equal the Python enums of aicore.provider.values."""
import json
import unittest
from pathlib import Path

from aicore.provider.values import AvailabilityDimension, SupportLevel, SupportSource

CONTRACT = Path(__file__).resolve().parents[2] / "schemas" / "capability-support" / "v1"


class TestEnumParity(unittest.TestCase):
    def setUp(self):
        self.defs = json.loads((CONTRACT / "capability-support.schema.json").read_text(encoding="utf-8"))["$defs"]

    def test_level(self):
        self.assertEqual([item.value for item in SupportLevel], self.defs["level"]["enum"])

    def test_source(self):
        self.assertEqual([item.value for item in SupportSource], self.defs["source"]["enum"])

    def test_dimension(self):
        self.assertEqual([item.value for item in AvailabilityDimension], self.defs["dimension"]["enum"])

    def test_unsupported_is_a_feature_level_only(self):
        description = json.loads((CONTRACT / "capability-support.schema.json").read_text(encoding="utf-8"))["description"]
        for word in ("resource", "policy", "health"):
            self.assertIn(word, description)


if __name__ == "__main__":
    unittest.main()
