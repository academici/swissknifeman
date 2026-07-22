import json
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness/lib"))

from core import (ConfigSource, ProviderConfigCatalog, ProviderConfigLayer, ProviderId,
                  canonical_json_bytes, sha256_digest)
from harness.mcp import load_mcp_catalog, plan_mcp_projection
from maind.provider_deploy import (ProviderDeployError, plan_provider_deploy,
                                   plan_provider_artifacts, apply_provider_artifacts,
                                   resolve_effective_providers, semantic_servers)
from maind.provider_deploy import conformance_report, write_conformance_report
from maind.provision.deploy import deploy_project, mark_deployed, provider_semantic_inventory
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
        disabled = ProviderConfigLayer(ConfigSource("operation", "test", "operation", "/"), {
            "contract_version": "1.0.0", "selection": {"claude-code": {"enabled": False}}})
        with self.assertRaisesRegex(ProviderDeployError, "MAIND_PROVIDER_DISABLED"):
            resolve_effective_providers(config, catalog, "demo", operation=disabled)
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
        self.assertTrue(all(row.artifact.provenance.canonical_sources[0].path ==
                            "packages/maind/lib/maind/provider_deploy.py" for row in plan.results))
        expected_hash = sha256_digest(canonical_json_bytes({"servers": [
            {"id": row.id, "binding": dict(row.binding)} for row in servers]}))
        self.assertTrue(all(row.artifact.provenance.canonical_sources[0].content_hash == expected_hash
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

    def test_project_extra_servers_join_provider_neutral_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            project_path = Path(tmp) / "project"
            project_path.mkdir()
            config = merge_defaults({"projects": [{"id": "demo", "name": "Demo",
                "local_path": str(project_path), "memory_scope": "project:demo",
                "mcp": {"extra_servers": {
                    "laravel-boost": {"command": "php", "args": ["artisan", "boost:mcp"]}}}}]})
            rows = provider_semantic_inventory(env, config, config["projects"][0],
                                               with_code=False, maind_server=True,
                                               with_agentmemory=False)
            self.assertEqual([row.id for row in rows], ["maind", "laravel-boost"])

    def test_provider_deploy_does_not_run_legacy_mcp_writer_twice(self):
        root = Path(__file__).resolve().parents[3] / "packages/harness/configs"
        catalog = load_mcp_catalog(root / "common/mcp/catalog.json")
        bases = tuple(plan_mcp_projection(catalog, provider_id=provider,
            bindings_path=root / provider.value / "mcp/bindings.json", selected=(), trusted=True)
            for provider in (ProviderId.CLAUDE_CODE, ProviderId.CODEX))
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            target = Path(tmp) / "project"
            target.mkdir()
            config = merge_defaults({"projects": [{"id": "demo", "name": "Demo",
                "local_path": str(target), "memory_scope": "project:demo"}]})
            result = deploy_project(env, config, config["projects"][0], with_code=False,
                                    provider_projections=bases)
            self.assertEqual(result["targets"], [".mcp.json", ".codex/config.toml"])
            self.assertEqual(json.loads((target / ".mcp.json").read_text())["mcpServers"],
                             {"maind": {"command": "maind",
                                        "args": ["mcp", "--scope", "project:demo"]}})

    def test_full_semantic_inventory_and_duplicate_server_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            project_path = Path(tmp) / "project"; project_path.mkdir()
            config = merge_defaults({"mcp": {"perplexity_web": {"enabled": True}},
                "projects": [{"id": "demo", "name": "Demo", "local_path": str(project_path),
                              "memory_scope": "project:demo", "code_graph": {"enabled": True}}]})
            rows = provider_semantic_inventory(env, config, config["projects"][0], with_code=True,
                                               maind_server=True, with_agentmemory=True)
            self.assertEqual([row.id for row in rows], ["maind", "agentmemory", "codegraph", "perplexity"])
        with self.assertRaisesRegex(ProviderDeployError, "MAIND_SEMANTIC_SERVER_DUPLICATE"):
            plan_provider_deploy((), (semantic_servers(maind={"command": "maind"})[0],) * 2)

    def test_facade_executes_provider_plan_and_dry_is_no_write(self):
        root = Path(__file__).resolve().parents[3] / "packages/harness/configs"
        catalog = load_mcp_catalog(root / "common/mcp/catalog.json")
        bases = tuple(plan_mcp_projection(catalog, provider_id=provider,
            bindings_path=root / provider.value / "mcp/bindings.json", selected=(), trusted=True)
            for provider in (ProviderId.CLAUDE_CODE, ProviderId.CODEX))
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp); target = Path(tmp) / "project"; target.mkdir()
            config = merge_defaults({"projects": [{"id": "demo", "name": "Demo",
                "local_path": str(target), "memory_scope": "project:demo"}]})
            project = config["projects"][0]
            deploy_project(env, config, project, with_code=False, provider_projections=bases, dry=True)
            self.assertFalse((target / ".codex/config.toml").exists())
            deploy_project(env, config, project, with_code=False, provider_projections=bases)
            self.assertTrue((target / ".mcp.json").exists())
            self.assertTrue((target / ".codex/config.toml").exists())
            (target / ".mcp.json").write_bytes((target / ".mcp.json").read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "MAIND_PROVIDER_DEPLOY_REFUSED"):
                deploy_project(env, config, project, with_code=False, provider_projections=bases)
            deploy_project(env, config, project, with_code=False, provider_projections=bases,
                           provider_repair=True)
            self.assertNotEqual(plan_provider_artifacts(target, plan_provider_deploy(
                bases, semantic_servers(maind={"command": "maind"}))) ["severity"], "error")

    def test_secret_reference_is_preserved_without_resolved_value(self):
        root = Path(__file__).resolve().parents[3] / "packages/harness/configs"
        catalog = load_mcp_catalog(root / "common/mcp/catalog.json")
        base = plan_mcp_projection(catalog, provider_id=ProviderId.CLAUDE_CODE,
            bindings_path=root / "claude-code/mcp/bindings.json", selected=(), trusted=True)
        codex = plan_mcp_projection(catalog, provider_id=ProviderId.CODEX,
            bindings_path=root / "codex/mcp/bindings.json", selected=(), trusted=True)
        plan = plan_provider_deploy((base, codex), semantic_servers(maind={"command": "maind",
            "env": {"TOKEN": "${MAIND_TOKEN}", "UNRELATED": "resolved-secret-value"}}),
            secret_values=("resolved-secret-value",))
        rendered = plan.results[0].rendered.decode("utf-8")
        self.assertIn("${MAIND_TOKEN}", rendered)
        self.assertNotIn("resolved-secret-value", rendered)
        self.assertNotIn("resolved-secret-value", conformance_report(plan))
        self.assertTrue(all(b"${SECRET_REF}" in row.rendered for row in plan.results))

    def test_duplicate_provider_projections_are_refused(self):
        root = Path(__file__).resolve().parents[3] / "packages/harness/configs"
        catalog = load_mcp_catalog(root / "common/mcp/catalog.json")
        claude = plan_mcp_projection(catalog, provider_id=ProviderId.CLAUDE_CODE,
            bindings_path=root / "claude-code/mcp/bindings.json", selected=(), trusted=True)
        with self.assertRaisesRegex(ProviderDeployError, "MAIND_PROVIDER_DUPLICATE"):
            plan_provider_deploy((claude, claude), semantic_servers(maind={"command": "maind"}))

    def test_consumer_inventory_projects_claude_and_codex_outputs(self):
        root = Path(__file__).resolve().parents[3] / "packages/harness/configs"
        catalog = load_mcp_catalog(root / "common/mcp/catalog.json")
        bases = tuple(plan_mcp_projection(catalog, provider_id=provider,
            bindings_path=root / provider.value / "mcp/bindings.json", selected=(), trusted=True)
            for provider in (ProviderId.CLAUDE_CODE, ProviderId.CODEX))
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp); target = Path(tmp) / "project"; target.mkdir()
            config = merge_defaults({"mcp": {"perplexity_web": {"enabled": True}}, "projects": [{
                "id": "demo", "name": "Demo", "local_path": str(target), "memory_scope": "project:demo",
                "code_graph": {"enabled": True}}]})
            rows = provider_semantic_inventory(env, config, config["projects"][0], with_code=True,
                                               maind_server=True, with_agentmemory=False)
            plan = plan_provider_deploy(bases, rows)
            apply_provider_artifacts(target, plan)
            claude, codex = (target / ".mcp.json").read_bytes(), (target / ".codex/config.toml").read_bytes()
            self.assertIn(b'"codegraph"', claude); self.assertIn(b'"perplexity"', claude)
            self.assertIn(b"[mcp_servers.codegraph]", codex); self.assertIn(b"[mcp_servers.perplexity]", codex)

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
