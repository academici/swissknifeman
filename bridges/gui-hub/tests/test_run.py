"""run.py: only `doctor` and `sync <cap> [--dry-run]` run; the project is the working folder; anything else exits 2."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BRIDGE = Path(__file__).resolve().parents[1]
FIXTURES = BRIDGE / "tests" / "fixtures"


class TestRun(unittest.TestCase):
    def setUp(self):
        self.home = Path(os.path.realpath(tempfile.mkdtemp()))
        self.addCleanup(shutil.rmtree, self.home, True)
        (self.home / "fleet" / "beta").mkdir(parents=True)
        self.env = {"PATH": os.environ["PATH"], "HOME": str(self.home), "SKM_UMBRELLA": str(FIXTURES / "umbrella-ok")}

    def run_py(self, *argv, cwd=None):
        return subprocess.run([sys.executable, str(BRIDGE / "run.py"), *argv], cwd=str(cwd or self.home / "fleet" / "beta"),
                              env=self.env, capture_output=True, text=True, timeout=60)

    def calls(self):
        log = self.home / "umbrella.log"
        return [json.loads(line)["argv"] for line in log.read_text().splitlines()] if log.exists() else []

    def test_doctor(self):
        result = self.run_py("doctor")
        self.assertEqual((0, "doctor: 3 ok, 1 warn\n"), (result.returncode, result.stdout))
        self.assertEqual([["doctor"]], self.calls())

    def test_sync_with_and_without_dry_run(self):
        result = self.run_py("sync", "mcp")
        self.assertEqual((0, "synced --project beta --only mcp\n"), (result.returncode, result.stdout))
        result = self.run_py("sync", "agent-pack", "--dry-run")
        self.assertEqual("synced --project beta --only agent-pack --dry-run\n", result.stdout)
        self.assertEqual(["hub", "sync", "--project", "beta", "--only", "agent-pack", "--dry-run"], self.calls()[-1])

    def test_refusals_run_nothing(self):
        cases = [("sync", "rm"), ("sync", "mcp", "--force"), ("sync",), ("doctor", "--json"), ("exec", "id"), (),
                 ("sync", "mcp;id")]
        for argv in cases:
            with self.subTest(argv=argv):
                result = self.run_py(*argv)
                self.assertEqual(2, result.returncode, result.stderr)
        self.assertEqual([], [call for call in self.calls() if call[:1] != ["status"]])

    def test_project_not_in_maind(self):
        outside = self.home / "elsewhere"
        outside.mkdir()
        result = self.run_py("sync", "mcp", cwd=outside)
        self.assertEqual(2, result.returncode)
        self.assertIn("PROJECT_NOT_IN_MAIND", result.stderr)
        self.assertEqual([["status", "--all", "--json"]], self.calls())

    def test_hub_failure_is_reported_without_a_trace(self):
        self.env["SKM_UMBRELLA"] = str(FIXTURES / "umbrella-fail")
        result = self.run_py("sync", "mcp")
        self.assertEqual(1, result.returncode)
        self.assertIn("HUB_CLI_FAILED", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
