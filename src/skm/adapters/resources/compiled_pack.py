"""Read the compiled pack index and verify its content-addressed assets."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.modules.extensions.domain.digest_rules import file_digest
from skm.modules.extensions.domain.payload import (
    DEFAULT_MAX_ARCHIVE_BYTES,
    PayloadFile,
    check_payload_limits,
    validate_payload_path,
)

if TYPE_CHECKING:
    from collections.abc import Collection
    from importlib.resources.abc import Traversable

__all__ = [
    "BLOB_DIR",
    "LOCK_NAME",
    "MANIFEST",
    "PackLock",
    "blob_content",
    "enclosing_lock_root",
    "read_lock",
]

LOCK_NAME: Final = "pack.lock.json"
BLOB_DIR: Final = ".pack-blobs"
MANIFEST: Final = "pack.toml"
_SHA256 = re.compile(r"sha256:[0-9a-f]{64}")


def _invalid(message: str, path: str) -> ValidationFailed:
    return ValidationFailed(ErrorCode.SCHEMA_INVALID, message, details={"path": path})


def _digest(value: object) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise _invalid("invalid SHA-256 in compiled pack lock", LOCK_NAME)
    return value


def _unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    document = dict(pairs)
    if len(document) != len(pairs):
        raise _invalid("duplicate key in compiled pack lock", LOCK_NAME)
    return document


@dataclass(frozen=True, slots=True)
class PackLock:
    """The logical tree digest and paths whose bytes live in the shared blob directory."""

    digest: str
    aliases: Mapping[str, str]

    def encode(self) -> bytes:
        return (
            json.dumps(
                {"version": 1, "tree_digest": self.digest, "aliases": self.aliases}, sort_keys=True, indent=2
            )
            + "\n"
        ).encode("utf-8")

    @classmethod
    def decode(cls, data: bytes) -> PackLock:
        try:
            parsed: object = json.loads(data, object_pairs_hook=_unique_keys)
        except (ValueError, RecursionError) as exc:
            raise _invalid("invalid compiled pack lock JSON", LOCK_NAME) from exc
        if not isinstance(parsed, dict):
            raise _invalid("invalid compiled pack lock object", LOCK_NAME)
        document = cast("dict[str, object]", parsed)
        if set(document) != {"version", "tree_digest", "aliases"} or type(document["version"]) is not int:
            raise _invalid("invalid compiled pack lock fields", LOCK_NAME)
        if document["version"] != 1:
            raise _invalid("unsupported compiled pack lock version", LOCK_NAME)
        raw_aliases = document["aliases"]
        if not isinstance(raw_aliases, dict):
            raise _invalid("invalid alias map in compiled pack lock", LOCK_NAME)
        aliases: dict[str, str] = {}
        for path, digest in cast("dict[str, object]", raw_aliases).items():
            parts = validate_payload_path(path).split("/")
            if "\x00" in path or {BLOB_DIR, LOCK_NAME}.intersection(parts):
                raise _invalid("invalid asset path in compiled pack lock", path)
            aliases[path] = _digest(digest)
        return cls(_digest(document["tree_digest"]), aliases)

    def assets(
        self, root: Traversable | Mapping[str, bytes], prefix: str, physical_paths: Collection[str]
    ) -> tuple[PayloadFile, ...]:
        """Restore absent assets for a pack. A materialized path takes precedence for editing."""
        blobs: dict[str, bytes] = {}
        files: list[PayloadFile] = []
        size = 0
        for path, digest in sorted(self.aliases.items()):
            if not path.startswith(prefix):
                continue
            relative = path.removeprefix(prefix)
            if relative == MANIFEST or relative in physical_paths:
                continue
            if digest not in blobs:
                blobs[digest] = blob_content(root, digest)
            size += len(blobs[digest])
            check_payload_limits(len(files) + 1, size)
            files.append(PayloadFile(relative, blobs[digest]))
        return tuple(files)


def enclosing_lock_root(path: Path) -> Path | None:
    absolute = path.resolve()
    return next(
        (
            root
            for root in (absolute, *absolute.parents)
            if any(os.path.lexists(root / name) for name in (LOCK_NAME, BLOB_DIR))
        ),
        None,
    )


def read_lock(root: Traversable, *, allow_orphan_blobs: bool = False) -> tuple[PackLock, bytes] | None:
    path = root.joinpath(LOCK_NAME)
    if isinstance(path, Path) and path.is_symlink():
        raise _invalid("compiled pack lock cannot be a symlink", LOCK_NAME)
    if not path.is_file():
        if path.is_dir():
            raise _invalid("compiled pack lock must be a regular file", LOCK_NAME)
        if isinstance(path, Path) and path.exists():
            raise _invalid("compiled pack lock must be a regular file", LOCK_NAME)
        if not allow_orphan_blobs:
            blobs = root.joinpath(BLOB_DIR)
            if (isinstance(blobs, Path) and blobs.is_symlink()) or (blobs.is_dir() and any(blobs.iterdir())):
                raise _invalid("compiled pack lock is missing", LOCK_NAME)
        return None
    with path.open("rb") as stream:
        data = stream.read(DEFAULT_MAX_ARCHIVE_BYTES + 1)
    check_payload_limits(0, len(data))
    return PackLock.decode(data), data


def blob_content(root: Traversable | Mapping[str, bytes], digest: str) -> bytes:
    name = _digest(digest).removeprefix("sha256:")
    relative = f"{BLOB_DIR}/{name}"
    if isinstance(root, Mapping):
        content = root.get(relative)
        if content is None:
            raise _invalid("compiled pack blob is missing", relative)
    else:
        directory = root.joinpath(BLOB_DIR)
        path = directory.joinpath(name)
        if isinstance(directory, Path) and directory.is_symlink():
            raise _invalid("compiled pack blob directory cannot be a symlink", BLOB_DIR)
        if (isinstance(path, Path) and path.is_symlink()) or not path.is_file():
            raise _invalid("compiled pack blob is missing or invalid", relative)
        with path.open("rb") as stream:
            content = stream.read(DEFAULT_MAX_ARCHIVE_BYTES + 1)
        check_payload_limits(1, len(content))
    if file_digest(content) != digest:
        raise _invalid("compiled pack blob SHA-256 mismatch", relative)
    return content
