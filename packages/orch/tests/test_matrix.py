from __future__ import annotations

import json
from pathlib import Path
import unittest

from orch import contracts
from orch.port import BINDINGS

ROOT = Path(__file__).resolve().parents[1]
IDS = (
    "prepare", "run", "watch", "cancel", "resume", "results", "model_set", "model_observe", "effort_set",
    "skill_delivery", "tool_restrictions", "plan_write_prevention", "usage", "effects", "stream_live",
)
SUPPORT = {"supported", "adapted", "unsupported", "unknown"}
# Provider seeds that P4.3 reconciles with capability records.
SEEDS = {
    ("native", "model_set", "grok"): "supported",
    ("native", "model_observe", "grok"): "unknown",
    ("native", "effort_set", "grok"): "supported",
    ("native", "resume", "grok"): "adapted",
    ("native", "usage", "grok"): "supported",
    ("native", "tool_restrictions", "grok"): "supported",
    ("native", "skill_delivery", "grok"): "unknown",
    ("native", "model_observe", "codex"): "adapted",
    ("native", "skill_delivery", "claude-code"): "native_plugin_dir",
    ("native", "skill_delivery", "codex"): "isolated_home",
    ("cao", "effort_set", "grok"): "unsupported",
}


def load():
    return json.loads((ROOT / "bindings/matrix.json").read_text(encoding="utf-8"))


def skill_modes():
    node, _ = contracts.load_registry().for_kind("capability-record")
    return set(node["properties"]["skill_delivery"]["properties"]["mode"]["enum"])


class MatrixTests(unittest.TestCase):
    def setUp(self):
        self.matrix = load()
        self.rows = {row["id"]: row for row in self.matrix["capabilities"]}

    def test_shape(self):
        self.assertEqual(set(self.matrix), {"version", "bindings", "capabilities"})
        self.assertEqual(self.matrix["version"], 1)
        self.assertEqual(tuple(self.matrix["bindings"]), BINDINGS)
        self.assertEqual(tuple(row["id"] for row in self.matrix["capabilities"]), IDS)

    def test_every_capability_has_every_binding_with_valid_values(self):
        modes = skill_modes()
        for capability, row in self.rows.items():
            self.assertEqual(set(row), {"id", *BINDINGS}, capability)
            allowed = modes if capability == "skill_delivery" else SUPPORT
            for binding in BINDINGS:
                with self.subTest(capability=capability, binding=binding):
                    cell = row[binding]
                    self.assertLessEqual(set(cell), {"support", "by_provider", "note"})
                    self.assertIn(cell["support"], allowed)
                    for provider, value in cell.get("by_provider", {}).items():
                        self.assertRegex(provider, r"^[a-z][a-z0-9-]*$")
                        self.assertIn(value, allowed)
                    if "note" in cell:
                        self.assertTrue(cell["note"].strip())

    def test_provider_seeds(self):
        for (binding, capability, provider), value in SEEDS.items():
            with self.subTest(binding=binding, capability=capability, provider=provider):
                self.assertEqual(self.rows[capability][binding]["by_provider"][provider], value)

    def test_native_cancel_preserves_known_support_and_agy_unknown(self):
        cell = self.rows["cancel"]["native"]
        self.assertEqual(cell["support"], "supported")
        self.assertEqual({key: value for key, value in cell["by_provider"].items() if key != "antigravity"},
                         {"claude-code": "supported", "codex": "supported", "grok": "supported"})
        self.assertEqual(cell["by_provider"]["antigravity"], "unknown")

    def test_docs_mention_every_capability(self):
        text = (ROOT / "docs/engine-port.md").read_text(encoding="utf-8")
        for capability in IDS:
            self.assertIn(f"`{capability}`", text, capability)


if __name__ == "__main__":
    unittest.main()
