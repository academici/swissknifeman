#!/usr/bin/env python3
"""Validate the frozen Artifex P1 contract set and its dependency graph."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


EXPECTED_IDS = {
    "supervisor-run-v1",
    "slice-manifest-v1",
    "authority-policy-v1",
    "worker-envelope-v1",
    "economy-evidence-v1",
}
ENTRY_KEYS = {
    "id",
    "version",
    "path",
    "sha256",
    "owner",
    "consumers",
    "dependencies",
    "references",
    "logical_enums",
}
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
VERSION_RE = re.compile(r"1\.0\.0\Z")
ITEM_RE = re.compile(r"P[1-6]\.[1-9][0-9]*\Z")


class ManifestError(ValueError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_string_list(value: Any, label: str, *, nonempty: bool) -> list[str]:
    if not isinstance(value, list) or (nonempty and not value):
        raise ManifestError(f"{label}: expected {'non-empty ' if nonempty else ''}list")
    if any(not isinstance(item, str) or not item for item in value) or len(set(value)) != len(value):
        raise ManifestError(f"{label}: values must be unique non-empty strings")
    return value


def assert_acyclic(entries: dict[str, dict[str, Any]]) -> None:
    temporary: set[str] = set()
    permanent: set[str] = set()

    def visit(contract_id: str) -> None:
        if contract_id in permanent:
            return
        if contract_id in temporary:
            raise ManifestError(f"dependency cycle at {contract_id}")
        temporary.add(contract_id)
        for dependency in entries[contract_id]["dependencies"]:
            visit(dependency)
        temporary.remove(contract_id)
        permanent.add(contract_id)

    for contract_id in sorted(entries):
        visit(contract_id)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--contracts", required=True, type=Path)
    args = parser.parse_args()
    try:
        with args.manifest.open("r", encoding="utf-8") as stream:
            manifest = json.load(stream)
        if not isinstance(manifest, dict) or set(manifest) != {"schema_version", "manifest_version", "contracts"}:
            raise ManifestError("manifest has an open or incomplete top-level shape")
        if manifest["schema_version"] != "artifex-contract-manifest-v1" or manifest["manifest_version"] != "1.0.0":
            raise ManifestError("unsupported manifest schema/version")
        rows = manifest["contracts"]
        if not isinstance(rows, list) or len(rows) != 5:
            raise ManifestError("manifest must contain exactly five contracts")
        if any(not isinstance(row, dict) or set(row) != ENTRY_KEYS for row in rows):
            raise ManifestError("contract row has an open or incomplete shape")
        entries = {row["id"]: row for row in rows if isinstance(row.get("id"), str)}
        if set(entries) != EXPECTED_IDS or len(entries) != len(rows):
            raise ManifestError("contract IDs are missing, duplicated, or unexpected")

        disk_files = {path.name for path in args.contracts.glob("*-v1.md") if path.is_file()}
        expected_files = {f"{contract_id}.md" for contract_id in EXPECTED_IDS}
        if disk_files != expected_files:
            raise ManifestError(f"contract directory mismatch: {sorted(disk_files ^ expected_files)}")

        enum_owners: dict[str, str] = {}
        for contract_id, row in entries.items():
            if row["path"] != f"{contract_id}.md" or Path(row["path"]).name != row["path"]:
                raise ManifestError(f"{contract_id}: path must be its local canonical filename")
            if not isinstance(row["version"], str) or not VERSION_RE.fullmatch(row["version"]):
                raise ManifestError(f"{contract_id}: version is not frozen at 1.0.0")
            if not isinstance(row["sha256"], str) or not SHA256_RE.fullmatch(row["sha256"]):
                raise ManifestError(f"{contract_id}: malformed SHA-256")
            contract_path = args.contracts / row["path"]
            if sha256(contract_path) != row["sha256"]:
                raise ManifestError(f"{contract_id}: content hash mismatch")
            text = contract_path.read_text(encoding="utf-8")
            if contract_id not in text or "1.0.0" not in text:
                raise ManifestError(f"{contract_id}: identity/version not present in contract")
            if not isinstance(row["owner"], str) or not ITEM_RE.fullmatch(row["owner"]):
                raise ManifestError(f"{contract_id}: invalid owner item")
            consumers = require_string_list(row["consumers"], f"{contract_id}.consumers", nonempty=True)
            if any(not ITEM_RE.fullmatch(consumer) for consumer in consumers):
                raise ManifestError(f"{contract_id}: invalid consumer item")
            dependencies = require_string_list(row["dependencies"], f"{contract_id}.dependencies", nonempty=False)
            references = require_string_list(row["references"], f"{contract_id}.references", nonempty=False)
            logical_enums = require_string_list(row["logical_enums"], f"{contract_id}.logical_enums", nonempty=True)
            if any(dependency not in entries or dependency == contract_id for dependency in dependencies):
                raise ManifestError(f"{contract_id}: unresolved/self dependency")
            if any(reference not in entries or reference == contract_id for reference in references):
                raise ManifestError(f"{contract_id}: unresolved/self reference")
            if set(references) != set(dependencies):
                raise ManifestError(f"{contract_id}: dependency/reference carriers diverge")
            missing_references = [reference for reference in references if reference not in text]
            if missing_references:
                raise ManifestError(f"{contract_id}: referenced contracts absent from text: {missing_references}")
            for logical_enum in logical_enums:
                if logical_enum in enum_owners:
                    raise ManifestError(
                        f"logical enum {logical_enum!r} has duplicate owners: "
                        f"{enum_owners[logical_enum]}, {contract_id}"
                    )
                enum_owners[logical_enum] = contract_id

        expected_owners = {
            "supervisor-run-v1": "P1.1",
            "slice-manifest-v1": "P1.2",
            "authority-policy-v1": "P1.3",
            "worker-envelope-v1": "P1.4",
            "economy-evidence-v1": "P1.5",
        }
        if {key: row["owner"] for key, row in entries.items()} != expected_owners:
            raise ManifestError("contract ownership does not match the P1 freeze items")
        assert_acyclic(entries)
    except (ManifestError, OSError, json.JSONDecodeError) as exc:
        print(f"contract-set: FAIL: {exc}", file=sys.stderr)
        return 1
    print(
        "contract-set: OK "
        f"({len(entries)} contracts; {len(enum_owners)} logical enums; acyclic; hashes resolved)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
