#!/usr/bin/env python3
"""Verify the sealed P0.1 inventory from git objects, never live inputs."""
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


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def object_paths(repo: Path, tree: str, pattern: str) -> list[str]:
    paths = git(repo, "ls-tree", "-r", "--name-only", tree).splitlines()
    expression = re.compile("^" + re.escape(pattern).replace(r"\*\*", ".*").replace(r"\*", "[^/]*") + "$" )
    return sorted(path for path in paths if expression.match(path))


def object_text(repo: Path, commit: str, path: str) -> str:
    return git(repo, "show", f"{commit}:{path}")


def block(finding: str, heading: str) -> list[str]:
    found = re.search(rf"^### {re.escape(heading)}\n\n```text\n(.*?)\n```", finding, re.M | re.S)
    if not found:
        raise ValueError(f"missing historical raw set: {heading}")
    return found.group(1).splitlines()


def fail(message: str) -> int:
    print(f"P0.1 anchor check failed: {message}", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--anchor-file", type=Path)
    args = parser.parse_args()
    if args.write:
        return fail("--write cannot rewrite immutable historical evidence")
    if args.live:
        return fail("live fallback is forbidden; replay is sealed to git objects")
    if not args.check:
        return fail("--check is required")
    repo = root()
    anchor_path = args.anchor_file or repo / ANCHOR_REL
    try:
        anchor_doc = json.loads(anchor_path.read_text(encoding="utf-8"))
        if anchor_doc.get("schema_version") != 1 or anchor_doc.get("plan_id") != PLAN_ID:
            raise ValueError("malformed anchor header")
        anchor = anchor_doc["anchors"]["p0.1"]
        tree = anchor["source_tree"]
        git(repo, "cat-file", "-e", f"{tree}^{{tree}}")
        finding = object_text(repo, anchor["item_commit"], anchor["finding_path"])
        if hashlib.sha256(finding.encode()).hexdigest() != anchor["finding_sha256"]:
            raise ValueError("wrong finding hash")
        collections = anchor["collections"]
        actual = {
            "canonical skills": object_paths(repo, tree, collections["canonical skills"]["glob"]),
            "task commands": object_paths(repo, tree, collections["task commands"]["glob"]),
            "MCP presets": object_paths(repo, tree, collections["MCP presets"]["glob"]),
            "agent packs": object_paths(repo, tree, collections["agent packs"]["glob"]),
        }
        for label, paths in actual.items():
            if len(paths) != collections[label]["expected_count"] or paths != block(finding, label):
                raise ValueError(f"changed root set: {label}")
        plugins = collections["plugin manifests"]
        external = plugins["external_paths"]
        if (plugins.get("collection_mode") != "tracked_source_tree_plus_sealed_external_paths"
                or canonical(external).hex() == ""
                or hashlib.sha256(canonical(external)).hexdigest() != plugins["external_paths_canonical_json_sha256"]
                or len(external) != 1):
            raise ValueError("malformed sealed external path anchor")
        tracked = object_paths(repo, tree, plugins["tracked_glob"])
        if len(tracked) != plugins["tracked_expected_count"]:
            raise ValueError("changed tracked plugin root set")
        replayed_plugins = sorted(tracked + external)
        if replayed_plugins != block(finding, "plugin manifests") or len(replayed_plugins) != 54:
            raise ValueError("missing, extra, or changed sealed external path")
        fleet = collections["fleet projects"]
        values = fleet["values"]
        if (fleet.get("collection_mode") != "sealed_redacted_ids"
                or hashlib.sha256(canonical(values)).hexdigest() != fleet["canonical_json_sha256"]
                or values != block(finding, "fleet projects")):
            raise ValueError("wrong redacted input hash")
    except (OSError, KeyError, TypeError, ValueError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        return fail(str(error))
    print("P0.1 inventory: sealed replay verified (53 tracked + 1 external path; no live fallback)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
