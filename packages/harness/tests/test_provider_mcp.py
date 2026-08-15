import tempfile
import unittest
import json
import re
from pathlib import Path
import sys

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.9/3.10 compatibility
    tomllib = None

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from core import ProviderId
from core import ArtifactActionKind, apply_plan, plan_artifact_lock, serialize_lock
from harness.mcp import (block_mcp, load_mcp_catalog, plan_mcp_artifact,
                         plan_mcp_projection, render_mcp_projection)
import tests.fixtures as fx


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "configs" / "common" / "mcp" / "catalog.json"
CLAUDE_BINDINGS = ROOT / "configs" / "claude-code" / "mcp" / "bindings.json"
CODEX_BINDINGS = ROOT / "configs" / "codex" / "mcp" / "bindings.json"
CLAUDE_PLAYWRIGHT_PRESET = ROOT / "configs" / "claude-code" / "mcp" / "playwright.json"


def assert_mcp_url(case, text, server_id, expected):
    if tomllib is not None:
        case.assertEqual(tomllib.loads(text)["mcp_servers"][server_id]["url"], expected)
        return
    table = re.search(
        rf"(?ms)^\[mcp_servers\.{re.escape(server_id)}\]\n(.*?)(?=^\[|\Z)", text
    )
    case.assertIsNotNone(table, server_id)
    url = re.search(r'(?m)^url = (".*")$', table.group(1))
    case.assertIsNotNone(url, server_id)
    case.assertEqual(json.loads(url.group(1)), expected)


def assert_mcp_server_ids(case, text, expected):
    if tomllib is not None:
        actual = set(tomllib.loads(text)["mcp_servers"])
    else:
        actual = set(re.findall(r"(?m)^\[mcp_servers\.([^]]+)\]$", text))
    case.assertEqual(actual, set(expected))


