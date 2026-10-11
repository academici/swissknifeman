"""The run options this bridge supplies to Task (``extends``) are a literal copy of orch's conductor contract."""
from __future__ import annotations

import json
from pathlib import Path
import unittest

import partner

BRIDGE = Path(__file__).resolve().parents[1]
ORCH = partner.find_orch_root()
CONTRACT = ORCH / "schemas/conductor/v1/run-options.schema.json" if ORCH else None


class SuppliedSchemaTests(unittest.TestCase):
    def test_the_manifest_supplies_the_shipped_schema(self):
        manifest = json.loads((BRIDGE / "bridge.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["extends"], {"orchestration.options": "schemas/run-options.schema.json"})
        supplied = json.loads((BRIDGE / "schemas/run-options.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(supplied["$id"], "urn:swissknifeman:orch:conductor:run-options:v1")

    @unittest.skipUnless(CONTRACT and CONTRACT.is_file(), "orch without the conductor run-options contract")
    def test_the_copy_equals_the_orch_contract(self):
        supplied = json.loads((BRIDGE / "schemas/run-options.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(supplied, json.loads(CONTRACT.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
