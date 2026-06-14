"""Тесты graph.py: узлы/рёбра, BFS-соседи, путь, подграф, статистика, персист."""
import tempfile
import unittest

from maind.graph import Graph, open_graph
from tests.fixtures import make_repo


def build(env):
    g = Graph(env)
    g.add_node("project:brain", "project", name="Brain")
    g.add_node("project:skm", "project", name="SKM")
    g.add_node("project:maind", "project", name="maind")
    g.add_node("skill:arch", "skill")
    g.add_edge("project:skm", "project:maind", "depends_on")
    g.add_edge("project:brain", "project:maind", "depends_on")
    g.add_edge("project:brain", "skill:arch", "uses")
    return g


class TestGraph(unittest.TestCase):
    def test_neighbors_depth_and_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            g = build(env)
            self.assertEqual({n["id"] for n in g.neighbors("project:brain", 1)},
                             {"project:maind", "skill:arch"})
            self.assertEqual(
                {n["id"] for n in g.neighbors("project:brain", 1, edge_types=["uses"])},
                {"skill:arch"})
            # direction=in: кто depends_on maind
            self.assertEqual(
                {n["id"] for n in g.neighbors("project:maind", 1, direction="in")},
                {"project:skm", "project:brain"})

    def test_node_type_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            with self.assertRaises(ValueError):
                Graph(env).add_node("x:y", "bogus")

    def test_edge_type_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            g = Graph(env)
            g.add_node("project:a", "project")
            g.add_node("project:b", "project")
            with self.assertRaises(ValueError):
                g.add_edge("project:a", "project:b", "bogus_edge")

    def test_edge_auto_creates_endpoints(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            g = Graph(env)
            g.add_edge("memory:m1", "project:p1", "belongs_to")
            self.assertEqual(g.nodes["memory:m1"]["type"], "memory")
            self.assertEqual(g.nodes["project:p1"]["type"], "project")

    def test_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            g = build(env)
            self.assertEqual(g.path("project:skm", "project:maind"),
                             ["project:skm", "project:maind"])
            self.assertIsNone(g.path("project:maind", "project:skm"))  # нет out-пути
            self.assertEqual(g.path("project:brain", "project:brain"), ["project:brain"])

    def test_subgraph_induced(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            g = build(env)
            sg = g.subgraph(["project:brain", "project:maind"])
            self.assertEqual({n["id"] for n in sg["nodes"]},
                             {"project:brain", "project:maind"})
            self.assertEqual(len(sg["edges"]), 1)  # только brain→maind между ними

    def test_stats(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            s = build(env).stats()
            self.assertEqual(s["nodes"], 4)
            self.assertEqual(s["edges"], 3)
            self.assertEqual(s["by_edge_type"]["depends_on"], 2)
            self.assertEqual(s["by_node_type"]["project"], 3)
            self.assertEqual(s["components"], 1)

    def test_persistence_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            build(env).save()
            g2 = Graph(env).load()
            self.assertEqual(g2.stats()["nodes"], 4)
            self.assertEqual(len(g2.neighbors("project:brain", 1)), 2)

    def test_open_graph_adapters(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            self.assertIsInstance(open_graph(env, {"graph": {"adapter": "memory"}}),
                                  Graph)
            with self.assertRaises(SystemExit):
                open_graph(env, {"graph": {"adapter": "disabled"}})


if __name__ == "__main__":
    unittest.main()
