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


def validate_provenance(root: Path, path: Path) -> None:
    validator = path.with_name("validate-provenance-reconciliation.py")
    run = subprocess.run([
        sys.executable, str(validator), "--record", str(path),
        "--plan-dir", str(root / "plans" / PLAN_ID), "--self-test",
    ], cwd=root, text=True, capture_output=True)
    if run.returncode:
        raise ValueError(run.stderr.strip() or "P4 provenance validation failed")


def git(root: Path, *argv: str) -> str:
    result = subprocess.run(["git", *argv], cwd=root, text=True, capture_output=True, check=False)
    if result.returncode:
        raise ValueError(result.stderr.strip() or "git command failed")
    return result.stdout.strip()


def resolve_g2_anchor(root: Path, manifest_path: Path, historical_commit: str | None) -> str:
    """D129/D133 repair (2): the frozen P4 snapshot is resolved at run time as the
    newest commit that changed the manifest itself, never hard-coded."""
    frozen_commit = historical_commit or git(root, "log", "-1", "--format=%H", "--", manifest_path.relative_to(root).as_posix())
    if not frozen_commit:
        raise ValueError("frozen P4 assurance anchor unresolved")
    return frozen_commit


def validate_g2_frozen(root: Path, frozen_commit: str, package_rows: list[dict]) -> None:
    """The recorded g2.package_files must be byte-equal to the package AT the
    P4-owning historical snapshot, proven through Git blobs, not through a live
    re-scan of the current tree (the package legitimately advanced to G2B)."""
    for row in package_rows:
        blob = subprocess.run(["git", "show", f"{frozen_commit}:{row['path']}"], cwd=root, capture_output=True, check=False)
        if blob.returncode or hashlib.sha256(blob.stdout).hexdigest() != row["sha256"]:
            raise ValueError(f"historical G2 package blob mismatch: {row['path']}")


def validate_g2b_live(root: Path, generation_path: Path) -> None:
    """The live side: the current package equals the sole G2B digest of the
    business successor generation manifest — same helper shape as
    `validate-package-promotion.py`'s `validate_package_generation`."""
    generation = load(generation_path)
    live_rows = generation.get("successor", {}).get("package_files")
    if not isinstance(live_rows, list) or not live_rows:
        raise ValueError("G2B generation manifest missing package rows")
    for row in live_rows:
        path = root / row["path"]
        if not path.is_file() or digest(path) != row["sha256"]:
            raise ValueError(f"current package differs from G2B: {row['path']}")


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
    if load(named["requalification"]).get("schema_version") != "artifex-p4-authority-requalification-v1":
        raise ValueError("P4.7/P4.8 successor evidence")
    validate_provenance(root, named["provenance"])
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
    parser.add_argument("--generation", type=Path, help="G2B generation manifest; defaults to the frozen P5 one")
    parser.add_argument("--historical-commit")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[4]
    args.admission_index = args.admission_index
    value = expected(root, args)
    if args.write:
        args.manifest.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("P4 assurance manifest: written")
        return 0

    loaded = load(args.manifest)
    non_g2_expected = {key: item for key, item in value.items() if key != "g2"}
    non_g2_loaded = {key: item for key, item in loaded.items() if key != "g2"}
    if non_g2_loaded != non_g2_expected:
        raise ValueError("G2 manifest drift")

    # D133 repair (2), two-sided: the frozen g2.package_files is proven against the
    # P4-owning historical snapshot through Git, never against the current tree
    # (which legitimately advanced past G2 into G2B); the live side separately
    # asserts the current package against the sole G2B digest.
    g2 = loaded.get("g2", {})
    package_rows = g2.get("package_files")
    if not isinstance(package_rows, list) or not package_rows:
        raise ValueError("G2 manifest drift")
    frozen_commit = resolve_g2_anchor(root, args.manifest.resolve(), args.historical_commit)
    head = git(root, "rev-parse", "HEAD")
    if frozen_commit == "HEAD" or git(root, "rev-parse", frozen_commit) == head:
        raise ValueError("historical G2 anchor cannot be the current tree")
    validate_g2_frozen(root, frozen_commit, package_rows)
    generation_path = args.generation or (root / "plans" / PLAN_ID / "artifacts" / "P5" / "business-successor-generation-v1.json")
    validate_g2b_live(root, generation_path)
    print("P4 assurance validator: OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(f"P4 assurance validator: FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
