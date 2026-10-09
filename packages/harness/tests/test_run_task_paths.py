"""Discovery of the planner package for `harness run`: env → neighbour → monorepo → PLANNER_UNAVAILABLE."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from harness.run import task_paths

REPO_ROOT = Path(__file__).resolve().parents[3]


def make_planner(root):
    (root / "scripts").mkdir(parents=True)
    (root / "scripts" / "plan.py").write_text("", encoding="utf-8")
    return root


class PlannerRootTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name).resolve()
        env = {k: v for k, v in os.environ.items() if k != task_paths.PLANNER_ROOT_ENV}
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _no_neighbour(self):
        # `parents[4]` of the module file decides the neighbour; point it at an empty tree.
        fake = self.tmp / "x" / "a" / "b" / "c" / "d" / "task_paths.py"
        return mock.patch.object(task_paths, "__file__", str(fake))

    def test_env_wins(self):
        planner = make_planner(self.tmp / "custom")
        with mock.patch.dict(os.environ, {task_paths.PLANNER_ROOT_ENV: str(planner)}):
            self.assertEqual(task_paths.planner_root(), planner)
            self.assertEqual(task_paths.plan_script(), planner / "scripts" / "plan.py")
            self.assertEqual(task_paths.routing_path(),
                             planner / "configs" / "command-routing.json")

    def test_invalid_env_falls_to_neighbour(self):
        with mock.patch.dict(os.environ, {task_paths.PLANNER_ROOT_ENV: str(self.tmp / "missing")}):
            self.assertEqual(task_paths.planner_root(self.tmp), REPO_ROOT / "packages" / "planner")

    def test_neighbour_of_installation(self):
        self.assertEqual(task_paths.planner_root(self.tmp), REPO_ROOT / "packages" / "planner")

    def test_monorepo_fallback_from_start(self):
        planner = make_planner(self.tmp / "repo" / "packages" / "planner")
        start = self.tmp / "repo" / "plans" / "P1"
        start.mkdir(parents=True)
        with self._no_neighbour():
            self.assertEqual(task_paths.planner_root(start), planner)

    def test_nothing_found_is_planner_unavailable(self):
        with self._no_neighbour(), self.assertRaises(task_paths.PlannerUnavailable) as caught:
            task_paths.planner_root(self.tmp)
        self.assertIn("PLANNER_UNAVAILABLE", str(caught.exception))
        self.assertIn(task_paths.PLANNER_ROOT_ENV, str(caught.exception))

    def test_explicit_monorepo_root_wins_without_fallthrough(self):
        with mock.patch.dict(os.environ, {task_paths.PLANNER_ROOT_ENV: str(make_planner(self.tmp / "e"))}):
            self.assertEqual(task_paths.planner_root(monorepo_root="/no/such/root"),
                             Path("/no/such/root") / "packages" / "planner")

    def test_legacy_exception_name_is_an_alias(self):
        self.assertIs(task_paths.TaskUnavailable, task_paths.PlannerUnavailable)


if __name__ == "__main__":
    unittest.main()
