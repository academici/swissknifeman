#!/usr/bin/env python3
"""Regression entry point for the P0.9 digest-only rebind proof."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "plans/2026.08.02-PROVIDER-CONTRACT-LOCALE"
HELPER = PLAN / "artifacts/p0-classification-rebind.py"
OUTPUT = PLAN / "artifacts/P0.9/classification-rebind-v1.json"


def command(*args: str) -> None:
    completed = subprocess.run([sys.executable, str(HELPER), *args], cwd=ROOT, check=False)
    if completed.returncode:
        raise SystemExit(completed.returncode)


def main() -> int:
    command("self-test")
    command("check", "--plan-dir", str(PLAN), "--historical-commit", "1e552dd4", "--output", str(OUTPUT))
    print("p0 classification rebind: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
