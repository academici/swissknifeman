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


class TestDetachedProject(unittest.TestCase):
    def test_detached_serve_does_not_register_its_cwd(self):
        import argparse
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".swissknifeman").mkdir()
            with mock.patch("pathlib.Path.cwd", return_value=Path(tmp)):
                self.assertIsNone(cli._project_dir(argparse.Namespace(project=None, detached=True)))
                self.assertIsNotNone(cli._project_dir(argparse.Namespace(project=None, detached=False)))


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


FIXTURES = MODULE_ROOT / "tests" / "fixtures" / "units"


class TestContributions(unittest.TestCase):
    def run_with_units(self, case, *argv):
        with mock.patch.dict(os.environ, {"SKM_UNITS_PATH": str(FIXTURES / case)}):
            return run_main(*argv)

    def test_json_is_a_valid_catalog(self):
        from gui import contracts

        code, out, err = self.run_with_units("two-owners", "contributions", "--json")
        self.assertEqual((0, ""), (code, err))
        doc = json.loads(out)
        self.assertEqual([], contracts.validate(doc, "catalog"))
        self.assertEqual(["alpha", "beta"], [entry["owner"] for entry in doc["contributions"]])

    def test_rejections_do_not_change_the_exit_code(self):
        code, out, _ = self.run_with_units("conflict-id", "contributions", "--json")
        doc = json.loads(out)
        self.assertEqual(0, code)
        self.assertEqual(([], {"CONTRIB_CONFLICT"}), (doc["contributions"], {r["code"] for r in doc["rejected"]}))

    def test_text_table(self):
        code, out, _ = self.run_with_units("conflict-id", "contributions")
        self.assertEqual(0, code)
        self.assertIn("owner  source", out)
        self.assertIn("rejected:\n  CONTRIB_CONFLICT demo ", out)
        self.assertRegex(out, r"digest: sha256:[0-9a-f]{64}\n$")
        code, out, _ = self.run_with_units("valid-one", "contributions")
        self.assertRegex(out, r"\ndemo +unit +2 +0 +1 +/")

    def test_project_option(self):
        with mock.patch("gui.catalog.sources.extension_sources", return_value=([], None)) as extensions:
            code, _, _ = self.run_with_units("empty", "contributions", "--project", str(MODULE_ROOT), "--json")
        self.assertEqual(0, code)
        self.assertEqual(MODULE_ROOT.resolve(), extensions.call_args[0][0])

    def test_wrapper_runs_the_resolver(self):
        env = {**{k: v for k, v in os.environ.items() if k != "PYTHONPATH"},
               "SKM_UNITS_PATH": str(FIXTURES / "conflict-id")}
        result = subprocess.run([str(MODULE_ROOT / "bin" / "gui"), "contributions", "--json"], capture_output=True,
                                text=True, env=env, timeout=60)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual({"CONTRIB_CONFLICT"}, {r["code"] for r in json.loads(result.stdout)["rejected"]})


class TestCheck(unittest.TestCase):
    def test_valid_contribution(self):
        code, out, _ = run_main("check", str(FIXTURES / "valid-one" / "demo"))
        self.assertEqual(0, code)
        self.assertTrue(out.startswith("ok gui.contribution.path: "))
        code, out, _ = run_main("check", str(FIXTURES / "valid-one" / "demo"), "--json")
        self.assertEqual(0, code)
        self.assertEqual({"ok"}, {result["status"] for result in json.loads(out)})

    def test_failure_exits_1(self):
        code, out, _ = run_main("check", str(FIXTURES / "empty" / "plain"))
        self.assertEqual(1, code)
        self.assertTrue(out.startswith("fail gui.contribution.path: "))

    def test_usage(self):
        code, _, err = run_main("check")
        self.assertEqual(2, code)
        self.assertIn("gui: usage:", err)


class TestPythonFloor(unittest.TestCase):
    def test_floor_is_3_11(self):
        import aicore
        self.assertEqual((3, 11), gui.MIN_PYTHON)
        self.assertGreaterEqual(gui.MIN_PYTHON, tuple(aicore.MIN_PYTHON))

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
