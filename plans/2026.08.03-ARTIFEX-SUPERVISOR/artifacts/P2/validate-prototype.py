#!/usr/bin/env python3
"""Generate or validate the closed P2 Artifex candidate manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


FILES = (
    "artifex/__init__.py", "artifex/__main__.py", "artifex/compiler.py", "artifex/store.py",
    "artifex/authority.py", "artifex/scheduler.py", "artifex/cli.py", "tests/__init__.py",
    "tests/support.py", "tests/test_compiler.py", "tests/test_store.py", "tests/test_authority.py",
    "tests/test_scheduler.py", "tests/test_cli.py", "tests/test_integration.py", "README.md",
)
FORBIDDEN = ("codex", "claude", "api_key", "authorization")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expected(root: Path, contracts: Path) -> dict:
    missing = [name for name in FILES if not (root / name).is_file()]
    if missing:
        raise ValueError("missing files: " + ", ".join(missing))
    contract = json.loads(contracts.read_text(encoding="utf-8"))
    return {"schema_version": "artifex-prototype-manifest-v1", "manifest_version": "1.0.0",
            "files": [{"path": name, "sha256": sha(root / name)} for name in FILES],
            "contracts": [{"id": row["id"], "sha256": row["sha256"], "version": row["version"]} for row in contract["contracts"]]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path); parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--contracts", required=True, type=Path); parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    value = expected(args.root, args.contracts)
    if args.write:
        args.manifest.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("prototype manifest: written")
        return 0
    if json.loads(args.manifest.read_text(encoding="utf-8")) != value:
        raise ValueError("manifest hash or contract drift")
    for path in (args.root / name for name in FILES if name.startswith("artifex/")):
        if path.name != "__init__.py":
            text = path.read_text(encoding="utf-8").lower()
            if any(token in text for token in FORBIDDEN) or re.search(r"(?<![a-z0-9_])input\(", text):
                raise ValueError(f"forbidden provider/privacy class: {path}")
    env = {"PYTHONPATH": str(args.root), "PATH": "/usr/bin:/bin"}
    tests = subprocess.run(["python3", "-m", "unittest", "discover", "-s", str(args.root / "tests"), "-p", "test_*.py"], env=env, text=True, capture_output=True, check=False)
    if tests.returncode:
        raise ValueError("test suite failed: " + tests.stdout + tests.stderr)
    p1 = args.contracts.parent / "validate-contract-set.py"
    check = subprocess.run(["python3", str(p1), "--manifest", str(args.contracts), "--contracts", str(args.contracts.parent.parent.parent / "root/contracts")], text=True, capture_output=True, check=False)
    if check.returncode:
        raise ValueError("P1 contract validator failed: " + check.stdout + check.stderr)
    print("prototype validator: OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"prototype validator: ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
