from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

from support import FIXTURE_PLAN


ARTIFEX = Path(__file__).resolve().parents[1]


class IntegrationTests(unittest.TestCase):
    def invoke(self, *args):
        return subprocess.run(["python3", "-m", "artifex", *args], cwd=ARTIFEX, text=True, capture_output=True,
                              env={"PYTHONPATH": str(ARTIFEX / "lib"), "PATH": "/usr/bin:/bin"}, check=False)

    def test_not_found_is_read_only_and_provider_free(self):
        runs = FIXTURE_PLAN / "runs"
        result = self.invoke("--repo-root", ".", "--plan-dir", str(FIXTURE_PLAN.relative_to(ARTIFEX)),
                             "--runs-root", str(runs.relative_to(ARTIFEX)), "status", "--run-id", "DOES-NOT-EXIST")
        self.assertEqual(3, result.returncode)
        self.assertEqual("RUN_NOT_FOUND", json.loads(result.stdout)["reason"])
        self.assertEqual("", result.stderr)
        self.assertFalse(runs.exists())

    def test_core_remains_provider_free_and_cli_only_exposes_selection(self):
        # The CLI may carry an explicit provider selector, but the authority, dispatch
        # and scheduler core never imports or launches a provider.
        for name in ("dispatch.py", "authority.py", "scheduler.py"):
            source = (ARTIFEX / "lib/artifex" / name).read_text(encoding="utf-8")
            for forbidden in ("providers.", "subprocess", "Popen", "codex", "claude", "input(", "os.environ"):
                self.assertNotIn(forbidden, source, f"{name}: {forbidden}")
        parser = __import__("artifex.cli", fromlist=["build_parser"]).build_parser()
        args = parser.parse_args(["--repo-root", ".", "--plan-dir", "plan", "--runs-root", "runs",
                                  "dispatch", "--run-id", "r", "--admission", "a", "--provider", "codex"])
        self.assertEqual("codex", args.provider)
