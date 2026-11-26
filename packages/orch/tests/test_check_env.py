"""A check command tests the project, not the orchestrator the conductor runs from: install roots outside the project are dropped."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from orch.conductor import checks


class CheckEnvTests(unittest.TestCase):
    def test_composer_uses_conductor_timeout_unless_explicitly_configured(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self.assertEqual(checks.check_env(project, {})["COMPOSER_PROCESS_TIMEOUT"], "0")
            self.assertEqual(checks.check_env(project, {"COMPOSER_PROCESS_TIMEOUT": "120"})[
                "COMPOSER_PROCESS_TIMEOUT"], "120")
            self.assertEqual(checks.check_env(project, {}, {"COMPOSER_PROCESS_TIMEOUT": "240"})[
                "COMPOSER_PROCESS_TIMEOUT"], "240")

    def test_roots_outside_the_project_are_dropped_and_roots_inside_are_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            (project / "packages" / "aicore").mkdir(parents=True)
            frozen = Path(tmp) / "frozen" / "packages" / "aicore"
            frozen.mkdir(parents=True)
            env = checks.check_env(project, {"AICORE_ROOT": str(frozen), "SKM_ORCH_ROOT": str(project / "packages" / "orch"),
                                             "PATH": "/usr/bin", "PLANNER_ROOT": ""})
            self.assertNotIn("AICORE_ROOT", env)
            self.assertEqual(env["SKM_ORCH_ROOT"], str(project / "packages" / "orch"))
            self.assertEqual(env["PATH"], "/usr/bin")

    def test_a_running_check_does_not_see_a_frozen_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.txt"
            import os
            old = os.environ.get("AICORE_ROOT")
            os.environ["AICORE_ROOT"] = "/somewhere/else"
            try:
                with out.open("wb") as handle:
                    code = checks._run_command(["python3", "-c", "import os;print(os.environ.get('AICORE_ROOT','absent'))"],
                                               cwd=Path(tmp), out=handle, timeout_s=30, warn_s=0)
            finally:
                os.environ.pop("AICORE_ROOT") if old is None else os.environ.__setitem__("AICORE_ROOT", old)
            self.assertEqual(code, 0)
            self.assertEqual(out.read_text(encoding="utf-8").strip(), "absent")


if __name__ == "__main__":
    unittest.main()
