#!/usr/bin/env python3
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
from task.task_contract import bundle_lint

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-root", required=True)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()
    root = Path(args.bundle_root).resolve()
    manifest_path = Path(args.manifest).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = {entry["path"]: entry for entry in manifest["files"]}
    actual = {path.name for path in root.iterdir() if path.is_file() and path.name not in {"manifest.json", "verify.py"}}
    if actual != set(expected):
        print("P63_BUNDLE_MEMBER_MISMATCH", file=sys.stderr)
        return 1
    for name, entry in expected.items():
        data = (root / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != entry["sha256"] or len(data) != entry["bytes"]:
            print("P63_BUNDLE_DIGEST_MISMATCH:" + name, file=sys.stderr)
            return 1
    reason = bundle_lint(
        root, manifest_path=manifest_path, verifier_path=root / "verify.py",
        declared_privacy=manifest["privacy"],
    )
    if reason:
        print(reason, file=sys.stderr)
        return 1
    verdict = json.loads((root / "fleet-health-verdict.json").read_text(encoding="utf-8"))
    if verdict.get("aggregate") != "non-green" or verdict.get("semantic_match") is not True:
        print("P63_VERDICT_INVALID", file=sys.stderr)
        return 1
    membership = json.loads((root / "project-membership.json").read_text(encoding="utf-8"))
    rows = membership.get("project_memberships")
    if not isinstance(rows, list) or len(rows) != len({row.get("project_id") for row in rows if isinstance(row, dict)}):
        print("P63_MEMBERSHIP_INVALID", file=sys.stderr)
        return 1
    optional_ids = {row.get("project_id") for row in rows if row.get("membership") == "optional"}
    if len(optional_ids) != 1 or not set(verdict.get("optional_non_green", [])).issubset(optional_ids):
        print("P63_OPTIONAL_MEMBERSHIP_INVALID", file=sys.stderr)
        return 1
    if any(blocker.rsplit(":", 1)[-1] in optional_ids
           for blocker in verdict.get("release_blockers", []) if ":" in blocker):
        print("P63_OPTIONAL_RELEASE_MASKING", file=sys.stderr)
        return 1
    print("P6.3 evidence bundle: allow")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
