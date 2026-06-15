"""Тесты mcp.py: JSON-RPC роутинг, вызовы инструментов, framing, conformance (реальный spawn)."""
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

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

    def test_tools_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            r = mcp.dispatch(env, cfg(), {"jsonrpc": "2.0", "id": 2,
                                          "method": "tools/list"})
            names = {t["name"] for t in r["result"]["tools"]}
            self.assertEqual(len(names), 11)
            self.assertTrue({"maind_graph_path", "maind_projects_status",
                             "maind_memory_forget", "maind_graph_project",
                             "maind_memory_links"} <= names)

    def test_protocol_version_echo(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            r = mcp.dispatch(env, cfg(), {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                          "params": {"protocolVersion": "2025-03-26"}})
            self.assertEqual(r["result"]["protocolVersion"], "2025-03-26")

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

    def test_graph_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            g = Graph(env)
            g.add_edge("project:a", "project:b", "depends_on")
            g.save()
            r = call(env, cfg(), "maind_graph_path", {"from": "project:a", "to": "project:b"})
            data = json.loads(r["result"]["content"][0]["text"])
            self.assertEqual(data["path"], ["project:a", "project:b"])

    def test_projects_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            r = call(env, cfg(projects=[{"id": "x", "name": "X"}]), "maind_projects_status")
            data = json.loads(r["result"]["content"][0]["text"])
            self.assertIn("hub", data)
            self.assertIn("projects", data)

    def test_memory_forget_unsupported_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            with FakeMemoryServer() as url:  # /forget не реализован → RuntimeError → isError
                r = call(env, cfg(memory={"url": url}), "maind_memory_forget",
                         {"scope": "project:x", "key": "k"})
                self.assertTrue(r["result"]["isError"])

    def test_missing_required_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            r = call(env, cfg(), "maind_graph_query", {})  # нет обязательного from
            self.assertTrue(r["result"]["isError"])
            self.assertIn("не хватает", r["result"]["content"][0]["text"])

    def test_auto_scope_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            with FakeMemoryServer() as url:
                # store без scope → уходит в default_scope
                mcp.dispatch(env, cfg(memory={"url": url}),
                             {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                              "params": {"name": "maind_memory_store",
                                         "arguments": {"value": "scoped fact"}}},
                             default_scope="project:flexcrm")
                r = call(env, cfg(memory={"url": url}), "maind_memory_recall",
                         {"scope": "project:flexcrm", "query": "scoped"})
                data = json.loads(r["result"]["content"][0]["text"])
                self.assertEqual(data[0]["text"], "scoped fact")

    def test_tool_error_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)  # граф disabled → die() → SystemExit → isError
            r = call(env, cfg(graph={"adapter": "disabled"}), "maind_graph_query",
                     {"from": "x"})
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
            self.assertEqual(len(resp["result"]["tools"]), 11)


class TestConformance(unittest.TestCase):
    """Реальный spawn сервера + полный NDJSON-хендшейк — ловит framing/handshake-баги,
    которые тесты в памяти не видят (там обе стороны используют один framing)."""

    def test_real_spawn_handshake(self):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "node"
            (root / "config" / "memory").mkdir(parents=True)
            (root / ".maind.json").write_text(
                json.dumps({"_version": "1", "projects": [{"id": "x", "name": "X"}]}),
                encoding="utf-8")
            proc = subprocess.Popen(
                [sys.executable, "-m", "maind", str(root), "mcp"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                env={**os.environ, "PYTHONPATH": str(repo / "lib")})
            msgs = [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                 "params": {"protocolVersion": "2025-03-26"}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                 "params": {"name": "maind_projects_list", "arguments": {}}},
                {"jsonrpc": "2.0", "id": 4, "method": "ping"},
            ]
            payload = "".join(json.dumps(m) + "\n" for m in msgs).encode("utf-8")
            out, _ = proc.communicate(payload, timeout=20)
            self.assertEqual(proc.returncode, 0)
            text = out.decode("utf-8")
            self.assertNotIn("Content-Length", text)            # NDJSON, не LSP
            by_id = {}
            for line in text.splitlines():
                if line.strip():
                    m = json.loads(line)                         # каждая строка — валидный JSON
                    if "id" in m:
                        by_id[m["id"]] = m
            self.assertEqual(by_id[1]["result"]["serverInfo"]["name"], "maind")
            self.assertEqual(by_id[1]["result"]["protocolVersion"], "2025-03-26")
            self.assertEqual(len(by_id[2]["result"]["tools"]), 11)
            self.assertIsInstance(json.loads(by_id[3]["result"]["content"][0]["text"]), list)
            self.assertIn(4, by_id)                              # ping ответил


if __name__ == "__main__":
    unittest.main()
