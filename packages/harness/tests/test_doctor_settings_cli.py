"""Internal documentation."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from harness import cli
from harness.doctor import cmd_doctor
from harness.settings import (add_hook, load_settings, set_swissknife,
                              write_json, write_text)
import tests.fixtures as fx


def run(fn, *a, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            out = fn(*a, **kw)
        except SystemExit as e:
            return e, buf.getvalue()
    return out, buf.getvalue()


class DoctorCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_help(self):
        _root, env = fx.make_root(self.tmp)
        _out, text = run(cmd_doctor, env, ["--help"])
        self.assertIn("harness doctor", text)

    def test_runs_on_real_env_reports_presets(self):
        env = fx.real_env(self.tmp)
        _out, text = run(cmd_doctor, env, [])
        self.assertIn("harness.environment", text)
        _out, text = run(cmd_doctor, env, ["--json"])
        evidence = json.loads(text)[0]["evidence"]
        self.assertTrue(any(line.startswith("mcp-presets: ") for line in evidence))
        self.assertTrue(any(line.startswith("permissions-presets: ") for line in evidence))

    def test_runs_when_script_missing_no_crash(self):

        _root, env = fx.make_root(self.tmp)
        out, text = run(cmd_doctor, env, [])
        self.assertIsInstance(out, SystemExit)          # a failed check exits 1, nothing crashes
        self.assertEqual(out.code, 1)
        self.assertRegex(text, r"(?m)^fail harness\.environment: ")

    def test_run_report_hook_stale_when_not_installed(self):


        env = fx.real_env(self.tmp)
        out, text = run(cmd_doctor, env, [])
        self.assertNotIsInstance(out, SystemExit)
        self.assertRegex(text, r"(?m)^warn harness\.hooks: ")
        self.assertIn("harness hooks --global", text)

    def test_route_evidence_guidance_line_present(self):


        env = fx.real_env(self.tmp)
        _out, text = run(cmd_doctor, env, [])
        self.assertIn("route evidence", text)
        self.assertIn("self-attested", text)

    def test_run_report_hook_fresh_no_warn(self):

        env = fx.real_env(self.tmp)
        src = fx.PACKAGE_ROOT / "configs" / "claude-code" / "hooks" / "run-report"
        dst = env.home / ".claude" / "hooks" / "run-report"
        dst.mkdir(parents=True, exist_ok=True)
        for name in ("run-report.py", "_lib.py", "_usage.py"):
            (dst / name).write_text((src / name).read_text(encoding="utf-8"), encoding="utf-8")
        _out, text = run(cmd_doctor, env, [])
        self.assertNotIn("stale", text)


class SettingsCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_load_settings_absent_returns_empty(self):
        data, f = load_settings(self.tmp, "settings.json")
        self.assertEqual(data, {})
        self.assertEqual(f, self.tmp / ".claude" / "settings.json")

    def test_write_json_dry_writes_nothing(self):
        f = self.tmp / "x.json"
        run(write_json, f, {"a": 1}, True)
        self.assertFalse(f.exists())

    def test_write_json_creates_and_keeps_the_old_copy_in_the_project_backups(self):
        (self.tmp / ".git").mkdir()
        f = self.tmp / ".claude" / "x.json"
        run(write_json, f, {"a": 1}, False)
        self.assertEqual(json.loads(f.read_text())["a"], 1)
        self.assertFalse((self.tmp / ".swissknifeman" / "backups").exists())

        run(write_json, f, {"a": 2}, False)
        self.assertEqual(json.loads(f.read_text())["a"], 2)
        self.assertFalse(Path(f"{f}.bak").exists())
        copies = sorted((self.tmp / ".swissknifeman" / "backups").glob("*/.claude/x.json"))
        self.assertEqual([json.loads(path.read_text())["a"] for path in copies], [1])

    def test_write_json_outside_a_project_keeps_the_copy_in_the_machine_state(self):
        skm = self.tmp / "skm"
        f = self.tmp / "loose" / "x.json"
        run(write_json, f, {"a": 1}, False)
        from aicore.state import locations
        marker_found = locations._marker_found
        # /tmp may be a real checkout; only markers inside this fixture belong to the test.
        with unittest.mock.patch.dict(os.environ, {"SKM_HOME": str(skm)}), \
                unittest.mock.patch.object(locations, "_marker_found", side_effect=lambda candidate, marker:
                                           candidate not in self.tmp.resolve().parents and marker_found(candidate, marker)):
            run(write_json, f, {"a": 2}, False)
        self.assertFalse(Path(f"{f}.bak").exists())
        self.assertEqual(len(list((skm / "state" / "backups").glob("*/**/x.json"))), 1)

    def test_write_text_dry_and_real(self):
        f = self.tmp / "t.txt"
        run(write_text, f, "hi", True)
        self.assertFalse(f.exists())
        run(write_text, f, "hi", False)
        self.assertEqual(f.read_text(), "hi")

    def test_add_hook_dedups(self):
        s = {}
        self.assertTrue(add_hook(s, "PreToolUse", "Bash", "cmd.sh"))
        self.assertFalse(add_hook(s, "PreToolUse", "Bash", "cmd.sh"))
        entry = s["hooks"]["PreToolUse"][0]
        self.assertEqual(entry["matcher"], "Bash")
        self.assertEqual(entry["hooks"][0]["command"], "cmd.sh")

    def test_add_hook_without_matcher_omits_key(self):
        s = {}
        add_hook(s, "Notification", "", "notify.sh")
        self.assertNotIn("matcher", s["hooks"]["Notification"][0])

    def test_set_swissknife_writes_and_idempotent(self):
        run(set_swissknife, self.tmp, "memory_brain", "core:file", False)
        f = self.tmp / ".swissknife.json"
        self.assertEqual(json.loads(f.read_text())["memory_brain"], "core:file")
        _out, text = run(set_swissknife, self.tmp, "memory_brain", "core:file", False)
        self.assertIn("already", text)


class CliDispatchCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_too_few_args_exits_2(self):
        out, _text = run(cli.main, [str(self.tmp)])
        self.assertIsInstance(out, SystemExit)
        self.assertEqual(out.code, 2)

    def test_unknown_command_exits_1(self):
        out, text = run(cli.main, [str(self.tmp), "bogus"])
        self.assertIsInstance(out, SystemExit)
        self.assertEqual(out.code, 1)
        self.assertIn("Unknown command", text)

    def test_doctor_dispatch_runs(self):
        out, text = run(cli.main, [str(fx.PACKAGE_ROOT), "doctor"])
        self.assertNotIsInstance(out, SystemExit)
        self.assertIn("harness.environment", text)

    def test_apply_is_alias_for_permissions(self):
        self.assertIs(cli.COMMANDS["apply"], cli.COMMANDS["permissions"])


if __name__ == "__main__":
    unittest.main()
