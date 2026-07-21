import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness/lib"))

from core import ProviderId
from harness.mcp import load_mcp_catalog, plan_mcp_projection
from maind.provider_deploy import plan_provider_deploy, semantic_servers
from maind.provider_deploy import write_conformance_report
from maind.provision.deploy import mark_deployed, provider_semantic_inventory
from tests.fixtures import make_repo
from maind.config import merge_defaults
import tempfile


class TestProviderDeploy(unittest.TestCase):
    def test_caller_owned_semantics_use_p5_targets_and_renderers(self):
        root = Path(__file__).resolve().parents[3] / "packages/harness/configs"
        catalog = load_mcp_catalog(root / "common/mcp/catalog.json")
        bases = tuple(plan_mcp_projection(catalog, provider_id=provider,
            bindings_path=root / provider.value / "mcp/bindings.json", selected=(), trusted=True)
            for provider in (ProviderId.CLAUDE_CODE, ProviderId.CODEX))
        servers = semantic_servers(maind={"command": "maind"},
            codegraph={"command": "uvx", "args": ["serena"]},
            perplexity={"command": "pplx"})
        plan = plan_provider_deploy(bases, servers)
        self.assertTrue(plan.green)
        self.assertEqual([row.target_path for row in plan.results], [".mcp.json", ".codex/config.toml"])
        self.assertTrue(all(b"maind" in row.rendered and b"codegraph" in row.rendered
                            for row in plan.results))
        self.assertTrue(all(row.artifact.provenance.target_path == row.target_path
                            for row in plan.results))

    def test_missing_disabled_and_selected_provider_are_tagged(self):
        root = Path(__file__).resolve().parents[3] / "packages/harness/configs"
        catalog = load_mcp_catalog(root / "common/mcp/catalog.json")
        claude = plan_mcp_projection(catalog, provider_id=ProviderId.CLAUDE_CODE,
            bindings_path=root / "claude-code/mcp/bindings.json", selected=(), trusted=True)
        servers = semantic_servers(maind={"command": "maind"})
        plan = plan_provider_deploy((claude,), servers,
            selected=(ProviderId.CLAUDE_CODE, ProviderId.CODEX),
            required_providers=(ProviderId.CLAUDE_CODE, ProviderId.CODEX))
        self.assertEqual([row.status for row in plan.results], ["planned", "failed"])
        self.assertEqual(plan.results[1].diagnostic, "MAIND_PROJECTION_MISSING")
        disabled = plan_provider_deploy((claude,), servers, selected=(ProviderId.CLAUDE_CODE,),
            disabled=(ProviderId.CLAUDE_CODE,))
        self.assertEqual(disabled.results[0].diagnostic, "MAIND_PROVIDER_DISABLED")

    def test_deploy_facade_preserves_semantic_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            project_path = Path(tmp) / "project"
            project_path.mkdir()
            config = merge_defaults({"projects": [{"id": "demo", "name": "Demo",
                "local_path": str(project_path), "memory_scope": "project:demo"}]})
            rows = provider_semantic_inventory(env, config, config["projects"][0],
                                               with_code=False, maind_server=True,
                                               with_agentmemory=False)
            self.assertEqual([row.id for row in rows], ["maind"])

    def test_temp_conformance_is_no_write_deterministic_and_preserves_foreign(self):
        root = Path(__file__).resolve().parents[3] / "packages/harness/configs"
        catalog = load_mcp_catalog(root / "common/mcp/catalog.json")
        bases = tuple(plan_mcp_projection(catalog, provider_id=provider,
            bindings_path=root / provider.value / "mcp/bindings.json", selected=(), trusted=True)
            for provider in (ProviderId.CLAUDE_CODE, ProviderId.CODEX))
        servers = semantic_servers(maind={"command": "maind"}, codegraph={"command": "uvx"})
        first, second = plan_provider_deploy(bases, servers), plan_provider_deploy(bases, servers)
        self.assertEqual([row.rendered for row in first.results], [row.rendered for row in second.results])
        with tempfile.TemporaryDirectory() as tmp:
            foreign = Path(tmp) / "foreign.json"
            foreign.write_text('{"foreign":true}', encoding="utf-8")
            evidence = Path(tmp) / "evidence.md"
            write_conformance_report(evidence, first)
            self.assertEqual(foreign.read_text(encoding="utf-8"), '{"foreign":true}')
            self.assertIn("Aggregate:** GREEN", evidence.read_text(encoding="utf-8"))

    def test_mark_deployed_keeps_legacy_fields_and_provider_tagged_state(self):
        root = Path(__file__).resolve().parents[3] / "packages/harness/configs"
        catalog = load_mcp_catalog(root / "common/mcp/catalog.json")
        bases = tuple(plan_mcp_projection(catalog, provider_id=provider,
            bindings_path=root / provider.value / "mcp/bindings.json", selected=(), trusted=True)
            for provider in (ProviderId.CLAUDE_CODE, ProviderId.CODEX))
        plan = plan_provider_deploy(bases, semantic_servers(maind={"command": "maind"}))
        config = merge_defaults({"projects": [{"id": "demo", "name": "Demo",
            "local_path": "/tmp/demo", "memory_scope": "project:demo"}]})
        result = {"servers": ["maind"], "code": "disabled", "code_server": "serena",
                  "targets": [".mcp.json"], "scope": "project:demo", "provider_plan": plan}
        saved = mark_deployed(config, "demo", result)
        project = saved["projects"][0]
        self.assertEqual(project["mcp"]["targets"], [".mcp.json"])
        self.assertEqual(project["provider_deploy"]["claude-code"]["status"], "planned")
        self.assertEqual(project["provider_deploy"]["codex"]["target_path"], ".codex/config.toml")


if __name__ == "__main__":
    unittest.main()
