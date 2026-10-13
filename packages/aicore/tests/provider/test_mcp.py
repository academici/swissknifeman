"""Tests for aicore.provider.mcp: pure MCP projection over caller-supplied documents."""
import json
import dataclasses
import tempfile
import unittest
from pathlib import Path

from aicore.artifacts.artifact import ArtifactSource, sha256_digest
from aicore.artifacts.lock import ArtifactActionKind, apply_plan, plan_artifact_lock, serialize_lock
from aicore.provider.mcp import (McpProjection, parse_mcp_catalog, plan_mcp_artifact,
                                 plan_mcp_projection, render_mcp_projection)
from aicore.provider.values import ProviderId

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.9 / 3.10
    tomllib = None


def catalog_document():
    return {"catalog_version": "1.0.0", "servers": [
        {"id": "docs", "transport": "http", "capability_id": "mcp.catalog", "secret_refs": []},
        {"id": "files", "transport": "stdio", "capability_id": "mcp.catalog", "secret_refs": []},
        {"id": "search", "transport": "stdio", "capability_id": "mcp.catalog",
         "secret_refs": ["search-key"]},
    ]}


def bindings_document(provider, target_path):
    servers = {
        "docs": {"url": "https://docs.example.test/mcp"},
        "files": {"command": "npx", "args": ["-y", "files-server", "."]},
        "search": {"command": "uvx", "args": ["search-server"], "env": {"SEARCH_KEY": "${SEARCH_KEY}"}},
    }
    if provider == "claude-code":
        servers["docs"] = {"type": "http", "url": "https://docs.example.test/mcp"}
    return {"binding_version": "1.0.0", "provider_id": provider, "target_scope": "project",
            "target_path": target_path, "servers": servers}


CODEX = bindings_document("codex", ".codex/config.toml")
CLAUDE = bindings_document("claude-code", ".mcp.json")
CURSOR = bindings_document("cursor", ".cursor/mcp.json")


def sources(bindings):
    return (ArtifactSource("test.catalog", "catalog.json",
                           sha256_digest(json.dumps(catalog_document()).encode())),
            ArtifactSource("test.bindings", "bindings.json",
                           sha256_digest(json.dumps(bindings).encode())))


class CatalogCase(unittest.TestCase):
    def test_declared_order_is_kept(self):
        self.assertEqual([item.id for item in parse_mcp_catalog(catalog_document())],
                         ["docs", "files", "search"])

    def test_invalid_documents_use_stable_codes(self):
        bad_version = catalog_document()
        bad_version["catalog_version"] = "2.0.0"
        with self.assertRaisesRegex(ValueError, "HARNESS_VERSION_UNSUPPORTED"):
            parse_mcp_catalog(bad_version)
        extra = catalog_document()
        extra["extra"] = 1
        duplicate = catalog_document()
        duplicate["servers"].append(dict(duplicate["servers"][0]))
        empty = {"catalog_version": "1.0.0", "servers": []}
        wrong_transport = catalog_document()
        wrong_transport["servers"][0]["transport"] = "ws"
        for document in (extra, duplicate, empty, wrong_transport, []):
            with self.subTest(document=document), self.assertRaisesRegex(
                    ValueError, "HARNESS_CATALOG_MISMATCH"):
                parse_mcp_catalog(document)


