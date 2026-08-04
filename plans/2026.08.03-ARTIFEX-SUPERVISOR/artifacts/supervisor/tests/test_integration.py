from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
PLAN = ROOT / "plans/2026.08.03-ARTIFEX-SUPERVISOR"
ARTIFEX = PLAN / "artifacts/supervisor"


class IntegrationTests(unittest.TestCase):
    def invoke(self, *args):
        return subprocess.run(["python3", "-m", "artifex", *args], cwd=ROOT, text=True, capture_output=True,
                              env={"PYTHONPATH": str(ARTIFEX), "PATH": "/usr/bin:/bin"}, check=False)

    def test_not_found_is_read_only_and_provider_free(self):
        with tempfile.TemporaryDirectory() as temp:
            run_root = Path(temp) / "runs"
            result = self.invoke("--repo-root", ".", "--plan-dir", str(PLAN.relative_to(ROOT)), "--runs-root", str(run_root.relative_to(Path(temp))) if False else "plans/2026.08.03-ARTIFEX-SUPERVISOR/runs", "status", "--run-id", "DOES-NOT-EXIST")
        self.assertEqual(3, result.returncode)
        self.assertEqual("RUN_NOT_FOUND", json.loads(result.stdout)["reason"])
        self.assertEqual("", result.stderr)

    def test_source_contains_no_provider_launcher_or_interactive_input(self):
        for name in ("dispatch.py", "authority.py", "scheduler.py", "cli.py"):
            source = (ARTIFEX / "artifex" / name).read_text(encoding="utf-8")
            for forbidden in ("providers.", "subprocess", "Popen", "codex", "claude", "input(", "os.environ"):
                self.assertNotIn(forbidden, source, f"{name}: {forbidden}")
