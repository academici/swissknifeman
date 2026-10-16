"""Discovery of the planner package for `harness run`: env → plan.py → PATH → PLANNER_UNAVAILABLE."""
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from harness.run import task_paths

_ENV_KEYS = (task_paths.PLANNER_ROOT_ENV, task_paths.LEGACY_ROOT_ENV, task_paths.PLAN_PY_ENV)


def make_planner(root):
    (root / "scripts").mkdir(parents=True)
    (root / "scripts" / "plan.py").write_text("", encoding="utf-8")
    return root


class PlannerRootTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name).resolve()
        self.empty_path = self.tmp / "empty-bin"
        self.empty_path.mkdir()
        env = {k: v for k, v in os.environ.items() if k not in _ENV_KEYS}
        env["PATH"] = str(self.empty_path)
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        warned = mock.patch.object(task_paths, "_LEGACY_ROOT_WARNED", False)
        warned.start()
        self.addCleanup(warned.stop)

    def test_env_wins(self):
        planner = make_planner(self.tmp / "custom")
        with mock.patch.dict(os.environ, {task_paths.PLANNER_ROOT_ENV: str(planner)}):
            self.assertEqual(task_paths.planner_root(), planner)
            self.assertEqual(task_paths.plan_script(), planner / "scripts" / "plan.py")

    def test_invalid_env_is_ignored_and_nothing_else_is_searched(self):
        with mock.patch.dict(os.environ, {task_paths.PLANNER_ROOT_ENV: str(self.tmp / "missing")}):
            with self.assertRaises(task_paths.PlannerUnavailable):
                task_paths.planner_root()

    def test_no_neighbour_and_no_monorepo_step(self):
        # a planner next to this installation or in a repository above the start folder is not a source
        self.assertFalse(hasattr(task_paths, "find_monorepo_root"))
        with self.assertRaises(task_paths.PlannerUnavailable) as caught:
            task_paths.planner_root()
        self.assertIn("PLANNER_UNAVAILABLE", str(caught.exception))
        self.assertIn(task_paths.PLANNER_ROOT_ENV, str(caught.exception))

    def test_plan_py_env_gives_the_folder_above_scripts(self):
        planner = make_planner(self.tmp / "by-plan-py")
        with mock.patch.dict(os.environ, {task_paths.PLAN_PY_ENV: str(planner / "scripts" / "plan.py")}):
            self.assertEqual(task_paths.planner_root(), planner)

    def test_planner_root_wins_over_plan_py(self):
        first = make_planner(self.tmp / "first")
        second = make_planner(self.tmp / "second")
        with mock.patch.dict(os.environ, {task_paths.PLANNER_ROOT_ENV: str(first),
                                          task_paths.PLAN_PY_ENV: str(second / "scripts" / "plan.py")}):
            self.assertEqual(task_paths.planner_root(), first)

    def test_planner_on_path_resolves_through_its_real_location(self):
        planner = make_planner(self.tmp / "installed")
        (planner / "bin").mkdir()
        launcher = planner / "bin" / "planner"
        launcher.write_text("#!/bin/sh\n", encoding="utf-8")
        launcher.chmod(0o755)
        link_dir = self.tmp / "on-path"
        link_dir.mkdir()
        (link_dir / "planner").symlink_to(launcher)
        with mock.patch.dict(os.environ, {"PATH": str(link_dir)}):
            self.assertEqual(task_paths.planner_root(), planner)

    def test_planner_on_path_without_a_plan_script_is_unavailable(self):
        lone = self.tmp / "lone" / "bin"
        lone.mkdir(parents=True)
        launcher = lone / "planner"
        launcher.write_text("#!/bin/sh\n", encoding="utf-8")
        launcher.chmod(0o755)
        with mock.patch.dict(os.environ, {"PATH": str(lone)}):
            with self.assertRaises(task_paths.PlannerUnavailable):
                task_paths.planner_root()

    def test_legacy_env_after_planner_root_warns_once(self):
        legacy = make_planner(self.tmp / "legacy")
        with mock.patch.dict(os.environ, {task_paths.LEGACY_ROOT_ENV: str(legacy)}), \
                mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
            self.assertEqual(task_paths.planner_root(), legacy)
            self.assertEqual(task_paths.planner_root(), legacy)
        self.assertEqual(stderr.getvalue().count("SKM_TASK_ROOT_DEPRECATED"), 1)
        self.assertIn("set PLANNER_ROOT", stderr.getvalue())

    def test_planner_root_wins_over_legacy_env_silently(self):
        planner = make_planner(self.tmp / "new")
        legacy = make_planner(self.tmp / "legacy")
        with mock.patch.dict(os.environ, {task_paths.PLANNER_ROOT_ENV: str(planner),
                                          task_paths.LEGACY_ROOT_ENV: str(legacy)}), \
                mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
            self.assertEqual(task_paths.planner_root(), planner)
        self.assertEqual(stderr.getvalue(), "")

    def test_invalid_legacy_env_is_ignored_without_warning(self):
        with mock.patch.dict(os.environ, {task_paths.LEGACY_ROOT_ENV: str(self.tmp / "missing")}), \
                mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
            with self.assertRaises(task_paths.PlannerUnavailable):
                task_paths.planner_root()
        self.assertEqual(stderr.getvalue(), "")

    def test_legacy_exception_name_is_an_alias(self):
        self.assertIs(task_paths.TaskUnavailable, task_paths.PlannerUnavailable)


if __name__ == "__main__":
    unittest.main()
