"""Internal documentation."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from harness.mcp import available_mcp, block_mcp, parse_mcp_flag
import tests.fixtures as fx


def run(fn, *a, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*a, **kw)
    return buf.getvalue()


class McpCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_root(self.tmp)
        self.proj = fx.make_project(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def test_available_mcp(self):
        self.assertEqual(available_mcp(self.env), ["context7", "playwright"])

    def test_parse_mcp_flag(self):
        self.assertEqual(parse_mcp_flag("a, b ,,c"), ["a", "b", "c"])
        self.assertEqual(parse_mcp_flag(""), [])
        self.assertEqual(parse_mcp_flag(None), [])

    def test_block_mcp_adds_context7_mergeonly(self):
        (self.proj / ".mcp.json").write_text(json.dumps(
            {"mcpServers": {"maind": {"command": "maind"}}}) + "\n")
        run(block_mcp, self.env, self.proj, ["context7"], False)
        data = json.loads((self.proj / ".mcp.json").read_text())
        self.assertEqual(data["mcpServers"]["context7"],
                         {"type": "http", "url": "https://mcp.context7.com/mcp"})
        self.assertIn("maind", data["mcpServers"])
        self.assertTrue((self.proj / ".mcp.json.bak").exists())

        run(block_mcp, self.env, self.proj, ["context7"], False)
        data2 = json.loads((self.proj / ".mcp.json").read_text())
        self.assertEqual(list(data2["mcpServers"]), list(data["mcpServers"]))

    def test_block_mcp_empty_writes_nothing(self):
        run(block_mcp, self.env, self.proj, [], False)
        self.assertFalse((self.proj / ".mcp.json").exists())

    def test_block_mcp_unknown_preset_skipped(self):
        run(block_mcp, self.env, self.proj, ["nope"], False)
        self.assertFalse((self.proj / ".mcp.json").exists())


if __name__ == "__main__":
    unittest.main()
