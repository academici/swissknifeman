"""run-report: защитный парсер транскрипта (_lib.parse_transcript), поведенческий прогон
самого SessionEnd-хука через subprocess (валидный транскрипт → .claude/runs/<sid>.json;
битый/пустой stdin → exit 0 без записи; ретеншн), и block_run_report (env.ini + регистрация)."""
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from harness.hooks import block_run_report
import tests.fixtures as fx

PKG = Path(__file__).resolve().parents[1]
RUN_REPORT = PKG / "configs" / "claude-code" / "hooks" / "run-report"
HOOK_PY = RUN_REPORT / "run-report.py"

sys.path.insert(0, str(RUN_REPORT))
from _lib import parse_events, parse_transcript  # noqa: E402

# синтетический транскрипт: тест (pass) + линт (fail) + Edit + dev-loop-воркфлоу + шум
FIXTURE = "\n".join([
    json.dumps({"type": "assistant", "message": {"content": [
        {"type": "text", "text": "go"},
        {"type": "tool_use", "id": "t1", "name": "Bash",
         "input": {"command": "python3 -m pytest tests/"}}]}}),
    json.dumps({"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "t1", "content": "5 passed", "is_error": False}]},
        "toolUseResult": {"stdout": "5 passed", "interrupted": False}}),
    json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "t2", "name": "Bash", "input": {"command": "ruff check ."}}]}}),
    json.dumps({"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "t2", "content": "E501", "is_error": True}]}}),
    json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "t3", "name": "Edit", "input": {"file_path": "/proj/a.py"}}]}}),
    json.dumps({"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "t3", "content": "ok", "is_error": False}]},
        "toolUseResult": {"filePath": "/proj/a.py"}}),
    json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "t4", "name": "Workflow", "input": {"name": "dev-loop"}}]}}),
    json.dumps({"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "t4",
         "content": '{"tool_failures":["perplexity-web locked"],"deferred":["e2e"]}',
         "is_error": False}]},
        "toolUseResult": {"runId": "wf_1", "status": "completed",
                          "summary": "dev-loop done", "workflowName": "dev-loop"}}),
    "broken line not json {{{",
    json.dumps({"type": "system", "content": "noise"}),
])


def _wf_line(uid, name, status, run_id=None):
    """assistant tool_use(Workflow) + user tool_result с toolUseResult.workflowName/status/runId."""
    tur = {"status": status, "workflowName": name, "summary": ""}
    if run_id is not None:
        tur["runId"] = run_id
    return "\n".join([
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": uid, "name": "Workflow", "input": {"name": name}}]}}),
        json.dumps({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": uid, "content": "ok", "is_error": False}]},
            "toolUseResult": tur}),
    ])


def _mcp_line(uid, name, result_obj):
    """assistant tool_use + user tool_result (result_obj → text блока, как в реальном транскрипте)."""
    return "\n".join([
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": uid, "name": name, "input": {"q": "x"}}]}}),
        json.dumps({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": uid,
             "content": [{"type": "text", "text": json.dumps(result_obj, ensure_ascii=False)}],
             "is_error": False}]}}),
    ])


# память/граф хаба: обычный сервер + вариант лейбла plugin_core_ + is_error-деградация
FIXTURE_MCP = "\n".join([
    _mcp_line("m1", "mcp__maind__maind_memory_recall",
              [{"score": 1, "text": "a"}, {"score": 2, "text": "b"}]),          # found=2
    _mcp_line("m2", "mcp__plugin_core_maind__maind_memory_recall",
              [{"score": 1, "text": "c"}]),                                     # found=1, др. лейбл
    _mcp_line("g1", "mcp__maind__maind_graph_query",
              {"root": "project:x", "count": 3, "neighbors": [1, 2, 3]}),       # count=3
    _mcp_line("s1", "mcp__maind__maind_memory_store", {"memory": {"id": "m_1"}}),  # count не извлечь
    json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "m3", "name": "mcp__maind__maind_memory_recall",
         "input": {"q": "z"}}]}}),
    json.dumps({"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "m3", "content": "boom", "is_error": True}]}}),
])


def _ev_assistant(content, model=None, usage=None):
    """assistant-событие: content-блоки + опц. model/usage (для _usage-агрегации)."""
    m = {"content": content}
    if model:
        m["model"] = model
    if usage:
        m["usage"] = usage
    return json.dumps({"type": "assistant", "message": m})


