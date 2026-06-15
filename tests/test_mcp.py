"""Тесты mcp.py: JSON-RPC роутинг (initialize/tools), вызовы инструментов, framing."""
import io
import json
import tempfile
import unittest

from maind import mcp
from maind import memory as memory_mod
from maind.config import merge_defaults
from maind.graph import Graph
from tests.fixtures import FakeMemoryServer, make_repo


def cfg(**over):
    base = merge_defaults({})
    base.update(over)
    return base


def call(env, config, name, arguments=None, req_id=1):
    return mcp.dispatch(env, config, {
        "jsonrpc": "2.0", "id": req_id, "method": "tools/call",
        "params": {"name": name, "arguments": arguments or {}}})


class TestDispatch(unittest.TestCase):
    def test_initialize(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            r = mcp.dispatch(env, cfg(), {"jsonrpc": "2.0", "id": 1,
                                          "method": "initialize"})
            self.assertEqual(r["result"]["serverInfo"]["name"], "maind")
            self.assertIn("protocolVersion", r["result"])

    def test_tools_list_has_six(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            r = mcp.dispatch(env, cfg(), {"jsonrpc": "2.0", "id": 2,
                                          "method": "tools/list"})
            self.assertEqual(len(r["result"]["tools"]), 6)

    def test_initialized_no_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            self.assertIsNone(mcp.dispatch(env, cfg(), {
                "jsonrpc": "2.0", "method": "notifications/initialized"}))

    def test_unknown_method(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            r = mcp.dispatch(env, cfg(), {"jsonrpc": "2.0", "id": 9, "method": "bogus"})
            self.assertEqual(r["error"]["code"], -32601)

    def test_unknown_tool(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            r = call(env, cfg(), "nope")
            self.assertEqual(r["error"]["code"], -32601)


class TestToolCalls(unittest.TestCase):
    def test_projects_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            r = call(env, cfg(projects=[{"id": "x", "name": "X"}]),
                     "maind_projects_list")
            data = json.loads(r["result"]["content"][0]["text"])
            self.assertEqual(data[0]["id"], "x")

    def test_graph_query(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            g = Graph(env)
            g.add_edge("project:a", "project:b", "depends_on")
            g.save()
            r = call(env, cfg(), "maind_graph_query", {"from": "project:a"})
            data = json.loads(r["result"]["content"][0]["text"])
            self.assertEqual(data["count"], 1)

    def test_memory_recall_against_fake(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            with FakeMemoryServer() as url:
                memory_mod.store(url, "project:x", "fact", "hello world")
                r = call(env, cfg(memory={"url": url}), "maind_memory_recall",
                         {"scope": "project:x", "query": "hello"})
                data = json.loads(r["result"]["content"][0]["text"])
                self.assertEqual(data[0]["text"], "hello world")

    def test_memory_down_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            r = call(env, cfg(memory={"url": "http://127.0.0.1:1"}),
                     "maind_memory_recall", {"scope": "x", "query": "y"})
            self.assertTrue(r["result"]["isError"])


class TestFraming(unittest.TestCase):
    def test_roundtrip(self):
        buf = io.BytesIO()
        mcp.write_message(buf, {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}})
        buf.seek(0)
        msg = mcp.read_message(buf)
        self.assertTrue(msg["result"]["ok"])

    def test_wire_is_newline_delimited(self):
        # реальный MCP-клиент (Cursor/Claude) шлёт NDJSON, НЕ Content-Length
        raw = b'{"jsonrpc":"2.0","id":7,"method":"tools/list"}\n'
        self.assertEqual(mcp.read_message(io.BytesIO(raw))["method"], "tools/list")
        buf = io.BytesIO()
        mcp.write_message(buf, {"id": 1, "result": {}})
        out = buf.getvalue()
        self.assertTrue(out.endswith(b"\n"))
        self.assertEqual(out.count(b"\n"), 1)          # одно сообщение = одна строка
        self.assertNotIn(b"Content-Length", out)        # никаких LSP-заголовков

    def test_serve_processes_then_eof(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            inp, outp = io.BytesIO(), io.BytesIO()
            mcp.write_message(inp, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
            inp.seek(0)
            mcp.serve(env, cfg(), stdin=inp, stdout=outp)
            outp.seek(0)
            resp = mcp.read_message(outp)
            self.assertEqual(len(resp["result"]["tools"]), 6)


if __name__ == "__main__":
    unittest.main()
