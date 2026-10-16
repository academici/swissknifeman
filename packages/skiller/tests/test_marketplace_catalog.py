"""D81: skiller states its plugins in catalog.json (plugin-catalog/v1); the root indexes are assembled from unit.json."""
import json
import tempfile
import unittest
from pathlib import Path

from aicore.util import schema
from skiller.registry import build_registry, check_drift, write_plugin_manifests
from tests.fixtures import make_registry

CATALOG_DIR = Path(__file__).resolve().parents[2] / "aicore" / "schemas" / "plugin-catalog" / "v1"


class TestMarketplaceCatalog(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root, self.env = make_registry(Path(temporary.name))
        _registry, self.metadata, self.buckets = build_registry(self.env)

    def read(self, relative):
        return json.loads((self.root / relative).read_text(encoding="utf-8"))

    def test_registry_writes_the_catalog_and_both_indexes(self):
        count = write_plugin_manifests(self.env, self.metadata, self.buckets)
        catalog = self.read(".claude-plugin/catalog.json")
        registry, kind = schema.load_contract(CATALOG_DIR)
        self.assertEqual([], schema.validate(catalog, kind, registry))
        names = [plugin["name"] for plugin in catalog["plugins"]]
        self.assertEqual(names, sorted(names))
        self.assertEqual(["devops", "generate-skill", "php", "quality"], names)
        claude = self.read(".claude-plugin/marketplace.json")
        self.assertEqual(names, [plugin["name"] for plugin in claude["plugins"]])
        self.assertEqual(count, len(claude["plugins"]))
        self.assertEqual({"skiller"}, {plugin["package"] for plugin in claude["plugins"]})
        self.assertEqual(claude["owner"], catalog["marketplace"]["owner"])
        codex = self.read(".agents/plugins/marketplace.json")
        self.assertEqual(names, [plugin["name"] for plugin in codex["plugins"]])
        self.assertEqual({"explicit"}, {plugin["install_policy"] for plugin in codex["plugins"]})

    def test_catalog_paths_do_not_name_the_host_layout(self):
        write_plugin_manifests(self.env, self.metadata, self.buckets)
        for plugin in self.read(".claude-plugin/catalog.json")["plugins"]:
            self.assertFalse(plugin["source"].startswith("./") and plugin["source"] != "./")
            self.assertFalse(any(path.startswith("./") for path in plugin.get("skills", [])))

    def test_drift_is_empty_after_writing_and_names_a_stale_index(self):
        write_plugin_manifests(self.env, self.metadata, self.buckets)
        self.assertEqual([], [path for path in check_drift(self.env)
                              if path.endswith(("catalog.json", "marketplace.json"))])
        (self.root / ".agents" / "plugins" / "marketplace.json").write_text("{}\n", encoding="utf-8")
        (self.root / ".claude-plugin" / "catalog.json").write_text("{}\n", encoding="utf-8")
        drift = check_drift(self.env)
        self.assertIn(".agents/plugins/marketplace.json", drift)
        self.assertIn(".claude-plugin/catalog.json", drift)


if __name__ == "__main__":
    unittest.main()
