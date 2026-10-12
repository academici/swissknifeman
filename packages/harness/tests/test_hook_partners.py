"""Hooks installed into projects find their partner commands by SKM_<P>_BIN, SKM_<P>_ROOT and PATH only."""
import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PACKAGE = Path(__file__).resolve().parents[1]
HOOKS = PACKAGE / "configs/claude-code/hooks"
MAIND_MODE = HOOKS / "memory/modes/maind.sh"
PLAN_CHECK = HOOKS / "review-gate/checks/plan-check.sh"
RUN_REPORT = HOOKS / "run-report/run-report.py"
_LADDER_ENV = ("MAIND_BIN", "SKM_MAIND_BIN", "SKM_MAIND_ROOT", "ANALYST_BIN", "SKM_ANALYST_BIN",
               "SKM_ANALYST_ROOT", "PLANNER_PLAN_PY", "PLANNER_ROOT")


def _executable(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return path


class HookPartnerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name).resolve()
        self.empty_bin = self.tmp / "empty-bin"
        self.empty_bin.mkdir()

    def _env(self, **extra):
        env = {k: v for k, v in os.environ.items() if k not in _LADDER_ENV}
        env["PATH"] = str(self.empty_bin) + os.pathsep + "/usr/bin:/bin"
        env["HOME"] = str(self.tmp / "home")
        env.update(extra)
        return env

    def _maind(self, **extra):
        proc = subprocess.run(["bash", "-c", f"source {MAIND_MODE}; _maind_bin"], env=self._env(**extra),
                              capture_output=True, text=True, timeout=20)
        return proc.returncode, proc.stdout, proc.stderr

    def test_maind_mode_prefers_skm_bin_then_root_then_path(self):
        by_bin = _executable(self.tmp / "a" / "maind")
        by_root = _executable(self.tmp / "root" / "bin" / "maind")
        on_path = _executable(self.empty_bin / "maind")
        self.assertEqual(self._maind(SKM_MAIND_BIN=str(by_bin), SKM_MAIND_ROOT=str(self.tmp / "root"))[:2],
                         (0, str(by_bin)))
        self.assertEqual(self._maind(SKM_MAIND_ROOT=str(self.tmp / "root"))[:2], (0, str(by_root)))
        self.assertEqual(self._maind()[:2], (0, str(on_path)))

    def test_maind_mode_without_a_partner_fails_open(self):
        self.assertEqual(self._maind()[0], 1)

    def test_maind_mode_names_no_checkout_path(self):
        text = MAIND_MODE.read_text(encoding="utf-8")
        self.assertNotIn("packages/" + "maind", text)
        self.assertNotIn("projects/packages", text)

    def test_legacy_maind_bin_still_works_with_one_warning(self):
        legacy = _executable(self.tmp / "legacy" / "maind")
        code, out, err = self._maind(MAIND_BIN=str(legacy))
        self.assertEqual((code, out), (0, str(legacy)))
        self.assertIn("MAIND_BIN_DEPRECATED", err)
        self.assertEqual(err.count("MAIND_BIN_DEPRECATED"), 1)

    def test_plan_check_names_no_checkout_path(self):
        self.assertNotIn("packages/" + "planner", PLAN_CHECK.read_text(encoding="utf-8"))

    def _analyst_bin(self, **env):
        spec = importlib.util.spec_from_file_location("run_report_hook", RUN_REPORT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with mock.patch.dict(os.environ, self._env(**env), clear=True):
            return module._analyst_bin()

    def test_run_report_finds_analyst_through_skm_bin_root_and_path(self):
        by_bin = _executable(self.tmp / "b" / "analyst")
        by_root = _executable(self.tmp / "aroot" / "bin" / "analyst")
        on_path = _executable(self.empty_bin / "analyst")
        self.assertEqual(self._analyst_bin(SKM_ANALYST_BIN=str(by_bin), SKM_ANALYST_ROOT=str(self.tmp / "aroot")),
                         str(by_bin))
        self.assertEqual(self._analyst_bin(SKM_ANALYST_ROOT=str(self.tmp / "aroot")), str(by_root))
        self.assertEqual(self._analyst_bin(), str(on_path))

    def test_run_report_without_analyst_returns_none(self):
        self.assertIsNone(self._analyst_bin())

    def test_run_report_names_no_checkout_path(self):
        text = RUN_REPORT.read_text(encoding="utf-8")
        self.assertNotIn("packages/" + "analyst", text)
        self.assertNotIn("projects/packages", text)


if __name__ == "__main__":
    unittest.main()
