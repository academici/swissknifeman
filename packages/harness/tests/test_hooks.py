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

from harness.hooks import _parse_memory_flag, block_autoapprove, block_memory, block_plans_dir
import tests.fixtures as fx

_HOOKS_ROOT = Path(__file__).resolve().parent.parent / "configs/claude-code/hooks"


def _read_mode(common_sh, hookdir, project_dir=None):
    """Internal documentation."""
    env = {"PATH": "/usr/bin:/bin"}
    if project_dir is not None:
        env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    result = subprocess.run(
        ["bash", "-c", f'source "{common_sh}"; read_mode "{hookdir}"'],
        capture_output=True, text=True, env=env, check=True)
    return result.stdout.strip()


def run(fn, *a, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
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
        self.assertEqual(fx.configured(self.proj, "auto_approve", "mode"), "strict")
        self.assertEqual(fx.env_ini_files(self.proj), [])
        s = json.loads((self.proj / ".claude" / "settings.json").read_text())
        matchers = [e.get("matcher") for e in s["hooks"]["PreToolUse"]]
        self.assertEqual(sorted(matchers), ["Bash", "ExitPlanMode"])

        run(block_autoapprove, self.proj, "strict", "settings.json", False)
        s2 = json.loads((self.proj / ".claude" / "settings.json").read_text())
        self.assertEqual(len(s2["hooks"]["PreToolUse"]), 2)

    def test_autoapprove_off_no_hook(self):
        run(block_autoapprove, self.proj, "off", "settings.json", False)
        self.assertEqual(fx.configured(self.proj, "auto_approve", "mode"), "off")
        self.assertEqual(fx.env_ini_files(self.proj), [])
        self.assertFalse((self.proj / ".claude" / "settings.json").exists())

    def test_autoapprove_preserves_existing_settings(self):
        cdir = self.proj / ".claude"; cdir.mkdir(parents=True)
        (cdir / "settings.json").write_text(
            json.dumps({"permissions": {"allow": ["Bash(ls *)"]}}) + "\n")
        run(block_autoapprove, self.proj, "permissive", "settings.json", False)
        s = json.loads((cdir / "settings.json").read_text())
        self.assertEqual(s["permissions"]["allow"], ["Bash(ls *)"])
        self.assertIn("PreToolUse", s["hooks"])

    def test_autoapprove_unknown_mode_exits(self):
        with self.assertRaises(SystemExit):
            run(block_autoapprove, self.proj, "nope", "settings.json", False)

    # --- memory -------------------------------------------------------------
    def test_memory_writes_brain_membership(self):
        run(block_memory, self.proj, "core", "federation", False)
        cfg = json.loads((self.proj / ".swissknife.json").read_text())
        self.assertEqual(cfg["memory_brain"], "core")
        self.assertEqual(fx.configured(self.proj, "memory", "mode"), "federation")
        self.assertEqual(fx.env_ini_files(self.proj), [])

    def test_parse_memory_flag(self):
        self.assertEqual(_parse_memory_flag("core:federation"), ("core", "federation"))
        self.assertEqual(_parse_memory_flag("file"), ("core", "file"))
        self.assertEqual(_parse_memory_flag(":file"), ("core", "file"))

    # --- plans-dir ------------------------------------------------------------
    def test_plans_dir_sets_key_in_shared_settings_json(self):
        run(block_plans_dir, self.proj, "plans", "settings.json", False)
        s = json.loads((self.proj / ".claude" / "settings.json").read_text())
        self.assertEqual(s["plansDirectory"], "plans")

        self.assertFalse((self.proj / ".claude" / "settings.local.json").exists())

    def test_plans_dir_idempotent_no_dupe_write(self):
        run(block_plans_dir, self.proj, "plans", "settings.json", False)
        before = (self.proj / ".claude" / "settings.json").read_text()
        out = run(block_plans_dir, self.proj, "plans", "settings.json", False)
        after = (self.proj / ".claude" / "settings.json").read_text()
        self.assertEqual(before, after)
        self.assertIn("already", out)

    def test_plans_dir_does_not_overwrite_foreign_value(self):
        cdir = self.proj / ".claude"; cdir.mkdir(parents=True)
        (cdir / "settings.json").write_text(
            json.dumps({"plansDirectory": "my-custom-plans"}) + "\n")
        out = run(block_plans_dir, self.proj, "plans", "settings.json", False)
        s = json.loads((cdir / "settings.json").read_text())
        self.assertEqual(s["plansDirectory"], "my-custom-plans")
        self.assertIn("respect", out)

    def test_plans_dir_off_removes_our_default(self):
        run(block_plans_dir, self.proj, "plans", "settings.json", False)
        run(block_plans_dir, self.proj, "off", "settings.json", False)
        s = json.loads((self.proj / ".claude" / "settings.json").read_text())
        self.assertNotIn("plansDirectory", s)

    def test_plans_dir_off_does_not_touch_foreign_value(self):
        cdir = self.proj / ".claude"; cdir.mkdir(parents=True)
        (cdir / "settings.json").write_text(
            json.dumps({"plansDirectory": "my-custom-plans"}) + "\n")
        out = run(block_plans_dir, self.proj, "off", "settings.json", False)
        s = json.loads((cdir / "settings.json").read_text())
        self.assertEqual(s["plansDirectory"], "my-custom-plans")
        self.assertIn("not our default", out)

    def test_plans_dir_off_noop_when_key_absent(self):
        out = run(block_plans_dir, self.proj, "off", "settings.json", False)
        self.assertFalse((self.proj / ".claude" / "settings.json").exists())
        self.assertIn("nothing to shoot", out)

    def test_plans_dir_absolute_path_dies(self):
        with self.assertRaises(SystemExit):
            run(block_plans_dir, self.proj, "/tmp/abs-plans", "settings.json", False)

    def test_plans_dir_dry_run_does_not_write(self):
        run(block_plans_dir, self.proj, "plans", "settings.json", True)
        self.assertFalse((self.proj / ".claude" / "settings.json").exists())


    def test_autoapprove_read_mode_priority_ladder(self):
        common_sh = _HOOKS_ROOT / "auto-approve/lib/common.sh"
        hookdir = _HOOKS_ROOT / "auto-approve"

        self.assertEqual(_read_mode(common_sh, self.tmp / "no-such-hookdir", self.proj), "off")

        self.assertEqual(_read_mode(common_sh, hookdir, self.proj), "strict")

        cdir = self.proj / ".claude"; cdir.mkdir(parents=True, exist_ok=True)
        (cdir / "auto-approve.env.ini").write_text("MODE=bypass\n")
        self.assertEqual(_read_mode(common_sh, hookdir, self.proj), "bypass")

    def test_memory_read_mode_priority_ladder(self):
        common_sh = _HOOKS_ROOT / "memory/lib/common.sh"
        hookdir = _HOOKS_ROOT / "memory"
        self.assertEqual(_read_mode(common_sh, self.tmp / "no-such-hookdir", self.proj), "off")
        self.assertEqual(_read_mode(common_sh, hookdir, self.proj), "federation")
        cdir = self.proj / ".claude"; cdir.mkdir(parents=True, exist_ok=True)
        (cdir / "memory.env.ini").write_text("MODE=off\n")
        self.assertEqual(_read_mode(common_sh, hookdir, self.proj), "off")

    def test_read_mode_ignores_unknown_key(self):


        common_sh = _HOOKS_ROOT / "auto-approve/lib/common.sh"
        cdir = self.proj / ".claude"; cdir.mkdir(parents=True, exist_ok=True)
        (cdir / "auto-approve.env.ini").write_text("FOO=bar\nMODE=permissive\n")
        self.assertEqual(
            _read_mode(common_sh, _HOOKS_ROOT / "auto-approve", self.proj), "permissive")


if __name__ == "__main__":
    unittest.main()