def _ev_user(content):
    return json.dumps({"type": "user", "message": {"content": content}})


def _tu(tid, name, inp):
    return {"type": "tool_use", "id": tid, "name": name, "input": inp}


def _tr(tid, content, is_error=False):
    return {"type": "tool_result", "tool_use_id": tid, "content": content, "is_error": is_error}


def build_schema2_fixture(proj):
    """Транскрипт под все срезы SCHEMA=2: usage главного агента, re-read хотспот (3× один
    файл), серия из 3 одинаковых ошибок Bash (error_loops), два похожих retrieval-запроса
    (WebSearch + mcp perplexity — near-dup ⇒ repeated_queries), 4 Edit'а (managed-скилл,
    managed agent-pack файл, user_owned agent-pack файл, обычный файл ⇒ protected_writes)."""
    lines = [
        _ev_assistant([{"type": "text", "text": "go"}], model="claude-opus-4-1",
                      usage={"input_tokens": 100, "output_tokens": 50,
                             "cache_read_input_tokens": 10, "cache_creation_input_tokens": 5}),
    ]
    for i in range(3):
        tid = f"rd{i}"
        lines.append(_ev_assistant([_tu(tid, "Read", {"file_path": "/proj/src/hot.py"})]))
        lines.append(_ev_user([_tr(tid, "…content…")]))
    for i in range(3):
        tid = f"eb{i}"
        lines.append(_ev_assistant([_tu(tid, "Bash", {"command": "pytest tests/broken"})]))
        lines.append(_ev_user([_tr(tid, "AssertionError: boom", is_error=True)]))
    lines.append(_ev_assistant([_tu("ws1", "WebSearch", {"query": "claude opus pricing 2026"})]))
    lines.append(_ev_user([_tr("ws1", "search result A" * 5)]))
    lines.append(_ev_assistant([_tu("pw1", "mcp__perplexity-web__search_advanced",
                                    {"query": "claude opus pricing 2026 update"})]))
    lines.append(_ev_user([_tr("pw1", "search result B" * 5)]))
    edits = [
        ("e1", str(proj / ".claude" / "skills" / "foo-skill" / "SKILL.md")),   # managed-скилл
        ("e2", str(proj / ".claude" / "agents" / "reviewer.md")),               # managed agent-pack
        ("e3", str(proj / ".claude" / "agents" / "owned.md")),                  # user_owned — не protected
        ("e4", str(proj / "src" / "app.py")),                                   # обычный файл
    ]
    for tid, fp in edits:
        lines.append(_ev_assistant([_tu(tid, "Edit", {"file_path": fp})]))
        lines.append(_ev_user([_tr(tid, "ok")]))
    return "\n".join(lines)


def write_protected_locks(proj):
    """skills-lock.json (skiller vendor) + .claude/agent-pack.lock.json (harness) —
    managed-наборы, пересечение с которыми даёт protected_writes."""
    (proj / "skills-lock.json").write_text(json.dumps({
        "version": 1,
        "skills": {"foo-skill": {"source": "swissknifeman", "managed": True, "bucket": "",
                                  "installed_path": ".claude/skills/foo-skill"}},
    }), encoding="utf-8")
    claude = proj / ".claude"
    claude.mkdir(parents=True, exist_ok=True)
    (claude / "agent-pack.lock.json").write_text(json.dumps({
        "schema": 1,
        "packs": {"demo": {"files": [
            {"target": ".claude/agents/reviewer.md", "user_owned": False},
            {"target": ".claude/agents/owned.md", "user_owned": True},
        ]}},
    }), encoding="utf-8")


def run(fn, *a, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*a, **kw)
    return buf.getvalue()


