"""``aicore project migrate``: move the project layer out of the checkout into ``projects/<code>/local/`` of the workspace.

A launcher-only checkout keeps ``.swissknifeman/launcher.py`` (with its lock) and ``project.json`` and nothing else of the
project layer. An older checkout may still hold ``config.toml``, ``state/``, ``backups/`` and ``stubs/`` there; :func:`plan`
lists what would move and :func:`apply` moves it. A file is never overwritten: one that is already in ``local/`` with the same
bytes is dropped from the checkout, one with other bytes is a conflict and both copies stay. A symbolic link is refused.
"""
from __future__ import annotations

import errno
import fcntl
import os
import shutil
import stat
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping

from aicore.state import LauncherError
from aicore.state.locations import PROJECT_DIRNAME, project_local_dir
from aicore.workspace import ensure_local

#: Names in ``<checkout>/.swissknifeman/`` that belong to the project layer and move to ``local/`` (same names there).
MOVABLE = ("config.toml", "state", "backups", "stubs")
CONFIG_MODE = 0o600


def leftovers(root: Path) -> List[str]:
    """The names of :data:`MOVABLE` that exist in the checkout (a symbolic link counts)."""
    base = Path(root) / PROJECT_DIRNAME
    return [name for name in MOVABLE if os.path.lexists(base / name)]


def _local(root: Path, env: Mapping[str, str]) -> Path:
    local = project_local_dir(root, env=env)
    if local is None:
        raise LauncherError("PROJECT_LOCAL_UNAVAILABLE",
                            f"{root} has no .swissknifeman/project.json, or the workspace it names has no folder for the "
                            f"project on this machine; run `swissknifeman workspace project attach` first")
    if local.is_symlink():
        raise LauncherError("PROJECT_LOCAL_UNAVAILABLE", f"{local} is a symbolic link")
    return local


def _same(first: Path, second: Path) -> bool:
    try:
        return first.read_bytes() == second.read_bytes()
    except OSError:
        return False


def _entries(source: Path, target: Path, relative: str, items: List[Dict[str, Any]]) -> None:
    """Append one item per file of ``source`` (a file or a folder): ``move``, ``drop`` (identical copy already there),
    ``conflict`` or ``refused`` (symbolic link)."""
    if source.is_symlink():
        items.append({"path": relative, "action": "refused", "code": "PROJECT_MIGRATE_SYMLINK",
                      "reason": "a symbolic link is not moved"})
    elif source.is_dir():
        if os.path.lexists(target) and (target.is_symlink() or not target.is_dir()):
            items.append({"path": relative, "action": "conflict",
                          "reason": "local/ holds a link or a file in the place of a folder"})
            return
        for child in sorted(source.iterdir(), key=lambda entry: entry.name):
            _entries(child, target / child.name, f"{relative}/{child.name}", items)
    elif not os.path.lexists(target):
        items.append({"path": relative, "action": "move"})
    elif target.is_file() and not target.is_symlink() and _same(source, target):
        items.append({"path": relative, "action": "drop"})
    else:
        items.append({"path": relative, "action": "conflict", "reason": "local/ holds a different file of that name"})


def plan(root: Path, env: Mapping[str, str]) -> Dict[str, Any]:
    """``{local, items: [{path, action, code?, reason?}]}``: what :func:`apply` does. ``PROJECT_LOCAL_UNAVAILABLE`` when the
    checkout is not tied to a workspace project folder on this machine."""
    root = Path(root)
    local = _local(root, env)
    base = root / PROJECT_DIRNAME
    items: List[Dict[str, Any]] = []
    for name in leftovers(root):
        _entries(base / name, local / name, name, items)
    return {"local": str(local), "items": items}


def _prune(folder: Path) -> None:
    """Remove ``folder`` and the empty folders under it; a folder that still holds a file stays."""
    if folder.is_symlink() or not folder.is_dir():
        return
    for child in folder.iterdir():
        _prune(child)
    try:
        folder.rmdir()
    except OSError:
        pass


_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
_NO_LINK = (errno.EXDEV, errno.EPERM, errno.EMLINK, errno.ENOTSUP, errno.EOPNOTSUPP, errno.ENOSYS)
LOCK_TIMEOUT_S = 10.0
_POLL_S = 0.05


def _lock(fd: int) -> None:
    """Hold ``flock(LOCK_EX)`` on the descriptor of ``local/`` (closing the descriptor releases it)."""
    deadline = time.monotonic() + LOCK_TIMEOUT_S
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except OSError:
            if time.monotonic() >= deadline:
                raise LauncherError("PROJECT_MIGRATE_LOCKED", f"another process is migrating this project (waited "
                                    f"{LOCK_TIMEOUT_S:g} s); try again") from None
            time.sleep(_POLL_S)


