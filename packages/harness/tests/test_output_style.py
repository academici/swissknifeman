"""block_output_style: копирует lean-стиль в проект + ставит top-level outputStyle в
settings.local.json (merge-only); off → ничего не ставит; неизвестный стиль → die; dry — без записи."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from harness.hooks import block_output_style
import tests.fixtures as fx


def run(fn, *a, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*a, **kw)
    return buf.getvalue()


class OutputStyleCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        # real_env → настоящий configs_dir с output-styles/lean.md; tmp-home изолирует ~/.claude
        self.env = fx.real_env(Path(self._tmp.name))
        self.proj = fx.make_project(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_lean_copies_and_sets_setting(self):
        run(block_output_style, self.env, self.proj, "lean", False)
        style = self.proj / ".claude" / "output-styles" / "lean.md"
        self.assertTrue(style.is_file())
        self.assertIn("keep-coding-instructions", style.read_text())
        s = json.loads((self.proj / ".claude" / "settings.local.json").read_text())
        self.assertEqual(s["outputStyle"], "lean")

    def test_off_sets_nothing(self):
        run(block_output_style, self.env, self.proj, "off", False)
        self.assertFalse((self.proj / ".claude" / "settings.local.json").exists())
        self.assertFalse((self.proj / ".claude" / "output-styles").exists())

    def test_unknown_style_dies(self):
        with self.assertRaises(SystemExit):
            run(block_output_style, self.env, self.proj, "nope", False)

    def test_dry_run_writes_nothing(self):
        run(block_output_style, self.env, self.proj, "lean", True)
        self.assertFalse((self.proj / ".claude" / "output-styles" / "lean.md").exists())
        self.assertFalse((self.proj / ".claude" / "settings.local.json").exists())

    def test_merge_preserves_existing_keys(self):
        claude = self.proj / ".claude"
        claude.mkdir()
        (claude / "settings.local.json").write_text('{"permissions": {"allow": ["Bash(ls)"]}}')
        run(block_output_style, self.env, self.proj, "lean", False)
        s = json.loads((claude / "settings.local.json").read_text())
        self.assertEqual(s["outputStyle"], "lean")
        self.assertEqual(s["permissions"]["allow"], ["Bash(ls)"])  # существующее сохранено


if __name__ == "__main__":
    unittest.main()
