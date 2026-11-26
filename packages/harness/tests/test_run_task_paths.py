"""Discovery of the planner package for `harness run`: env → plan.py → PATH → PLANNER_UNAVAILABLE."""
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from harness.run import task_paths

_ENV_KEYS = (task_paths.PLANNER_ROOT_ENV, "SKM_TASK_ROOT", task_paths.PLAN_PY_ENV)


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

    def test_retired_root_variable_is_ignored(self):
        legacy = make_planner(self.tmp / "legacy")
        with mock.patch.dict(os.environ, {"SKM_TASK_ROOT": str(legacy)}), \
                mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
            with self.assertRaises(task_paths.PlannerUnavailable):
                task_paths.planner_root()
        self.assertEqual(stderr.getvalue(), "")

    def test_planner_root_wins_and_retired_variable_is_silent(self):
        planner = make_planner(self.tmp / "new")
        legacy = make_planner(self.tmp / "legacy")
        with mock.patch.dict(os.environ, {task_paths.PLANNER_ROOT_ENV: str(planner),
                                          "SKM_TASK_ROOT": str(legacy)}), \
                mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
            self.assertEqual(task_paths.planner_root(), planner)
        self.assertEqual(stderr.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
