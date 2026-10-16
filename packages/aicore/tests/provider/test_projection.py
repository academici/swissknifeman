"""Tests for configs/provider-projection.json and aicore.provider.projection."""
import json
import tempfile
import unittest
from pathlib import Path

from aicore.provider.projection import (load_projection_catalog, projection_spec,
                                        project_common_instructions)
from aicore.provider.values import ProviderId


class ProjectionCatalogTests(unittest.TestCase):
    def test_cursor_skips_common_instructions(self):
        catalog = load_projection_catalog()
        self.assertFalse(project_common_instructions(catalog, ProviderId.CURSOR))
        self.assertFalse(project_common_instructions(catalog, ProviderId.CODEX))
        self.assertFalse(project_common_instructions(catalog, ProviderId.GROK))

    def test_command_invocation_policies(self):
        catalog = load_projection_catalog()
        for provider, style in ((ProviderId.CLAUDE_CODE, "slash"), (ProviderId.CURSOR, "semantic"),
                                (ProviderId.CODEX, "dollar"), (ProviderId.GROK, "slash")):
            with self.subTest(provider=provider):
                self.assertEqual(projection_spec(catalog, provider).command_invocation.style, style)

    def test_invalid_catalog_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text(json.dumps({"schema_version": "0"}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "PPROJ_CATALOG_SCHEMA_INVALID"):
                load_projection_catalog(path)


if __name__ == "__main__":
    unittest.main()
