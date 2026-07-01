"""intent-router: block_router (env.ini + регистрация пары хуков), cmd_router --generate
(каталог из агентов + локальных скиллов + /task:*), и поведенческие тесты самих Python-хуков
(subprocess: task-like → подсказка, вопрос/escape/битый stdin → тишина, SessionStart → политика)."""
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from harness.hooks import block_router
from harness.router import cmd_router
import tests.fixtures as fx

PKG = Path(__file__).resolve().parents[1]
AGENT_ROUTER = PKG / "configs" / "claude-code" / "hooks" / "agent-router"
ROUTER_PY = AGENT_ROUTER / "router.py"
SESSION_PY = AGENT_ROUTER / "session-policy.py"


def run(fn, *a, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*a, **kw)
    return buf.getvalue()


def hook(script, payload, cwd=None):
    """Прогнать Python-хук через subprocess: stdin=JSON → stdout (str)."""
    p = subprocess.run([sys.executable, str(script)],
                       input=json.dumps(payload).encode() if isinstance(payload, dict)
                       else payload.encode(),
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    return p.stdout.decode("utf-8", "replace"), p.returncode


# ── block_router: env.ini + регистрация пары хуков ───────────────────────────
class BlockRouterCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.proj = fx.make_project(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_writes_envini_and_registers_both_hooks(self):
        run(block_router, self.proj, "propose", "settings.json", False)
        self.assertEqual(
            (self.proj / ".claude" / "agent-router.env.ini").read_text().strip(),
            "POLICY=propose")
        s = json.loads((self.proj / ".claude" / "settings.json").read_text())
        self.assertIn("UserPromptSubmit", s["hooks"])
        self.assertIn("SessionStart", s["hooks"])
        # matcher-less записи (UserPromptSubmit/SessionStart без matcher)
        self.assertNotIn("matcher", s["hooks"]["UserPromptSubmit"][0])
        self.assertIn("router.py", s["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"])
        self.assertIn("session-policy.py", s["hooks"]["SessionStart"][0]["hooks"][0]["command"])

    def test_off_no_hooks(self):
        run(block_router, self.proj, "off", "settings.json", False)
        self.assertEqual(
            (self.proj / ".claude" / "agent-router.env.ini").read_text().strip(),
            "POLICY=off")
        self.assertFalse((self.proj / ".claude" / "settings.json").exists())

    def test_idempotent_no_dupes(self):
        run(block_router, self.proj, "propose", "settings.json", False)
        run(block_router, self.proj, "propose", "settings.json", False)
        s = json.loads((self.proj / ".claude" / "settings.json").read_text())
        self.assertEqual(len(s["hooks"]["UserPromptSubmit"]), 1)
        self.assertEqual(len(s["hooks"]["SessionStart"]), 1)

    def test_unknown_mode_exits(self):
        with self.assertRaises(SystemExit):
            run(block_router, self.proj, "bogus", "settings.json", False)


# ── cmd_router --generate: каталог из агентов + локальных скиллов + /task:* ───
class GenerateCatalogCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.proj = fx.make_project(Path(self._tmp.name))
        claude = self.proj / ".claude"
        (claude / "agents").mkdir(parents=True)
        (claude / "skills" / "sales-report").mkdir(parents=True)
        (claude / "agents" / "acme-reviewer.md").write_text(
            "---\nname: acme-reviewer\ndescription: >-\n"
            "  Ревью PR с severity-градацией находок и проверкой зависимостей.\n---\nбоди\n")
        (claude / "skills" / "sales-report" / "SKILL.md").write_text(
            '---\nname: sales-report\ndescription: "Локальный скилл отчётов по продажам"\n'
            "---\nбоди\n")

    def tearDown(self):
        self._tmp.cleanup()

    def test_generate_merges_all_sources(self):
        run(cmd_router, None, ["--generate", "--target", str(self.proj)])
        cat = json.loads(
            (self.proj / ".claude" / "agent-router.config.json").read_text())
        cmd_names = [c["name"] for c in cat["commands"]]
        self.assertEqual(len(cmd_names), 5)
        self.assertIn("/task:dev", cmd_names)
        self.assertEqual([a["name"] for a in cat["agents"]], ["@acme-reviewer"])
        self.assertEqual([s["name"] for s in cat["skills"]], ["skill:sales-report"])
        # ключевые слова агента извлечены из блок-скалярного description
        self.assertIn("ревью", cat["agents"][0]["keywords"])


# ── поведенческие: реальные Python-хуки через subprocess ─────────────────────
class HookBehaviorCase(unittest.TestCase):
    def _ac(self, out):
        return json.loads(out)["hookSpecificOutput"]["additionalContext"]

    def test_task_like_yields_hint(self):
        out, rc = hook(ROUTER_PY, {"user_input": "добавь эндпоинт создания заказа",
                                   "cwd": "/nonexistent"})
        self.assertEqual(rc, 0)
        self.assertIn("/task:dev", self._ac(out))

    def test_question_below_threshold_silent(self):
        out, rc = hook(ROUTER_PY, {"user_input": "что такое CAP-теорема?",
                                   "cwd": "/nonexistent"})
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "")

    def test_escape_prefix_silent(self):
        out, rc = hook(ROUTER_PY, {"user_input": "~добавь эндпоинт заказа",
                                   "cwd": "/nonexistent"})
        self.assertEqual(out.strip(), "")

    def test_malformed_stdin_silent(self):
        out, rc = hook(ROUTER_PY, "not json{")
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "")

    def test_session_policy_injects_policy(self):
        out, rc = hook(SESSION_PY, {"cwd": "/nonexistent", "source": "startup"})
        self.assertEqual(rc, 0)
        ac = self._ac(out)
        self.assertIn("intent-router", ac)
        self.assertIn("/task:design", ac)


if __name__ == "__main__":
    unittest.main()
