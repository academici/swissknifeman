#!/usr/bin/env python3
"""Validate the frozen Artifex contract set and its dependency graph.

Two manifest versions are handled explicitly, selected by the manifest's own
`schema_version`. `artifex-contract-manifest-v1` runs the frozen six-contract path
with its expectations unedited — same checks, same diagnostics, same OK line — so a
run against `contract-manifest-v1.json` on a v1-era tree still produces v1's exact
former behavior. `artifex-contract-manifest-v2` (P5.7, D123/D127) validates the
additive eight-contract aggregate: D108's `business-dispatch-admission-v1`, which the
frozen six-contract aggregate read as directory drift, and `economy-evidence-v2`,
which supersedes `economy-evidence-v1` and inherits its logical enums.
"""

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
    "dispatch-admission-v1",
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

# --- artifex-contract-manifest-v2 (P5.7, D123/D127) ---------------------------
# Additive: every name below is new. Nothing above this block changed.
EXPECTED_IDS_V2 = EXPECTED_IDS | {"business-dispatch-admission-v1", "economy-evidence-v2"}
ENTRY_KEYS_V2 = ENTRY_KEYS | {"status", "supersedes"}
SEMVER_RE = re.compile(r"[1-9][0-9]*\.[0-9]+\.[0-9]+\Z")
STATUSES = {"live", "superseded"}
EXPECTED_OWNERS_V2 = {
    "supervisor-run-v1": "P1.1",
    "slice-manifest-v1": "P1.2",
    "authority-policy-v1": "P1.3",
    "worker-envelope-v1": "P1.4",
    "economy-evidence-v1": "P1.5",
    "dispatch-admission-v1": "P1.6",
    "business-dispatch-admission-v1": "P5.5",
    "economy-evidence-v2": "P5.7",
}


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


def validate_v1(manifest: dict[str, Any], contracts_dir: Path) -> tuple[dict[str, Any], dict[str, str]]:
    """The frozen six-contract path — checks, literals and diagnostics unedited."""
    if manifest["manifest_version"] != "1.0.0":
        raise ManifestError("unsupported manifest schema/version")
    rows = manifest["contracts"]
    if not isinstance(rows, list) or len(rows) != 6:
        raise ManifestError("manifest must contain exactly six contracts")
    if any(not isinstance(row, dict) or set(row) != ENTRY_KEYS for row in rows):
        raise ManifestError("contract row has an open or incomplete shape")
    entries = {row["id"]: row for row in rows if isinstance(row.get("id"), str)}
    if set(entries) != EXPECTED_IDS or len(entries) != len(rows):
        raise ManifestError("contract IDs are missing, duplicated, or unexpected")

    disk_files = {path.name for path in contracts_dir.glob("*-v1.md") if path.is_file()}
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
        contract_path = contracts_dir / row["path"]
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
        "dispatch-admission-v1": "P1.6",
    }
    if {key: row["owner"] for key, row in entries.items()} != expected_owners:
        raise ManifestError("contract ownership does not match the P1 freeze items")
    assert_acyclic(entries)
    return entries, enum_owners


