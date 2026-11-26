"""Containment checks for paths supplied by callers; no filesystem mutations."""

import stat
from pathlib import Path, PurePosixPath, PureWindowsPath

from skm.platform.fs.atomic_write import UnsafePathError


def is_within(root: Path, candidate: Path) -> bool:
    return candidate.resolve().is_relative_to(root.resolve())


def safe_join(root: Path, relative: str, *, allow_symlinks: bool = False) -> Path:
    if not relative:
        raise UnsafePathError(relative, "empty")
    if "\0" in relative:
        raise UnsafePathError(relative, "nul")
    path = PurePosixPath(relative)
    windows = PureWindowsPath(relative)
    if path.is_absolute() or windows.drive or windows.root:
        raise UnsafePathError(relative, "absolute")
    depth = 0
    result = root
    for part in path.parts:
        depth += -1 if part == ".." else 1
        if depth < 0:
            raise UnsafePathError(relative, "escapes_root")
        result /= part
        if not allow_symlinks:
            try:
                info = result.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(info.st_mode):
                raise UnsafePathError(result, "symlink")
    if not is_within(root, result):
        raise UnsafePathError(result, "escapes_root")
    return result
