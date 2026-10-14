"""``orch.py``: the project of a command is ``--project``, ``SKM_PROJECT_ROOT`` or the nearest marker; the run cycle needs one."""
import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from orch import cli


class ProjectOfOrchTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()
        (self.base / "home").mkdir()
        (self.base / "loose").mkdir()
        (self.base / "proj" / ".git").mkdir(parents=True)
        patcher = mock.patch.dict(os.environ, {"HOME": str(self.base / "home"), "SKM_HOME": str(self.base / "skm")})
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("SKM_PROJECT_ROOT", None)
        cwd = Path.cwd()
        os.chdir(self.base / "loose")
        self.addCleanup(os.chdir, cwd)

    def main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main([str(item) for item in argv])
        return code, out.getvalue(), err.getvalue()

    def test_the_run_cycle_needs_a_project_and_names_the_flag(self):
        code, out, err = self.main("source", "brief", "--run", "r1")
        self.assertEqual(code, 1)
        self.assertIn("PROJECT_CONTEXT_REQUIRED", err)
        self.assertIn("--project DIR", err)

    def test_the_flag_names_the_project(self):
        code, out, err = self.main("--project", self.base / "proj", "source", "brief", "--run", "r1")
        self.assertEqual(code, 1)
        self.assertIn("RUN_UNKNOWN", err)

    def test_the_environment_names_the_project(self):
        with mock.patch.dict(os.environ, {"SKM_PROJECT_ROOT": str(self.base / "proj")}):
            code, out, err = self.main("source", "brief", "--run", "r1")
        self.assertIn("RUN_UNKNOWN", err)

    def test_a_command_without_state_works_outside_a_project(self):
        code, out, err = self.main("doctor", "--json")
        self.assertEqual(code, 0, err)


if __name__ == "__main__":
    unittest.main()
