"""The model selectors in command-routing.json are a generated snapshot of the aicore model catalog."""
import json
from pathlib import Path
import unittest

try:
    from . import fixtures  # noqa: F401 — package invocation
except ImportError:
    import fixtures  # noqa: F401 — direct discovery
from planner import integration

ROUTING_PATH = Path(__file__).resolve().parents[1] / "configs" / "command-routing.json"
HINT = "regenerate: python3 packages/planner/scripts/render-provider-commands.py --write --root ."


@unittest.skipUnless(integration.available(), "aicore is not available")
class ModelCatalogSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from planner.integration import models
        cls.models = models
        cls.raw = ROUTING_PATH.read_text(encoding="utf-8")
        cls.routing = json.loads(cls.raw)

    def test_snapshot_changes_nothing(self):
        self.assertEqual(self.models.routing_snapshot(self.routing), self.routing, HINT)

    def test_serialization_reproduces_the_file_bytes(self):
        self.assertEqual(self.models.routing_text(self.models.routing_snapshot(self.routing)), self.raw, HINT)

    def test_snapshot_overwrites_only_the_catalog_fields(self):
        stale = json.loads(self.raw)
        for mapping in stale["mappings"].values():
            mapping["class_selectors"] = {}
            mapping["effort_selectors"] = {}
            mapping["model_inventory"] = {}
            mapping["evidence"] = ["kept"]
        stale["plugin_version"] = "kept"
        refreshed = self.models.routing_snapshot(stale)
        self.assertEqual(refreshed["plugin_version"], "kept")
        for provider, mapping in refreshed["mappings"].items():
            with self.subTest(provider=provider):
                self.assertEqual(mapping["evidence"], ["kept"])
                for field in self.models.SNAPSHOT_FIELDS:
                    self.assertEqual(mapping[field], self.routing["mappings"][provider][field])
        self.assertEqual(stale["mappings"]["codex"]["class_selectors"], {})

    def test_provider_set_mismatch_is_refused(self):
        broken = json.loads(self.raw)
        del broken["mappings"]["grok"]
        with self.assertRaisesRegex(ValueError, "MODEL_SNAPSHOT_PROVIDERS"):
            self.models.routing_snapshot(broken)


if __name__ == "__main__":
    unittest.main()
