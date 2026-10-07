from __future__ import annotations

import json
from pathlib import Path
import unittest

from orch import contracts

ORCH = Path(__file__).resolve().parents[1]
SEEDS = sorted((ORCH / "bindings/capabilities").glob("*.json"))
MATRIX = json.loads((ORCH / "bindings/matrix.json").read_text(encoding="utf-8"))
CAPABILITIES = {item["id"]: item for item in MATRIX["capabilities"]}


def _expected(capability: str, binding: str, provider: str) -> str:
    cell = CAPABILITIES[capability][binding]
    return cell.get("by_provider", {}).get(provider, cell["support"])


def _pairs(doc: dict):
    yield "model_set", doc["model"]["set"]
    yield "model_observe", doc["model"]["observe"]
    yield "effort_set", doc["effort"]["set"]
    for name in ("cancel", "resume", "usage"):
        yield name, doc[name]


class CapabilitySeedTests(unittest.TestCase):
    def test_seven_seeds(self):
        self.assertEqual(len(SEEDS), 7)

    def test_seeds_are_valid_declared_and_named_after_binding_provider(self):
        for path in SEEDS:
            with self.subTest(seed=path.name):
                doc = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(contracts.validate(doc, "capability-record"), [])
                self.assertEqual(doc["status"], "declared")
                self.assertEqual(path.stem, f"{doc['binding']}--{doc['provider']}")

    def test_values_match_binding_matrix(self):
        for path in SEEDS:
            doc = json.loads(path.read_text(encoding="utf-8"))
            for capability, value in _pairs(doc):
                with self.subTest(seed=path.name, capability=capability):
                    self.assertEqual(value, _expected(capability, doc["binding"], doc["provider"]))

    def test_skill_delivery_mode_matches_matrix(self):
        for path in SEEDS:
            doc = json.loads(path.read_text(encoding="utf-8"))
            with self.subTest(seed=path.name):
                self.assertEqual(doc["skill_delivery"]["mode"],
                                 _expected("skill_delivery", doc["binding"], doc["provider"]))

    def test_cao_seeds_name_cao_provider(self):
        for path in SEEDS:
            doc = json.loads(path.read_text(encoding="utf-8"))
            if doc["binding"] == "cao":
                with self.subTest(seed=path.name):
                    self.assertIn(doc["extensions"]["cao_provider"], {"claude_code", "codex", "grok_cli"})


if __name__ == "__main__":
    unittest.main()
