"""Immutable outputs of an attempt (execution §4.11).

An attempt seals a sequence of outputs (``seq`` 1, 2, …); checks and reviews refer to an ``output_id``,
the attempt points at its newest one and the task at the one it accepted. A sealed output never changes.
``manifest_digest`` is the SHA-256 of the whole canonical manifest; ``tree_digest`` (computed by the host,
adapters §3.6) identifies the paths and trees only, and the two are never interchangeable.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from fnmatch import fnmatchcase
from functools import lru_cache
from typing import TYPE_CHECKING, Final, Literal, NoReturn

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for

if TYPE_CHECKING:
    from datetime import datetime

    from skm.kernel.ids import AttemptId, FileVersionId, RepositoryId, RunId, TaskId
    from skm.kernel.json_types import JsonObject
    from skm.modules.execution.domain.ids import OutputId, StepId

__all__ = [
    "OUTPUT_ALGORITHM",
    "ChangedPath",
    "DiffStats",
    "Output",
    "OutputManifest",
    "OutputMount",
    "OutputSource",
    "display_path",
    "manifest_digest",
    "manifest_to_json",
    "matches_path",
    "normalize_pattern",
    "output_tree_digest",
    "raw_path_bytes",
]

OUTPUT_ALGORITHM: Final = "skm-output-v2"
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_FINGERPRINT = re.compile(r"absent|(100644|100755|120000|160000) ([0-9a-f]{40}|[0-9a-f]{64})")
_SHA = {"sha1": re.compile(r"[0-9a-f]{40}"), "sha256": re.compile(r"[0-9a-f]{64}")}
_BASE64URL = re.compile(r"[A-Za-z0-9_-]+")


class OutputSource(StrEnum):
    EXECUTOR = "executor"
    RANGE = "range"


@dataclass(frozen=True, slots=True)
class ChangedPath:
    mount: str
    path: str
    path_bytes: str
    change: Literal["added", "modified", "deleted", "renamed"]
    old_path: str | None
    old_path_bytes: str | None
    fingerprint: str

    def __post_init__(self) -> None:
        if self.change not in {"added", "modified", "deleted", "renamed"}:
            _invalid("change", f"unsupported change {self.change!r}")
        _raw_path(self.path_bytes, "path_bytes")
        renamed = self.change == "renamed"
        if renamed != (self.old_path_bytes is not None) or renamed != (self.old_path is not None):
            _invalid("old_path_bytes", "old_path/old_path_bytes are set exactly for a rename")
        if self.old_path_bytes is not None:
            _raw_path(self.old_path_bytes, "old_path_bytes")
        if not _FINGERPRINT.fullmatch(self.fingerprint):
            _invalid("fingerprint", "fingerprint is '<mode> <git blob>' or 'absent'")
        if (self.change == "deleted") != (self.fingerprint == "absent"):
            _invalid("fingerprint", "only a deleted path is absent")


@dataclass(frozen=True, slots=True)
class OutputMount:
    mount: str
    repository_id: RepositoryId
    object_format: Literal["sha1", "sha256"]
    base_commit: str
    head_commit: str
    tree_sha: str

    def __post_init__(self) -> None:
        pattern = _SHA.get(self.object_format)
        if pattern is None:
            _invalid("object_format", "object format is sha1 or sha256")
        for name in ("base_commit", "head_commit", "tree_sha"):
            if not pattern.fullmatch(getattr(self, name)):
                _invalid(name, f"{name} is a {self.object_format} object id")


@dataclass(frozen=True, slots=True)
class DiffStats:
    files: int
    insertions: int
    deletions: int


@dataclass(frozen=True, slots=True)
class OutputManifest:
    algorithm: Literal["skm-output-v2"]
    mounts: tuple[OutputMount, ...]
    changed_paths: tuple[ChangedPath, ...]
    tree_digest: str
    outside_write_scope: tuple[ChangedPath, ...]
    excluded_paths: tuple[ChangedPath, ...]
    patch_file_version_id: FileVersionId | None
    diff_stats: DiffStats
    empty: bool

    def __post_init__(self) -> None:
        if self.algorithm != OUTPUT_ALGORITHM:
            _invalid("algorithm", f"a new seal uses {OUTPUT_ALGORITHM}")
        if not _DIGEST.fullmatch(self.tree_digest):
            _invalid("tree_digest", "tree_digest is sha256:<64 hex>")
        mounts = [mount.mount for mount in self.mounts]
        if len(set(mounts)) != len(mounts):
            _invalid("mounts", "each mount appears once")
        raw = [(path.mount, path.path_bytes) for path in self.changed_paths]
        if len(set(raw)) != len(raw):
            _invalid("changed_paths", "raw paths are not repeated")
        if any(path.mount not in mounts for path in self.changed_paths):
            _invalid("changed_paths", "a changed path belongs to a sealed mount")
        if self.empty != (not self.changed_paths):
            _invalid("empty", "empty means no changed paths")


@dataclass(frozen=True, slots=True)
class Output:
    id: OutputId
    attempt_id: AttemptId
    task_id: TaskId
    run_id: RunId
    seq: int
    source: OutputSource
    manifest: OutputManifest
    manifest_digest: str
    sealed_at: datetime
    produced_by_step_id: StepId | None

    def __post_init__(self) -> None:
        if self.seq < 1:
            _invalid("seq", "seq >= 1")
        if (self.source is OutputSource.EXECUTOR) != (self.produced_by_step_id is not None):
            _invalid("produced_by_step_id", "an executor output names its step; a range output has none")
        if self.manifest_digest != manifest_digest(self.manifest):
            _invalid("manifest_digest", "manifest_digest is the digest of this manifest")


def manifest_to_json(manifest: OutputManifest) -> JsonObject:
    """The canonical manifest document; base/head maps are derived from ``mounts``, never stored twice."""
    return {
        "algorithm": manifest.algorithm,
        "mounts": [
            {
                "mount": mount.mount,
                "repository_id": str(mount.repository_id),
                "object_format": mount.object_format,
                "base_commit": mount.base_commit,
                "head_commit": mount.head_commit,
                "tree_sha": mount.tree_sha,
            }
            for mount in manifest.mounts
        ],
        "changed_paths": [_path_json(path) for path in manifest.changed_paths],
        "tree_digest": manifest.tree_digest,
        "outside_write_scope": [_path_json(path) for path in manifest.outside_write_scope],
        "excluded_paths": [_path_json(path) for path in manifest.excluded_paths],
        "patch_file_version_id": None
        if manifest.patch_file_version_id is None
        else str(manifest.patch_file_version_id),
        "diff_stats": {
            "files": manifest.diff_stats.files,
            "insertions": manifest.diff_stats.insertions,
            "deletions": manifest.diff_stats.deletions,
        },
        "empty": manifest.empty,
    }


def manifest_digest(manifest: OutputManifest) -> str:
    """``sha256:`` of the canonical JSON (sorted keys, no spaces, UTF-8) of the whole manifest."""
    text = json.dumps(manifest_to_json(manifest), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _path_json(path: ChangedPath) -> JsonObject:
    return {
        "mount": path.mount,
        "path": path.path,
        "path_bytes": path.path_bytes,
        "change": path.change,
        "old_path": path.old_path,
        "old_path_bytes": path.old_path_bytes,
        "fingerprint": path.fingerprint,
    }


def _raw_path(value: str, field: str) -> bytes:
    """Canonical base64url without padding of relative raw Git path bytes."""
    if not _BASE64URL.fullmatch(value):
        _invalid(field, "path bytes are base64url without padding")
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (binascii.Error, ValueError):
        _invalid(field, "path bytes are base64url without padding")
    if base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=") != value:
        _invalid(field, "path bytes are not canonical base64url")
    if not raw or b"\x00" in raw or any(part in {b"", b".", b".."} for part in raw.split(b"/")):
        _invalid(field, "a changed path is a canonical non-empty relative path")
    return raw


def _invalid(field: str, message: str) -> NoReturn:
    raise error_for(ErrorCode.SCHEMA_INVALID, message, details={"field": field})


def raw_path_bytes(value: str) -> bytes:
    """Canonical base64url raw path, without normalization or filesystem access."""
    return _raw_path(value, "path_bytes")


def display_path(path: bytes) -> str:
    try:
        return path.decode("utf-8", "strict")
    except UnicodeDecodeError:
        return path.decode("utf-8", "backslashreplace")


def normalize_pattern(pattern: str) -> str:
    if pattern.startswith("/") or "\0" in pattern or "\\" in pattern:
        raise ValueError("scope must be repository-relative")
    parts = [part for part in pattern.split("/") if part not in {"", "."}]
    if ".." in parts or not parts:
        raise ValueError("invalid scope")
    return "/".join(parts) + ("/" if pattern.endswith("/") else "")


def matches_path(path: str, pattern: str) -> bool:
    if not path or path.startswith("/") or "\0" in path:
        return False
    parts = tuple(path.split("/"))
    if any(part in {"", ".", ".."} for part in parts):
        return False
    normalized = normalize_pattern(pattern)
    if normalized.endswith("/"):
        normalized += "**"
    patterns = tuple(normalized.split("/"))

    @lru_cache(None)
    def match(i: int, j: int) -> bool:
        if j == len(patterns):
            return i == len(parts)
        if patterns[j] == "**":
            return match(i, j + 1) or (i < len(parts) and match(i + 1, j))
        return i < len(parts) and fnmatchcase(parts[i], patterns[j]) and match(i + 1, j + 1)

    return match(0, 0)


def output_tree_digest(
    mounts: Iterable[OutputMount], paths: Iterable[ChangedPath], *, algorithm: str = OUTPUT_ALGORITHM
) -> str:
    """Typed v2 identity shared by host sealing and server verification (adapters §3.6)."""
    if algorithm != OUTPUT_ALGORITHM:
        raise ValueError("only skm-output-v2 is supported")
    identities = sorted(mounts, key=lambda m: m.mount.encode("utf-8"))
    if len({m.mount for m in identities}) != len(identities):
        raise ValueError("duplicate mount")
    entries: dict[str, dict[bytes, str]] = {m.mount: {} for m in identities}
    formats = {m.mount: m.object_format for m in identities}
    for path in paths:
        raw = raw_path_bytes(path.path_bytes)
        if path.mount not in entries or display_path(raw) != path.path:
            raise ValueError("display/bytes/mount mismatch")
        values = [(raw, path.fingerprint)]
        if path.old_path_bytes is not None:
            old = raw_path_bytes(path.old_path_bytes)
            if display_path(old) != path.old_path:
                raise ValueError("old display differs from bytes")
            values.append((old, "absent"))
        for name, fingerprint in values:
            if name in entries[path.mount]:
                raise ValueError("duplicate raw path")
            if fingerprint != "absent":
                mode, oid = fingerprint.split(" ")
                size = 40 if formats[path.mount] == "sha1" else 64
                if (
                    mode not in {"100644", "100755", "120000"}
                    or len(oid) != size
                    or any(c not in "0123456789abcdef" for c in oid)
                ):
                    raise ValueError("invalid mode/object identity")
            entries[path.mount][name] = fingerprint
    payload = [
        [
            m.mount,
            str(m.repository_id),
            m.object_format,
            m.base_commit,
            m.head_commit,
            m.tree_sha,
            [
                [base64.urlsafe_b64encode(p).decode("ascii").rstrip("="), f]
                for p, f in sorted(entries[m.mount].items())
            ],
        ]
        for m in identities
    ]
    text = json.dumps(
        [algorithm, payload], ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
