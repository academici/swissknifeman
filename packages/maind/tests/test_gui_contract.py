"""Контракт статуса (Phase 3) — фиксируем ключи, на которые опирается GUI-панель.

Если схема probe изменится — этот тест упадёт, защищая gui/index.html от молчаливой поломки."""
import tempfile
import unittest
from pathlib import Path

from maind import probe
from maind.config import merge_defaults
from tests.fixtures import make_repo

HUB_KEYS = {"memory", "graph", "docs_watcher"}
MEMORY_KEYS = {"running", "url", "pid"}
GRAPH_KEYS = {"adapter", "nodes", "edges"}
PROJECT_KEYS = {"id", "name", "path", "memory_scope", "configured", "skills",
                "daemons", "status", "trusted"}
CONFIGURED_KEYS = {"agentmemory_mcp", "maind_mcp", "code_mcp", "mcp_files",
                   "skills_lock", "skills_count", "boost", "deployed_flag"}
SKILLS_KEYS = {"total", "swissknifeman", "laravel_boost", "local"}


class TestGuiContract(unittest.TestCase):
    def test_hub_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            hub = probe.probe_hub(env, merge_defaults({}))
            self.assertEqual(set(hub), HUB_KEYS)
            self.assertLessEqual(MEMORY_KEYS, set(hub["memory"]))
            self.assertLessEqual(GRAPH_KEYS, set(hub["graph"]))
            self.assertIn("running", hub["docs_watcher"])

    def test_project_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            ppath = Path(tmp) / "p"
            ppath.mkdir()
            cfg = merge_defaults({"projects": [{"id": "p", "name": "P",
                                                "local_path": str(ppath)}]})
            r = probe.probe_project(env, cfg, cfg["projects"][0], memory_reachable=False)
            self.assertLessEqual(PROJECT_KEYS, set(r))
            self.assertEqual(set(r["configured"]), CONFIGURED_KEYS)
            self.assertEqual(set(r["skills"]), SKILLS_KEYS)


if __name__ == "__main__":
    unittest.main()
