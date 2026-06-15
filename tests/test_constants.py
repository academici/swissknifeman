"""Тесты constants.py: инварианты наборов/портов/scope'ов (защита от рассинхрона)."""
import unittest

from maind import constants as c


class TestConstants(unittest.TestCase):
    def test_graph_adapters_canonical_and_legacy(self):
        self.assertEqual(c.GRAPH_ADAPTERS, {"federation", "disabled"})
        self.assertEqual(c.LEGACY_GRAPH_ADAPTERS, {"memory", "graphify", "networkx"})
        # канонический и legacy наборы не пересекаются
        self.assertFalse(c.GRAPH_ADAPTERS & c.LEGACY_GRAPH_ADAPTERS)

    def test_node_and_edge_types_cover_derive(self):
        # типы, которые реально создаёт derive/seed
        self.assertLessEqual({"project", "package", "skill", "tool"}, c.NODE_TYPES)
        self.assertLessEqual({"depends_on", "requires", "provided_by", "uses"},
                             c.EDGE_TYPES)

    def test_memory_ports_distinct_ints(self):
        ports = [c.MEMORY_HTTP_PORT, c.MEMORY_STREAM_PORT, c.MEMORY_VIEWER_PORT]
        self.assertTrue(all(isinstance(p, int) for p in ports))
        self.assertEqual(len(set(ports)), len(ports))   # без коллизий
        self.assertIn(str(c.MEMORY_HTTP_PORT), c.MEMORY_DEFAULT_URL)

    def test_scope_buckets(self):
        self.assertEqual(c.GLOBAL_SCOPE, "global")
        self.assertEqual(c.NS_SCOPE_PREFIX, "ns:")

    def test_planes_and_via(self):
        self.assertEqual(c.GRAPH_PLANES, {"code", "doc", "meta", "runtime"})
        self.assertEqual(c.LINK_VIA, {"code", "doc", "override", "skills"})

    def test_agent_timings_positive(self):
        self.assertGreater(c.HEARTBEAT_DEFAULT_MS, 0)
        self.assertGreater(c.MAX_IDLE_DEFAULT_MS, c.HEARTBEAT_DEFAULT_MS)
        self.assertGreaterEqual(c.AGENT_STALE_FACTOR, 1)


if __name__ == "__main__":
    unittest.main()
