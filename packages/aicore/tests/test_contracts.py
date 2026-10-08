"""Every schema of aicore: closed, described, and exercised by its valid and invalid examples."""
import json
import unittest
from pathlib import Path

from aicore.util import schema

SCHEMAS = Path(__file__).resolve().parent.parent / "schemas"
CONTRACTS = sorted(path.parent for path in SCHEMAS.glob("*/v*/*.schema.json"))


def examples(contract: Path, group: str) -> list:
    return sorted((contract / "examples" / group).glob("*.json"))


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class TestContractExamples(unittest.TestCase):
    def test_contracts_are_found(self):
        self.assertTrue({"unit", "check-result", "digest"} <= {path.parent.name for path in CONTRACTS})

    def test_every_contract_loads_under_the_closed_profile(self):
        for contract in CONTRACTS:
            with self.subTest(contract=f"{contract.parent.name}/{contract.name}"):
                registry, kind = schema.load_contract(contract)
                self.assertEqual(kind, contract.parent.name)
                self.assertEqual(registry.for_kind(kind)[1], f"urn:swissknifeman:aicore:{kind}:{contract.name}")

    def test_example_counts(self):
        for contract in CONTRACTS:
            with self.subTest(contract=contract.parent.name):
                self.assertGreaterEqual(len(examples(contract, "valid")), 1)
                self.assertGreaterEqual(len(examples(contract, "invalid")), 3)

    def test_valid_examples_pass_and_invalid_fail(self):
        for contract in CONTRACTS:
            registry, kind = schema.load_contract(contract)
            for path in examples(contract, "valid"):
                with self.subTest(example=f"{kind}/valid/{path.name}"):
                    self.assertEqual(schema.validate(load(path), kind, registry), [])
            for path in examples(contract, "invalid"):
                with self.subTest(example=f"{kind}/invalid/{path.name}"):
                    self.assertNotEqual(schema.validate(load(path), kind, registry), [])

    def test_every_object_is_closed_and_every_property_described(self):
        def walk(node, where):
            if not isinstance(node, dict):
                return
            if node.get("type") == "object" and "properties" in node:
                self.assertIs(node.get("additionalProperties"), False, where)
            for name, child in node.get("properties", {}).items():
                self.assertIn("description", child, f"{where}/{name}")
                walk(child, f"{where}/{name}")
            for name, child in node.get("$defs", {}).items():
                self.assertIn("description", child, f"{where}/$defs/{name}")
                walk(child, f"{where}/$defs/{name}")
            walk(node.get("items"), f"{where}/items")

        for contract in CONTRACTS:
            kind = contract.parent.name
            walk(load(contract / f"{kind}.schema.json"), kind)


class TestDigestContract(unittest.TestCase):
    def test_digest_schema_accepts_only_tagged_form(self):
        contract = SCHEMAS / "digest" / "v1"
        registry, kind = schema.load_contract(contract)
        tagged = "sha256:" + "0" * 64
        self.assertEqual(schema.validate(tagged, kind, registry), [])
        for bad in (tagged.upper(), "0" * 64, tagged + "0", 5):
            self.assertTrue(schema.validate(bad, kind, registry), repr(bad))
        root, owner = registry.resolve("#/$defs/hex", registry.for_kind(kind)[1])
        self.assertEqual(schema.validate_node(registry, root, owner, "0" * 64), [])
        self.assertTrue(schema.validate_node(registry, root, owner, tagged))


if __name__ == "__main__":
    unittest.main()
