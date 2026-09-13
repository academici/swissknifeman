"""Internal documentation."""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from harness.hooks import STATUSLINE_VALUE, block_statusline
import tests.fixtures as fx

SCRIPT = (Path(__file__).resolve().parent.parent
          / "configs" / "claude-code" / "statusline" / "context-notify.sh")


def run(fn, *a, **kw):
    """Internal documentation."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        fn(*a, **kw)
    return buf.getvalue()


def sample(pct, session="s1", model="Opus 5", cwd="/home/u/proj"):
    """Internal documentation."""
    return json.dumps({
        "session_id": session,
        "cwd": cwd,
        "workspace": {"current_dir": cwd},
        "model": {"id": "claude-opus-5", "display_name": model},
        "context_window": {
            "context_window_size": 200000,
            "used_percentage": pct,
            "current_usage": None if pct is None else {"input_tokens": 1000},
        },
    })


class StatuslineSettingCase(unittest.TestCase):
    """Internal documentation."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.proj = fx.make_project(Path(self._tmp.name))
        self.local = self.proj / ".claude" / "settings.local.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_context_sets_key_in_settings_local(self):
        run(block_statusline, self.proj, "context", False)
        s = json.loads(self.local.read_text())
        self.assertEqual(s["statusLine"], STATUSLINE_VALUE)

        self.assertFalse((self.proj / ".claude" / "settings.json").exists())

    def test_merge_preserves_existing_keys(self):
        claude = self.proj / ".claude"
        claude.mkdir()
        self.local.write_text('{"permissions": {"allow": ["Bash(ls)"]}}')
        run(block_statusline, self.proj, "context", False)
        s = json.loads(self.local.read_text())
        self.assertEqual(s["statusLine"], STATUSLINE_VALUE)
        self.assertEqual(s["permissions"]["allow"], ["Bash(ls)"])

    def test_foreign_value_respected(self):
        claude = self.proj / ".claude"
        claude.mkdir()
        foreign = {"type": "command", "command": "~/my-own-line.sh"}
        self.local.write_text(json.dumps({"statusLine": foreign}))
        out = run(block_statusline, self.proj, "context", False)
        self.assertEqual(json.loads(self.local.read_text())["statusLine"], foreign)
        self.assertIn("уважаю локальный выбор", out)

    def test_off_removes_only_our_key(self):
        run(block_statusline, self.proj, "context", False)
        run(block_statusline, self.proj, "off", False)
        self.assertNotIn("statusLine", json.loads(self.local.read_text()))

    def test_off_keeps_foreign_key(self):
        claude = self.proj / ".claude"
        claude.mkdir()
        foreign = {"type": "command", "command": "~/my-own-line.sh"}
        self.local.write_text(json.dumps({"statusLine": foreign}))
        out = run(block_statusline, self.proj, "off", False)
        self.assertEqual(json.loads(self.local.read_text())["statusLine"], foreign)
        self.assertIn("не снимаю", out)

    def test_unknown_mode_dies(self):
        with self.assertRaises(SystemExit):
            run(block_statusline, self.proj, "nope", False)

    def test_dry_run_writes_nothing(self):
        run(block_statusline, self.proj, "context", True)
        self.assertFalse(self.local.exists())


