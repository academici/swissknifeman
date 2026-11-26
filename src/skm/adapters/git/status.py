"""Binary porcelain and tree entries; display strings never identify a path."""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from skm.modules.execution.domain.output import ChangedPath

if TYPE_CHECKING:
    from .runner import GitRunner

__all__ = ["changed_paths", "decode_path", "display_path", "encode_path", "parse_porcelain", "tree_entries"]


def validate_path(path: bytes) -> bytes:
    if not path or b"\0" in path or any(p in {b"", b".", b".."} for p in path.split(b"/")):
        raise ValueError("invalid relative Git byte path")
    return path


def encode_path(path: bytes) -> str:
    return base64.urlsafe_b64encode(validate_path(path)).decode("ascii").rstrip("=")


def decode_path(encoded: str) -> bytes:
    raw = base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True)
    if encode_path(raw) != encoded:
        raise ValueError("noncanonical byte path")
    return raw


def display_path(path: bytes) -> str:
    try:
        return path.decode("utf-8", "strict")
    except UnicodeDecodeError:
        return path.decode("utf-8", "backslashreplace")


@dataclass(frozen=True)
class StatusPath:
    status: bytes
    path: bytes
    old_path: bytes | None = None


def parse_porcelain(raw: bytes) -> tuple[StatusPath, ...]:
    chunks = iter(raw.split(b"\0"))
    paths: list[StatusPath] = []
    for record in chunks:
        if not record:
            continue
        if len(record) < 4 or record[2:3] != b" ":
            raise ValueError("malformed porcelain record")
        old = next(chunks, b"") if b"R" in record[:2] or b"C" in record[:2] else None
        paths.append(
            StatusPath(record[:2], validate_path(record[3:]), None if old is None else validate_path(old))
        )
    return tuple(sorted(paths, key=lambda p: p.path))


def tree_entries(git: GitRunner, root: Path, commit: str) -> dict[bytes, str]:
    raw = git.run_bytes(root, ["ls-tree", "-r", "-z", commit]).stdout
    result: dict[bytes, str] = {}
    for record in raw.split(b"\0"):
        if not record:
            continue
        header, path = record.split(b"\t", 1)
        mode, kind, oid = header.split(b" ")
        if mode not in {b"100644", b"100755", b"120000"} or kind != b"blob":
            raise ValueError("nested repositories/submodules are unsupported")
        result[validate_path(path)] = (mode + b" " + oid).decode("ascii")
    return result


def changed_paths(
    git: GitRunner, root: Path, base: str, *, head: str | None = None, mount: str = "."
) -> tuple[ChangedPath, ...]:
    from .fingerprint import inventory, path_fingerprint

    before = tree_entries(git, root, base)
    after = (
        tree_entries(git, root, head)
        if head is not None
        else {p: path_fingerprint(root, p, git=git) for p in inventory(git, root)}
    )
    result: list[ChangedPath] = []
    for path in sorted(before.keys() | after.keys()):
        fingerprint = after.get(path, "absent")
        if before.get(path, "absent") == fingerprint:
            continue
        change = "deleted" if fingerprint == "absent" else "modified" if path in before else "added"
        result.append(
            ChangedPath(
                mount,
                display_path(path),
                encode_path(path),
                change,
                None,
                None,
                fingerprint,
            )
        )
    return tuple(result)


def prune_stubs(git: GitRunner, root: Path, stub_paths: tuple[str, ...]) -> None:
    for entry in parse_porcelain(
        git.run_bytes(root, ["status", "--porcelain=v1", "-z", "--untracked-files=all"]).stdout
    ):
        if entry.status != b"??" or display_path(entry.path) not in stub_paths:
            continue
        path = root / os.fsdecode(entry.path)
        info = path.lstat()
        if path.is_file() and not path.is_symlink() and info.st_size == 0 and info.st_mode & 0o222 == 0:
            path.unlink()
