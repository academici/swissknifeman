"""Tests for configs/provider-projection.json and core.provider.projection."""
import json
import tempfile
import unittest
from pathlib import Path

from core.provider.projection import (load_projection_catalog, projection_spec,
                                        project_common_instructions)
from core.provider.values import ProviderId


class ProjectionCatalogTests(unittest.TestCase):
    def test_cursor_skips_common_instructions(self):
        catalog = load_projection_catalog()
        self.assertFalse(project_common_instructions(catalog, ProviderId.CURSOR))
        self.assertTrue(project_common_instructions(catalog, ProviderId.CODEX))

    def test_route_and_command_policies(self):
        catalog = load_projection_catalog()
        cursor = projection_spec(catalog, ProviderId.CURSOR)
        self.assertEqual(cursor.route_evidence.adapter, "route_evidence_cursor")
        self.assertEqual(cursor.command_invocation.style, "semantic")
        codex = projection_spec(catalog, ProviderId.CODEX)
        self.assertEqual(codex.route_evidence.semantic_prefix, "$ ")
        self.assertEqual(codex.command_invocation.style, "dollar")

    def test_invalid_catalog_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text(json.dumps({"schema_version": "0"}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "PPROJ_CATALOG_SCHEMA_INVALID"):
                load_projection_catalog(path)


if __name__ == "__main__":
    unittest.main()
