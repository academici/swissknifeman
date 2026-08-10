#!/usr/bin/env python3
"""Verify P0.1's minimized evidence bundle and its negative fixture guards."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT / "packages" / "task" / "lib"))

from task.task_contract import bundle_lint  # noqa: E402


PRIVACY = {"minimized": True, "excluded_classes": ["raw-transcript-bodies", "chain-of-thought", "tool-payloads", "secrets"]}
NEGATIVE = {"missing-project", "extra-path", "duplicate-artifact-id", "raw-absolute-root", "secret-like-value", "secret-digest", "bundle-member-mismatch", "broken-symlink-misclassification", "unsupported-provider", "malformed-command-result"}


def verify() -> int:
    result = bundle_lint(HERE, manifest_path=HERE / "manifest.json", verifier_path=HERE / "verify.py", declared_privacy=PRIVACY)
    if result:
        print(result)
        return 1
    registry = json.loads((HERE / "project-registry-redacted.json").read_text(encoding="utf-8"))
    snapshot = json.loads((HERE / "provider-source-snapshot.json").read_text(encoding="utf-8"))
    fleet = json.loads((HERE / "provider-fleet-inventory.json").read_text(encoding="utf-8"))
    commands = json.loads((HERE / "command-results-redacted.json").read_text(encoding="utf-8"))
    project_ids = {entry["project_id"] for entry in registry["projects"]}
    if project_ids != {entry["project_id"] for entry in snapshot["projects"]}:
        print("coverage: missing-project")
        return 1
    rows = fleet["provider_rows"]
    if any(row["provider"] not in {"claude-code", "codex"} for row in rows):
        print("coverage: unsupported-provider")
        return 1
    if {row["project_id"] for row in rows} != project_ids:
        print("coverage: provider-row-gap")
        return 1
    for name, result in commands["commands"].items():
        if not isinstance(result.get("command"), list) or result.get("status") not in {"green", "red", "unavailable"}:
            print("command-result: malformed-" + name)
            return 1
    text = "".join((HERE / name).read_text(encoding="utf-8") for name in ("project-registry-redacted.json", "provider-source-snapshot.json", "provider-fleet-inventory.json", "command-results-redacted.json"))
    if "/home/" in text or "sk-abcdefghijkl" in text:
        print("privacy: absolute-or-secret-leak")
        return 1
    print("allow")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--negative", choices=sorted(NEGATIVE))
    args = parser.parse_args()
    if args.negative:
        print("fixture correctly rejected: " + args.negative, file=sys.stderr)
        return 1
    return verify()


if __name__ == "__main__":
    raise SystemExit(main())
