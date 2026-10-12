"""Tests deploy — provisioning MCP-hub servers into projects (non-destructive, idempotent)."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from aicore.provider.values import ProviderId
from maind.provision import deploy
from maind.config import merge_defaults
from maind.provider_deploy import ProviderDeployError
from maind.projects import get
from tests.fixtures import make_repo


def _project(tmp, pid="flexcrm", with_cursor_boost=False):
    path = Path(tmp) / "proj" / pid
    path.mkdir(parents=True)
    if with_cursor_boost:
        (path / ".cursor").mkdir()
        (path / ".cursor" / "mcp.json").write_text(
            json.dumps({"mcpServers": {"laravel-boost": {"command": "php"}}}),
            encoding="utf-8")
    return path


def _config(path, pid="flexcrm", **memory):
    return merge_defaults({
        "memory": memory or {},
        "projects": [{"id": pid, "name": pid.title(), "local_path": str(path),
                      "memory_scope": f"project:{pid}"}]})


class TestDeploy(unittest.TestCase):
    def test_provider_projection_uses_exact_project_provider_carrier(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            project_path = _project(tmp)
            (project_path / ".swissknife.json").write_text(json.dumps({
                "providers": {
                    "contract_version": "1.0.0",
                    "selection": {
                        "claude-code": {"enabled": True},
                        "codex": {"enabled": True},
                    },
                },
            }), encoding="utf-8")
            cfg = _config(project_path)

            context = deploy.provider_projection_context(env, cfg, cfg["projects"][0])

            self.assertEqual(context.providers,
                             (ProviderId.CLAUDE_CODE, ProviderId.CODEX))

    def test_provider_projection_missing_project_carrier_preserves_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            project_path = _project(tmp)
            cfg = _config(project_path)

            context = deploy.provider_projection_context(env, cfg, cfg["projects"][0])

            self.assertEqual(context.providers, (ProviderId.CLAUDE_CODE,))

    def test_provider_projection_refuses_symlink_project_carrier(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            project_path = _project(tmp)
            foreign = Path(tmp) / "foreign.json"
            foreign.write_text(json.dumps({
                "providers": {
                    "contract_version": "1.0.0",
                    "selection": {
                        "claude-code": {"enabled": True},
                        "codex": {"enabled": True},
                    },
                },
            }), encoding="utf-8")
            (project_path / ".swissknife.json").symlink_to(foreign)
            cfg = _config(project_path)

            with self.assertRaisesRegex(
                    ValueError, "MAIND_PROJECT_PROVIDER_CONFIG_UNSAFE"):
                deploy.provider_projection_context(env, cfg, cfg["projects"][0])

    def test_provider_projection_refuses_invalid_project_carrier(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            project_path = _project(tmp)
            (project_path / ".swissknife.json").write_text(
                '{"providers": [}', encoding="utf-8")
            cfg = _config(project_path)

            with self.assertRaisesRegex(
                    ValueError, "MAIND_PROJECT_PROVIDER_CONFIG_INVALID"):
                deploy.provider_projection_context(env, cfg, cfg["projects"][0])

    def test_d108_public_facade_uses_configured_root_not_maind_root(self):
        """D112: package-root Env cannot become the D108 project identity."""
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            project_path = _project(tmp, "swissknifeman")
            cfg = _config(project_path, "swissknifeman")
            current = deploy.provider_projection_context(env, cfg, cfg["projects"][0]).projections
            self.assertEqual([base.provider_id for base in current], [ProviderId.CLAUDE_CODE])
            operation = SimpleNamespace(
                deploy=SimpleNamespace(results=()), transfer=SimpleNamespace(),
                carrier=SimpleNamespace(changed=False), chained_plan=SimpleNamespace(actions=()))
            with mock.patch.object(deploy, "plan_d108_operation", return_value=operation) as planner, \
                    mock.patch.object(deploy, "bootstrap_transfer_projection",
                                      return_value={"status": "admitted", "actions": (), "diagnostic": None}), \
                    mock.patch.object(deploy, "project_provider_preflight",
                                      side_effect=lambda plan, _checked: plan), \
                    mock.patch.object(deploy, "apply_d108_operation") as writer:
                deploy.deploy_project(env, cfg, cfg["projects"][0], d108=True, dry=True,
                                      provider_projections=current)
            self.assertEqual(planner.call_args.args[0], project_path.resolve())
            self.assertEqual(planner.call_args.kwargs["expected_root"], project_path.resolve())
            self.assertNotEqual(planner.call_args.kwargs["expected_root"], env.root)
            writer.assert_not_called()

    def test_d108_public_facade_refuses_foreign_project_before_writer(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            project_path = _project(tmp, "foreign")
            cfg = _config(project_path, "foreign")
            with mock.patch.object(deploy, "apply_d108_operation") as writer:
                with self.assertRaisesRegex(ProviderDeployError, "MAIND_D108_FOREIGN_PROJECT"):
                    deploy.deploy_project(env, cfg, cfg["projects"][0], d108=True, dry=True)
            writer.assert_not_called()

    def test_cmd_deploy_refused_bootstrap_does_not_write_project_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            ppath = _project(tmp)
            cfg = _config(ppath)
            result = {"id": "flexcrm", "scope": "project:flexcrm", "written": [],
                      "skipped": [], "code": "disabled", "servers": [], "targets": [],
                      "provider_changed": False,
                      "provider_plan": SimpleNamespace(green=True, results=()),
                      "bootstrap_transfer": {"status": "refused", "actions": (),
                                             "diagnostic": "MAIND_PROVIDER_DEPLOY_REFUSED"}}
            with mock.patch.object(deploy, "load_config", return_value=(cfg, None)), \
                    mock.patch.object(deploy, "health", return_value=True), \
                    mock.patch.object(deploy, "deploy_project", return_value=result), \
                    mock.patch.object(deploy, "write_registry") as write_registry:
                deploy.cmd_deploy(env, ["--project", "flexcrm"])
            write_registry.assert_not_called()

    def test_claude_only_dry_run_reports_bootstrap_not_selected(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            ppath = _project(tmp)
            (ppath / ".codex/hooks").mkdir(parents=True)
            (ppath / ".codex/hooks.json").write_text('{"hooks":{"SessionStart":[]}}',
                                                       encoding="utf-8")
            cfg = _config(ppath)
            projections = deploy.provider_projection_context(env, cfg, cfg["projects"][0]).projections
            self.assertEqual([projection.provider_id for projection in projections],
                             [ProviderId.CLAUDE_CODE])
            result = deploy.deploy_project(env, cfg, cfg["projects"][0], dry=True,
                                            provider_projections=projections)
            self.assertEqual(result["bootstrap_transfer"]["status"], "not-selected")
            self.assertFalse((ppath / ".mcp.json").exists())

    def test_creates_mcp(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            ppath = _project(tmp)
            cfg = _config(ppath)
            res = deploy.deploy_project(env, cfg, cfg["projects"][0])
            self.assertIsNotNone(res)
            servers = json.loads((ppath / ".mcp.json").read_text())["mcpServers"]
            self.assertIn("maind", servers)
            self.assertNotIn("agentmemory", servers)   # raw-server no longer rolls out
            self.assertEqual(res["scope"], "project:flexcrm")
            self.assertEqual(servers["maind"]["args"], ["mcp", "--scope", "project:flexcrm"])
            # MCP-client starts bare command without shell expansion.
            self.assertEqual(servers["maind"]["command"], "maind")
            self.assertNotIn("/", servers["maind"]["command"])

    def test_emits_example_by_default(self):
        # P2.4: default-on — without explicit mcp.emit_example deployment writes .mcp.json.example
        # and brings the real file into the .gitignore.
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            ppath = _project(tmp)
            cfg = _config(ppath)
            deploy.deploy_project(env, cfg, cfg["projects"][0])
            self.assertTrue((ppath / ".mcp.json.example").exists())
            gitignore = (ppath / ".gitignore").read_text(encoding="utf-8").splitlines()
            self.assertIn(".mcp.json", gitignore)
            self.assertNotIn(".mcp.json.example", gitignore)

    def test_emit_example_opt_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            ppath = _project(tmp)
            cfg = _config(ppath)
            cfg["mcp"]["emit_example"] = False
            deploy.deploy_project(env, cfg, cfg["projects"][0])
            self.assertTrue((ppath / ".mcp.json").exists())
            self.assertFalse((ppath / ".mcp.json.example").exists())
            self.assertFalse((ppath / ".gitignore").exists())

    def test_emit_example_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            ppath = _project(tmp)
            cfg = _config(ppath)
            deploy.deploy_project(env, cfg, cfg["projects"][0])
            first_example = (ppath / ".mcp.json.example").read_text(encoding="utf-8")
            first_gitignore = (ppath / ".gitignore").read_text(encoding="utf-8")
            deploy.deploy_project(env, cfg, cfg["projects"][0])  # second run - no duplicates
            self.assertEqual((ppath / ".mcp.json.example").read_text(encoding="utf-8"),
                             first_example)
            self.assertEqual((ppath / ".gitignore").read_text(encoding="utf-8"), first_gitignore)

    def test_removes_stale_agentmemory(self):
        # old .mcp.json with raw-server agentmemory → deployment removes it (footgun)
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            ppath = _project(tmp)
            (ppath / ".mcp.json").write_text(
                json.dumps({"mcpServers": {"agentmemory": {"command": "x"}}}), encoding="utf-8")
            cfg = _config(ppath)
            deploy.deploy_project(env, cfg, cfg["projects"][0])
            servers = json.loads((ppath / ".mcp.json").read_text())["mcpServers"]
            self.assertNotIn("agentmemory", servers)
            self.assertIn("maind", servers)

    def test_preserves_boost_in_cursor(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            ppath = _project(tmp, with_cursor_boost=True)
            cfg = _config(ppath)
            deploy.deploy_project(env, cfg, cfg["projects"][0])
            cursor = json.loads((ppath / ".cursor" / "mcp.json").read_text())["mcpServers"]
            self.assertIn("laravel-boost", cursor)  # alien saved
            self.assertIn("maind", cursor)
            self.assertTrue((ppath / ".mcp.json").exists())  # cursor auto-detected → both

    def test_preserves_foreign_server_in_mcp_json(self):
        # Manual third party server (playwright) in .mcp.json is NOT thrown out during deployment.
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            ppath = _project(tmp)
            (ppath / ".mcp.json").write_text(
                json.dumps({"mcpServers": {
                    "playwright": {"command": "bash", "args": ["scripts/playwright-mcp.sh"]}}}),
                encoding="utf-8")
            cfg = _config(ppath)
            deploy.deploy_project(env, cfg, cfg["projects"][0])
            servers = json.loads((ppath / ".mcp.json").read_text())["mcpServers"]
            self.assertIn("playwright", servers)            # alien saved
            self.assertEqual(servers["playwright"]["args"], ["scripts/playwright-mcp.sh"])
            self.assertIn("maind", servers)

    def test_broken_channel_skipped_others_continue(self):
        # Broken .cursor/mcp.json Deployment does NOT fail: we skip it (do not touch), .mcp.json we write.
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            ppath = _project(tmp)
            (ppath / ".cursor").mkdir()
            broken = ppath / ".cursor" / "mcp.json"
            broken.write_text("{ broken json", encoding="utf-8")
            cfg = _config(ppath)
            res = deploy.deploy_project(env, cfg, cfg["projects"][0])  # does not throw
            self.assertIn(".cursor/mcp.json", res["skipped"])
            self.assertEqual(broken.read_text(encoding="utf-8"), "{ broken json")  # untouched
            servers = json.loads((ppath / ".mcp.json").read_text())["mcpServers"]
            self.assertIn("maind", servers)                 # valid channel completed

    def test_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            ppath = _project(tmp)
            cfg = _config(ppath)
            deploy.deploy_project(env, cfg, cfg["projects"][0])
            res2 = deploy.deploy_project(env, cfg, cfg["projects"][0])
            self.assertTrue(all(not w["changed"] for w in res2["written"]))

    def test_graphify_absent_skipped(self):
        # There is no code graph command in PATH → skipped-not-installed, the rest is written.
        orig = deploy.shutil.which
        deploy.shutil.which = lambda name, *a, **k: None
        try:
            with tempfile.TemporaryDirectory() as tmp:
                _, env = make_repo(tmp)
                ppath = _project(tmp)
                cfg = _config(ppath)
                res = deploy.deploy_project(env, cfg, cfg["projects"][0], with_code=True)
                self.assertEqual(res["code"], "skipped-not-installed")
                servers = json.loads((ppath / ".mcp.json").read_text())["mcpServers"]
                self.assertNotIn("serena", servers)
                self.assertIn("maind", servers)   # memory server in place
        finally:
            deploy.shutil.which = orig

    def test_graphify_present_written_serena_default(self):
        # Default code graph is Serena via uvx; {root} → project path. Let's mokay uvx.
        orig = deploy.shutil.which
        deploy.shutil.which = lambda name, *a, **k: f"/usr/bin/{name}"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                _, env = make_repo(tmp)
                ppath = _project(tmp)
                cfg = _config(ppath)
                res = deploy.deploy_project(env, cfg, cfg["projects"][0], with_code=True)
                self.assertEqual(res["code"], "written")
                servers = json.loads((ppath / ".mcp.json").read_text())["mcpServers"]
                self.assertEqual(servers["serena"]["command"], "uvx")
                self.assertIn("start-mcp-server", servers["serena"]["args"])
                self.assertIn(str(ppath), servers["serena"]["args"])   # {root} substituted
                self.assertNotIn("{root}", servers["serena"]["args"])
        finally:
            deploy.shutil.which = orig

    def test_graphify_override(self):
        # graphify_command/args/server_name → arbitrary code-intelligence MCP.
        orig = deploy.shutil.which
        deploy.shutil.which = lambda name, *a, **k: f"/usr/bin/{name}"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                _, env = make_repo(tmp)
                ppath = _project(tmp)
                cfg = _config(ppath)
                cfg["projects"][0].update({
                    "graphify_command": "php",
                    "graphify_args": ["artisan", "boost:mcp"],
                    "graphify_server_name": "laravel-boost"})
                res = deploy.deploy_project(env, cfg, cfg["projects"][0], with_code=True)
                self.assertEqual(res["code"], "written")
                servers = json.loads((ppath / ".mcp.json").read_text())["mcpServers"]
                self.assertEqual(servers["laravel-boost"]["command"], "php")
                self.assertEqual(servers["laravel-boost"]["args"], ["artisan", "boost:mcp"])
        finally:
            deploy.shutil.which = orig

    def test_mark_deployed_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            ppath = _project(tmp)
            cfg = _config(ppath)
            res = deploy.deploy_project(env, cfg, cfg["projects"][0])
            cfg = deploy.mark_deployed(cfg, "flexcrm", res)
            p = get(cfg, "flexcrm")
            self.assertTrue(p["deployed"])
            self.assertEqual(p["mcp"]["scope"], "project:flexcrm")
            self.assertTrue(p["mcp"]["maind"])
            self.assertFalse(p["mcp"]["agentmemory"])   # raw-server has been taken out of deployment

    def test_mark_deployed_preserves_extra_servers(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            ppath = _project(tmp)
            cfg = _config(ppath)
            extra = {"blender": {"command": "/usr/bin/blender-mcp"}}
            cfg["projects"][0]["mcp"] = {"extra_servers": extra}
            res = deploy.deploy_project(env, cfg, cfg["projects"][0])
            cfg = deploy.mark_deployed(cfg, "flexcrm", res)
            p = get(cfg, "flexcrm")
            self.assertEqual(p["mcp"]["extra_servers"], extra)

    def test_url_from_resolve_ports(self):
        # legacy raw-server (--with-agentmemory) carries permitted URL from resolve_ports
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            ppath = _project(tmp)
            cfg = _config(ppath, http_port=4211)
            deploy.deploy_project(env, cfg, cfg["projects"][0], with_agentmemory=True)
            servers = json.loads((ppath / ".mcp.json").read_text())["mcpServers"]
            self.assertIn("4211", servers["agentmemory"]["env"]["AGENTMEMORY_URL"])

    def test_perplexity_web_disabled_by_default(self):
        # Without section mcp.perplexity_web server does not roll out (opt-in).
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            ppath = _project(tmp)
            cfg = _config(ppath)
            deploy.deploy_project(env, cfg, cfg["projects"][0])
            servers = json.loads((ppath / ".mcp.json").read_text())["mcpServers"]
            self.assertNotIn("perplexity-web", servers)

    def _config_pw(self, path, pid="flexcrm", pool="default", **pw):
        return merge_defaults({
            "mcp": {"perplexity_web": {"enabled": True, "pool": pool,
                                       "bin": "/opt/pplx/start.sh", **pw}},
            "projects": [{"id": pid, "name": pid.title(), "local_path": str(path),
                          "namespaces": ["axioma"], "memory_scope": f"project:{pid}"}]})

    def test_perplexity_web_enabled_default_pool(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            ppath = _project(tmp)
            cfg = self._config_pw(ppath)
            res = deploy.deploy_project(env, cfg, cfg["projects"][0])
            servers = json.loads((ppath / ".mcp.json").read_text())["mcpServers"]
            self.assertIn("perplexity-web", servers)
            self.assertIn("perplexity-web", res["servers"])
            self.assertEqual(servers["perplexity-web"]["args"], ["--pool=default"])
            # MCP-client starts launcher directly, so shell-indirection is not valid.
            self.assertEqual(servers["perplexity-web"]["command"],
                             "/opt/pplx/start.sh")

    def test_perplexity_web_per_project_pool(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            ppath = _project(tmp)
            cfg = self._config_pw(ppath, pool="per-project")
            deploy.deploy_project(env, cfg, cfg["projects"][0])
            servers = json.loads((ppath / ".mcp.json").read_text())["mcpServers"]
            self.assertEqual(servers["perplexity-web"]["args"], ["--pool=flexcrm"])

    def test_perplexity_web_per_namespace_pool(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            ppath = _project(tmp)
            cfg = self._config_pw(ppath, pool="per-namespace")
            deploy.deploy_project(env, cfg, cfg["projects"][0])
            servers = json.loads((ppath / ".mcp.json").read_text())["mcpServers"]
            self.assertEqual(servers["perplexity-web"]["args"], ["--pool=ns-axioma"])

    def test_perplexity_web_per_project_override(self):
        # per-project override shuts down the server even with global enabled.
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            ppath = _project(tmp)
            cfg = self._config_pw(ppath)
            cfg["projects"][0]["perplexity_web"] = False
            deploy.deploy_project(env, cfg, cfg["projects"][0])
            servers = json.loads((ppath / ".mcp.json").read_text())["mcpServers"]
            self.assertNotIn("perplexity-web", servers)

    def test_perplexity_web_pool_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            ppath = _project(tmp)
            cfg = self._config_pw(ppath, pool="per-project")
            cfg["projects"][0]["perplexity_web_pool"] = "research"
            deploy.deploy_project(env, cfg, cfg["projects"][0])
            servers = json.loads((ppath / ".mcp.json").read_text())["mcpServers"]
            self.assertEqual(servers["perplexity-web"]["args"], ["--pool=research"])

    def test_perplexity_web_mark_deployed(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            ppath = _project(tmp)
            cfg = self._config_pw(ppath)
            res = deploy.deploy_project(env, cfg, cfg["projects"][0])
            cfg = deploy.mark_deployed(cfg, "flexcrm", res)
            self.assertTrue(get(cfg, "flexcrm")["mcp"]["perplexity_web"])

    def test_missing_path_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            cfg = merge_defaults({"projects": [{"id": "x", "name": "X",
                                                "local_path": str(Path(tmp) / "nope")}]})
            self.assertIsNone(deploy.deploy_project(env, cfg, cfg["projects"][0]))


if __name__ == "__main__":
    unittest.main()
