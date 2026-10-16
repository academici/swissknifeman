"""gui.contracts.bundle and `gui schemas bundle`: self-contained, deterministic, equivalent for the examples."""
import json
import tempfile
import unittest
from pathlib import Path

from aicore.util import schema

from gui import contracts
from tests.test_cli import run_main

MODULE_ROOT = Path(__file__).resolve().parents[1]
UNIT = json.loads((MODULE_ROOT / "unit.json").read_text(encoding="utf-8"))
NAMES = [entry["id"].rpartition(":")[2] for entry in UNIT["provides"]["contracts"]]


def refs(node):
    if isinstance(node, dict):
        if isinstance(node.get("$ref"), str):
            yield node["$ref"]
        for value in node.values():
            yield from refs(value)
    elif isinstance(node, list):
        for value in node:
            yield from refs(value)


class TestBundle(unittest.TestCase):
    def test_every_contract_bundles_without_external_refs(self):
        for name in NAMES:
            with self.subTest(contract=name):
                document = contracts.bundle(name)
                found = list(refs(document))
                self.assertTrue(all(ref.startswith("#/$defs/") for ref in found), found)
                for ref in found:
                    self.assertIn(ref[len("#/$defs/"):], document.get("$defs", {}))
                self.assertNotIn("packages/", json.dumps(document))  # no path of a module reaches the frontend

    def test_deterministic(self):
        for name in NAMES:
            self.assertEqual(json.dumps(contracts.bundle(name), sort_keys=True),
                             json.dumps(contracts.bundle(name), sort_keys=True))

    def test_bundle_keeps_the_meaning_for_the_examples(self):
        """A local validator over the bundle answers like the contract for every example."""
        for name in NAMES:
            document = contracts.bundle(name)
            folder = Path(tempfile.mkdtemp()) / name / "v1"
            folder.mkdir(parents=True)
            urn = f"urn:swissknifeman:bundle:{name}:v1"
            (folder / f"{name}.schema.json").write_text(json.dumps({**document, "$id": urn}), encoding="utf-8")
            registry, kind = schema.load_contract(folder, urn_prefix="urn:swissknifeman:bundle:")
            for group, valid in (("valid", True), ("invalid", False)):
                for example in sorted((contracts.contract_dir(name) / "examples" / group).glob("*.json")):
                    with self.subTest(example=f"{name}/{group}/{example.name}"):
                        issues = schema.validate(json.loads(example.read_text(encoding="utf-8")), kind, registry)
                        self.assertEqual(valid, not issues, issues)

    def test_cli_writes_one_file_per_contract(self):
        out = Path(tempfile.mkdtemp())
        code, stdout, _ = run_main("schemas", "bundle", "--out", str(out))
        self.assertEqual(0, code)
        self.assertEqual(sorted(f"{name}.schema.json" for name in NAMES), sorted(p.name for p in out.iterdir()))
        self.assertEqual(contracts.bundle("run"), json.loads((out / "run.schema.json").read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
