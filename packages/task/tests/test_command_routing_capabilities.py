"""Guard: routing capability_bindings levels agree with provider-capabilities."""
import json
from pathlib import Path
import unittest

from core.provider.manifest import default_manifest_path

REPO_ROOT = Path(__file__).resolve().parents[3]
ROUTING = REPO_ROOT / "packages/task/configs/command-routing.json"
MANIFEST = default_manifest_path()
SOURCE = ("the source of truth for levels is packages/aicore/configs/provider-capabilities.json "
          "(command_render.py reads levels from it)")


class RoutingCapabilityLevelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (ROUTING.is_file() and MANIFEST.is_file()):
            raise unittest.SkipTest("monorepo configs not available (standalone Task)")
        cls.routing = json.loads(ROUTING.read_text(encoding="utf-8"))
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_routing_providers_exist_in_manifest(self):
        known = {p["id"] for p in self.manifest["providers"]}
        for provider in self.routing["mappings"]:
            with self.subTest(provider=provider):
                self.assertIn(provider, known, SOURCE)

    def test_capability_binding_levels_match_manifest(self):
        levels = {c["id"]: c.get("support", {}) for c in self.manifest["capabilities"]}
        for provider, mapping in self.routing["mappings"].items():
            for cap_id, level in mapping["capability_bindings"].items():
                with self.subTest(provider=provider, capability=cap_id):
                    self.assertIn(cap_id, levels, SOURCE)
                    self.assertEqual(level, levels[cap_id][provider]["level"], SOURCE)


if __name__ == "__main__":
    unittest.main()
