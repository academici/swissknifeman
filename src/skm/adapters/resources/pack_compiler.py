"""Compile extension pack directories into a SHA-256 lock and shared asset blobs."""

from __future__ import annotations

import fcntl
import json
import os
import re
from collections import defaultdict
from pathlib import Path

from skm.adapters.resources.compiled_pack import (
    BLOB_DIR,
    LOCK_NAME,
    MANIFEST,
    PackLock,
    enclosing_lock_root,
    read_lock,
)
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable, ValidationFailed
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.extensions.domain.digest_rules import file_digest, is_excluded
from skm.modules.extensions.domain.payload import check_payload_limits, validate_payload_path
from skm.platform.fs.atomic_write import UnsafePathError, atomic_write
from skm.platform.fs.safe_paths import safe_join

__all__ = ["compile_packs"]

_BLOB_NAME = re.compile(r"[0-9a-f]{64}")


def _invalid(path: Path | str, message: str) -> ValidationFailed:
    return ValidationFailed(ErrorCode.SCHEMA_INVALID, message, details={"path": str(path)})


def _entries(root: Path, folder: Path) -> list[Path]:
    entries: list[Path] = []
    for entry in sorted(folder.iterdir()):
        if entry.name in {LOCK_NAME, BLOB_DIR}:
            if folder == root:
                continue
            raise _invalid(entry, "nested compiled pack metadata; compile at a single root")
        validate_payload_path(entry.relative_to(root).as_posix())
        if entry.is_symlink() or not (entry.is_dir() or entry.is_file()):
            raise _invalid(entry, "pack entries must be regular files or directories")
        if entry.name != "__pycache__" and not is_excluded(entry.name):
            entries.append(entry)
    return entries


def _pack_dirs(root: Path, folder: Path) -> list[Path]:
    entries = _entries(root, folder)
    if any(entry.name == MANIFEST and entry.is_file() for entry in entries):
        return [folder]
    return [pack for entry in entries if entry.is_dir() for pack in _pack_dirs(root, entry)]


