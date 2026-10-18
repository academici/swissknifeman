"""Project-bound invocation: the launcher fixes the plans root and no user-facing surface names a package path."""
import contextlib
import io
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from planner.plan import cli, store
from planner.plan.model import PlanError

PLANNER = Path(__file__).resolve().parents[1]
# A user, a command or a provider artifact never names a package script or retargets the project.
FORBIDDEN = re.compile(r"<Planner package root>|<Task package root>|scripts/plan\.py|scripts/conduct\.py"
                       r"|packages/[A-Za-z0-9_*-]+/scripts/|--project\b|--plans-root\b")
SURFACES = ("commands", "aliases", "adapters", "skills", ".claude-plugin", ".codex-plugin")


def launcher(root: Path, pid=None) -> dict:
    return {"SKM_LAUNCHER_ACTIVE": "1", "SKM_LAUNCHER_PROJECT_ROOT": str(root),
            "SKM_LAUNCHER_PID": str(os.getpid() if pid is None else pid)}


class LauncherPlansRootTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve() / "proj"
        (self.root / "plans").mkdir(parents=True)
        self.other = Path(self._tmp.name).resolve() / "other"
        (self.other / "plans").mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def test_launcher_root_gives_project_plans_without_a_search(self):
        with mock.patch.dict(os.environ, launcher(self.root)):
            self.assertEqual(store.find_plans_root(), self.root / "plans")
            self.assertEqual(store.find_plans_root(self.other), self.other / "plans")  # an explicit start still searches

    def test_inherited_launcher_variables_are_ignored(self):
        with mock.patch.dict(os.environ, launcher(self.root, pid=os.getpid() + 1)):
            self.assertIsNone(store.launcher_project_root())

    def test_override_outside_the_project_is_refused(self):
        with mock.patch.dict(os.environ, launcher(self.root)):
            store.require_project_plans(self.root / "plans")
            store.require_project_plans(self.root / "plans" / "archive")
            for bad in (self.other / "plans", self.root, self.root / "plans-other"):
                with self.subTest(bad=bad), self.assertRaises(PlanError) as caught:
                    store.require_project_plans(bad)
                self.assertEqual(caught.exception.code, "PROJECT_PATH_OVERRIDE_FORBIDDEN")

    def test_cli_refuses_a_foreign_plans_root(self):
        err = io.StringIO()
        with mock.patch.dict(os.environ, launcher(self.root)), contextlib.redirect_stderr(err), \
                contextlib.redirect_stdout(io.StringIO()):
            code = cli.main(["next", "PLAN1", "--plans-root", str(self.other / "plans")])
        self.assertEqual(code, 1)
        self.assertIn("PROJECT_PATH_OVERRIDE_FORBIDDEN", err.getvalue())

    def test_without_launcher_nothing_is_checked(self):
        with mock.patch.dict(os.environ, {"SKM_LAUNCHER_ACTIVE": ""}):
            store.require_project_plans(self.other / "plans")


class LauncherWorkspaceTests(unittest.TestCase):
    """A launcher project whose marker moved the plans to the workspace: that folder is the plans root, the old
    ``<project>/plans`` and the folders of other projects stay refused."""

    PID = "billium"

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name).resolve()
        self.root = base / "proj"
        (self.root / "plans").mkdir(parents=True)
        (self.root / ".swissknifeman").mkdir()
        (self.root / ".swissknifeman" / "project.json").write_text(json.dumps({
            "$schema": "urn:swissknifeman:aicore:project-marker:v1", "workspace": "axioma", "project_id": self.PID,
            "plans_store": "workspace"}), encoding="utf-8")
        self.ws = base / "wss" / "axioma"
        self.plans = self.ws / "projects" / self.PID / "plans"
        self.other = self.ws / "projects" / "commerz" / "plans"
        for folder in (self.plans, self.other):
            folder.mkdir(parents=True)
        env = {k: v for k, v in os.environ.items() if not k.startswith(("SKM_", "XDG_"))}
        env.update(HOME=str(base / "home"), SKM_HOME=str(base / "home"), SKM_WORKSPACES_ROOT=str(self.ws.parent), **launcher(self.root))
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_workspace_folder_is_the_plans_root(self):
        self.assertEqual(store.find_plans_root(), self.plans)
        store.require_project_plans(self.plans)
        store.require_project_plans(self.plans / "archive")

    def test_foreign_and_old_folders_are_still_refused(self):
        for bad in (self.root / "plans", self.other, self.ws / "projects", self.plans.parent):
            with self.subTest(bad=bad), self.assertRaises(PlanError) as caught:
                store.require_project_plans(bad)
            self.assertEqual(caught.exception.code, "PROJECT_PATH_OVERRIDE_FORBIDDEN")

    def test_cli_refuses_the_old_plans_folder_and_foreign_project(self):
        for bad in (self.root / "plans", self.other):
            err = io.StringIO()
            with self.subTest(bad=bad), contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                code = cli.main(["next", "PLAN1", "--plans-root", str(bad)])
            self.assertEqual(code, 1)
            self.assertIn("PROJECT_PATH_OVERRIDE_FORBIDDEN", err.getvalue())

    def test_a_missing_workspace_folder_is_reported_not_guessed(self):
        self.plans.rmdir()
        with self.assertRaises(PlanError) as caught:
            store.find_plans_root()
        self.assertEqual(caught.exception.code, "WORKSPACE_PROJECT_MISSING")


class NoExternalPathsTests(unittest.TestCase):
    def test_user_facing_surfaces_name_no_package_path(self):
        found = []
        for surface in SURFACES:
            for path in sorted((PLANNER / surface).rglob("*")):
                if path.is_file() and path.suffix in (".md", ".json", ".yaml", ".toml"):
                    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                        if FORBIDDEN.search(line):
                            found.append(f"{path.relative_to(PLANNER)}:{number}: {line.strip()[:120]}")
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
