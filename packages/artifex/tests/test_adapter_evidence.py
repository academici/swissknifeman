from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "plans" / ("2026" + ".08.03-ARTIFEX-SUPERVISOR")
VALIDATOR = PLAN / "artifacts/P3/validate-adapters.py"


class AdapterEvidenceTests(unittest.TestCase):
    def command(self, manifest: Path, smoke: Path) -> list[str]:
        return ["python3", str(VALIDATOR), "--root", str(PLAN / "artifacts" / "supervisor"), "--manifest", str(manifest),
                "--prototype", str(PLAN / "artifacts/P2/prototype-manifest-v1.json"), "--contracts", str(PLAN / "artifacts/P1/contract-manifest-v1.json"),
                "--admission-index", str(PLAN / "artifacts/P2/p3-smoke-admission-index-v1.json"), "--grant-index", str(PLAN / "artifacts/P1/p3-smoke-dispatch-grants-v1.json"),
                "--tasks", str(PLAN / "artifacts/P1/p3-smoke-task-set-v1.json"), "--parity", str(PLAN / "artifacts/P3/provider-parity-v1.json"), "--smoke-dir", str(smoke)]

    def test_current_generation_and_real_rows_are_required(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); manifest = root / "manifest.json"; smoke = root / "smoke"
            shutil.copytree(PLAN / "artifacts/P3/provider-smoke", smoke)
            generate = [*self.command(manifest, smoke), "--write"]
            self.assertEqual(0, subprocess.run(generate, text=True, capture_output=True).returncode)
            self.assertEqual(0, subprocess.run(self.command(manifest, smoke), text=True, capture_output=True).returncode)
            row = json.loads((smoke / "codex.json").read_text()); row["evidence_class"] = "synthetic"
            (smoke / "codex.json").write_text(json.dumps(row), encoding="utf-8")
            self.assertNotEqual(0, subprocess.run(self.command(manifest, smoke), text=True, capture_output=True).returncode)

    def test_unknown_argument_and_baseline_mutation_refuse(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); manifest = root / "manifest.json"; smoke = root / "smoke"
            shutil.copytree(PLAN / "artifacts/P3/provider-smoke", smoke)
            subprocess.run([*self.command(manifest, smoke), "--write"], check=True, text=True, capture_output=True)
            self.assertNotEqual(0, subprocess.run([*self.command(manifest, smoke), "--unknown"], text=True, capture_output=True).returncode)
            value = json.loads(manifest.read_text()); value["base_prototype"]["git_commit"] = "0" * 40
            manifest.write_text(json.dumps(value), encoding="utf-8")
            self.assertNotEqual(0, subprocess.run(self.command(manifest, smoke), text=True, capture_output=True).returncode)


if __name__ == "__main__":
    unittest.main()
