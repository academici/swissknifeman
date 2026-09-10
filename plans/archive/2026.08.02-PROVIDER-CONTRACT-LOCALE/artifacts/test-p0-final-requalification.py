#!/usr/bin/env python3
"""Regression test for the P0.10 static requalification carrier."""
from __future__ import annotations

import json
import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "plans/2026.08.02-PROVIDER-CONTRACT-LOCALE"
SCRIPT = PLAN / "artifacts/p0-final-requalification.py"
spec = importlib.util.spec_from_file_location("p0_final_requalification", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


def main() -> int:
    with tempfile.TemporaryDirectory() as temp:
        output = Path(temp) / "fan-in.json"
        original_validate = module.validate
        module.validate = lambda: [{"carrier": "fixture", "status": "green"}]
        module.write(output)
        module.check(output)
        module.validate = original_validate
        value = json.loads(output.read_text(encoding="utf-8"))
        value["external_target_delta"] = 1
        output.write_text(json.dumps(value), encoding="utf-8")
        try:
            module.validate = lambda: [{"carrier": "fixture", "status": "green"}]
            module.check(output)
        except ValueError:
            pass
        else:
            raise AssertionError("mutated fan-in was accepted")
        finally:
            module.validate = original_validate
        evidence = Path(temp) / "old-observation.json"
        stored = json.loads((PLAN / "artifacts/P0.4/fresh-security-trust-evidence.json").read_text(encoding="utf-8"))
        stored["observed_at"] = "2000-01-01T00:00:00Z"
        evidence.write_text(json.dumps(stored), encoding="utf-8")
        security = PLAN / "artifacts/p0-security-trust-evidence.py"
        manifest = PLAN / "artifacts/P0.1/evidence/manifest.json"
        branch = Path(temp) / "integrity.json"
        assert subprocess.run([sys.executable, str(security), "check", "--plan-dir", str(PLAN), "--manifest", str(manifest), "--evidence", str(evidence), "--branch-output", str(branch)], cwd=ROOT, check=False).returncode == 0
        assert json.loads(branch.read_text(encoding="utf-8"))["result"] == "integrity-only"
        unsafe = Path(temp) / "unsafe.json"
        unsafe.write_text(json.dumps({"commands": [{"id": "harness-provider-audit", "exit": 0, "class": "green"}, {"id": "maind-strict-health", "exit": None, "class": "unavailable"}, {"id": "codex-doctor", "exit": 0, "class": "green"}]}), encoding="utf-8")
        assert subprocess.run([sys.executable, str(security), "admit", "--plan-dir", str(PLAN), "--manifest", str(manifest), "--fixture", str(unsafe), "--stdout"], cwd=ROOT, check=False).returncode != 0
    print("p0 final requalification: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
