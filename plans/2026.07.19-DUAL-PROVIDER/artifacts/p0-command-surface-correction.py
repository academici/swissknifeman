#!/usr/bin/env python3
"""Verify sealed P0.5 command-surface evidence from git objects."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

PLAN_ID = "2026.07.19-DUAL-PROVIDER"
ANCHOR_REL = f"plans/{PLAN_ID}/artifacts/p0-evidence-anchors.json"


def root() -> Path:
    return Path(__file__).resolve().parents[3]


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True,
                          check=True).stdout


def object_paths(repo: Path, tree: str, root_path: str) -> list[str]:
    prefix = root_path + "/"
    return sorted(path for path in git(repo, "ls-tree", "-r", "--name-only", tree).splitlines()
                  if path.startswith(prefix) and path[len(prefix):].count("/") == 0 and path.endswith(".md"))


def block(finding: str, name: str) -> list[str]:
    found = re.search(rf"^### {re.escape(name)} — `[^`]+` \(\d+\)\n\n```text\n(.*?)\n```", finding, re.M | re.S)
    if not found:
        raise ValueError(f"missing historical raw root: {name}")
    return found.group(1).splitlines()


def fail(message: str) -> int:
    print(f"P0.5 anchor check failed: {message}", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--anchor-file", type=Path)
    args = parser.parse_args()
    if args.write:
        return fail("--write cannot rewrite immutable historical evidence")
    if not args.check:
        return fail("--check is required")
    repo = root()
    try:
        anchor_doc = json.loads((args.anchor_file or repo / ANCHOR_REL).read_text(encoding="utf-8"))
        if anchor_doc.get("schema_version") != 1 or anchor_doc.get("plan_id") != PLAN_ID:
            raise ValueError("malformed anchor header")
        anchor = anchor_doc["anchors"]["p0.5"]
        tree = anchor["source_tree"]
        git(repo, "cat-file", "-e", f"{tree}^{{tree}}")
        finding = git(repo, "show", f"{anchor['item_commit']}:{anchor['finding_path']}")
        if hashlib.sha256(finding.encode()).hexdigest() != anchor["finding_sha256"]:
            raise ValueError("wrong finding hash")
        roots = anchor["roots"]
        if not isinstance(roots, list) or len(roots) != 5:
            raise ValueError("malformed root set")
        for row in roots:
            if not isinstance(row, list) or len(row) != 2:
                raise ValueError("malformed root row")
            name, root_path = row
            if object_paths(repo, tree, root_path) != block(finding, name):
                raise ValueError(f"changed root set: {name}")
    except (OSError, KeyError, TypeError, ValueError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        return fail(str(error))
    print("P0.5 command surface: sealed replay verified (no live HEAD/status fallback)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