def _open_parent(root_fd: int, parts: List[str]) -> int:
    """A descriptor of the folder ``local/<parts>`` made component by component without following a symbolic link (the
    missing ones are created); ``OSError`` (``ELOOP``, ``ENOTDIR``) when a component is a link or a file."""
    fd = os.dup(root_fd)
    try:
        for part in parts:
            try:
                inner = os.open(part, _DIR_FLAGS, dir_fd=fd)
            except FileNotFoundError:
                os.mkdir(part, 0o700, dir_fd=fd)
                inner = os.open(part, _DIR_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = inner
    except BaseException:
        os.close(fd)
        raise
    return fd


def _same_at(source: Path, folder_fd: int, name: str) -> bool:
    """Whether ``name`` in the folder is a regular file (not a link) with the bytes of ``source``."""
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0), dir_fd=folder_fd)
        with os.fdopen(fd, "rb") as handle:
            return stat.S_ISREG(os.fstat(handle.fileno()).st_mode) and handle.read() == source.read_bytes()
    except OSError:
        return False


def _place(source: Path, folder_fd: int, name: str) -> bool:
    """Put ``source`` at ``name`` in the folder without replacing anything: a hard link (a copy across devices) that fails
    when the name is taken. ``False`` when the name is taken; the source stays until the caller removes it."""
    try:
        os.link(source, name, dst_dir_fd=folder_fd, follow_symlinks=False)
        return True
    except FileExistsError:
        return False
    except OSError as exc:
        if exc.errno not in _NO_LINK:
            raise
    info = source.lstat()
    try:
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0), 0o600,
                     dir_fd=folder_fd)
    except FileExistsError:
        return False
    try:
        with os.fdopen(fd, "wb") as out, source.open("rb") as handle:
            shutil.copyfileobj(handle, out)
            os.fchmod(out.fileno(), stat.S_IMODE(info.st_mode))
            os.utime(out.fileno(), ns=(info.st_atime_ns, info.st_mtime_ns))
    except BaseException:
        os.unlink(name, dir_fd=folder_fd)
        raise
    return True


def _carry(base: Path, root_fd: int, item: Dict[str, Any]) -> Dict[str, Any]:
    """Do one ``move``/``drop`` item against what ``local/`` holds now (the plan may be old): nothing there is moved, an
    identical file is dropped from the checkout, anything else is a ``conflict`` and both copies stay."""
    relative = item["path"]
    parts = relative.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise LauncherError("PROJECT_MIGRATE_PATH", f"{relative!r} is not a path inside the project layer")
    source = base / relative
    if source.is_symlink() or not source.is_file():
        return {**item, "action": "conflict", "reason": "the file in the checkout changed since the plan"}
    try:
        folder_fd = _open_parent(root_fd, parts[:-1])
    except OSError as exc:
        if exc.errno not in (errno.ELOOP, errno.ENOTDIR, errno.EEXIST):
            raise
        return {**item, "action": "conflict", "reason": "local/ holds a link or a file in the place of a folder"}
    try:
        if _place(source, folder_fd, parts[-1]):
            source.unlink()
            if relative == "config.toml":
                fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0), dir_fd=folder_fd)
                try:
                    os.fchmod(fd, CONFIG_MODE)
                finally:
                    os.close(fd)
            return {**item, "action": "move"}
        if _same_at(source, folder_fd, parts[-1]):
            source.unlink()
            return {**item, "action": "drop"}
        return {**item, "action": "conflict", "reason": "local/ holds a different file of that name"}
    finally:
        os.close(folder_fd)


def apply(root: Path, result: Dict[str, Any]) -> Dict[str, Any]:
    """Carry out a :func:`plan` result under a lock on ``local/``. Each item is checked again just before it is done and no
    file is ever replaced: a hard link that fails when the name is taken (a copy across devices), then the source is
    removed; a name taken or turned into a link since the plan makes the item a ``conflict`` and both copies stay. A failure
    stops the run and the files already moved stay moved (run it again: the rest is still listed)."""
    base = Path(root) / PROJECT_DIRNAME
    local = Path(result["local"])
    ensure_local(local.parents[2], local.parent.name)
    try:
        root_fd = os.open(local, _DIR_FLAGS)
    except OSError as exc:
        raise LauncherError("PROJECT_LOCAL_UNAVAILABLE", f"{local} is not a folder (or is a symbolic link): "
                            f"{exc.strerror or exc.__class__.__name__}") from None
    items: List[Dict[str, Any]] = []
    try:
        _lock(root_fd)
        for item in result["items"]:
            items.append(_carry(base, root_fd, item) if item["action"] in ("move", "drop") else item)
    finally:
        os.close(root_fd)
    for name in MOVABLE:
        if name != "config.toml":
            _prune(base / name)
    return {**result, "items": items, "applied": True, "remaining": leftovers(root)}


def run(root: Path, env: Mapping[str, str], *, dry_run: bool = False) -> Dict[str, Any]:
    """Plan and (unless ``dry_run``) apply; the result of :func:`plan` plus ``applied`` and ``remaining`` after a run."""
    result = plan(root, env)
    if dry_run or not any(item["action"] in ("move", "drop") for item in result["items"]):
        return {**result, "applied": False, "remaining": leftovers(root)}
    return apply(root, result)
