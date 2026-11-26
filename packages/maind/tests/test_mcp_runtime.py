"""Tests for host-level MCP runtime scan."""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from maind.mcp_runtime import runtime_summary, scan_runtime


class TestMcpRuntime(unittest.TestCase):
    def test_scan_runtime_detects_duplicate_project(self):
        ps = "\n".join([
            "111 100000 serena start-mcp-server --project /tmp/a",
            "222 200000 serena start-mcp-server --project /tmp/a",
            "333 600000 node intelephense --stdio",
        ])
        with mock.patch("maind.mcp_runtime.subprocess.check_output", return_value=ps):
            snap = scan_runtime()
        self.assertEqual(len(snap["duplicates"]), 1)
        self.assertEqual(snap["duplicates"][0]["count"], 2)
        self.assertTrue(snap["heavy"])
        self.assertIn("dup:", runtime_summary(snap))
