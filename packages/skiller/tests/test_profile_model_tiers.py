"""Profiles name model classes (aicore model catalog), not model names; the validator accepts both."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLASSES = {"economy", "implementation", "frontier"}


class ModelTiersTests(unittest.TestCase):
    def test_profiles_use_classes(self):
        files = sorted((ROOT / "profiles").glob("*.json"))
        self.assertTrue(files)
        for path in files:
            tiers = json.loads(path.read_text(encoding="utf-8")).get("model_tiers") or {}
            for role, tier in tiers.items():
                self.assertIn(tier, CLASSES, f"{path.name}: model_tiers.{role}")

    def test_the_validator_accepts_a_class_or_a_name(self):
        text = (ROOT / "scripts" / "validate.sh").read_text(encoding="utf-8")
        found = re.search(r"^MODEL_TIERS = \{(.*?)\}", text, re.M).group(1)
        accepted = set(re.findall(r'"([a-z]+)"', found))
        self.assertTrue(CLASSES | {"inherit", "opus", "sonnet", "haiku"} <= accepted, accepted)


if __name__ == "__main__":
    unittest.main()
