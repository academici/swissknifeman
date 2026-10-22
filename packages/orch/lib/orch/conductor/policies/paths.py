"""Contained instruction paths and bounded, strict UTF-8 reads (no symlink traversal at open time)."""
from __future__ import annotations

import os
from pathlib import Path
import stat
from typing import Iterable, Optional


def has_symlink(path: Path) -> bool:
    """Whether any component of the spelling of ``path`` is a symlink, including a dangling link."""
    path = Path(path).absolute()
    return any(part.is_symlink() for part in (path, *path.parents))


def contained(path: Path, roots: Iterable[Path]) -> Optional[Path]:
    """The existing canonical path inside one lexical root; None on an escape or an unavailable path.

    Roots are authority boundaries, so resolving a root symlink must not silently grant its destination.
    An internal symlink is allowed only while every link along the path stays inside that same root.
    """
    path = Path(path).absolute()
    try:
        resolved = path.resolve(strict=True)
        for root in roots:
            root = Path(root).absolute()
            try:
                relative = path.relative_to(root)
                resolved.relative_to(root)
                if root.resolve(strict=True) != root:
                    continue
                current = root
                for part in relative.parts:
                    current = current / part
                    current.resolve(strict=True).relative_to(root)
                return resolved
            except ValueError:
                continue
    except (OSError, RuntimeError):
        pass
    return None


def read_capped(path: Path, limit: int) -> str:
    """Read at most ``limit`` bytes as UTF-8, preserving exact bytes on re-encoding.

    Stat before opening, and check again through the descriptor; a growing file is read only up to limit + 1.
    Canonical callers already checked containment. Opening every component without following links closes the
    gap where a parent directory or the file is replaced by a symlink after that check.
    """
    path = Path(path).absolute()
    info = os.stat(path, follow_symlinks=False)
    if stat.S_ISLNK(info.st_mode):
        raise ValueError("symlink")
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("outside")
    if info.st_size > limit:
        raise ValueError("too_large")
    directory = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    handle = -1
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        handle = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        info = os.fstat(handle)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("outside")
        if info.st_size > limit:
            raise ValueError("too_large")
        with os.fdopen(handle, "rb") as stream:
            handle = -1
            data = stream.read(limit + 1)
        if len(data) > limit:
            raise ValueError("too_large")
    finally:
        os.close(directory)
        if handle >= 0:
            os.close(handle)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("not_utf8") from None
