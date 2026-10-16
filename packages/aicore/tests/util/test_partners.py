"""aicore.util.partners: lookup order, deprecation warnings, planner branch, JSON runner."""
import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

from aicore.util import partners
from aicore.util.partners import (PartnerError, PartnerUnavailable, partner_command, require_partner,
                                  run_partner_json)


def _script(path: Path, body: str, mode: int = 0o755) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8")
    path.chmod(mode)
    return str(path)


class PartnerTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        partners._WARNED.clear()
        self.empty = str(self.tmp / "empty-path")
        os.makedirs(self.empty)

    def env(self, **kw):
        return {"PATH": self.empty, **kw}


class TestLookupOrder(PartnerTestCase):
    def test_absent_is_none(self):
        self.assertIsNone(partner_command("analyst", env=self.env()))

    def test_bin_beats_root_beats_path(self):
        by_bin = _script(self.tmp / "a" / "analyst-bin", "true")
        root = self.tmp / "root"
        _script(root / "bin" / "analyst", "true")
        on_path = self.tmp / "path"
        _script(on_path / "analyst", "true")
        env = self.env(SKM_ANALYST_BIN=by_bin, SKM_ANALYST_ROOT=str(root), PATH=str(on_path))
        self.assertEqual(partner_command("analyst", env=env), [by_bin])
        del env["SKM_ANALYST_BIN"]
        self.assertEqual(partner_command("analyst", env=env), [str(root / "bin" / "analyst")])
        del env["SKM_ANALYST_ROOT"]
        self.assertEqual(partner_command("analyst", env=env), [str(on_path / "analyst")])

    def test_not_executable_or_missing_is_skipped(self):
        plain = _script(self.tmp / "plain", "true", mode=0o644)
        env = self.env(SKM_ANALYST_BIN=plain, SKM_ANALYST_ROOT=str(self.tmp / "none"))
        self.assertIsNone(partner_command("analyst", env=env))

    def test_env_without_path_does_not_fall_back_to_the_process_path(self):
        self.assertIsNone(partner_command("ls", env={}))
        self.assertIsNone(partner_command("planner", env={}))

    def test_name_with_dash_maps_to_underscore(self):
        found = _script(self.tmp / "x", "true")
        self.assertEqual(partner_command("agent-memory", env=self.env(SKM_AGENT_MEMORY_BIN=found)), [found])

    def test_legacy_env_wins_and_warns_once(self):
        legacy = _script(self.tmp / "legacy", "true")
        new = _script(self.tmp / "new", "true")
        env = self.env(MAIND_HARNESS_BIN=legacy, SKM_HARNESS_BIN=new)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            first = partner_command("harness", env=env, legacy_env=("MAIND_HARNESS_BIN",))
            second = partner_command("harness", env=env, legacy_env=("MAIND_HARNESS_BIN",))
        self.assertEqual((first, second), ([legacy], [legacy]))
        self.assertEqual(err.getvalue().count("MAIND_HARNESS_BIN_DEPRECATED"), 1)
        self.assertIn("set SKM_HARNESS_BIN", err.getvalue())

    def test_unusable_legacy_falls_through_silently(self):
        new = _script(self.tmp / "new", "true")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            found = partner_command("harness", env=self.env(MAIND_HARNESS_BIN=str(self.tmp / "gone"),
                                                           SKM_HARNESS_BIN=new),
                                    legacy_env=("MAIND_HARNESS_BIN",))
        self.assertEqual(found, [new])
        self.assertEqual(err.getvalue(), "")


class TestPlanner(PartnerTestCase):
    def plan_py(self, root: Path) -> str:
        path = root / "scripts" / "plan.py"
        path.parent.mkdir(parents=True)
        path.write_text("print('x')\n", encoding="utf-8")
        return str(path)

    def test_plan_py_then_root_then_task_root(self):
        a, b, c = (self.tmp / n for n in "abc")
        pa, pb, pc = self.plan_py(a), self.plan_py(b), self.plan_py(c)
        env = self.env(PLANNER_PLAN_PY=pa, PLANNER_ROOT=str(b), SKM_TASK_ROOT=str(c))
        self.assertEqual(partner_command("planner", env=env), [sys.executable, pa])
        del env["PLANNER_PLAN_PY"]
        self.assertEqual(partner_command("planner", env=env), [sys.executable, pb])
        del env["PLANNER_ROOT"]
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(partner_command("planner", env=env), [sys.executable, pc])
            partner_command("planner", env=env)
        self.assertEqual(err.getvalue().count("SKM_TASK_ROOT_DEPRECATED"), 1)

    def test_planner_ignores_skm_bin_and_uses_path_last(self):
        on_path = self.tmp / "path"
        _script(on_path / "planner", "true")
        other = _script(self.tmp / "other", "true")
        env = self.env(SKM_PLANNER_BIN=other, PATH=str(on_path))
        self.assertEqual(partner_command("planner", env=env), [str(on_path / "planner")])
        self.assertIsNone(partner_command("planner", env=self.env(SKM_PLANNER_BIN=other)))

    def test_planner_is_found_as_the_installed_plan_py_link(self):
        on_path = self.tmp / "installed"
        _script(on_path / "plan.py", "true")
        env = self.env(PATH=str(on_path))
        self.assertEqual(partner_command("planner", env=env), [str(on_path / "plan.py")])
        _script(on_path / "planner", "true")
        self.assertEqual(partner_command("planner", env=env), [str(on_path / "planner")])  # a launcher wins


class TestRequireAndRun(PartnerTestCase):
    def test_require_raises_with_code(self):
        with self.assertRaises(PartnerUnavailable) as ctx:
            require_partner("analyst", env=self.env())
        self.assertEqual(str(ctx.exception),
                         "PARTNER_UNAVAILABLE: analyst not found (set SKM_ANALYST_ROOT or put analyst on PATH)")

    def test_run_ok_passes_args_and_input(self):
        script = _script(self.tmp / "p", 'printf \'{"args": "%s", "stdin": "%s"}\' "$*" "$(/bin/cat)"')
        out = run_partner_json("p", ["runs", "show"], env=self.env(SKM_P_BIN=script), input="hi")
        self.assertEqual(out, {"args": "runs show", "stdin": "hi"})

    def test_run_failure_reports_last_stderr_line(self):
        script = _script(self.tmp / "p", 'echo first >&2; echo boom >&2; exit 3')
        with self.assertRaises(PartnerError) as ctx:
            run_partner_json("p", ["verb"], env=self.env(SKM_P_BIN=script))
        self.assertEqual(str(ctx.exception), "PARTNER_FAILED: p verb exited 3: boom")

    def test_run_garbage_is_bad_output(self):
        script = _script(self.tmp / "p", "echo not-json")
        with self.assertRaises(PartnerError) as ctx:
            run_partner_json("p", ["verb"], env=self.env(SKM_P_BIN=script))
        self.assertTrue(str(ctx.exception).startswith("PARTNER_BAD_OUTPUT: p verb"))

    def test_run_unavailable(self):
        with self.assertRaises(PartnerUnavailable):
            run_partner_json("p", ["verb"], env=self.env())


if __name__ == "__main__":
    unittest.main()