def hook(payload):
    """Прогнать SessionEnd-хук через subprocess: stdin=JSON → (returncode)."""
    p = subprocess.run([sys.executable, str(HOOK_PY)],
                       input=(json.dumps(payload) if isinstance(payload, dict)
                              else payload).encode(),
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    return p.returncode


# ── чистый парсер ─────────────────────────────────────────────────────────────
class ParseCase(unittest.TestCase):
    def test_extracts_all_slices(self):
        r = parse_transcript(FIXTURE)
        self.assertEqual(r["tools"]["total"], 4)
        self.assertEqual(r["tools"]["by_name"]["Bash"], 2)
        self.assertEqual(r["files_changed"], ["/proj/a.py"])
        # тест прошёл, линт упал
        self.assertEqual(r["bash"]["tests"], [{"command": "python3 -m pytest tests/", "ok": True}])
        self.assertEqual(r["bash"]["lints"], [{"command": "ruff check .", "ok": False}])
        self.assertEqual(r["bash"]["failed"], ["ruff check ."])
        # tool_failure — по is_error
        self.assertEqual(len(r["tool_failures"]), 1)
        self.assertEqual(r["tool_failures"][0]["tool"], "Bash")
        # воркфлоу + dev-loop-сигнал
        self.assertEqual(r["workflows"][0]["name"], "dev-loop")
        self.assertEqual(r["workflows"][0]["status"], "completed")
        self.assertEqual(r["devloop"]["tool_failures"], ["perplexity-web locked"])
        self.assertEqual(r["devloop"]["deferred"], ["e2e"])
        self.assertIsNone(r["maind"])                          # в FIXTURE нет maind-вызовов

    def test_maind_mcp_metrics(self):
        r = parse_transcript(FIXTURE_MCP)
        m = r["maind"]
        # recall: m1(2)+m2(1) успешных + m3(is_error) → calls=3, results=2, found_total=3, max=2
        self.assertEqual(m["memory_recall"]["calls"], 3)
        self.assertEqual(m["memory_recall"]["results"], 2)
        self.assertEqual(m["memory_recall"]["found_total"], 3)
        self.assertEqual(m["memory_recall"]["found_max"], 2)
        # store: вызов есть, но count из результата не извлекаем (dict без count/neighbors/nodes/path)
        self.assertEqual(m["memory_store"]["calls"], 1)
        self.assertEqual(m["memory_store"]["results"], 0)
        # graph_query: count из dict
        self.assertEqual(m["graph_query"]["calls"], 1)
        self.assertEqual(m["graph_query"]["found_total"], 3)
        # back-compat: MCP-вызовы всё ещё видны в общем tools.by_name (2× обычный лейбл: m1,m3)
        self.assertEqual(r["tools"]["by_name"]["mcp__maind__maind_memory_recall"], 2)

    def test_empty_and_garbage(self):
        for bad in ("", "not json", "{{{", "null\n[]\n42"):
            r = parse_transcript(bad)
            self.assertEqual(r["tools"]["total"], 0)
            self.assertIsNone(r["devloop"])

    def test_large_transcript_line_streaming(self):
        # много Bash-строк — парс идёт построчно, без слурпа структуры
        big = "\n".join(
            json.dumps({"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": f"b{i}", "name": "Bash",
                 "input": {"command": f"echo {i}"}}]}}) for i in range(5000))
        r = parse_transcript(big)
        self.assertEqual(r["tools"]["total"], 5000)


# ── workflow_relaunch (P1.2, plans/2026.07.15-TELEMETRY-OPT) ────────────────────
class WorkflowRelaunchCase(unittest.TestCase):
    def test_three_same_name_async_flags(self):
        t = "\n".join(_wf_line(f"w{i}", "dterema-site-p3-api", "async_launched")
                       for i in range(3))
        r = parse_transcript(t)
        self.assertEqual(len(r["workflow_relaunch"]), 1)
        entry = r["workflow_relaunch"][0]
        self.assertEqual(entry["name"], "dterema-site-p3-api")
        self.assertEqual(entry["count"], 3)
        self.assertEqual(entry["statuses"], {"async_launched": 3})

    def test_single_call_no_flag(self):
        t = _wf_line("w1", "dterema-site-p3-api", "async_launched")
        r = parse_transcript(t)
        self.assertEqual(r["workflow_relaunch"], [])

    def test_three_different_names_no_flag(self):
        t = "\n".join(_wf_line(f"w{i}", name, "async_launched")
                       for i, name in enumerate(["a", "b", "c"]))
        r = parse_transcript(t)
        self.assertEqual(r["workflow_relaunch"], [])

    def test_groups_by_run_id_not_name(self):
        # тот же workflowName, но ДВА разных runId (dterema-кейс: новый run + resume-цепочка) —
        # каждая группа своя, ни одна не достигает порога сама по себе
        t = "\n".join([
            _wf_line("w1", "dterema-site-p3-api", "async_launched", run_id="wf_run_a"),
            _wf_line("w2", "dterema-site-p3-api", "async_launched", run_id="wf_run_a"),
            _wf_line("w3", "dterema-site-p3-api", "async_launched", run_id="wf_run_b"),
            _wf_line("w4", "dterema-site-p3-api", "async_launched", run_id="wf_run_b"),
        ])
        r = parse_transcript(t)
        self.assertEqual(r["workflow_relaunch"], [])

    def test_same_run_id_three_resumes_flags(self):
        t = "\n".join(_wf_line(f"w{i}", "dterema-site-p3-api", "async_launched",
                                run_id="wf_run_a") for i in range(3))
        r = parse_transcript(t)
        self.assertEqual(len(r["workflow_relaunch"]), 1)
        self.assertEqual(r["workflow_relaunch"][0]["count"], 3)


