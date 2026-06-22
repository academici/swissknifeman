"""Хуки: auto-approve env.ini + регистрация (merge-only); memory membership."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from harness.hooks import _parse_memory_flag, block_autoapprove, block_memory
import tests.fixtures as fx


def run(fn, *a, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*a, **kw)
    return buf.getvalue()


class HooksCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.proj = fx.make_project(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    # --- auto-approve -------------------------------------------------------
    def test_autoapprove_writes_envini_and_hooks_idempotent(self):
        run(block_autoapprove, self.proj, "strict", "settings.json", False)
        self.assertEqual(
            (self.proj / ".claude" / "auto-approve.env.ini").read_text().strip(),
            "MODE=strict")
        s = json.loads((self.proj / ".claude" / "settings.json").read_text())
        matchers = [e.get("matcher") for e in s["hooks"]["PreToolUse"]]
        self.assertEqual(sorted(matchers), ["Bash", "ExitPlanMode"])
        # повтор не плодит дубли (merge-only)
        run(block_autoapprove, self.proj, "strict", "settings.json", False)
        s2 = json.loads((self.proj / ".claude" / "settings.json").read_text())
        self.assertEqual(len(s2["hooks"]["PreToolUse"]), 2)

    def test_autoapprove_off_no_hook(self):
        run(block_autoapprove, self.proj, "off", "settings.json", False)
        self.assertEqual(
            (self.proj / ".claude" / "auto-approve.env.ini").read_text().strip(),
            "MODE=off")
        self.assertFalse((self.proj / ".claude" / "settings.json").exists())

    def test_autoapprove_preserves_existing_settings(self):
        cdir = self.proj / ".claude"; cdir.mkdir(parents=True)
        (cdir / "settings.json").write_text(
            json.dumps({"permissions": {"allow": ["Bash(ls *)"]}}) + "\n")
        run(block_autoapprove, self.proj, "permissive", "settings.json", False)
        s = json.loads((cdir / "settings.json").read_text())
        self.assertEqual(s["permissions"]["allow"], ["Bash(ls *)"])  # не затёрто
        self.assertIn("PreToolUse", s["hooks"])

    def test_autoapprove_unknown_mode_exits(self):
        with self.assertRaises(SystemExit):
            run(block_autoapprove, self.proj, "nope", "settings.json", False)

    # --- memory -------------------------------------------------------------
    def test_memory_writes_brain_membership(self):
        run(block_memory, self.proj, "core", "federation", False)
        cfg = json.loads((self.proj / ".swissknife.json").read_text())
        self.assertEqual(cfg["memory_brain"], "core")
        self.assertEqual(
            (self.proj / ".claude" / "memory.env.ini").read_text().strip(),
            "MODE=federation")

    def test_parse_memory_flag(self):
        self.assertEqual(_parse_memory_flag("core:federation"), ("core", "federation"))
        self.assertEqual(_parse_memory_flag("file"), ("core", "file"))
        self.assertEqual(_parse_memory_flag(":file"), ("core", "file"))


if __name__ == "__main__":
    unittest.main()