def validate_v2(manifest: dict[str, Any], contracts_dir: Path) -> tuple[dict[str, Any], dict[str, str]]:
    """The additive eight-contract path: the six frozen rows plus D108's
    `business-dispatch-admission-v1` (whose absence from the aggregate was F3) and
    `economy-evidence-v2`, which supersedes `economy-evidence-v1` and must inherit
    every logical enum the superseded row owned — a supersession may not orphan one."""
    if manifest["manifest_version"] != "2.0.0":
        raise ManifestError("unsupported manifest schema/version")
    rows = manifest["contracts"]
    if not isinstance(rows, list) or len(rows) != 8:
        raise ManifestError("manifest must contain exactly eight contracts")
    if any(not isinstance(row, dict) or set(row) != ENTRY_KEYS_V2 for row in rows):
        raise ManifestError("contract row has an open or incomplete shape")
    entries = {row["id"]: row for row in rows if isinstance(row.get("id"), str)}
    if set(entries) != EXPECTED_IDS_V2 or len(entries) != len(rows):
        raise ManifestError("contract IDs are missing, duplicated, or unexpected")

    disk_files = {path.name for path in contracts_dir.glob("*.md") if path.is_file()}
    expected_files = {f"{contract_id}.md" for contract_id in EXPECTED_IDS_V2}
    if disk_files != expected_files:
        raise ManifestError(f"contract directory mismatch: {sorted(disk_files ^ expected_files)}")

    live_enum_owners: dict[str, str] = {}
    enum_owners: dict[str, str] = {}
    for contract_id, row in entries.items():
        if row["path"] != f"{contract_id}.md" or Path(row["path"]).name != row["path"]:
            raise ManifestError(f"{contract_id}: path must be its local canonical filename")
        if not isinstance(row["version"], str) or not SEMVER_RE.fullmatch(row["version"]):
            raise ManifestError(f"{contract_id}: version is not a frozen semantic version")
        if not isinstance(row["sha256"], str) or not SHA256_RE.fullmatch(row["sha256"]):
            raise ManifestError(f"{contract_id}: malformed SHA-256")
        contract_path = contracts_dir / row["path"]
        if sha256(contract_path) != row["sha256"]:
            raise ManifestError(f"{contract_id}: content hash mismatch")
        text = contract_path.read_text(encoding="utf-8")
        # Both frozen idioms in this contract set, and each binds the identity to the
        # version — a bare `version in text` would pass on a predecessor's version
        # quoted elsewhere in a successor's own text.
        freeze_forms = (f"`{contract_id}` is frozen at `{row['version']}`", f"`{contract_id}@{row['version']}`")
        if not any(form in text for form in freeze_forms):
            raise ManifestError(f"{contract_id}: contract does not freeze itself at {row['version']}")
        if row["status"] not in STATUSES:
            raise ManifestError(f"{contract_id}: status must be one of {sorted(STATUSES)}")
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
        supersedes = row["supersedes"]
        if supersedes is not None and (supersedes not in entries or supersedes == contract_id):
            raise ManifestError(f"{contract_id}: unresolved/self supersession")
        if supersedes is not None and entries[supersedes]["status"] != "superseded":
            raise ManifestError(f"{contract_id}: supersedes {supersedes} but that row is not marked superseded")
        for logical_enum in logical_enums:
            enum_owners[logical_enum] = contract_id
            if row["status"] != "live":
                continue
            if logical_enum in live_enum_owners:
                raise ManifestError(
                    f"logical enum {logical_enum!r} has duplicate owners: "
                    f"{live_enum_owners[logical_enum]}, {contract_id}"
                )
            live_enum_owners[logical_enum] = contract_id

    successors = {row["supersedes"]: contract_id for contract_id, row in entries.items() if row["supersedes"]}
    for contract_id, row in entries.items():
        if row["status"] != "superseded":
            continue
        successor = successors.get(contract_id)
        if successor is None:
            raise ManifestError(f"{contract_id}: superseded without a successor row")
        orphaned = sorted(set(row["logical_enums"]) - set(entries[successor]["logical_enums"]))
        if orphaned:
            raise ManifestError(f"{contract_id}: supersession orphans logical enums {orphaned}")
    if {key: row["owner"] for key, row in entries.items()} != EXPECTED_OWNERS_V2:
        raise ManifestError("contract ownership does not match the freeze items")
    assert_acyclic(entries)
    return entries, live_enum_owners


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
        schema_version = manifest["schema_version"]
        if schema_version == "artifex-contract-manifest-v1":
            entries, enum_owners = validate_v1(manifest, args.contracts)
            summary = f"({len(entries)} contracts; {len(enum_owners)} logical enums; acyclic; hashes resolved)"
        elif schema_version == "artifex-contract-manifest-v2":
            entries, enum_owners = validate_v2(manifest, args.contracts)
            superseded = sum(1 for row in entries.values() if row["status"] == "superseded")
            summary = (
                f"({len(entries)} contracts, {len(entries) - superseded} live and {superseded} superseded; "
                f"{len(enum_owners)} logical enums with one live owner each; acyclic; hashes resolved)"
            )
        else:
            raise ManifestError("unsupported manifest schema/version")
    except (ManifestError, OSError, json.JSONDecodeError) as exc:
        print(f"contract-set: FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"contract-set: OK {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
