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
from maind.federation import rebuild_index, store_path
from maind.graph import Graph
from tests.fixtures import FakeMemoryServer, make_repo


def cfg(**over):
    base = merge_defaults({})
    base.update(over)
    return base


def fed_edge(env, config, src_pid, edge_dst, etype="depends_on"):
    """Записать ребро src_pid → edge_dst в стор проекта src_pid (федерация) + индекс.
    Граф читается федерацией (per-project сторы), а не единым legacy graph.db."""
    proj = {"id": src_pid}
    g = Graph(env, config, path=store_path(env, config, proj))
    g._loaded = True
    g.add_node(f"project:{src_pid}", "project", project=src_pid)
    g.add_edge(f"project:{src_pid}", edge_dst, etype)
    g.save()
    rebuild_index(env, config)


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

    def test_tool_descriptions_within_2kb_cap(self):
        # client-side cap на description инструмента (research/04-P3-listing-budget-and-trim-math.md)
        for tool in mcp.TOOLS:
            self.assertLessEqual(len(tool["description"].encode("utf-8")), 2048,
                                 f"{tool['name']}: description превышает 2048 байт")

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
            config = cfg(projects=[{"id": "a"}, {"id": "b"}])
            fed_edge(env, config, "a", "project:b")
            r = call(env, config, "maind_graph_query", {"from": "project:a"})
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
            config = cfg(projects=[{"id": "a"}, {"id": "b"}])
            fed_edge(env, config, "a", "project:b")
            r = call(env, config, "maind_graph_path",
                     {"from": "project:a", "to": "project:b"})
            data = json.loads(r["result"]["content"][0]["text"])
            self.assertEqual(data["path"], ["project:a", "project:b"])

    def test_projects_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            r = call(env, cfg(projects=[{"id": "x", "name": "X"}]), "maind_projects_status")
            data = json.loads(r["result"]["content"][0]["text"])
            self.assertIn("hub", data)
            self.assertIn("projects", data)

    def test_memory_forget_deletes_by_id(self):
        # forget шлёт {memoryId} (не {namespace,id}) → удаляет факт; раньше был HTTP 400.
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            with FakeMemoryServer() as url:
                c = cfg(memory={"url": url})
                stored = json.loads(call(env, c, "maind_memory_store",
                    {"scope": "project:x", "key": "fact", "value": "hello world"}
                    )["result"]["content"][0]["text"])
                mid = stored["memory"]["id"]
                got = json.loads(call(env, c, "maind_memory_recall",
                    {"scope": "project:x", "query": "hello"})["result"]["content"][0]["text"])
                self.assertEqual(len(got), 1)
                r = call(env, c, "maind_memory_forget", {"scope": "project:x", "key": mid})
                self.assertFalse(r["result"].get("isError"))
                self.assertEqual(json.loads(r["result"]["content"][0]["text"])["deleted"], 1)
                gone = json.loads(call(env, c, "maind_memory_recall",
                    {"scope": "project:x", "query": "hello"})["result"]["content"][0]["text"])
                self.assertEqual(len(gone), 0)

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

    def test_default_scope_from_cwd(self):
        # без явного --scope/MAIND_SCOPE дефолт = project:<id> по cwd, иначе global
        # (argless-сервер пишет в бакет своего проекта, а не в общий global).
        from maind import projects as projects_mod
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            proj_dir = os.path.realpath(os.path.join(tmp, "proj"))
            outside = os.path.realpath(os.path.join(tmp, "outside"))
            os.makedirs(proj_dir)
            os.makedirs(outside)
            config = cfg(projects=[{"id": "foo", "local_path": proj_dir}])
            self.assertEqual(projects_mod.match_cwd(env, config, cwd=proj_dir)["id"], "foo")
            self.assertIsNone(projects_mod.match_cwd(env, config, cwd=outside))
            cwd0 = os.getcwd()
            try:
                os.chdir(proj_dir)
                self.assertEqual(mcp._default_scope_from_cwd(env, config), "project:foo")
                os.chdir(outside)
                self.assertEqual(mcp._default_scope_from_cwd(env, config), "global")
            finally:
                os.chdir(cwd0)

    def test_tool_error_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)  # граф disabled → die() → SystemExit → isError
            r = call(env, cfg(graph={"adapter": "disabled"}), "maind_graph_query",
                     {"from": "x"})
            self.assertTrue(r["result"]["isError"])


def scoped_call(env, config, name, arguments, default_scope, req_id=1):
    """tools/call с явным default_scope (как у запинненного к проекту сервера)."""
    return mcp.dispatch(env, config, {
        "jsonrpc": "2.0", "id": req_id, "method": "tools/call",
        "params": {"name": name, "arguments": arguments or {}}}, default_scope=default_scope)


