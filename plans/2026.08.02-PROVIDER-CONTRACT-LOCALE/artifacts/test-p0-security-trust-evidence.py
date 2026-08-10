#!/usr/bin/env python3
"""Copied-evidence adversarial tests for the P0.7 producer."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "plans/2026.08.02-PROVIDER-CONTRACT-LOCALE"
SCRIPT = PLAN / "artifacts/p0-security-trust-evidence.py"
FIXTURE = PLAN / "artifacts/P0.7/fixtures/safe-command-results.json"


def run(*args: str) -> int:
    return subprocess.run(["python3", str(SCRIPT), *args], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False).returncode


def main() -> int:
    with tempfile.TemporaryDirectory() as temp:
        copied = Path(temp) / "plan"
        shutil.copytree(PLAN, copied)
        manifest = copied / "artifacts/P0.1/evidence/manifest.json"
        evidence = copied / "artifacts/P0.4/evidence.json"
        verdict = copied / "artifacts/P0.4/verdict.json"
        assert run("capture", "--plan-dir", str(copied), "--manifest", str(manifest), "--fixture", str(FIXTURE), "--output", str(evidence)) == 0
        assert run("check", "--plan-dir", str(copied), "--manifest", str(manifest), "--evidence", str(evidence), "--branch-output", str(verdict)) == 0
        for key, value in (("protected_target_delta", 1), ("action_set", ["containment-review"]), ("provider_trust", {"claude-code": "green", "codex": "red"})):
            candidate = json.loads(evidence.read_text(encoding="utf-8")); candidate[key] = value
            evidence.write_text(json.dumps(candidate), encoding="utf-8")
            assert run("check", "--plan-dir", str(copied), "--manifest", str(manifest), "--evidence", str(evidence), "--branch-output", str(verdict)) != 0
            assert run("capture", "--plan-dir", str(copied), "--manifest", str(manifest), "--fixture", str(FIXTURE), "--output", str(evidence)) == 0
    print("allow")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
