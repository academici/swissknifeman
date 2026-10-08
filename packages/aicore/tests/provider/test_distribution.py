"""Tests for configs/provider-distribution.json and aicore.provider.distribution."""
import json
import tempfile
import unittest
from pathlib import Path

from aicore.provider.distribution import (DistributionCatalog, connect_channel,
                                          load_distribution_catalog, vendor_channel)
from aicore.provider.values import ProviderId


class DistributionCatalogTests(unittest.TestCase):
    def test_default_catalog_cursor_has_discovery_only(self):
        catalog = load_distribution_catalog()
        cursor = catalog.providers["cursor"]
        self.assertIsNone(cursor.connect)
        self.assertIsNone(cursor.vendor)
        self.assertEqual(cursor.discovery.surface, ".agents/skills")
        grok = catalog.providers["grok"]
        self.assertIsNone(grok.connect)
        self.assertIsNone(grok.vendor)
        self.assertEqual(grok.discovery.surface, ".agents/skills")

    def test_connect_and_vendor_specs(self):
        catalog = load_distribution_catalog()
        self.assertEqual(connect_channel(catalog, ProviderId.CLAUDE_CODE).mode,
                         "claude-marketplace")
        self.assertEqual(connect_channel(catalog, ProviderId.CODEX).mode, "codex-marketplace")
        self.assertIsNone(connect_channel(catalog, ProviderId.CURSOR))
        self.assertIsNone(connect_channel(catalog, ProviderId.GROK))
        self.assertEqual(vendor_channel(catalog, ProviderId.CODEX).path_param, "codex_path")
        self.assertIsNone(vendor_channel(catalog, ProviderId.CURSOR))
        self.assertIsNone(vendor_channel(catalog, ProviderId.GROK))

    def test_invalid_catalog_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text(json.dumps({"schema_version": "0"}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "PDIST_CATALOG_SCHEMA_INVALID"):
                load_distribution_catalog(path)


if __name__ == "__main__":
    unittest.main()