class ProjectionCase(unittest.TestCase):
    def setUp(self):
        self.catalog = parse_mcp_catalog(catalog_document())
        self.selected = tuple(item.id for item in self.catalog)

    def plan(self, provider, bindings, selected=None, trusted=True):
        return plan_mcp_projection(
            self.catalog, provider_id=provider, bindings=bindings,
            selected=self.selected if selected is None else selected, trusted=trusted)

    def test_independent_native_targets(self):
        claude = self.plan(ProviderId.CLAUDE_CODE, CLAUDE)
        codex = self.plan(ProviderId.CODEX, CODEX)
        self.assertEqual((claude.target_path, codex.target_path), (".mcp.json", ".codex/config.toml"))
        self.assertEqual(codex.secret_refs, ("search-key",))
        self.assertEqual(json.loads(render_mcp_projection(claude))["mcpServers"]["docs"]["type"], "http")
        text = render_mcp_projection(codex).decode("utf-8")
        if tomllib is not None:
            value = tomllib.loads(text)["mcp_servers"]
            self.assertEqual(value["docs"]["url"], "https://docs.example.test/mcp")
            self.assertEqual(value["search"]["env"], {"SEARCH_KEY": "${SEARCH_KEY}"})
        self.assertEqual(render_mcp_projection(codex), render_mcp_projection(codex))

    def test_cursor_renders_json(self):
        cursor = self.plan(ProviderId.CURSOR, CURSOR, selected=("files",))
        self.assertEqual(json.loads(render_mcp_projection(cursor)),
                         {"mcpServers": {"files": CURSOR["servers"]["files"]}})

    def test_refuses_untrusted_unknown_duplicate_and_foreign_bindings(self):
        with self.assertRaisesRegex(ValueError, "HARNESS_TRUST_REQUIRED"):
            self.plan(ProviderId.CODEX, CODEX, trusted=False)
        for selected in (("docs", "docs"), ("missing",)):
            with self.subTest(selected=selected), self.assertRaisesRegex(
                    ValueError, "HARNESS_CATALOG_MISMATCH"):
                self.plan(ProviderId.CODEX, CODEX, selected=selected)
        with self.assertRaisesRegex(ValueError, "HARNESS_MAPPING_MISSING"):
            self.plan(ProviderId.CODEX, CLAUDE)
        with self.assertRaisesRegex(ValueError, "HARNESS_MAPPING_MISSING"):
            self.plan(ProviderId.CODEX, {**CODEX, "servers": {}}, selected=("docs",))

    def test_secret_references_must_be_declared_placeholders(self):
        resolved = json.loads(json.dumps(CODEX))
        resolved["servers"]["search"]["env"] = {"SEARCH_KEY": "real-token"}
        with self.assertRaisesRegex(ValueError, "HARNESS_SECRET_VALUE_EXPOSED"):
            self.plan(ProviderId.CODEX, resolved)
        exposed = json.loads(json.dumps(CODEX))
        exposed["servers"]["docs"]["secret_value"] = "x"
        with self.assertRaisesRegex(ValueError, "HARNESS_SECRET_VALUE_EXPOSED"):
            self.plan(ProviderId.CODEX, exposed)
        missing = json.loads(json.dumps(CODEX))
        del missing["servers"]["search"]["env"]
        with self.assertRaisesRegex(ValueError, "HARNESS_SECRET_REFERENCE_MISSING"):
            self.plan(ProviderId.CODEX, missing)


class ArtifactCase(unittest.TestCase):
    def setUp(self):
        self.catalog = parse_mcp_catalog(catalog_document())

    def projection(self, provider, bindings, selected):
        return plan_mcp_projection(self.catalog, provider_id=provider, bindings=bindings,
                                   selected=selected, trusted=True)

    def test_sources_and_adapter_come_from_the_caller(self):
        projection = self.projection(ProviderId.CODEX, CODEX, ("docs", "files"))
        artifact = plan_mcp_artifact(projection, sources=sources(CODEX), adapter_id="test.codex.mcp")
        provenance = artifact.provenance
        self.assertEqual(provenance.artifact_id, "test.codex.mcp.docs.files")
        self.assertEqual(provenance.adapter_id, "test.codex.mcp")
        self.assertEqual([item.source_id for item in provenance.canonical_sources],
                         ["test.bindings", "test.catalog"])
        self.assertEqual(artifact.managed_bytes, render_mcp_projection(projection))

    def test_claude_has_no_whole_file_artifact(self):
        projection = self.projection(ProviderId.CLAUDE_CODE, CLAUDE, ("docs",))
        with self.assertRaisesRegex(ValueError, "HARNESS_MAPPING_MISSING"):
            plan_mcp_artifact(projection, sources=sources(CLAUDE), adapter_id="test.claude.mcp")

    def test_sources_are_required(self):
        projection = self.projection(ProviderId.GROK, bindings_document("grok", ".grok/config.toml"),
                                     ("docs",))
        with self.assertRaises(TypeError):
            plan_mcp_artifact(projection, sources=(), adapter_id="test.grok.mcp")

    def test_artifact_is_a_locked_whole_file_consumer(self):
        projection = self.projection(ProviderId.CODEX, CODEX, ("docs", "search"))
        expected = plan_mcp_artifact(projection, sources=sources(CODEX), adapter_id="test.codex.mcp")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = plan_artifact_lock(root, (expected,), lock_bytes=None)
            apply_plan(root, plan)
            self.assertEqual((root / ".codex/config.toml").read_bytes(), expected.managed_bytes)
            self.assertNotIn(b"real-token", serialize_lock(plan.next_lock))
            clean = plan_artifact_lock(root, (expected,), lock_bytes=serialize_lock(plan.next_lock))
            self.assertEqual(clean.actions[0].action, ArtifactActionKind.NOOP)


class ValueCase(unittest.TestCase):
    def test_projection_is_immutable(self):
        projection = McpProjection(ProviderId.CODEX, "project", ".codex/config.toml", (), ())
        with self.assertRaises(dataclasses.FrozenInstanceError):
            projection.target_path = "x"


if __name__ == "__main__":
    unittest.main()
