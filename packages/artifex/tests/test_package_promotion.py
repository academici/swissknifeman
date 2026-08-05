from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "plans" / ("2026" + ".08.03-ARTIFEX-SUPERVISOR")
VALIDATOR = PLAN / "artifacts/P3/validate-package-promotion.py"
MANIFEST = PLAN / "artifacts/P3/package-promotion-manifest-v1.json"
PROTOTYPE = PLAN / "artifacts/P3/adapter-manifest-v1.json"
PACKAGE = ROOT / "packages/artifex"


class PackagePromotionTests(unittest.TestCase):
    def command(self, *extra: str) -> list[str]:
        return ["python3", str(VALIDATOR), "--manifest", str(MANIFEST), "--prototype", str(PROTOTYPE),
                "--package", str(PACKAGE), *extra]

    def test_current_generation_is_exact(self):
        result = subprocess.run(self.command(), cwd=ROOT, text=True, capture_output=True, check=False)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_historical_mode_refuses_the_current_tree_alias(self):
        result = subprocess.run(self.command("--historical-commit", "HEAD"), cwd=ROOT, text=True,
                                capture_output=True, check=False)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("historical baseline cannot be the current tree", result.stderr)