class ProviderMcpCase(unittest.TestCase):
    def test_exact_common_inventory_and_independent_native_targets(self):
        catalog = load_mcp_catalog(CATALOG)
        selected = tuple(item.id for item in catalog)
        self.assertEqual(len(catalog), 8)
        self.assertEqual({item.id for item in catalog},
                         {path.stem for path in (ROOT / "configs" / "claude-code" / "mcp").glob("*.json")
                          if path.name != "bindings.json"})
        for path, provider in ((CLAUDE_BINDINGS, "claude-code"), (CODEX_BINDINGS, "codex")):
            envelope = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(set(envelope), {"binding_version", "provider_id", "target_scope",
                                             "target_path", "servers"})
            self.assertEqual(envelope["provider_id"], provider)
            self.assertEqual(set(envelope["servers"]), set(selected))
        claude = plan_mcp_projection(catalog, provider_id=ProviderId.CLAUDE_CODE,
                                     bindings_path=CLAUDE_BINDINGS, selected=selected, trusted=True)
        codex = plan_mcp_projection(catalog, provider_id=ProviderId.CODEX,
                                    bindings_path=CODEX_BINDINGS, selected=selected, trusted=True)
        self.assertEqual(claude.target_path, ".mcp.json")
        self.assertEqual(codex.target_path, ".codex/config.toml")
        self.assertEqual({server_id for server_id, _ in claude.servers}, set(selected))
        self.assertEqual({server_id for server_id, _ in codex.servers}, set(selected))
        self.assertEqual(json.loads(render_mcp_projection(claude))["mcpServers"]["context7"]["type"], "http")
        assert_mcp_url(self, render_mcp_projection(codex).decode("utf-8"),
                       "context7", "https://mcp.context7.com/mcp")
        self.assertEqual(render_mcp_projection(codex), render_mcp_projection(codex))
        self.assertNotIn(b"PERPLEXITY_API_KEY=", render_mcp_projection(codex))

    def test_refuses_untrusted_unknown_duplicate_and_resolved_secret(self):
        catalog = load_mcp_catalog(CATALOG)
        with self.assertRaisesRegex(ValueError, "HARNESS_TRUST_REQUIRED"):
            plan_mcp_projection(catalog, provider_id=ProviderId.CODEX, bindings_path=CODEX_BINDINGS,
                                selected=("context7",), trusted=False)
        with self.assertRaisesRegex(ValueError, "HARNESS_CATALOG_MISMATCH"):
            plan_mcp_projection(catalog, provider_id=ProviderId.CODEX, bindings_path=CODEX_BINDINGS,
                                selected=("context7", "context7"), trusted=True)
        with self.assertRaisesRegex(ValueError, "HARNESS_MAPPING_MISSING"):
            plan_mcp_projection(catalog, provider_id=ProviderId.CODEX, bindings_path=CLAUDE_BINDINGS,
                                selected=("context7",), trusted=True)
        with self.assertRaisesRegex(ValueError, "HARNESS_MAPPING_MISSING"):
            plan_mcp_projection(catalog, provider_id=ProviderId.CLAUDE_CODE, bindings_path=CODEX_BINDINGS,
                                selected=("context7",), trusted=True)
        with tempfile.TemporaryDirectory() as tmp:
            altered = Path(tmp) / "bindings.json"
            altered.write_text(CODEX_BINDINGS.read_text(encoding="utf-8").replace("${PERPLEXITY_API_KEY}", "real-token"), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "HARNESS_SECRET_VALUE_EXPOSED"):
                plan_mcp_projection(catalog, provider_id=ProviderId.CODEX, bindings_path=altered,
                                    selected=("perplexity",), trusted=True)

    def test_codex_projection_is_a_p2_locked_actual_consumer(self):
        catalog = load_mcp_catalog(CATALOG)
        projection = plan_mcp_projection(catalog, provider_id=ProviderId.CODEX,
                                         bindings_path=CODEX_BINDINGS,
                                         selected=("context7", "perplexity"), trusted=True)
        expected = plan_mcp_artifact(projection, catalog_path=CATALOG, bindings_path=CODEX_BINDINGS)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = plan_artifact_lock(root, (expected,), lock_bytes=None)
            apply_plan(root, plan)
            actual = (root / ".codex/config.toml").read_text(encoding="utf-8")
            assert_mcp_server_ids(self, actual, {"context7", "perplexity"})
            self.assertNotIn(".claude", actual)
            self.assertNotIn("real-token", actual)
            self.assertIn("${PERPLEXITY_API_KEY}", actual)
            self.assertNotIn(b"real-token", serialize_lock(plan.next_lock))
            clean = plan_artifact_lock(root, (expected,), lock_bytes=serialize_lock(plan.next_lock))
            self.assertEqual(clean.actions[0].action, ArtifactActionKind.NOOP)
            (root / expected.target.path).write_text("local drift\n", encoding="utf-8")
            repaired = plan_artifact_lock(root, (expected,), lock_bytes=serialize_lock(plan.next_lock),
                                          repair_artifact_ids=(expected.provenance.artifact_id,))
            self.assertEqual(repaired.actions[0].action, ArtifactActionKind.REPAIR)

    def test_playwright_output_dir_and_pinned_version_consistent_across_carriers(self):


        preset = json.loads(CLAUDE_PLAYWRIGHT_PRESET.read_text(encoding="utf-8"))
        claude_bindings = json.loads(CLAUDE_BINDINGS.read_text(encoding="utf-8"))
        codex_bindings = json.loads(CODEX_BINDINGS.read_text(encoding="utf-8"))
        args = tuple(preset["args"])
        self.assertEqual(tuple(claude_bindings["servers"]["playwright"]["args"]), args)
        self.assertEqual(tuple(codex_bindings["servers"]["playwright"]["args"]), args)
        self.assertIn("--output-dir", args)
        self.assertEqual(args[args.index("--output-dir") + 1], ".playwright-mcp")
        version_arg = next(a for a in args if a.startswith("@playwright/mcp@"))
        self.assertNotEqual(version_arg, "@playwright/mcp@latest")
        catalog = load_mcp_catalog(CATALOG)
        self.assertIn("playwright", {item.id for item in catalog})

    def test_current_claude_merge_only_consumer_preserves_foreign_server(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "project"
            target.mkdir()
            (target / ".mcp.json").write_text('{"mcpServers":{"foreign":{"url":"https://foreign"}}}',
                                                encoding="utf-8")
            env = fx.real_env(root)
            block_mcp(env, target, ["context7"], False)
            value = __import__("json").loads((target / ".mcp.json").read_text(encoding="utf-8"))
            self.assertEqual(set(value["mcpServers"]), {"foreign", "context7"})


if __name__ == "__main__":
    unittest.main()