def _physical_files(root: Path, pack: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    folders = [pack]
    size = 0
    while folders:
        for entry in _entries(root, folders.pop()):
            if entry.is_dir():
                folders.append(entry)
                continue
            path = entry.relative_to(root).as_posix()
            check_payload_limits(len(files), size + entry.stat().st_size)
            content = entry.read_bytes()
            size += len(content)
            check_payload_limits(len(files), size)
            files[path] = content
    return files


def _logical_files(
    root: Path, packs: list[Path], lock: PackLock | None
) -> tuple[dict[str, bytes], dict[str, bytes], set[str]]:
    physical: dict[str, bytes] = {}
    logical: dict[str, bytes] = {}
    manifests: set[str] = set()
    for pack in packs:
        files = _physical_files(root, pack)
        physical.update(files)
        prefix = "" if pack == root else pack.relative_to(root).as_posix() + "/"
        manifests.add(prefix + MANIFEST)
        if lock is not None:
            # An absent alias is still part of this pack. Physical edits override it.
            paths = {path.removeprefix(prefix) for path in files}
            for asset in lock.assets(root, prefix, paths):
                path = prefix + asset.path
                if safe_join(root, path).is_dir():
                    raise _invalid(path, "compiled asset path is now a directory")
                files[path] = asset.content
        check_payload_limits(len(files) - 1, sum(map(len, files.values())))
        logical.update(files)
    return logical, physical, manifests


def _build_lock(files: dict[str, bytes], manifests: set[str]) -> tuple[PackLock, dict[str, bytes]]:
    digests: dict[str, str] = {}
    groups: dict[str, list[str]] = defaultdict(list)
    for path, content in sorted(files.items()):
        digest = file_digest(content)
        digests[path] = digest
        if path not in manifests:
            groups[digest].append(path)

    aliases: dict[str, str] = {}
    blobs: dict[str, bytes] = {}
    for digest, paths in groups.items():
        if len(paths) < 2:
            continue
        first = files[paths[0]]
        if any(files[path] != first for path in paths[1:]):
            raise _invalid(paths[0], "distinct assets have the same SHA-256")
        blobs[digest.removeprefix("sha256:")] = first
        aliases.update(dict.fromkeys(paths, digest))
    tree_digest = file_digest(json.dumps(digests, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return PackLock(tree_digest, aliases), blobs


def _stored_blobs(directory: Path) -> dict[str, Path]:
    if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
        raise _invalid(directory, "compiled pack blobs must be stored in a directory")
    if not directory.is_dir():
        return {}
    blobs: dict[str, Path] = {}
    for entry in sorted(directory.iterdir()):
        if not _BLOB_NAME.fullmatch(entry.name) or entry.is_symlink() or not entry.is_file():
            raise _invalid(entry, "unexpected entry in compiled pack blob directory")
        blobs[entry.name] = entry
    return blobs


def _publish(
    root: Path,
    *,
    logical: dict[str, bytes],
    physical: dict[str, bytes],
    duplicates: dict[str, bytes],
    blobs: dict[str, bytes],
    stored: dict[str, Path],
    lock: PackLock,
    old_bytes: bytes | None,
) -> None:
    # Publish all bytes before the index, then remove superseded copies. An interrupted
    # publish leaves readable assets and can be retried from the same logical tree.
    for name, content in blobs.items():
        if name not in stored or stored[name].read_bytes() != content:
            atomic_write(root / BLOB_DIR / name, content)
    for path in logical.keys() - physical.keys() - lock.aliases.keys():
        atomic_write(safe_join(root, path), logical[path])
    lock_bytes = lock.encode()
    if lock_bytes != old_bytes:
        atomic_write(root / LOCK_NAME, lock_bytes)
    for path, content in duplicates.items():
        source = safe_join(root, path)
        if source.read_bytes() != content:
            raise _invalid(path, "asset changed during compilation; retry skm pack compile")
        source.unlink()
    for name in stored.keys() - blobs.keys():
        stored[name].unlink()


def _compile(root: Path, *, check: bool) -> JsonObject:
    previous = read_lock(root, allow_orphan_blobs=True)
    packs = _pack_dirs(root, root)
    if not packs:
        raise _invalid(root, "no pack.toml found under the compile path")
    logical, physical, manifests = _logical_files(root, packs, previous[0] if previous else None)
    lock, blobs = _build_lock(logical, manifests)
    old_bytes = previous[1] if previous else None
    duplicates = {path: physical[path] for path in lock.aliases if path in physical}
    stored = _stored_blobs(root / BLOB_DIR)
    if previous is None and stored.keys() - blobs.keys():
        raise _invalid(root / LOCK_NAME, "compiled pack lock is missing; restore it before compiling")
    if check:
        if (
            duplicates
            or lock.encode() != old_bytes
            or stored.keys() != blobs.keys()
            or any(stored[name].read_bytes() != content for name, content in blobs.items())
        ):
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "compiled packs are out of date; run skm pack compile",
                details={"path": str(root), "uncompiled_paths": list[JsonValue](sorted(duplicates))},
            )
    else:
        _publish(
            root,
            logical=logical,
            physical=physical,
            duplicates=duplicates,
            blobs=blobs,
            stored=stored,
            lock=lock,
            old_bytes=old_bytes,
        )
    return {
        "packs": len(packs),
        "files": len(logical),
        "duplicate_copies": len(lock.aliases) - len(blobs),
        "tree_digest": lock.digest,
    }


def compile_packs(path: Path, *, check: bool = False) -> JsonObject:
    """Compile a pack or collection in place. Check mode acquires a read lock and never writes."""
    if path.is_symlink() or not path.is_dir():
        raise _invalid(path, "pack compile path must be a directory")
    root = path.resolve()
    if root.parent != root and enclosing_lock_root(root.parent) is not None:
        raise _invalid(path, "compile at the enclosing pack lock directory")
    try:
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            fcntl.flock(fd, fcntl.LOCK_SH if check else fcntl.LOCK_EX)
            return _compile(root, check=check)
        finally:
            os.close(fd)
    except UnsafePathError as exc:
        raise _invalid(exc.path, "unsafe path in compiled pack") from exc
    except OSError as exc:
        raise BackendUnavailable(
            ErrorCode.BACKEND_UNAVAILABLE, "could not read or compile packs", details={"path": str(path)}
        ) from exc
