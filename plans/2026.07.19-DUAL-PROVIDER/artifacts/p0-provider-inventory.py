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
P01_ANCHOR_CANONICAL_SHA256 = "c0a1a7649fa0dc088857ac3c07c7074f64e54fbe68b754ae061cf8c4ec9eb984"
EXPECTED_P01_ANCHOR = {
    "source_tree": "9844f499797faf063aede49b79703c71f7ef666e",
    "item_commit": "f4d230e6e83aac56ab7fe82a085b7bb18d59d6de",
    "bookkeeping_commit": "d8ac22c04fc4d4219dc95244ee9d181e92553a74",
    "finding_path": "plans/2026.07.19-DUAL-PROVIDER/findings/P0-provider-coupling-baseline.md",
    "finding_sha256": "23f8bccce5fcbfc1841ef0373fad4bf0ed5c341b25b037f797eb3c5695550b88",
    "collections": {
        "canonical skills": {"glob": "packages/skiller/skills/**/SKILL.md", "expected_count": 216},
        "task commands": {"glob": "packages/task/commands/*.md", "expected_count": 11},
        "plugin manifests": {
            "collection_mode": "tracked_source_tree_plus_sealed_external_paths",
            "tracked_glob": "packages/**/.claude-plugin/plugin.json",
            "tracked_expected_count": 53,
            "external_paths": [
                "packages/maind/node_modules/@agentmemory/agentmemory/plugin/.claude-plugin/plugin.json"
            ],
            "external_paths_canonical_json_sha256": (
                "d0471d0cbafc3e0889dbf2499493670147bfbb0b8ef83c70998f49b1205c0eb4"
            ),
            "external_provenance": (
                "immutable P0.1 finding at f4d230e6e83aac56ab7fe82a085b7bb18d59d6de; "
                "source tree 9844f499797faf063aede49b79703c71f7ef666e"
            ),
        },
        "MCP presets": {
            "glob": "packages/harness/configs/claude-code/mcp/*.json",
            "expected_count": 8,
        },
        "agent packs": {
            "glob": "packages/harness/configs/claude-code/agent-packs/**/pack.json",
            "expected_count": 10,
        },
        "fleet projects": {
            "collection_mode": "sealed_redacted_ids",
            "values": [
                "agelto", "diabox", "flexcrm", "axiomaerpsdk", "azguard", "botkit",
                "vaulter", "swissknifeman", "axiomastudio", "corex", "memster", "cms",
                "edufy", "vintera", "dterema", "dterema-app", "sibintek-insiders",
                "chatom", "perplexity-web-mcp", "loqum", "brain", "local-repo",
                "local-repo", "local-repo", "local-repo",
            ],
            "canonical_json_sha256": (
                "fb18cc310634a91d0062f836f49cc48fb9401b41d56af031ae835c088066045d"
            ),
        },
    },
}


def root() -> Path:
    return Path(__file__).resolve().parents[3]


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True,
                          check=True).stdout


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


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
        if (type(anchor_doc) is not dict
                or set(anchor_doc) != {"schema_version", "plan_id", "anchors"}
                or type(anchor_doc["schema_version"]) is not int
                or anchor_doc["schema_version"] != 1
                or type(anchor_doc["plan_id"]) is not str
                or anchor_doc["plan_id"] != PLAN_ID
                or type(anchor_doc["anchors"]) is not dict
                or set(anchor_doc["anchors"]) != {"p0.1", "p0.5"}):
            raise ValueError("malformed anchor header")
        anchor = anchor_doc["anchors"]["p0.1"]
        if hashlib.sha256(canonical_anchor(anchor)).hexdigest() != P01_ANCHOR_CANONICAL_SHA256:
            raise ValueError("P0.1 anchor differs from the approved immutable structure")
        require_exact(anchor, EXPECTED_P01_ANCHOR, "anchors.p0.1")
        tree = anchor["source_tree"]
        git(repo, "cat-file", "-e", f"{tree}^{{tree}}")
        git(repo, "cat-file", "-e", f"{anchor['item_commit']}^{{commit}}")
        git(repo, "cat-file", "-e", f"{anchor['bookkeeping_commit']}^{{commit}}")
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
