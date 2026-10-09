"""Discovery order of the planner package: env → neighbour → monorepo ancestor → PLANNER_UNAVAILABLE."""
from __future__ import annotations

from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest import mock

BRIDGE = Path(__file__).resolve().parents[1]
if str(BRIDGE) not in sys.path:
    sys.path.insert(0, str(BRIDGE))

import discovery  # noqa: E402


def make_planner(root: Path) -> Path:
    (root / "scripts").mkdir(parents=True)
    (root / "scripts" / "plan.py").write_text("", encoding="utf-8")
    (root / "configs").mkdir()
    return root


class PlannerRoot(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name).resolve()
        self.addCleanup(self._tmp.cleanup)
        env = {k: v for k, v in os.environ.items() if k != discovery.PLANNER_ROOT_ENV}
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def no_neighbour(self):
        return mock.patch.object(discovery, "orch_root", return_value=self.tmp / "nowhere" / "orch")

    def test_env_wins(self):
        planner = make_planner(self.tmp / "custom")
        with mock.patch.dict(os.environ, {discovery.PLANNER_ROOT_ENV: str(planner)}):
            self.assertEqual(discovery.planner_root(), planner)
            self.assertEqual(discovery.plan_script(), planner / "scripts" / "plan.py")
            self.assertEqual(discovery.routing_path(), planner / "configs" / "command-routing.json")

    def test_invalid_env_falls_to_neighbour(self):
        orch = self.tmp / "packages" / "orch"
        orch.mkdir(parents=True)
        neighbour = make_planner(self.tmp / "packages" / "planner")
        with mock.patch.dict(os.environ, {discovery.PLANNER_ROOT_ENV: str(self.tmp / "missing")}), \
                mock.patch.object(discovery, "orch_root", return_value=orch):
            self.assertEqual(discovery.planner_root(), neighbour)

    def test_neighbour_of_installation(self):
        orch = self.tmp / "pkgs" / "orch"
        orch.mkdir(parents=True)
        neighbour = make_planner(self.tmp / "pkgs" / "planner")
        with mock.patch.object(discovery, "orch_root", return_value=orch):
            self.assertEqual(discovery.planner_root(self.tmp), neighbour)

    def test_monorepo_ancestor_of_start(self):
        planner = make_planner(self.tmp / "repo" / "packages" / "planner")
        start = self.tmp / "repo" / "plans" / "P1"
        start.mkdir(parents=True)
        with self.no_neighbour():
            self.assertEqual(discovery.planner_root(start), planner)

    def test_nothing_found_is_planner_unavailable(self):
        with self.no_neighbour(), self.assertRaises(discovery.PlannerUnavailable) as caught:
            discovery.planner_root(self.tmp)
        self.assertIn("PLANNER_UNAVAILABLE", str(caught.exception))
        self.assertIn(discovery.PLANNER_ROOT_ENV, str(caught.exception))

    def test_orch_root_is_the_orch_package(self):
        self.assertTrue((discovery.orch_root() / "bridges" / "task" / "bridge.json").is_file())


if __name__ == "__main__":
    unittest.main()
