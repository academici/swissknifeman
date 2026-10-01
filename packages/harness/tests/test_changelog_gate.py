"""Internal documentation."""
import contextlib
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from harness.hooks import block_changelog_gate
import tests.fixtures as fx

PKG = Path(__file__).resolve().parents[1]
GATE_DIR = PKG / "configs" / "claude-code" / "hooks" / "changelog-gate"
HOOK_PY = GATE_DIR / "changelog-gate.py"

_FAKE_GIT = """#!/usr/bin/env python3
import os, sys
args = sys.argv[1:]
if args[:1] == ["-C"]:
    args = args[2:]
if args[:1] == ["ls-files"]:
    print(os.environ.get("FAKE_GIT_LS_FILES", ""))
elif args[:3] == ["diff", "--cached", "--name-only"]:
    print(os.environ.get("FAKE_GIT_DIFF_CACHED", ""))
else:
    sys.exit(1)
"""

_FAILING_GIT = """#!/usr/bin/env python3
import sys
sys.exit(128)  # git always crashes - not a repository / git not available
"""


def run(fn, *a, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*a, **kw)
    return buf.getvalue()


class HookBehaviorCase(unittest.TestCase):
    """Internal documentation."""

    @classmethod
    def setUpClass(cls):
        cls._bin_tmp = tempfile.TemporaryDirectory()
        bindir = Path(cls._bin_tmp.name)
        git_shim = bindir / "git"
        git_shim.write_text(_FAKE_GIT, encoding="utf-8")
        git_shim.chmod(git_shim.stat().st_mode | stat.S_IEXEC)
        cls._bindir = str(bindir)

        cls._failbin_tmp = tempfile.TemporaryDirectory()
        failbindir = Path(cls._failbin_tmp.name)
        fail_shim = failbindir / "git"
        fail_shim.write_text(_FAILING_GIT, encoding="utf-8")
        fail_shim.chmod(fail_shim.stat().st_mode | stat.S_IEXEC)
        cls._failbindir = str(failbindir)

    @classmethod
    def tearDownClass(cls):
        cls._bin_tmp.cleanup()
        cls._failbin_tmp.cleanup()

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.proj = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _set_mode(self, mode):
        d = self.proj / ".claude"
        d.mkdir(parents=True, exist_ok=True)
        (d / "changelog-gate.env.ini").write_text(f"MODE={mode}\n")

    def hook(self, command, ls_files="CHANGELOG.md\nsrc/x.py", diff_cached=""):
        """Internal documentation."""
        payload = {"cwd": str(self.proj), "tool_name": "Bash",
                   "tool_input": {"command": command}}
        env = dict(os.environ)
        env["PATH"] = self._bindir + os.pathsep + env.get("PATH", "")
        env["FAKE_GIT_LS_FILES"] = ls_files
        env["FAKE_GIT_DIFF_CACHED"] = diff_cached
        p = subprocess.run([sys.executable, str(HOOK_PY)],
                           input=json.dumps(payload).encode(),
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           env=env, timeout=20)
        return p.returncode, p.stdout.decode(), p.stderr.decode()


    def test_warn_feat_without_changelog_warns_not_block(self):
        self._set_mode("warn")
        rc, out, err = self.hook('git commit -m "feat: X"')
        self.assertEqual(rc, 0)
        data = json.loads(out)
        ctx = data["hookSpecificOutput"]["additionalContext"]
        self.assertIn("changelog-gate", ctx)
        self.assertIn("feat:", ctx)
        self.assertEqual(data["hookSpecificOutput"]["permissionDecision"], "allow")


    def test_warn_docs_silent(self):
        self._set_mode("warn")
        rc, out, err = self.hook('git commit -m "docs: X"')
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")


    def test_warn_skip_marker_silent(self):
        self._set_mode("warn")
        rc, out, err = self.hook('git commit -m "feat: X [changelog-skip]"')
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")


    def test_warn_changelog_staged_silent(self):
        self._set_mode("warn")
        rc, out, err = self.hook('git commit -m "feat: X"', diff_cached="CHANGELOG.md")
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")


    def test_strict_blocks(self):
        self._set_mode("strict")
        rc, out, err = self.hook('git commit -m "feat: X"')
        self.assertEqual(rc, 2)
        self.assertIn("changelog-gate", err)


    def test_malformed_stdin_no_crash(self):
        env = dict(os.environ)
        env["PATH"] = self._bindir + os.pathsep + env.get("PATH", "")
        p = subprocess.run([sys.executable, str(HOOK_PY)], input=b"not json{",
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=20)
        self.assertEqual(p.returncode, 0)


    def test_no_dash_m_noop(self):
        self._set_mode("warn")
        rc, out, err = self.hook("git commit")
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")


    def test_non_git_bash_noop(self):
        self._set_mode("warn")
        rc, out, err = self.hook("ls -la")
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")

    def test_off_by_default_no_envini(self):

        rc, out, err = self.hook('git commit -m "feat: X"')
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")

    def test_bogus_mode_in_envini_defaults_off(self):
        self._set_mode("bogus")
        rc, out, err = self.hook('git commit -m "feat: X"')
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")

    def test_repo_without_changelog_noop(self):
        self._set_mode("warn")
        rc, out, err = self.hook('git commit -m "feat: X"', ls_files="src/x.py\nREADME.md")
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")

    def test_fix_and_perf_and_refactor_trigger(self):
        self._set_mode("warn")
        for t in ("fix", "perf", "refactor"):
            rc, out, err = self.hook(f'git commit -m "{t}: X"')
            self.assertEqual(rc, 0, t)
            self.assertNotEqual(out, "", t)

    def test_chained_command_still_detected(self):
        self._set_mode("warn")
        rc, out, err = self.hook('git add -A && git commit -m "feat: X"')
        self.assertEqual(rc, 0)
        self.assertNotEqual(out, "")

    def test_git_subprocess_failure_is_noop(self):


        self._set_mode("warn")
        env = dict(os.environ)
        env["PATH"] = self._failbindir + os.pathsep + env.get("PATH", "")
        payload = {"cwd": str(self.proj), "tool_name": "Bash",
                   "tool_input": {"command": 'git commit -m "feat: X"'}}
        p = subprocess.run([sys.executable, str(HOOK_PY)],
                           input=json.dumps(payload).encode(),
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=20)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(p.stdout.decode(), "")



class BlockChangelogGateCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.proj = fx.make_project(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_strict_writes_envini_and_registers(self):
        run(block_changelog_gate, self.proj, "strict", "settings.json", False)
        self.assertEqual(
            (self.proj / ".claude" / "changelog-gate.env.ini").read_text().strip(),
            "MODE=strict")
        s = json.loads((self.proj / ".claude" / "settings.json").read_text())
        entries = s["hooks"]["PreToolUse"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["matcher"], "Bash")
        self.assertIn("changelog-gate.py", entries[0]["hooks"][0]["command"])

    def test_off_no_hook(self):
        run(block_changelog_gate, self.proj, "off", "settings.json", False)
        self.assertEqual(
            (self.proj / ".claude" / "changelog-gate.env.ini").read_text().strip(), "MODE=off")
        self.assertFalse((self.proj / ".claude" / "settings.json").exists())

    def test_idempotent(self):
        run(block_changelog_gate, self.proj, "warn", "settings.json", False)
        run(block_changelog_gate, self.proj, "warn", "settings.json", False)
        s = json.loads((self.proj / ".claude" / "settings.json").read_text())
        self.assertEqual(len(s["hooks"]["PreToolUse"]), 1)

    def test_unknown_mode_exits(self):
        with self.assertRaises(SystemExit):
            run(block_changelog_gate, self.proj, "bogus", "settings.json", False)

    def test_no_mode_noop(self):
        run(block_changelog_gate, self.proj, "", "settings.json", False)
        self.assertFalse((self.proj / ".claude").exists())


if __name__ == "__main__":
    unittest.main()
