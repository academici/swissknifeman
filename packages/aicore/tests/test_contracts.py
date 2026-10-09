"""Every schema of aicore: closed, described, and exercised by its valid and invalid examples."""
import json
import shutil
import tempfile
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
            if node.get("type") == "object" and ("properties" in node or "patternProperties" in node):
                self.assertIs(node.get("additionalProperties"), False, where)
            for name, child in node.get("properties", {}).items():
                self.assertIn("description", child, f"{where}/{name}")
                walk(child, f"{where}/{name}")
            for name, child in node.get("$defs", {}).items():
                self.assertIn("description", child, f"{where}/$defs/{name}")
                walk(child, f"{where}/$defs/{name}")
            for pattern, child in node.get("patternProperties", {}).items():
                self.assertIn("description", child, f"{where}/patternProperties/{pattern}")
                walk(child, f"{where}/patternProperties/{pattern}")
            walk(node.get("items"), f"{where}/items")
            walk(node.get("propertyNames"), f"{where}/propertyNames")

        for contract in CONTRACTS:
            kind = contract.parent.name
            walk(load(contract / f"{kind}.schema.json"), kind)


def pattern_keys(node):
    """Every key of every ``patternProperties`` below ``node``."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "patternProperties":
                yield from value
                for child in value.values():
                    yield from pattern_keys(child)
            elif key in ("properties", "$defs"):
                for child in value.values():
                    yield from pattern_keys(child)
            elif key in ("items", "propertyNames"):
                yield from pattern_keys(value)
            elif key == "oneOf":
                for child in value:
                    yield from pattern_keys(child)


class TestPatternPropertiesInContracts(unittest.TestCase):
    def test_pattern_keys_are_anchored(self):
        for contract in CONTRACTS:
            kind = contract.parent.name
            for pattern in pattern_keys(load(contract / f"{kind}.schema.json")):
                with self.subTest(contract=kind, pattern=pattern):
                    self.assertTrue(pattern.startswith("^") and pattern.endswith("$"), pattern)


class TestCommonContract(unittest.TestCase):
    """The shared definitions, and the R02 rule for namespaced extension keys."""

    FIXTURE = {
        "$schema": schema.DIALECT, "$id": "urn:swissknifeman:aicore:fixture:v1", "title": "fixture",
        "description": "Test fixture that references the shared definitions.", "type": "object",
        "additionalProperties": False,
        "properties": {
            "extensions": {"$ref": "urn:swissknifeman:aicore:common:v1#/$defs/extensions",
                           "description": "Namespaced extension values."},
            "at": {"$ref": "urn:swissknifeman:aicore:common:v1#/$defs/rfc3339_utc",
                   "description": "A timestamp."},
        },
    }

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        shutil.copytree(SCHEMAS / "common", root / "common")
        contract = root / "fixture" / "v1"
        contract.mkdir(parents=True)
        (contract / "fixture.schema.json").write_text(json.dumps(self.FIXTURE), encoding="utf-8")
        schema.clear_registry_cache()
        self.addCleanup(schema.clear_registry_cache)
        self.registry, self.kind = schema.load_contract(contract)

    def codes(self, doc):
        return sorted((issue.path, issue.code) for issue in schema.validate(doc, self.kind, self.registry))

    def test_namespaced_key_passes_with_any_value(self):
        for value in (1, "s", None, [1], {"a": {"b": 2}}):
            with self.subTest(value=value):
                self.assertEqual(self.codes({"extensions": {"acme.flag": value}}), [])
        self.assertEqual(self.codes({"extensions": {"acme.sub.flag-1": True}}), [])

    def test_key_without_namespace_is_additional(self):
        self.assertEqual(self.codes({"extensions": {"flag": 1}}), [("/extensions/flag", "additional")])
        self.assertEqual(self.codes({"extensions": {"Acme.flag": 1}}), [("/extensions/Acme.flag", "additional")])
        self.assertEqual(self.codes({"extensions": {"acme.flag\n": 1}}), [("/extensions/acme.flag\n", "additional")])

    def test_shared_formats(self):
        self.assertEqual(self.codes({"at": "2026-10-09T02:15:31Z"}), [])
        self.assertEqual(self.codes({"at": "2026-10-09T02:15:31.5Z"}), [])
        self.assertEqual(self.codes({"at": "2026-10-09 02:15:31"}), [("/at", "pattern")])

    def test_shared_definitions_match_unit(self):
        unit = load(SCHEMAS / "unit" / "v1" / "unit.schema.json")["$defs"]
        common = load(SCHEMAS / "common" / "v1" / "common.schema.json")["$defs"]
        for name in ("semver", "relpath", "argv", "stability"):
            self.assertEqual(unit[name], common[name], name)


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
