#!/usr/bin/env python3
"""Materialize the bounded static P0.10 requalification fan-in."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


PLAN = Path(__file__).resolve().parent.parent
ROOT = PLAN.parents[1]
OUTPUT = PLAN / "artifacts/P0.10/final-requalification-v1.json"
D67 = "b6b66da4b69b42ffd171034c1ff35f7572d2358106b79471c2b25fb99f1c95b8"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(label: str, *argv: str) -> dict:
    print(f"checking: {label}", file=sys.stderr, flush=True)
    completed = subprocess.run(argv, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    if completed.returncode:
        raise ValueError(f"{label} rejected: {completed.stderr.strip() or completed.stdout.strip()}")
    return {"carrier": label, "status": "green"}


def validate() -> list[dict]:
    plan = str(PLAN)
    rows = [
        run("P0.5 baseline", sys.executable, str(PLAN / "artifacts/p0-provider-fleet-inventory.py"), "--check"),
        run("P0.2 classifier", sys.executable, str(PLAN / "artifacts/p0-provider-fleet-classify.py"), "--check"),
        run("P0.6 recovery", sys.executable, str(PLAN / "artifacts/test-p0-recovery-gates-check.py")),
        run("P0.7 security", sys.executable, str(PLAN / "artifacts/test-p0-security-trust-evidence.py")),
        run("P0.8 provenance", sys.executable, str(PLAN / "artifacts/test-p0-execution-provenance.py")),
        run("P0.9 rebind", sys.executable, str(PLAN / "artifacts/test-p0-classification-rebind.py")),
        run("P0.10 live admit", sys.executable, str(PLAN / "artifacts/p0-security-trust-evidence.py"), "admit", "--plan-dir", plan, "--manifest", str(PLAN / "artifacts/P0.1/evidence/manifest.json"), "--stdout"),
        run("task package suite", "bash", "-c", "cd packages/task && PYTHONPATH=lib:../.. python3 -m unittest discover -s tests -p 'test_*.py'"),
        run("scoped diff", "git", "diff", "--check"),
    ]
    for view in ("status", "decisions"):
        rows.append(run(f"view {view}", sys.executable, "packages/task/scripts/plan-views.py", view, "--plan-dir", plan, "--check"))
    for item in [f"P0.{number}" for number in range(1, 11)]:
        rows.append(run(f"bundle {item}", sys.executable, "packages/task/scripts/plan-views.py", "bundle", "--plan-dir", plan, "--item", item, "--check"))
    return rows


def build() -> dict:
    if sha(PLAN / "root/contracts/provider-recovery-gates-v1.md") != D67:
        raise ValueError("D67 frozen contract drift")
    return {"schema_version": "p0-final-requalification/v1", "contract_sha256": D67,
            "validators": validate(), "external_target_delta": 0}


def write(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build(), ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def check(path: Path) -> None:
    if not path.is_file() or json.loads(path.read_text(encoding="utf-8")) != build():
        raise ValueError("final requalification carrier is stale")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("write", "check"))
    parser.add_argument("--plan-dir", type=Path, default=PLAN)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    if args.plan_dir.resolve() != PLAN:
        raise SystemExit("rejected: unexpected plan directory")
    try:
        (write if args.action == "write" else check)(args.output)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"rejected: {exc}", file=sys.stderr)
        return 1
    print("allow")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
