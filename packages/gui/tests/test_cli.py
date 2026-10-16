"""CLI: version, help, usage errors and the Python floor (PYTHON_TOO_OLD)."""
import contextlib
import io
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

import gui
from gui import cli

MODULE_ROOT = Path(__file__).resolve().parents[1]


def run_main(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = cli.main(list(argv))
        except SystemExit as stop:
            code = stop.code
    return code, out.getvalue(), err.getvalue()


class TestVersion(unittest.TestCase):
    def test_package_version_matches_unit(self):
        unit = json.loads((MODULE_ROOT / "unit.json").read_text(encoding="utf-8"))
        self.assertEqual(unit["version"], gui.__version__)
        self.assertEqual("0.1.0", gui.__version__)

    def test_version_flag(self):
        code, out, _ = run_main("--version")
        self.assertEqual(0, code)
        self.assertEqual("gui 0.1.0\n", out)

    def test_wrapper_prints_version(self):
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        result = subprocess.run([str(MODULE_ROOT / "bin" / "gui"), "--version"], capture_output=True, text=True,
                                env=env, timeout=60)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("gui 0.1.0", result.stdout.strip())


class TestUsage(unittest.TestCase):
    def test_no_command_prints_help(self):
        code, out, _ = run_main()
        self.assertEqual(0, code)
        self.assertIn("usage: gui", out)

    def test_help_flag(self):
        code, out, _ = run_main("--help")
        self.assertEqual(0, code)
        self.assertIn("--version", out)

    def test_unknown_command_is_usage_error(self):
        code, _, err = run_main("nope")
        self.assertEqual(cli.EXIT_USAGE, code)
        self.assertIn("gui: usage:", err)


class TestPythonFloor(unittest.TestCase):
    def test_floor_is_3_11(self):
        self.assertEqual((3, 11), gui.MIN_PYTHON)

    def test_supported_versions_pass(self):
        for version in ((3, 11, 0), (3, 12, 3), (4, 0)):
            with self.subTest(version=version):
                self.assertIsNone(cli.check_python(version))

    def test_old_versions_are_refused(self):
        for version in ((3, 9, 18), (3, 10, 14), (2, 7)):
            with self.subTest(version=version):
                message = cli.check_python(version)
                self.assertTrue(message.startswith("PYTHON_TOO_OLD: gui requires Python >= 3.11"), message)
                self.assertIn(f"found {version[0]}.{version[1]}", message)

    def test_main_refuses_old_interpreter(self):
        with mock.patch.object(sys, "version_info", (3, 10, 14, "final", 0)):
            code, out, err = run_main("--version")
        self.assertEqual(cli.EXIT_FAILURE, code)
        self.assertEqual("", out)
        self.assertIn("PYTHON_TOO_OLD", err)


if __name__ == "__main__":
    unittest.main()
