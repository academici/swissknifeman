"""The MCP projection moved to aicore.provider.mcp; its plans must not change by one byte.

``fixtures_data/mcp-artifact-before-v1.json`` was captured from the in-package implementation
before the move. ``python3 tests/test_mcp_artifact_equality.py --capture`` rewrites it (only for a
deliberate, reviewed contract change)."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from aicore.provider.values import ProviderId
from harness.mcp import (load_mcp_catalog, plan_mcp_artifact, plan_mcp_projection,
                         render_mcp_projection)

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "configs" / "common" / "mcp" / "catalog.json"
FIXTURE = ROOT / "tests" / "fixtures_data" / "mcp-artifact-before-v1.json"
PROVIDERS = (ProviderId.CLAUDE_CODE, ProviderId.CODEX, ProviderId.CURSOR, ProviderId.GROK)
ARTIFACT_PROVIDERS = (ProviderId.CODEX, ProviderId.CURSOR, ProviderId.GROK)


def _provenance(artifact):
    value = artifact.provenance
    return {
        "artifact_id": value.artifact_id,
        "sources": [[source.source_id, source.path, source.content_hash]
                    for source in value.canonical_sources],
        "adapter_id": value.adapter_id, "adapter_version": value.adapter_version,
        "provider_id": value.provider_id.value, "target_path": value.target_path,
        "source_hash": value.source_hash, "rendered_hash": value.rendered_hash,
        "managed_boundary": [value.managed_boundary[0], list(value.managed_boundary[1])],
        "capability_requirements": [repr(item) for item in value.capability_requirements],
        "semantic_metadata": [[key, item] for key, item in value.semantic_metadata],
    }


def snapshot():
    catalog = load_mcp_catalog(CATALOG)
    ids = tuple(item.id for item in catalog)
    result = {"catalog": [[s.id, s.transport, s.capability_id, list(s.secret_refs)] for s in catalog]}
    for provider in PROVIDERS:
        bindings = ROOT / "configs" / provider.value / "mcp" / "bindings.json"
        for label, selected in (("all", ids), ("base", ()), ("pair", ids[:2])):
            projection = plan_mcp_projection(catalog, provider_id=provider,
                                             bindings_path=bindings, selected=selected, trusted=True)
            row = {"target_scope": projection.target_scope, "target_path": projection.target_path,
                   "server_ids": [server_id for server_id, _ in projection.servers],
                   "secret_refs": list(projection.secret_refs),
                   "rendered": render_mcp_projection(projection).decode("utf-8")}
            if provider in ARTIFACT_PROVIDERS and selected:
                artifact = plan_mcp_artifact(projection, catalog_path=CATALOG, bindings_path=bindings)
                row["artifact"] = {"target": artifact.target.path,
                                   "managed": artifact.managed_bytes.decode("utf-8"),
                                   "provenance": _provenance(artifact)}
            result[f"{provider.value}/{label}"] = row
    return result


class McpArtifactEqualityCase(unittest.TestCase):
    def test_plans_equal_the_pre_move_capture(self):
        expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
        actual = json.loads(json.dumps(snapshot()))
        self.assertEqual(sorted(actual), sorted(expected))
        for key in expected:
            with self.subTest(key=key):
                self.assertEqual(actual[key], expected[key])

    def test_artifact_sources_keep_harness_labels_and_paths(self):
        expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
        sources = expected["codex/all"]["artifact"]["provenance"]["sources"]
        self.assertEqual([item[:2] for item in sources], [
            ["harness.codex.mcp-bindings", "packages/harness/configs/codex/mcp/bindings.json"],
            ["harness.mcp.catalog", "packages/harness/configs/common/mcp/catalog.json"]])


if __name__ == "__main__":
    if "--capture" in sys.argv:
        FIXTURE.write_text(json.dumps(snapshot(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
        print(f"captured {FIXTURE}")
    else:
        unittest.main()
