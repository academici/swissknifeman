"""Тесты federation.py: per-project сторы, индекс, union-запрос через границу, views."""
import tempfile
import unittest

from maind import federation
from maind.config import load_config
from maind.graph import Graph
from tests.fixtures import make_repo, write_maind_config

FED_PROJECTS = [
    {"id": "flexcrm", "name": "FlexCRM", "type": "php-package", "status": "active",
     "enabled": True, "memory_scope": "project:flexcrm"},
    {"id": "azguard", "name": "AzGuard", "type": "php-package", "status": "active",
     "enabled": True, "memory_scope": "project:azguard"},
]

PKG = "package:axioma-studio/azguard-core"


def _setup(tmp):
    root, env = make_repo(tmp)
    write_maind_config(root, graph={"adapter": "federation"}, projects=FED_PROJECTS)
    config, _ = load_config(env)
    flex, az = config["projects"][0], config["projects"][1]

    fg = Graph(env, config, path=federation.store_path(env, config, flex)).load()
    fg.add_node("project:flexcrm", "project", project="flexcrm", name="FlexCRM")
    fg.add_node(PKG, "package")  # заглушка-конечник: владелец — azguard
    fg.add_edge("project:flexcrm", PKG, "requires", via="code", plane="code")
    fg.add_edge("project:flexcrm", "project:azguard", "depends_on", via="code", plane="code")
    fg.save()

    ag = Graph(env, config, path=federation.store_path(env, config, az)).load()
    ag.add_node("project:azguard", "project", project="azguard", name="AzGuard")
    ag.add_node(PKG, "package", project="azguard", name="azguard-core")
    ag.add_node("skill:rbac", "skill", project="azguard")  # внутренний узел azguard
    ag.add_edge("project:azguard", "skill:rbac", "uses", via="skills", plane="code")
    ag.save()
    return env, config


class TestFederation(unittest.TestCase):
    def test_store_path_default_and_local(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            config, _ = load_config(env)
            hub = federation.store_path(env, config, {"id": "x"})
            self.assertEqual(hub, env.data_dir / "graphs" / "x.db")
            loc = federation.store_path(env, config,
                                        {"id": "x", "graph_store": "local",
                                         "local_path": str(root)})
            self.assertEqual(loc, root / ".maind" / "graph.db")

    def test_federated_query_crosses_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config = _setup(tmp)
            # из flexcrm на глубину 1 виден azguard (cross-ребро) и пакет
            res = federation.Federation(env, config).query("project:flexcrm", depth=1)
            ids = {n["id"] for n in res["neighbors"]}
            self.assertIn("project:azguard", ids)
            self.assertIn(PKG, ids)

    def test_rebuild_index_marks_cross_edges(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config = _setup(tmp)
            stats = federation.rebuild_index(env, config)
            self.assertEqual(stats["projects"], 2)
            # flexcrm→azguard и flexcrm→azguard-core — оба межпроектные
            self.assertGreaterEqual(stats["cross_edges"], 2)
            cross = federation.Federation(env, config).cross()
            srcs = {e["src"] for e in cross["edges"]}
            self.assertIn("project:flexcrm", srcs)

    def test_project_view_is_isolated(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config = _setup(tmp)
            view = federation.Federation(env, config).project_view("flexcrm")
            ids = {n["id"] for n in view["nodes"]}
            self.assertIn("project:flexcrm", ids)
            self.assertIn("project:azguard", ids)   # исходящая граница — видна
            # но внутренний узел azguard в стор flexcrm не утекает
            self.assertNotIn("skill:rbac", ids)

    def test_stats_has_per_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config = _setup(tmp)
            federation.rebuild_index(env, config)
            s = federation.Federation(env, config).stats()
            self.assertIn("per_project", s)
            self.assertIn("flexcrm", s["per_project"])
            self.assertGreaterEqual(s["cross_edges"], 2)


if __name__ == "__main__":
    unittest.main()
