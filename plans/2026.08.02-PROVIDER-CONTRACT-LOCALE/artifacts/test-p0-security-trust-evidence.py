#!/usr/bin/env python3
"""Copied-evidence adversarial tests for the P0.7 producer."""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "plans/2026.08.02-PROVIDER-CONTRACT-LOCALE"
SCRIPT = PLAN / "artifacts/p0-security-trust-evidence.py"
FIXTURE = PLAN / "artifacts/P0.7/fixtures/safe-command-results.json"

spec = importlib.util.spec_from_file_location("p0_security_trust_evidence", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def run(*args: str) -> int:
    return subprocess.run(["python3", str(SCRIPT), *args], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False).returncode


def main() -> int:
    completed = mock.Mock(returncode=0)
    with mock.patch.object(module.subprocess, "run", return_value=completed) as run_command:
        assert module.command("probe", ["probe"], cwd=ROOT)["class"] == "green"
        assert run_command.call_args.kwargs["timeout"] == module.COMMAND_TIMEOUT_SECONDS == 60

    with tempfile.TemporaryDirectory() as temp:
        copied = Path(temp) / "plan"
        shutil.copytree(PLAN, copied)
        manifest = copied / "artifacts/P0.1/evidence/manifest.json"
        evidence = copied / "artifacts/P0.4/evidence.json"
        verdict = copied / "artifacts/P0.4/verdict.json"
        assert run("capture", "--plan-dir", str(copied), "--manifest", str(manifest), "--fixture", str(FIXTURE), "--output", str(evidence)) == 0
        assert run("check", "--plan-dir", str(copied), "--manifest", str(manifest), "--evidence", str(evidence), "--branch-output", str(verdict)) == 0
        unsafe_fixture = Path(temp) / "unsafe-command-results.json"
        unsafe = json.loads(FIXTURE.read_text(encoding="utf-8"))
        unsafe["commands"][-1].update({"class": "unavailable", "exit": None})
        unsafe_fixture.write_text(json.dumps(unsafe), encoding="utf-8")
        assert run("capture", "--plan-dir", str(copied), "--manifest", str(manifest), "--fixture", str(unsafe_fixture), "--output", str(evidence)) != 0
        assert json.loads(evidence.read_text(encoding="utf-8"))["action_set"] == ["containment-review"]
        assert run("capture", "--plan-dir", str(copied), "--manifest", str(manifest), "--fixture", str(FIXTURE), "--output", str(evidence)) == 0
        for key, value in (("protected_target_delta", 1), ("action_set", ["containment-review"]), ("provider_trust", {"claude-code": "green", "codex": "red"})):
            candidate = json.loads(evidence.read_text(encoding="utf-8")); candidate[key] = value
            evidence.write_text(json.dumps(candidate), encoding="utf-8")
            assert run("check", "--plan-dir", str(copied), "--manifest", str(manifest), "--evidence", str(evidence), "--branch-output", str(verdict)) != 0
            assert run("capture", "--plan-dir", str(copied), "--manifest", str(manifest), "--fixture", str(FIXTURE), "--output", str(evidence)) == 0
    print("allow")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