# ── поведенческий: реальный хук через subprocess ─────────────────────────────
class HookBehaviorCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.proj = Path(self._tmp.name)
        self.tpath = self.proj / "session.jsonl"
        self.tpath.write_text(FIXTURE, encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_writes_run_report(self):
        rc = hook({"transcript_path": str(self.tpath), "cwd": str(self.proj),
                   "session_id": "sess-01", "reason": "clear"})
        self.assertEqual(rc, 0)
        out = self.proj / ".claude" / "runs" / "sess-01.json"
        self.assertTrue(out.is_file())
        data = json.loads(out.read_text())
        self.assertEqual(data["session_id"], "sess-01")
        self.assertEqual(data["cwd"], str(self.proj))
        self.assertEqual(data["bash"]["tests"][0]["ok"], True)
        self.assertEqual(data["devloop"]["deferred"], ["e2e"])
        # runs/ само-игнорируется — не засоряет git status проекта
        self.assertEqual((self.proj / ".claude" / "runs" / ".gitignore").read_text().strip(), "*")

    def test_malformed_stdin_no_write(self):
        rc = hook("not json{")
        self.assertEqual(rc, 0)
        self.assertFalse((self.proj / ".claude" / "runs").exists())

    def test_missing_transcript_no_crash(self):
        rc = hook({"transcript_path": str(self.proj / "nope.jsonl"),
                   "cwd": str(self.proj), "session_id": "x"})
        self.assertEqual(rc, 0)
        self.assertFalse((self.proj / ".claude" / "runs" / "x.json").exists())

    def test_disabled_via_envini(self):
        claude = self.proj / ".claude"
        claude.mkdir()
        (claude / "run-report.env.ini").write_text("ENABLED=off\n")
        rc = hook({"transcript_path": str(self.tpath), "cwd": str(self.proj),
                   "session_id": "s2"})
        self.assertEqual(rc, 0)
        self.assertFalse((claude / "runs" / "s2.json").exists())

    def test_retention_keeps_last_n(self):
        claude = self.proj / ".claude"
        claude.mkdir()
        (claude / "run-report.env.ini").write_text("ENABLED=on\nRUNS_KEEP=3\n")
        for i in range(6):
            hook({"transcript_path": str(self.tpath), "cwd": str(self.proj),
                  "session_id": f"s{i}"})
        kept = list((claude / "runs").glob("*.json"))
        self.assertEqual(len(kept), 3)


# ── block_run_report: env.ini + регистрация SessionEnd ───────────────────────
class BlockRunReportCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.proj = fx.make_project(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_on_writes_envini_and_registers(self):
        run(block_run_report, self.proj, "on", "settings.json", False)
        self.assertIn("ENABLED=on",
                      (self.proj / ".claude" / "run-report.env.ini").read_text())
        s = json.loads((self.proj / ".claude" / "settings.json").read_text())
        self.assertIn("SessionEnd", s["hooks"])
        self.assertNotIn("matcher", s["hooks"]["SessionEnd"][0])
        self.assertIn("run-report.py",
                      s["hooks"]["SessionEnd"][0]["hooks"][0]["command"])
        # само-игнорируемый runs/ создаётся уже при включении
        self.assertEqual((self.proj / ".claude" / "runs" / ".gitignore").read_text().strip(), "*")

    def test_off_no_hook(self):
        run(block_run_report, self.proj, "off", "settings.json", False)
        self.assertIn("ENABLED=off",
                      (self.proj / ".claude" / "run-report.env.ini").read_text())
        self.assertFalse((self.proj / ".claude" / "settings.json").exists())

    def test_idempotent(self):
        run(block_run_report, self.proj, "on", "settings.json", False)
        run(block_run_report, self.proj, "on", "settings.json", False)
        s = json.loads((self.proj / ".claude" / "settings.json").read_text())
        self.assertEqual(len(s["hooks"]["SessionEnd"]), 1)

    def test_unknown_mode_exits(self):
        with self.assertRaises(SystemExit):
            run(block_run_report, self.proj, "bogus", "settings.json", False)


# ── SCHEMA=2: usage/reads/error_loops/retrieval/protected_writes ────────────────
class Schema2ParseCase(unittest.TestCase):
    """parse_events напрямую (без subprocess) — точные числа по всем новым срезам,
    плюс сайдкар-каталог субагента рядом с транскриптом."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.proj = root / "proj"
        self.proj.mkdir()
        write_protected_locks(self.proj)

        transcripts = root / "transcripts"
        transcripts.mkdir()
        self.tpath = transcripts / "sess-1.jsonl"
        self.tpath.write_text(build_schema2_fixture(self.proj), encoding="utf-8")

        sub_dir = transcripts / "sess-1" / "subagents"
        sub_dir.mkdir(parents=True)
        (sub_dir / "agent-aaa.jsonl").write_text(
            _ev_assistant([{"type": "text", "text": "sub"}], model="claude-haiku-4",
                          usage={"input_tokens": 20, "output_tokens": 10}) + "\n",
            encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def _parse(self):
        with open(self.tpath, encoding="utf-8") as fh:
            return parse_events(fh, transcript_path=str(self.tpath), cwd=str(self.proj))

    def test_schema_is_2(self):
        self.assertEqual(self._parse()["schema"], 2)

    def test_usage_main_plus_subagent(self):
        u = self._parse()["usage"]
        self.assertIsNotNone(u)
        self.assertEqual(u["totals"]["in"], 120)          # 100 (main) + 20 (субагент)
        self.assertEqual(u["totals"]["out"], 60)           # 50 + 10
        self.assertEqual(u["totals"]["cache_read"], 10)
        self.assertEqual(u["totals"]["cache_creation"], 5)
        self.assertEqual(u["subagents_parsed"], 1)
        self.assertEqual(u["subagents_skipped"], 0)
        self.assertEqual(len(u["agents"]), 2)
        self.assertIn("claude-opus-4-1", u["by_model"])
        self.assertIn("claude-haiku-4", u["by_model"])
        # first_turn_overhead/turns — ГЛАВНОГО транскрипта (100+5, не мёрж с субагентом);
        # turns = число assistant-событий главного транскрипта (1 usage-запись + 3 reads +
        # 3 bash + 1 websearch + 1 perplexity + 4 edits = 13, см. build_schema2_fixture)
        self.assertEqual(u["first_turn_overhead"], 105)
        self.assertEqual(u["turns"], 13)

    def test_reads_top_rereads(self):
        reads = self._parse()["reads"]
        self.assertEqual(reads["total"], 3)
        self.assertEqual(reads["unique"], 1)
        self.assertEqual(reads["top_rereads"], [{"path": "/proj/src/hot.py", "count": 3}])

    def test_error_loops_detects_streak(self):
        loops = self._parse()["error_loops"]
        self.assertTrue(loops)
        self.assertEqual(loops[0]["tool"], "Bash")
        self.assertGreaterEqual(loops[0]["len"], 3)

    def test_retrieval_calls_and_repeated_queries(self):
        retr = self._parse()["retrieval"]
        self.assertEqual(retr["calls"], 2)
        self.assertIn("WebSearch", retr["by_tool"])
        self.assertIn("mcp__perplexity-web__search_advanced", retr["by_tool"])
        self.assertGreater(retr["result_chars"], 0)
        self.assertEqual(len(retr["queries"]), 2)
        self.assertTrue(retr["repeated_queries"])         # запросы похожи (ratio ≥0.7)

    def test_protected_writes_intersects_locks(self):
        pw = set(self._parse()["protected_writes"])
        self.assertIn(str(self.proj / ".claude" / "skills" / "foo-skill" / "SKILL.md"), pw)
        self.assertIn(str(self.proj / ".claude" / "agents" / "reviewer.md"), pw)
        self.assertNotIn(str(self.proj / ".claude" / "agents" / "owned.md"), pw)  # user_owned
        self.assertNotIn(str(self.proj / "src" / "app.py"), pw)                   # обычный файл

    def test_no_lock_files_empty_protected_writes(self):
        proj2 = Path(self._tmp.name) / "proj2"
        proj2.mkdir()
        tp = Path(self._tmp.name) / "sess-2.jsonl"
        tp.write_text(build_schema2_fixture(proj2), encoding="utf-8")
        with open(tp, encoding="utf-8") as fh:
            r = parse_events(fh, transcript_path=str(tp), cwd=str(proj2))
        self.assertEqual(r["protected_writes"], [])

    def test_subagents_cap_and_skip_on_garbage_file(self):
        sub_dir = Path(self._tmp.name) / "transcripts" / "sess-1" / "subagents"
        (sub_dir / "agent-bad.jsonl").write_bytes(b"\xff\xfe not really jsonl")
        u = self._parse()["usage"]
        # битый файл читается защитно (iter_jsonl толерантен) — не считается «skipped»,
        # просто даёт пустой аккумулятор; здесь важно, что парсер не падает.
        self.assertGreaterEqual(u["subagents_parsed"], 1)


# ── деградация без вендоренного _usage.py (старый хук до scripts/sync-usage.sh) ─
class NoUsageModuleCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.hook_dir = root / "hook"
        self.hook_dir.mkdir()
        for name in ("run-report.py", "_lib.py"):   # НЕТ _usage.py — умышленно
            (self.hook_dir / name).write_text((RUN_REPORT / name).read_text(encoding="utf-8"),
                                               encoding="utf-8")
        self.proj = root / "proj"
        self.proj.mkdir()
        self.tpath = self.proj / "session.jsonl"
        self.tpath.write_text(FIXTURE, encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_usage_none_no_crash(self):
        p = subprocess.run([sys.executable, str(self.hook_dir / "run-report.py")],
                           input=json.dumps({"transcript_path": str(self.tpath),
                                             "cwd": str(self.proj),
                                             "session_id": "nou"}).encode(),
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        self.assertEqual(p.returncode, 0, p.stderr.decode())
        out = json.loads((self.proj / ".claude" / "runs" / "nou.json").read_text())
        self.assertEqual(out["schema"], 2)
        self.assertIsNone(out["usage"])
        # реестр/тренд по-прежнему пишутся — деградация только usage-блока
        self.assertTrue((self.proj / ".claude" / "analyze" / "usage-trend.ndjson").is_file())


# ── тренд-файл usage-trend.ndjson (SCHEMA=2) ─────────────────────────────────────
class TrendCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.proj = Path(self._tmp.name)
        self.tpath = self.proj / "session.jsonl"
        self.tpath.write_text(FIXTURE, encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_trend_line_fields(self):
        rc = hook({"transcript_path": str(self.tpath), "cwd": str(self.proj),
                   "session_id": "t1"})
        self.assertEqual(rc, 0)
        p = self.proj / ".claude" / "analyze" / "usage-trend.ndjson"
        self.assertTrue(p.is_file())
        entry = json.loads(p.read_text(encoding="utf-8").splitlines()[-1])
        for k in ("ts", "session", "in", "out", "cache_read", "cache_creation", "by_model",
                  "tools_total", "files_changed", "agents", "wall_s", "retr_chars"):
            self.assertIn(k, entry)
        self.assertEqual(entry["session"], "t1")
        self.assertEqual((self.proj / ".claude" / "analyze" / ".gitignore").read_text().strip(), "*")

    def test_retention_trims_to_2000(self):
        analyze = self.proj / ".claude" / "analyze"
        analyze.mkdir(parents=True)
        with open(analyze / "usage-trend.ndjson", "w", encoding="utf-8") as fh:
            for i in range(4005):
                fh.write(json.dumps({"n": i}) + "\n")
        rc = hook({"transcript_path": str(self.tpath), "cwd": str(self.proj),
                   "session_id": "trend-last"})
        self.assertEqual(rc, 0)
        lines = (analyze / "usage-trend.ndjson").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2000)
        self.assertEqual(json.loads(lines[-1])["session"], "trend-last")


if __name__ == "__main__":
    unittest.main()
