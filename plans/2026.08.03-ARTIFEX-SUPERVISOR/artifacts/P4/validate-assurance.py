#!/usr/bin/env python3
"""Independent P4 G2 assurance manifest writer and validator."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


PLAN_ID = "2026.08.03-ARTIFEX-SUPERVISOR"
P3_ITEM_COMMIT = "367e477a"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"object required: {path}")
    return value


def package_files(root: Path) -> list[dict]:
    package = root / "packages/artifex"
    paths = [path for path in package.rglob("*") if path.is_file() and path.suffix in {".py", ".sh", ""}]
    paths = [path for path in paths if path.name == "README.md" or "bin" in path.parts or "lib" in path.parts or "tests" in path.parts or "scripts" in path.parts]
    return [{"path": path.relative_to(root).as_posix(), "sha256": digest(path)} for path in sorted(paths)]


def expected(root: Path, args: argparse.Namespace) -> dict:
    named = {name: Path(getattr(args, name)).resolve() for name in ("faults", "recovery", "worktrees", "hooks", "security", "attention", "contracts", "admission_index", "prototype", "adapters", "provenance", "requalification")}
    faults, recovery, worktrees, hooks, security, attention = (load(named[name]) for name in ("faults", "recovery", "worktrees", "hooks", "security", "attention"))
    if (faults.get("schema_version") != "artifex-fault-matrix-v1" or len(faults.get("rows", [])) != 16
            or recovery.get("schema_version") != "artifex-recovery-results-v1" or len(recovery.get("results", [])) != 16
            or any(row.get("unknown_rerun") is not False for row in recovery["results"])
            or worktrees.get("schema_version") != "artifex-worktree-results-v1" or len(worktrees.get("results", [])) != 7
            or hooks.get("post_repair", {}).get("status") != "green" or hooks.get("post_repair", {}).get("actions") != []
            or security.get("result") != "green" or attention.get("schema_version") != "artifex-attention-cases-v1"
            or [row.get("id") for row in attention.get("cases", [])] != ["dedup-resume", "routine-dependency-order", "owner-resolution", "immediate-security", "unknown-provider-usage", "packet-cap"]):
        raise ValueError("P4 evidence is incomplete")
    if len(load(named["contracts"]).get("contracts", [])) != 6 or len(load(named["admission_index"]).get("admissions", [])) != 2:
        raise ValueError("frozen contract/admission evidence")
    if (load(named["provenance"]).get("schema_version") != "artifex-p4-provenance-reconciliation-v1"
            or load(named["requalification"]).get("schema_version") != "artifex-p4-authority-requalification-v1"):
        raise ValueError("P4.7/P4.8 successor evidence")
    if load(named["prototype"]).get("schema_version") != "artifex-prototype-manifest-v1" or load(named["adapters"]).get("schema_version") != "artifex-adapter-manifest-v1":
        raise ValueError("prototype/adapter evidence")
    g1 = root / "plans" / PLAN_ID / "artifacts/P3/package-promotion-manifest-v1.json"
    commit = subprocess.run(["git", "rev-parse", "--verify", f"{P3_ITEM_COMMIT}^{{commit}}"], cwd=root, capture_output=True, text=True).stdout.strip()
    if not commit.startswith(P3_ITEM_COMMIT):
        raise ValueError("P3.8 historical commit unavailable")
    return {"schema_version": "artifex-p4-assurance-manifest-v1", "readiness": "green",
            "g1": {"path": str(g1.relative_to(root)), "sha256": digest(g1), "p3_item_commit": P3_ITEM_COMMIT},
            "evidence": {name: {"path": str(path.relative_to(root)), "sha256": digest(path)} for name, path in named.items()},
            "g2": {"package_files": package_files(root)}}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    for name in ("faults", "recovery", "worktrees", "hooks", "security", "attention", "contracts", "admission-index", "prototype", "adapters", "provenance", "requalification"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[4]
    args.admission_index = args.admission_index
    value = expected(root, args)
    if args.write:
        args.manifest.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("P4 assurance manifest: written")
    elif load(args.manifest) != value:
        raise ValueError("G2 manifest drift")
    else:
        print("P4 assurance validator: OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(f"P4 assurance validator: FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
