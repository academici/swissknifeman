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
from _lib import parse_transcript  # noqa: E402

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


if __name__ == "__main__":
    unittest.main()
