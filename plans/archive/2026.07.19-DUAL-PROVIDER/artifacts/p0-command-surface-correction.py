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
P05_ANCHOR_CANONICAL_SHA256 = "f9054c5d9c12c1894b5514d1d223ef642b06fb469c7debfe55b9fa6bbe952b3d"
EXPECTED_P05_ANCHOR = {
    "source_tree": "d8ac22c04fc4d4219dc95244ee9d181e92553a74",
    "item_commit": "56239e92dfaa3aa7ec51e15727e94783f14c9370",
    "bookkeeping_commit": "566719e2602b2571726c91e72d5f71cec99c441d",
    "finding_path": "plans/2026.07.19-DUAL-PROVIDER/findings/P0-command-surface-correction.md",
    "finding_sha256": "39913b25e9dd3a454f311ab69b2e072d117438b1c23c6aa0f1ae54ed4a682996",
    "roots": [
        ["task", "packages/task/commands"],
        ["skiller", "packages/skiller/skm/commands"],
        ["harness", "packages/harness/commands"],
        ["maind", "packages/maind/commands"],
        ["analyst", "packages/analyst/commands"],
    ],
}


def canonical_anchor(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def require_exact(actual: object, expected: object, path: str) -> None:
    if type(actual) is not type(expected):
        raise ValueError(f"wrong anchor type: {path}")
    if isinstance(expected, dict):
        if actual.keys() != expected.keys():
            raise ValueError(f"wrong anchor keys: {path}")
        for key, expected_value in expected.items():
            require_exact(actual[key], expected_value, f"{path}.{key}")
    elif isinstance(expected, list):
        if len(actual) != len(expected):
            raise ValueError(f"wrong anchor length: {path}")
        for index, expected_value in enumerate(expected):
            require_exact(actual[index], expected_value, f"{path}[{index}]")
    elif actual != expected:
        raise ValueError(f"wrong anchor value: {path}")


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
        if (type(anchor_doc) is not dict
                or set(anchor_doc) != {"schema_version", "plan_id", "anchors"}
                or type(anchor_doc["schema_version"]) is not int
                or anchor_doc["schema_version"] != 1
                or type(anchor_doc["plan_id"]) is not str
                or anchor_doc["plan_id"] != PLAN_ID
                or type(anchor_doc["anchors"]) is not dict
                or set(anchor_doc["anchors"]) != {"p0.1", "p0.5"}):
            raise ValueError("malformed anchor header")
        anchor = anchor_doc["anchors"]["p0.5"]
        if hashlib.sha256(canonical_anchor(anchor)).hexdigest() != P05_ANCHOR_CANONICAL_SHA256:
            raise ValueError("P0.5 anchor differs from the approved immutable structure")
        require_exact(anchor, EXPECTED_P05_ANCHOR, "anchors.p0.5")
        tree = anchor["source_tree"]
        git(repo, "cat-file", "-e", f"{tree}^{{tree}}")
        git(repo, "cat-file", "-e", f"{anchor['item_commit']}^{{commit}}")
        git(repo, "cat-file", "-e", f"{anchor['bookkeeping_commit']}^{{commit}}")
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
