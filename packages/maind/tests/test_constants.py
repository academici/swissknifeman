"""Тесты constants.py: инварианты наборов/портов/scope'ов (защита от рассинхрона)."""
import json
import unittest

from maind import constants as c

try:
    from core.repo import find_monorepo_root
except ImportError:
    find_monorepo_root = None


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

    def test_tracked_templates_pin_serena_same_as_source(self):
        # F1 (P5.5, D115/D116): версионируемые шаблоны политики code_graph обязаны нести
        # тот же REF, что constants.SERENA_SRC — иначе свежая установка (install.sh
        # `cp config.example.json → config.json`) раскатывает непиннованную политику.
        if find_monorepo_root is None:
            self.skipTest("core.repo недоступен (standalone-раскладка пакета)")
        root = find_monorepo_root(__file__)
        if root is None:
            self.skipTest("корень монорепо не найден (standalone-раскладка пакета)")

        with open(root / "config.example.json", encoding="utf-8") as f:
            cfg_example = json.load(f)
        code_graph = cfg_example["code_graph"]
        for field in ("args", "index_args"):
            values = [a for a in code_graph[field] if a.startswith("git+")]
            self.assertEqual(values, [c.SERENA_SRC],
                              f"config.example.json code_graph.{field} не пиннован на "
                              f"constants.SERENA_SRC ({c.SERENA_SRC!r}): {values!r}")

        with open(root / ".mcp.json.example", encoding="utf-8") as f:
            mcp_example = json.load(f)
        codegraph = mcp_example["mcpServers"]["codegraph"]
        serena_args = codegraph["args"]
        from_idx = serena_args.index("--from")
        self.assertEqual(serena_args[from_idx + 1], c.SERENA_SRC,
                          f".mcp.json.example codegraph.args не пиннован на "
                          f"constants.SERENA_SRC ({c.SERENA_SRC!r}): "
                          f"{serena_args[from_idx + 1]!r}")


if __name__ == "__main__":
    unittest.main()
