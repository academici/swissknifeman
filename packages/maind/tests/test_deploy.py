"""Тесты deploy — провижининг MCP-серверов хаба в проекты (недеструктивно, идемпотентно)."""
import json
import tempfile
import unittest
from pathlib import Path

from maind import deploy
from maind.config import merge_defaults
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
    def test_creates_mcp(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            ppath = _project(tmp)
            cfg = _config(ppath)
            res = deploy.deploy_project(env, cfg, cfg["projects"][0])
            self.assertIsNotNone(res)
            servers = json.loads((ppath / ".mcp.json").read_text())["mcpServers"]
            self.assertIn("maind", servers)
            self.assertNotIn("agentmemory", servers)   # raw-сервер больше не раскатывается
            self.assertEqual(res["scope"], "project:flexcrm")
            self.assertEqual(servers["maind"]["args"], ["mcp", "--scope", "project:flexcrm"])

    def test_removes_stale_agentmemory(self):
        # старый .mcp.json с raw-сервером agentmemory → деплой его убирает (footgun)
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
            self.assertIn("laravel-boost", cursor)  # чужой сохранён
            self.assertIn("maind", cursor)
            self.assertTrue((ppath / ".mcp.json").exists())  # cursor auto-detected → both

    def test_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            ppath = _project(tmp)
            cfg = _config(ppath)
            deploy.deploy_project(env, cfg, cfg["projects"][0])
            res2 = deploy.deploy_project(env, cfg, cfg["projects"][0])
            self.assertTrue(all(not w["changed"] for w in res2["written"]))

    def test_graphify_absent_skipped(self):
        # Команды код-графа нет в PATH → skipped-not-installed, остальное пишется.
        orig = deploy.shutil.which
        deploy.shutil.which = lambda name: None
        try:
            with tempfile.TemporaryDirectory() as tmp:
                _, env = make_repo(tmp)
                ppath = _project(tmp)
                cfg = _config(ppath)
                res = deploy.deploy_project(env, cfg, cfg["projects"][0], with_code=True)
                self.assertEqual(res["code"], "skipped-not-installed")
                servers = json.loads((ppath / ".mcp.json").read_text())["mcpServers"]
                self.assertNotIn("serena", servers)
                self.assertIn("maind", servers)   # сервер памяти на месте
        finally:
            deploy.shutil.which = orig

    def test_graphify_present_written_serena_default(self):
        # Код-граф по умолчанию — Serena через uvx; {root} → путь проекта. Мокаем uvx.
        orig = deploy.shutil.which
        deploy.shutil.which = lambda name: f"/usr/bin/{name}"
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
                self.assertIn(str(ppath), servers["serena"]["args"])   # {root} подставлен
                self.assertNotIn("{root}", servers["serena"]["args"])
        finally:
            deploy.shutil.which = orig

    def test_graphify_override(self):
        # graphify_command/args/server_name → произвольный code-intelligence MCP.
        orig = deploy.shutil.which
        deploy.shutil.which = lambda name: f"/usr/bin/{name}"
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
            self.assertFalse(p["mcp"]["agentmemory"])   # raw-сервер выведен из деплоя

    def test_url_from_resolve_ports(self):
        # legacy raw-сервер (--with-agentmemory) несёт разрешённый URL из resolve_ports
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            ppath = _project(tmp)
            cfg = _config(ppath, http_port=4211)
            deploy.deploy_project(env, cfg, cfg["projects"][0], with_agentmemory=True)
            servers = json.loads((ppath / ".mcp.json").read_text())["mcpServers"]
            self.assertIn("4211", servers["agentmemory"]["env"]["AGENTMEMORY_URL"])

    def test_missing_path_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            cfg = merge_defaults({"projects": [{"id": "x", "name": "X",
                                                "local_path": str(Path(tmp) / "nope")}]})
            self.assertIsNone(deploy.deploy_project(env, cfg, cfg["projects"][0]))


if __name__ == "__main__":
    unittest.main()
