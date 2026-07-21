import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness/lib"))

from core import (ConfigSource, ProviderConfigCatalog, ProviderConfigLayer, ProviderId)
from harness.mcp import load_mcp_catalog, plan_mcp_projection
from maind.provider_deploy import (ProviderDeployError, plan_provider_deploy,
                                   plan_provider_artifacts, apply_provider_artifacts,
                                   resolve_effective_providers, semantic_servers)
from maind.provider_deploy import write_conformance_report
from maind.provision.deploy import mark_deployed, provider_semantic_inventory
from tests.fixtures import make_repo
from maind.config import merge_defaults
import tempfile
import subprocess


class TestProviderDeploy(unittest.TestCase):
    def test_effective_provider_resolution_honors_operation_override_and_refuses_invalid(self):
        catalog = ProviderConfigCatalog("1.0.0", (ProviderId.CLAUDE_CODE, ProviderId.CODEX), (), ())
        config = merge_defaults({"projects": [{"id": "demo", "name": "Demo"}]})
        self.assertEqual(resolve_effective_providers(config, catalog, "demo"),
                         (ProviderId.CLAUDE_CODE,))
        operation = ProviderConfigLayer(ConfigSource("operation", "test", "operation", "/"), {
            "contract_version": "1.0.0", "selection": {"codex": {"enabled": True},
            "claude-code": {"enabled": False}}})
        self.assertEqual(resolve_effective_providers(config, catalog, "demo", operation=operation),
                         (ProviderId.CODEX,))
        unknown = ProviderConfigLayer(ConfigSource("operation", "test", "operation", "/"), {
            "contract_version": "1.0.0", "selection": {"unknown": {"enabled": True}}})
        with self.assertRaisesRegex(ProviderDeployError, "PCFG_UNKNOWN_PROVIDER"):
            resolve_effective_providers(config, catalog, "demo", operation=unknown)
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

    def test_worktree_local_cli_generates_conformance_report(self):
        launcher = Path(__file__).resolve().parents[1] / "bin/maind"
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "P6-provider-deploy-conformance.md"
            result = subprocess.run([str(launcher), "deploy", "--conformance", str(output)],
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("| codex | .codex/config.toml | planned |", output.read_text(encoding="utf-8"))

    def test_provider_artifact_check_apply_repair_is_no_write_and_deterministic(self):
        root = Path(__file__).resolve().parents[3] / "packages/harness/configs"
        catalog = load_mcp_catalog(root / "common/mcp/catalog.json")
        bases = tuple(plan_mcp_projection(catalog, provider_id=provider,
            bindings_path=root / provider.value / "mcp/bindings.json", selected=(), trusted=True)
            for provider in (ProviderId.CLAUDE_CODE, ProviderId.CODEX))
        deploy = plan_provider_deploy(bases, semantic_servers(maind={"command": "maind"}))
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            checked = plan_provider_artifacts(target, deploy)
            self.assertFalse((target / ".mcp.json").exists())
            self.assertEqual(checked["mode"], "check")
            apply_provider_artifacts(target, deploy)
            self.assertTrue((target / ".mcp.json").exists())
            self.assertEqual(plan_provider_artifacts(target, deploy)["severity"], "green")
            (target / ".mcp.json").write_bytes((target / ".mcp.json").read_bytes() + b"\n")
            self.assertEqual(plan_provider_artifacts(target, deploy)["severity"], "error")
            repaired = plan_provider_artifacts(target, deploy, repair=True)
            self.assertEqual(repaired["mode"], "repair")
            apply_provider_artifacts(target, deploy, repair=True)
            self.assertEqual(plan_provider_artifacts(target, deploy)["severity"], "green")
            (target / ".mcp.json").write_text('{"foreign": true}', encoding="utf-8")
            self.assertEqual(plan_provider_artifacts(target, deploy)["severity"], "error")


if __name__ == "__main__":
    unittest.main()
