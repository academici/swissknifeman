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

from harness.hooks import block_pack_guard
import tests.fixtures as fx

PKG = Path(__file__).resolve().parents[1]
PACK_GUARD = PKG / "configs" / "claude-code" / "hooks" / "pack-guard"
HOOK_PY = PACK_GUARD / "pack-guard.py"


def run(fn, *a, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*a, **kw)
    return buf.getvalue()


def hook(payload):
    """Internal documentation."""
    p = subprocess.run([sys.executable, str(HOOK_PY)],
                       input=json.dumps(payload).encode(),
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    return p.returncode, p.stderr.decode()


def _write_lock(proj, managed_target=".claude/agents/x-reviewer.md",
                owned_target=".claude/agents/x-overrides.md", pack="demo-pack"):
    lock = {
        "schema": 1,
        "packs": {
            pack: {
                "files": [
                    {"target": managed_target, "base_sha256": "aaa", "user_owned": False},
                    {"target": owned_target, "base_sha256": "bbb", "user_owned": True},
                ]
            }
        },
    }
    d = proj / ".claude"
    d.mkdir(parents=True, exist_ok=True)
    (d / "agent-pack.lock.json").write_text(json.dumps(lock))


def _edit_payload(proj, rel_target, tool="Edit"):
    fp = str(proj / rel_target)
    key = "notebook_path" if tool == "NotebookEdit" else "file_path"
    return {"cwd": str(proj), "tool_name": tool, "tool_input": {key: fp}}



class HookBehaviorCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.proj = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _set_mode(self, mode):
        d = self.proj / ".claude"
        d.mkdir(parents=True, exist_ok=True)
        (d / "pack-guard.env.ini").write_text(f"MODE={mode}\n")

    def test_off_by_default_no_envini(self):

        _write_lock(self.proj)
        rc, err = hook(_edit_payload(self.proj, ".claude/agents/x-reviewer.md"))
        self.assertEqual(rc, 0)
        self.assertEqual(err, "")

    def test_strict_blocks_managed_file(self):
        self._set_mode("strict")
        _write_lock(self.proj)
        rc, err = hook(_edit_payload(self.proj, ".claude/agents/x-reviewer.md"))
        self.assertEqual(rc, 2)
        self.assertIn("demo-pack", err)
        self.assertIn("swissknifeman:generated", err)

    def test_warn_does_not_block(self):
        self._set_mode("warn")
        _write_lock(self.proj)
        rc, err = hook(_edit_payload(self.proj, ".claude/agents/x-reviewer.md"))
        self.assertEqual(rc, 0)
        self.assertIn("demo-pack", err)

    def test_strict_passes_user_owned_file(self):
        self._set_mode("strict")
        _write_lock(self.proj)
        rc, err = hook(_edit_payload(self.proj, ".claude/agents/x-overrides.md"))
        self.assertEqual(rc, 0)
        self.assertEqual(err, "")

    def test_strict_passes_unmanaged_file(self):
        self._set_mode("strict")
        _write_lock(self.proj)
        rc, err = hook(_edit_payload(self.proj, "some/other/file.md"))
        self.assertEqual(rc, 0)
        self.assertEqual(err, "")

    def test_strict_no_lock_passes(self):
        self._set_mode("strict")
        rc, err = hook(_edit_payload(self.proj, ".claude/agents/x-reviewer.md"))
        self.assertEqual(rc, 0)
        self.assertEqual(err, "")

    def test_strict_blocks_write_and_multiedit(self):
        self._set_mode("strict")
        _write_lock(self.proj)
        for tool in ("Write", "MultiEdit"):
            rc, err = hook(_edit_payload(self.proj, ".claude/agents/x-reviewer.md", tool=tool))
            self.assertEqual(rc, 2, tool)

    def test_strict_blocks_notebook_edit(self):
        self._set_mode("strict")
        _write_lock(self.proj, managed_target=".claude/agents/x.ipynb")
        rc, err = hook(_edit_payload(self.proj, ".claude/agents/x.ipynb", tool="NotebookEdit"))
        self.assertEqual(rc, 2)

    def test_irrelevant_tool_passes(self):
        self._set_mode("strict")
        _write_lock(self.proj)
        rc, err = hook({"cwd": str(self.proj), "tool_name": "Bash",
                        "tool_input": {"command": "ls"}})
        self.assertEqual(rc, 0)
        self.assertEqual(err, "")

    def test_malformed_stdin_no_crash(self):
        p = subprocess.run([sys.executable, str(HOOK_PY)], input=b"not json{",
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        self.assertEqual(p.returncode, 0)

    def test_bogus_mode_in_envini_defaults_off(self):
        self._set_mode("bogus")
        _write_lock(self.proj)
        rc, err = hook(_edit_payload(self.proj, ".claude/agents/x-reviewer.md"))
        self.assertEqual(rc, 0)
        self.assertEqual(err, "")



class BlockPackGuardCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.proj = fx.make_project(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_strict_writes_envini_and_registers(self):
        run(block_pack_guard, self.proj, "strict", "settings.json", False)
        self.assertEqual(fx.configured(self.proj, "pack_guard", "mode"), "strict")
        self.assertEqual(fx.env_ini_files(self.proj), [])
        s = json.loads((self.proj / ".claude" / "settings.json").read_text())
        matchers = sorted(e.get("matcher") for e in s["hooks"]["PreToolUse"])
        self.assertEqual(matchers, ["Edit", "MultiEdit", "NotebookEdit", "Write"])
        for entry in s["hooks"]["PreToolUse"]:
            self.assertIn("pack-guard.py", entry["hooks"][0]["command"])

    def test_off_no_hook(self):
        run(block_pack_guard, self.proj, "off", "settings.json", False)
        self.assertEqual(fx.configured(self.proj, "pack_guard", "mode"), "off")
        self.assertEqual(fx.env_ini_files(self.proj), [])
        self.assertFalse((self.proj / ".claude" / "settings.json").exists())

    def test_idempotent(self):
        run(block_pack_guard, self.proj, "warn", "settings.json", False)
        run(block_pack_guard, self.proj, "warn", "settings.json", False)
        s = json.loads((self.proj / ".claude" / "settings.json").read_text())
        self.assertEqual(len(s["hooks"]["PreToolUse"]), 4)

    def test_unknown_mode_exits(self):
        with self.assertRaises(SystemExit):
            run(block_pack_guard, self.proj, "bogus", "settings.json", False)

    def test_no_mode_noop(self):
        run(block_pack_guard, self.proj, "", "settings.json", False)
        self.assertFalse((self.proj / ".claude").exists())


if __name__ == "__main__":
    unittest.main()
