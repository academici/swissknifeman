"""Tests constants.py: set invariants/ports/scope'ov (protection against desync)."""
import json
import unittest
from pathlib import Path

from maind import constants as c

try:
    from aicore.util.repo import find_monorepo_root
except ImportError:
    find_monorepo_root = None


class TestConstants(unittest.TestCase):
    def test_graph_adapters_canonical_and_legacy(self):
        self.assertEqual(c.GRAPH_ADAPTERS, {"federation", "disabled"})
        self.assertEqual(c.LEGACY_GRAPH_ADAPTERS, {"memory", "graphify", "networkx"})
        # canonical and legacy sets do not intersect
        self.assertFalse(c.GRAPH_ADAPTERS & c.LEGACY_GRAPH_ADAPTERS)

    def test_node_and_edge_types_cover_derive(self):
        # types that actually creates derive/seed
        self.assertLessEqual({"project", "package", "skill", "tool"}, c.NODE_TYPES)
        self.assertLessEqual({"depends_on", "requires", "provided_by", "uses"},
                             c.EDGE_TYPES)

    def test_memory_ports_distinct_ints(self):
        ports = [c.MEMORY_HTTP_PORT, c.MEMORY_STREAM_PORT, c.MEMORY_VIEWER_PORT]
        self.assertTrue(all(isinstance(p, int) for p in ports))
        self.assertEqual(len(set(ports)), len(ports))   # without collisions
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
        # F1 (P5.5, D115/D116): versionable policy templates code_graph are required to bear
        # same REF, what constants.SERENA_SRC — otherwise a fresh installation rolls out
        # unpinned politics. The policy lives in the defaults of the [maind] settings schema.
        if find_monorepo_root is None:
            self.skipTest("core.repo not available (standalone-package layout)")
        root = find_monorepo_root(__file__)
        if root is None:
            self.skipTest("monorepo root not found (standalone-package layout)")

        schema_path = Path(__file__).resolve().parents[1] / "configs" / "config.schema.json"
        with open(schema_path, encoding="utf-8") as f:
            code_graph = json.load(f)["properties"]["code_graph"]["properties"]
        for field in ("args", "index_args"):
            values = [a for a in code_graph[field]["default"] if a.startswith("git+")]
            self.assertEqual(values, [c.SERENA_SRC],
                              f"config.schema.json code_graph.{field} is not pinned on "
                              f"constants.SERENA_SRC ({c.SERENA_SRC!r}): {values!r}")

        with open(root / ".mcp.json.example", encoding="utf-8") as f:
            mcp_example = json.load(f)
        servers = (mcp_example.get("mcpServers") or {})
        codegraph = servers.get("codegraph") or servers.get("serena")
        if codegraph is None:
            return  # umbrella without codegraph — pin Serena is checked via code_graph above
        serena_args = codegraph["args"]
        from_idx = serena_args.index("--from")
        self.assertEqual(serena_args[from_idx + 1], c.SERENA_SRC,
                          f".mcp.json.example codegraph.args is not pinned on "
                          f"constants.SERENA_SRC ({c.SERENA_SRC!r}): "
                          f"{serena_args[from_idx + 1]!r}")


if __name__ == "__main__":
    unittest.main()
