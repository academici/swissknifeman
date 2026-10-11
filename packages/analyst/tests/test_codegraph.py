"""Tests for analyst.codegraph."""
import unittest

from analyst.codegraph import (codegraph_from_by_name, codegraph_summary,
                                      codegraph_tool_op, scan_run_report)


class TestCodegraphTelemetry(unittest.TestCase):
    def test_mcp_claude_names(self):
        self.assertEqual(codegraph_tool_op("mcp__codegraph__find_symbol"), "find_symbol")
        self.assertEqual(codegraph_tool_op("mcp__plugin_core_codegraph__get_symbols_overview"),
                         "get_symbols_overview")
        self.assertIsNone(codegraph_tool_op("mcp__maind__maind_memory_recall"))

    def test_cursor_mcp_prefix(self):
        self.assertEqual(codegraph_tool_op("MCP:plugin-core-codegraph:find_symbol"),
                         "find_symbol")
        self.assertEqual(codegraph_tool_op("mcp:laravel-boost:search-docs"), "search-docs")

    def test_aggregate_by_name(self):
        block = codegraph_from_by_name({
            "Grep": 10,
            "mcp__codegraph__find_symbol": 2,
            "mcp__plugin_core_codegraph__find_symbol": 1,
            "mcp__perplexity-web__search": 3,
        })
        self.assertEqual(block["find_symbol"]["calls"], 3)

    def test_scan_run_report_prefers_block(self):
        rep = {"codegraph": {"find_symbol": {"calls": 5}},
               "tools": {"by_name": {"mcp__codegraph__find_symbol": 1}}}
        self.assertEqual(scan_run_report(rep)["calls"], 5)


if __name__ == "__main__":
    unittest.main()