class StatuslineScriptCase(unittest.TestCase):
    """Internal documentation."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.runtime = self.tmp / "runtime"
        self.runtime.mkdir()
        self.notify_log = self.tmp / "notify.log"
        self.notify = self.tmp / "fake-notify.sh"
        self.notify.write_text(
            "#!/usr/bin/env bash\n"
            f'cat >> "{self.notify_log}"\n'
            f'printf "\\n" >> "{self.notify_log}"\n')
        self.notify.chmod(0o755)
        self.env_file = self.tmp / "env.ini"
        self.write_env(cooldown=0)

    def tearDown(self):
        self._tmp.cleanup()

    def write_env(self, thresholds="80,90", cooldown=0, debug="false"):
        self.env_file.write_text(
            f"THRESHOLDS={thresholds}\nCOOLDOWN_MIN={cooldown}\n"
            f"BAR_WIDTH=10\nDEBUG={debug}\nNOTIFY_CMD={self.notify}\n")

    def render(self, pct, session="s1", columns=None):
        env = dict(os.environ)
        env["XDG_RUNTIME_DIR"] = str(self.runtime)
        env["STATUSLINE_ENV_FILE"] = str(self.env_file)
        if columns:
            env["COLUMNS"] = str(columns)
        p = subprocess.run(["bash", str(SCRIPT)], input=sample(pct, session=session),
                           text=True, capture_output=True, env=env, timeout=30)
        self.assertEqual(p.returncode, 0, f"скрипт обязан всегда выходить 0: {p.stderr}")
        return p.stdout

    def notifications(self, expected, timeout=5.0):
        """Internal documentation."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            lines = [ln for ln in self.notify_log.read_text().splitlines() if ln.strip()] \
                if self.notify_log.exists() else []
            if len(lines) >= expected:
                break
            time.sleep(0.05)
        time.sleep(0.2)
        if not self.notify_log.exists():
            return []
        return [ln for ln in self.notify_log.read_text().splitlines() if ln.strip()]

    def state_file(self, session="s1"):
        return self.runtime / "claude-statusline" / f"{session}.state"

    def test_renders_model_dir_bar_and_percent(self):
        out = self.render(81)
        self.assertIn("Opus 5", out)
        self.assertIn("proj", out)
        self.assertIn("81%", out)
        self.assertIn("[########--]", out)

    def test_null_percent_draws_no_bar_and_makes_no_decision(self):
        out = self.render(None)
        self.assertIn("Opus 5", out)
        self.assertNotIn("%", out)
        self.assertNotIn("[", out)

        self.assertFalse(self.state_file().exists())
        self.assertEqual(self.notifications(0, timeout=0.5), [])

    def test_bar_absent_for_non_numeric_percent(self):
        env = dict(os.environ)
        env["XDG_RUNTIME_DIR"] = str(self.runtime)
        env["STATUSLINE_ENV_FILE"] = str(self.env_file)
        p = subprocess.run(["bash", str(SCRIPT)], input='{"model":{"display_name":"X"}}',
                           text=True, capture_output=True, env=env, timeout=30)
        self.assertEqual(p.returncode, 0)
        self.assertIn("X", p.stdout)
        self.assertNotIn("%", p.stdout)

    def test_broken_stdin_never_fails_outward(self):
        env = dict(os.environ)
        env["XDG_RUNTIME_DIR"] = str(self.runtime)
        env["STATUSLINE_ENV_FILE"] = str(self.env_file)
        p = subprocess.run(["bash", str(SCRIPT)], input="не json вовсе",
                           text=True, capture_output=True, env=env, timeout=30)
        self.assertEqual(p.returncode, 0)
        self.assertTrue(p.stdout.strip())

    def test_columns_truncates_line(self):
        out = self.render(81, columns=20).rstrip("\n")
        self.assertLessEqual(len(out), 20)

    def test_band_sequence_without_cooldown(self):
        """Internal documentation."""
        for pct in (None, 5, 79, 81, 85, 91, 30, 95):
            self.render(pct)
        lines = self.notifications(3)
        self.assertEqual(len(lines), 3, f"ожидались ровно 3 уведомления, получено: {lines}")
        # Notification commands run in the background: dispatch order is not
        # completion order. Each crossing must still have exactly one alert.
        for percent, threshold in (("81%", "порог 80%"), ("91%", "порог 90%"), ("95%", "порог 90%")):
            matching = [line for line in lines if percent in line and threshold in line]
            self.assertEqual(len(matching), 1, lines)

    def test_cooldown_suppresses_and_does_not_lose_alert(self):
        """Internal documentation."""
        self.write_env(cooldown=15)
        for pct in (81, 85, 91, 95):
            self.render(pct)
        lines = self.notifications(1)
        self.assertEqual(len(lines), 1, f"кулдаун обязан подавить остальные: {lines}")
        self.assertIn("81%", lines[0])
        self.assertEqual(self.read_state()["BAND"], "1")
        self.write_env(cooldown=0)
        self.render(91)
        lines = self.notifications(2)
        self.assertEqual(len(lines), 2)
        self.assertIn("91%", lines[1])

    def read_state(self, session="s1"):
        return dict(ln.split("=", 1) for ln in
                    self.state_file(session).read_text().splitlines() if "=" in ln)

    def test_state_is_per_session_and_atomic(self):
        self.render(81, session="a")
        self.render(81, session="b")
        self.assertTrue(self.state_file("a").is_file())
        self.assertTrue(self.state_file("b").is_file())
        lines = self.notifications(2)
        self.assertEqual(len(lines), 2)

        leftovers = list((self.runtime / "claude-statusline").glob("*.tmp"))
        self.assertEqual(leftovers, [], f"частично записанное состояние: {leftovers}")

    def test_fresh_session_cleans_old_state_and_tmp_files(self):
        """Internal documentation."""
        state_dir = self.runtime / "claude-statusline"
        state_dir.mkdir()
        old_state = state_dir / "old.state"
        old_tmp = state_dir / "old.tmp"
        fresh_state = state_dir / "fresh.state"
        fresh_tmp = state_dir / "fresh.tmp"
        for path in (old_state, old_tmp, fresh_state, fresh_tmp):
            path.write_text("state\n")
        old = time.time() - 3 * 24 * 60 * 60
        for path in (old_state, old_tmp):
            os.utime(path, (old, old))

        self.render(5, session="cleanup")

        self.assertFalse(old_state.exists())
        self.assertFalse(old_tmp.exists())
        self.assertTrue(fresh_state.exists())
        self.assertTrue(fresh_tmp.exists())

    def test_drop_resets_band_down(self):
        self.render(95)
        self.render(30)
        self.assertEqual(self.read_state()["BAND"], "0")

    def test_no_orphan_notifier_processes(self):
        for pct in (81, 91, 30, 95):
            self.render(pct)
        self.notifications(3)
        p = subprocess.run(["pgrep", "-P", "1", "-f", "fake-notify.sh"],
                           capture_output=True, text=True)
        self.assertEqual(p.stdout.strip(), "", "остались подпроцессы-сироты доставки")


if __name__ == "__main__":
    unittest.main()