class TestScopeIsolation(unittest.TestCase):
    """Серверный энфорс namespace-изоляции: сервер, запинненный к project:a, не должен
    читать/писать/удалять память и граф другого проекта (регрессия на 2 бреши blocker)."""

    NS = property(lambda self: [{"id": "a", "namespaces": ["x"]},
                                {"id": "b", "namespaces": ["y"]}])  # a и b НЕ делят namespace

    def test_recall_foreign_scope_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            with FakeMemoryServer() as url:
                memory_mod.store(url, "project:b", "fact", "секрет проекта b")
                config = cfg(projects=self.NS, memory={"url": url})
                r = scoped_call(env, config, "maind_memory_recall",
                                {"scope": "project:b", "query": "секрет"}, "project:a")
                self.assertTrue(r["result"].get("isError"))
                self.assertIn("изоляция namespace", r["result"]["content"][0]["text"])

    def test_store_foreign_scope_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            with FakeMemoryServer() as url:
                config = cfg(projects=self.NS, memory={"url": url})
                r = scoped_call(env, config, "maind_memory_store",
                                {"scope": "project:b", "value": "впрыск"}, "project:a")
                self.assertTrue(r["result"].get("isError"))
                self.assertEqual(len(memory_mod.export(url, "project:b")), 0)  # в чужой scope не записано

    def test_forget_foreign_memory_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            with FakeMemoryServer() as url:
                stored = memory_mod.store(url, "project:b", "fact", "удали меня")
                mid = stored["memory"]["id"]
                config = cfg(projects=self.NS, memory={"url": url})
                # scope=project:a разрешён, но memoryId принадлежит project:b → отказ по владению
                r = scoped_call(env, config, "maind_memory_forget",
                                {"scope": "project:a", "key": mid}, "project:a")
                self.assertTrue(r["result"].get("isError"))
                self.assertEqual(len(memory_mod.export(url, "project:b")), 1)  # факт b цел

    def test_graph_project_foreign_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            config = cfg(projects=self.NS)
            fed_edge(env, config, "b", "project:c")
            r = scoped_call(env, config, "maind_graph_project", {"project": "b"}, "project:a")
            self.assertTrue(r["result"].get("isError"))
            self.assertIn("изоляция namespace", r["result"]["content"][0]["text"])

    def test_graph_query_foreign_node_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            config = cfg(projects=self.NS)
            fed_edge(env, config, "b", "project:c")
            r = scoped_call(env, config, "maind_graph_query", {"from": "project:b"}, "project:a")
            self.assertTrue(r["result"].get("isError"))

    def test_own_scope_still_works(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            with FakeMemoryServer() as url:
                memory_mod.store(url, "project:a", "fact", "своя память")
                config = cfg(projects=self.NS, memory={"url": url})
                r = scoped_call(env, config, "maind_memory_recall",
                                {"scope": "project:a", "query": "своя"}, "project:a")
                self.assertFalse(r["result"].get("isError"))
                self.assertEqual(json.loads(r["result"]["content"][0]["text"])[0]["text"],
                                 "своя память")

    def test_explicit_recall_scope_never_surfaces_related_namespace_records(self):
        """Explicit MCP scope is exact even though the backend payload offers all shapes."""
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            with FakeMemoryServer() as url:
                memory_mod.store(url, "project:a", "fact", "private matching fact")
                memory_mod.store(url, "ns:axioma", "fact", "shared matching fact")
                config = cfg(projects=[{"id": "a", "namespaces": ["axioma"]}],
                             memory={"url": url})
                response = scoped_call(env, config, "maind_memory_recall",
                                       {"scope": "project:a", "query": "matching"},
                                       "project:a")
                records = json.loads(response["result"]["content"][0]["text"])
                self.assertEqual(len(records), 1)
                self.assertEqual(records[0]["text"], "private matching fact")
                self.assertEqual({record["scope"] for record in records}, {"project:a"})

    def test_shared_namespace_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            shared = [{"id": "a", "namespaces": ["x"]}, {"id": "b", "namespaces": ["x"]}]
            config = cfg(projects=shared)
            fed_edge(env, config, "b", "project:c")
            r = scoped_call(env, config, "maind_graph_project", {"project": "b"}, "project:a")
            self.assertFalse(r["result"].get("isError"))  # делят namespace x → доступ разрешён

    def test_cross_scope_env_flag_disables_enforcement(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            with FakeMemoryServer() as url:
                memory_mod.store(url, "project:b", "fact", "админ-доступ")
                config = cfg(projects=self.NS, memory={"url": url})
                os.environ["MAIND_MCP_ALLOW_CROSS_SCOPE"] = "1"
                try:
                    r = scoped_call(env, config, "maind_memory_recall",
                                    {"scope": "project:b", "query": "админ"}, "project:a")
                finally:
                    del os.environ["MAIND_MCP_ALLOW_CROSS_SCOPE"]
                self.assertFalse(r["result"].get("isError"))  # явный админ-режим снимает изоляцию

    def test_hub_global_default_unrestricted(self):
        # default_scope=global (хаб-сервер без --scope) → энфорс выключен, back-compat
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            with FakeMemoryServer() as url:
                memory_mod.store(url, "project:b", "fact", "хаб видит всё")
                config = cfg(projects=self.NS, memory={"url": url})
                r = scoped_call(env, config, "maind_memory_recall",
                                {"scope": "project:b", "query": "хаб"}, "global")
                self.assertFalse(r["result"].get("isError"))


class TestContentTrimming(unittest.TestCase):
    """`_content` — единая воронка тримминга (P3.2): ниже порога — байт-в-байт как раньше;
    выше — снятие `indent=2`, а если и этого не хватило — receipt с `truncated`/
    `returned_count`/`total_count` на крупнейшем топ-уровневом списке. `isError` не
    пересекается с `truncated`-путём (разные классы — ошибка инструмента vs частичность)."""

    def test_small_payload_unchanged_bytes(self):
        payload = {"a": 1, "b": [1, 2, 3]}
        out = mcp._content(payload)
        self.assertEqual(out["content"][0]["text"],
                          json.dumps(payload, ensure_ascii=False, indent=2))

    def test_over_threshold_drops_indent_first(self):
        # список средней ширины: превышает порог с indent=2, но укладывается компактным —
        # тримминг обязан остановиться на рычаге (1), не резать данные.
        payload = {"items": [{"id": i, "note": "x" * 40} for i in range(400)]}
        indented_tokens = mcp._estimate_tokens(
            json.dumps(payload, ensure_ascii=False, indent=2))
        compact_tokens = mcp._estimate_tokens(json.dumps(payload, ensure_ascii=False))
        self.assertGreater(indented_tokens, mcp.TRIM_TARGET_TOKENS)   # проверка фикстуры
        self.assertLessEqual(compact_tokens, mcp.TRIM_TARGET_TOKENS)  # проверка фикстуры
        out = mcp._content(payload)
        text = out["content"][0]["text"]
        data = json.loads(text)
        self.assertEqual(len(data["items"]), 400)           # ничего не потеряно
        self.assertNotIn("truncated", data)
        self.assertNotIn("\n  ", text)                       # indent=2 снят (компактный JSON)

    def test_far_over_threshold_truncates_with_receipt(self):
        payload = [{"id": i, "note": "x" * 200} for i in range(2000)]
        out = mcp._content(payload)
        data = json.loads(out["content"][0]["text"])
        self.assertTrue(data["truncated"])
        self.assertEqual(data["total_count"], 2000)
        self.assertLess(data["returned_count"], 2000)
        self.assertEqual(len(data["items"]), data["returned_count"])
        self.assertIn("hint", data)
        self.assertLessEqual(mcp._estimate_tokens(out["content"][0]["text"]),
                             mcp.TRIM_TARGET_TOKENS)

    def test_truncation_preserves_dict_shape_and_sibling_keys(self):
        payload = {"hub": {"ok": True}, "projects": [{"id": i} for i in range(3000)]}
        out = mcp._content(payload)
        data = json.loads(out["content"][0]["text"])
        self.assertEqual(data["hub"], {"ok": True})          # соседний ключ не тронут
        self.assertTrue(data["projects_truncated"]["truncated"])
        self.assertEqual(data["projects_truncated"]["total_count"], 3000)
        self.assertEqual(len(data["projects"]), data["projects_truncated"]["returned_count"])

    def test_is_error_path_never_truncated(self):
        # ошибочный payload короткий на практике, но воронка обязана НЕ трогать isError-путь
        # тримминг-логикой (isError занят классом «ошибка инструмента», не «частичность»).
        payload = {"error": "x" * 5000}
        out = mcp._content(payload, is_error=True)
        self.assertTrue(out["isError"])
        self.assertNotIn("truncated", out["content"][0]["text"])
        self.assertEqual(out["content"][0]["text"],
                         json.dumps(payload, ensure_ascii=False, indent=2))

    def test_no_truncatable_list_leaves_payload_as_is(self):
        # верхнеуровневых списков нет — тримминг молчаливо не срабатывает (хвостовой случай
        # эскалации по Implementation Rules, не наблюдался на живом узле P3.2).
        payload = {"note": "x" * 50000}
        out = mcp._content(payload)
        data = json.loads(out["content"][0]["text"])
        self.assertEqual(data, payload)
        self.assertNotIn("truncated", data)


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
        # Пакет `core` лежит в <monorepo>/core (на два уровня выше пакета); чтобы
        # `from core import ...` работал при реальном спавне, в PYTHONPATH нужен
        # КОРЕНЬ монорепо. standalone-раскладка: каталога core нет — путь не добавляется.
        monorepo = repo.parents[1]
        pp = [str(repo / "lib")]
        if (monorepo / "core").is_dir():
            pp.append(str(monorepo))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "node"
            (root / "config" / "memory").mkdir(parents=True)
            (root / "config.json").write_text(
                json.dumps({"_version": "1", "projects": [{"id": "x", "name": "X"}]}),
                encoding="utf-8")
            proc = subprocess.Popen(
                [sys.executable, "-m", "maind", str(root), "mcp"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                env={**os.environ, "PYTHONPATH": os.pathsep.join(pp)})
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
