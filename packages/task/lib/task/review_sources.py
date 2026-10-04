"""Immutable source witnesses and transport-owned consulted dependency ledgers."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def source_identity(root: Path, relative: str) -> dict:
    if not relative.startswith("vendor/"):
        return {"kind": "repository-source", "path": relative}
    package = "/".join(relative.split("/")[1:3])
    lock = root / "composer.lock"
    value = json.loads(lock.read_text())
    records = [entry for entry in value.get("packages", []) + value.get("packages-dev", [])
               if entry.get("name") == package]
    if len(records) != 1 or not records[0].get("version"):
        raise ValueError("REVIEW_EXTERNAL_SOURCE_INVALID: vendor source needs its locked package")
    reference = (records[0].get("source") or records[0].get("dist") or {}).get("reference")
    if not isinstance(reference, str) or not reference:
        raise ValueError("REVIEW_EXTERNAL_SOURCE_INVALID: missing immutable package reference")
    return {"kind": "composer-source", "package": package, "version": records[0]["version"],
            "reference": reference, "lock_path": "composer.lock", "lock_sha256": sha(lock.read_bytes())}


def archive(root: Path, directory: Path, members, tracked) -> list[dict]:
    members = list(members)
    if (any(row["path"].startswith("vendor/") and row["path"] not in tracked for row in members)
            and "composer.lock" not in tracked
            and not any(row["path"] == "composer.lock" for row in members)):
        from task import review_packet
        members.extend(review_packet._members(root, ["composer.lock"]))
    sources = []
    for row in members:
        if row["path"] in tracked or row.get("sha256") in {None, "directory"}:
            continue
        path = root / row["path"]
        if path.is_symlink():
            raise ValueError("REVIEW_EXTERNAL_SOURCE_INVALID: untracked inputs must be regular files")
        payload = path.read_bytes()
        digest = sha(payload)
        if digest != row["sha256"]:
            raise ValueError("REVIEW_CANDIDATE_STALE: source changed while archiving")
        identity = source_identity(root, row["path"])
        carrier = directory / "source-blobs" / digest
        carrier.parent.mkdir(parents=True, exist_ok=True)
        if carrier.exists():
            if carrier.read_bytes() != payload:
                raise ValueError("REVIEW_EXTERNAL_SOURCE_INVALID: altered source blob")
        else:
            carrier.write_bytes(payload)
        sources.append({"member": row, "blob_path": carrier.relative_to(root).as_posix(), "identity": identity})
    return sources


def frozen_members(sources, *, read, tree: dict) -> dict:
    by_path = {source["member"]["path"]: source for source in sources}
    if len(by_path) != len(sources):
        raise ValueError("REVIEW_CLOSURE_INVALID: duplicate source witness")
    def input_bytes(path):
        source = by_path.get(path)
        if path not in tree and source is not None:
            payload = read(source["blob_path"])
            if sha(payload) != source["member"]["sha256"]:
                raise ValueError("REVIEW_CLOSURE_INVALID: source input blob changed")
            return payload
        return read(path)
    result = {}
    for source in sources:
        row = source["member"]
        payload = read(source["blob_path"])
        if sha(payload) != row["sha256"]:
            raise ValueError("REVIEW_CLOSURE_INVALID: source blob changed")
        identity = source["identity"]
        if identity["kind"] == "composer-source":
            if not row["path"].startswith("vendor/" + identity["package"] + "/"):
                raise ValueError("REVIEW_CLOSURE_INVALID: source package/path mismatch")
            lock = input_bytes(identity["lock_path"])
            if sha(lock) != identity["lock_sha256"]:
                raise ValueError("REVIEW_CLOSURE_INVALID: source lock changed")
            value = json.loads(lock)
            records = [entry for entry in value.get("packages", []) + value.get("packages-dev", [])
                       if entry.get("name") == identity["package"]]
            if len(records) != 1:
                raise ValueError("REVIEW_CLOSURE_INVALID: source package missing")
            package = records[0]
            reference = (package.get("source") or package.get("dist") or {}).get("reference")
            if package.get("version") != identity["version"] or reference != identity["reference"]:
                raise ValueError("REVIEW_CLOSURE_INVALID: substituted package reference")
        elif identity == {"kind": "legacy-reviewed-bytes", "path": row["path"],
                          "sha256": row["sha256"], "identity_limit": "original-lock-not-bound"}:
            # A legacy receipt authenticates these exact bytes, but says nothing
            # about a lock/package version. Do not invent that missing history.
            if not row["path"].startswith("vendor/"):
                raise ValueError("REVIEW_CLOSURE_INVALID: invalid legacy external-source path")
        elif identity != {"kind": "repository-source", "path": row["path"]}:
            raise ValueError("REVIEW_CLOSURE_INVALID: substituted source identity")
        if row["path"] in result:
            raise ValueError("REVIEW_CLOSURE_INVALID: duplicate source witness")
        result[row["path"]] = row
    return result


def recovered_members(root, commit, manifest, *, prefix, missing, read_original):
    """Later blobs may supply bytes already authenticated by an original input digest.

    They never supply a missing verdict/route/closure artifact or alter its digest.
    """
    from task import review_packet as review
    recovery_prefix = prefix + "source-recovery/" + manifest["candidate_sha256"] + "/"
    tree = {}
    for raw in review._git(root, "ls-tree", "-r", "-z", "HEAD").split(b"\0"):
        if raw:
            meta, name = raw.split(b"\t", 1)
            tree[name.decode()] = tuple(meta.decode().split())
    def read(path):
        if path == "composer.lock":
            return read_original(path)
        if not path.startswith(recovery_prefix):
            raise ValueError("REVIEW_CLOSURE_INVALID: source recovery escapes its candidate")
        row = tree.get(path)
        if not row or row[0] not in {"100644", "100755"} or row[1] != "blob":
            raise ValueError("REVIEW_EXTERNAL_SOURCE_UNARCHIVED: commit source-recovery witnesses before historical consumption")
        return review._git(root, "cat-file", "blob", row[2])
    witness = json.loads(read(recovery_prefix + "witness.json"))
    if (witness.get("schema_version") != "review-source-recovery/v1"
            or witness.get("closure_commit") != commit
            or witness.get("candidate_sha256") != manifest["candidate_sha256"]
            or sorted((row["member"] for row in witness.get("sources", [])), key=lambda row: row["path"]) != missing):
        raise ValueError("REVIEW_CLOSURE_INVALID: source recovery differs from original authenticated inputs")
    return frozen_members(witness["sources"], read=read, tree=tree)


def recover(plan_dir, item: str) -> dict:
    """Prepare additive source witnesses; the original reviewed hashes remain authority."""
    from task import plan_recovery, review_packet as review
    plan_dir = Path(plan_dir).resolve()
    event = plan_recovery._positions(plan_dir).get(item, {})
    root, commit, tree = review._committed_closure(plan_dir, item,
        decision=event.get("decision"), result=event.get("result"))
    directory = review._location(plan_dir, item)
    prefix = directory.relative_to(root).as_posix() + "/"
    paths = sorted(path for path in tree if path.startswith(prefix + "attempt-") and path.endswith("/receipt.json"))
    receipts = [json.loads(review._git(root, "cat-file", "blob", tree[path][2])) for path in paths]
    receipt = next((row for row in reversed(receipts) if row.get("status") == "complete"), None)
    if not receipt:
        raise ValueError("REVIEW_CLOSURE_INVALID: original closure has no complete review")
    review._green_receipt(receipt, receipt["reviewer"])
    manifest = receipt["manifest"]
    if sha(review._json(manifest["snapshot"])) != manifest["candidate_sha256"]:
        raise ValueError("REVIEW_CLOSURE_INVALID: original snapshot digest mismatch")
    lock_entry = tree.get("composer.lock")
    lock = review._git(root, "cat-file", "blob", lock_entry[2]) if lock_entry else None
    packages = json.loads(lock) if lock is not None else {}
    records = packages.get("packages", []) + packages.get("packages-dev", [])
    target = directory / "source-recovery" / manifest["candidate_sha256"]
    sources = []
    with review._lock(directory):
        for row in manifest["snapshot"]["inputs"]:
            if not row["path"].startswith("vendor/") or row["path"] in tree or not row.get("sha256"):
                continue
            path = review._inside(root, row["path"])
            payload = path.read_bytes()
            if path.is_symlink() or sha(payload) != row["sha256"]:
                raise ValueError("REVIEW_EXTERNAL_SOURCE_INVALID: live source differs from original reviewed bytes")
            name = "/".join(row["path"].split("/")[1:3])
            matches = [package for package in records if package.get("name") == name]
            if lock is not None and len(matches) != 1:
                raise ValueError("REVIEW_EXTERNAL_SOURCE_INVALID: source has no original locked package")
            package = matches[0] if lock is not None else None
            identity = {"kind": "composer-source", "package": name, "version": package["version"],
                "reference": (package.get("source") or package.get("dist") or {})["reference"],
                "lock_path": "composer.lock", "lock_sha256": sha(lock)} if package else {
                "kind": "legacy-reviewed-bytes", "path": row["path"], "sha256": row["sha256"],
                "identity_limit": "original-lock-not-bound"}
            blob = target / "source-blobs" / row["sha256"]
            blob.parent.mkdir(parents=True, exist_ok=True)
            if blob.exists() and blob.read_bytes() != payload:
                raise ValueError("REVIEW_EXTERNAL_SOURCE_INVALID: recovery blob changed")
            blob.write_bytes(payload)
            sources.append({"member": row, "blob_path": blob.relative_to(root).as_posix(), "identity": identity})
        if not sources:
            return {"action": "no-source-recovery-needed"}
        value = {"schema_version": "review-source-recovery/v1", "closure_commit": commit,
                 "candidate_sha256": manifest["candidate_sha256"], "sources": sources}
        witness = target / "witness.json"
        if witness.exists() and witness.read_bytes() != review._json(value):
            raise ValueError("REVIEW_EXTERNAL_SOURCE_INVALID: recovery witness differs")
        witness.write_bytes(review._json(value))
    return {"action": "source-recovery-prepared", "witness": str(witness),
            "source_count": len(sources), "requires_commit": True,
            "identity_limit": "original-lock-not-bound" if lock is None else None}


class ReadLedger:
    """Hash before a native read starts, verify on completion and before GREEN."""
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.rows = {}

    def read_path(self, update: dict) -> Path | None:
        if update.get("sessionUpdate") not in {"tool_call", "tool_call_update"}:
            return None
        tool = update.get("_meta", {}).get("x.ai/tool", {})
        if tool.get("name", update.get("title")) != "read_file":
            return None
        arguments = update.get("rawInput", {})
        location = arguments.get("target_file") or arguments.get("path") or tool.get("input", {}).get("path")
        if not isinstance(location, str) or not location:
            raise ValueError("REVIEW_READ_UNVERIFIABLE: native file read has no path")
        path = Path(location)
        if not path.is_absolute():
            path = self.root / path
        if ".." in path.parts or not path.is_relative_to(self.root):
            raise ValueError("REVIEW_READ_UNVERIFIABLE: path escapes the repository")
        return path

    def observe(self, update: dict) -> None:
        path = self.read_path(update)
        if path is None:
            return  # grep/list are discovery, not a claim to have read every match.
        arguments = update.get("rawInput", {})
        if not path.resolve().is_relative_to(self.root) or not path.is_file():
            raise ValueError("REVIEW_READ_UNVERIFIABLE: source must be a repository-local file")
        relative = path.relative_to(self.root).as_posix()
        from task import review_packet
        row = review_packet._members(self.root, [relative])[0]
        if relative in self.rows and self.rows[relative]["member"] != row:
            raise ValueError("REVIEW_DEPENDENCY_STALE: consulted bytes changed during review")
        identity = source_identity(self.root, relative) if relative.startswith("vendor/") else None
        entry = self.rows.setdefault(relative, {"member": row, "reads": [], "identity": identity})
        if entry.get("identity") != identity:
            raise ValueError("REVIEW_DEPENDENCY_STALE: external source lock changed during review")
        record = {"tool_call_id": update.get("toolCallId"),
                  "offset": arguments.get("offset", arguments.get("start_line")),
                  "limit": arguments.get("limit", arguments.get("end_line"))}
        if record not in entry["reads"]:
            entry["reads"].append(record)

    def verify(self):
        from task import review_packet
        for relative, entry in self.rows.items():
            if review_packet._members(self.root, [relative])[0] != entry["member"]:
                raise ValueError("REVIEW_DEPENDENCY_STALE: " + relative)
            if entry.get("identity") is not None and source_identity(self.root, relative) != entry["identity"]:
                raise ValueError("REVIEW_DEPENDENCY_STALE: external source identity changed")

    def result(self):
        return {"schema_version": "review-read-ledger/v1", "reads": [self.rows[key] for key in sorted(self.rows)]}
