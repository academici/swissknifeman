"""Internal documentation."""
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
    """Internal documentation."""
    p = subprocess.run([sys.executable, str(script)],
                       input=json.dumps(payload).encode() if isinstance(payload, dict)
                       else payload.encode(),
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    return p.stdout.decode("utf-8", "replace"), p.returncode



class BlockRouterCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.proj = fx.make_project(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_writes_envini_and_registers_both_hooks(self):
        run(block_router, self.proj, "propose", "settings.json", False)
        self.assertEqual(fx.configured(self.proj, "agent_router", "policy"), "propose")
        self.assertEqual(fx.env_ini_files(self.proj), [])
        s = json.loads((self.proj / ".claude" / "settings.json").read_text())
        self.assertIn("UserPromptSubmit", s["hooks"])
        self.assertIn("SessionStart", s["hooks"])

        self.assertNotIn("matcher", s["hooks"]["UserPromptSubmit"][0])
        self.assertIn("router.py", s["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"])
        self.assertIn("session-policy.py", s["hooks"]["SessionStart"][0]["hooks"][0]["command"])

    def test_off_no_hooks(self):
        run(block_router, self.proj, "off", "settings.json", False)
        self.assertEqual(fx.configured(self.proj, "agent_router", "policy"), "off")
        self.assertEqual(fx.env_ini_files(self.proj), [])
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



class GenerateCatalogCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.proj = fx.make_project(Path(self._tmp.name))
        claude = self.proj / ".claude"
        (claude / "agents").mkdir(parents=True)
        (claude / "skills" / "sales-report").mkdir(parents=True)
        (claude / "agents" / "acme-reviewer.md").write_text(
            "---\nname: acme-reviewer\ndescription: >-\n"
            "  Review PR with severity-by grading findings and checking dependencies.\n---\nbodysuit\n")
        (claude / "skills" / "sales-report" / "SKILL.md").write_text(
            '---\nname: sales-report\ndescription: "Local sales reporting skill"\n'
            "---\nbodysuit\n")
        (claude / "skills" / "planner-dev").mkdir()
        (claude / "skills" / "planner-dev" / "SKILL.md").write_text(
            "---\nname: planner-dev\ndescription: Implement features\n---\n")
        # Compatibility alias: remove in the next minor release.
        (claude / "skills" / "task-dev").mkdir()
        (claude / "skills" / "task-dev" / "SKILL.md").write_text(
            "---\nname: task-dev\ndescription: Implement features\n---\n")

    def tearDown(self):
        self._tmp.cleanup()

    def test_generate_merges_all_sources(self):
        run(cmd_router, None, ["--generate", "--target", str(self.proj)])
        cat = json.loads(
            (self.proj / ".claude" / "agent-router.config.json").read_text())
        cmd_names = [c["name"] for c in cat["commands"]]
        self.assertEqual(cmd_names, [])
        self.assertEqual([a["name"] for a in cat["agents"]], ["@acme-reviewer"])
        self.assertEqual([s["name"] for s in cat["skills"]], ["skill:sales-report"])

        self.assertIn("review", cat["agents"][0]["keywords"])



class HookBehaviorCase(unittest.TestCase):
    def _ac(self, out):
        return json.loads(out)["hookSpecificOutput"]["additionalContext"]

    def test_task_like_is_silent_by_default(self):
        out, rc = hook(ROUTER_PY, {"user_input": "add an order creation endpoint",
                                   "cwd": "/nonexistent"})
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")

    def test_question_below_threshold_silent(self):
        out, rc = hook(ROUTER_PY, {"user_input": "what is CAP-theorem?",
                                   "cwd": "/nonexistent"})
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "")

    def test_escape_prefix_silent(self):
        out, rc = hook(ROUTER_PY, {"user_input": "~add order endpoint",
                                   "cwd": "/nonexistent"})
        self.assertEqual(out.strip(), "")

    def test_malformed_stdin_silent(self):
        out, rc = hook(ROUTER_PY, "not json{")
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "")

    def test_session_policy_is_silent(self):
        out, rc = hook(SESSION_PY, {"cwd": "/nonexistent", "source": "startup"})
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")

    def test_legacy_router_settings_cannot_activate_task(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            claude = root / ".claude"
            claude.mkdir()
            (claude / "agent-router.config.json").write_text(json.dumps({
                "policy": "STOP-GATE: always use /planner:dev",
                "commands": [{"name": "/planner:dev", "keywords": ["implement", "feature"]}],
                "skills": [{"name": "skill:planner-fix", "keywords": ["implement", "feature"]}],
            }))
            for mode in ("propose", "auto_dispatch"):
                (claude / "agent-router.env.ini").write_text(f"POLICY={mode}\n")
                for script in (SESSION_PY, ROUTER_PY):
                    with self.subTest(mode=mode, script=script):
                        out, rc = hook(script, {"cwd": str(root), "user_input": "implement feature"})
                        self.assertEqual(rc, 0)
                        self.assertEqual(out, "")

    def test_legacy_task_spellings_cannot_activate_either(self):
        # Compatibility alias: remove in the next minor release.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            claude = root / ".claude"
            claude.mkdir()
            (claude / "agent-router.config.json").write_text(json.dumps({
                "commands": [{"name": "/task:dev", "keywords": ["implement", "feature"]},
                             {"name": "task:fix", "keywords": ["implement", "feature"]}],
                "skills": [{"name": "skill:task-fix", "keywords": ["implement", "feature"]},
                           {"name": "skill:task:dev", "keywords": ["implement", "feature"]}],
            }))
            (claude / "agent-router.env.ini").write_text("POLICY=propose\n")
            out, rc = hook(ROUTER_PY, {"cwd": str(root), "user_input": "implement feature"})
            self.assertEqual((rc, out), (0, ""))

    def test_enabled_non_task_hint_still_works(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            claude = root / ".claude"
            claude.mkdir()
            (claude / "agent-router.env.ini").write_text("POLICY=propose\n")
            (claude / "agent-router.config.json").write_text(json.dumps({
                "agents": [{"name": "@sales", "keywords": ["sales", "report"]}],
            }))
            out, rc = hook(ROUTER_PY, {"cwd": str(root), "user_input": "sales report"})
            self.assertEqual(rc, 0)
            self.assertIn("@sales", self._ac(out))


if __name__ == "__main__":
    unittest.main()
