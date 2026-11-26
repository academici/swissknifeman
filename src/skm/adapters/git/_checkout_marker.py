"""Descriptor-relative checkout marker IO shared by Git adapters."""

from __future__ import annotations

import contextlib
import errno
import json
import os
import stat
from collections.abc import Mapping
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import TYPE_CHECKING, Any, NoReturn, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.json_types import JsonValue
from skm.modules.workspace.domain.checkout_marker import marker_from_document
from skm.modules.workspace.ports import MARKER_INVALID

from .runner import validate_repository_trust

if TYPE_CHECKING:
    from skm.modules.workspace.domain.checkout_marker import CheckoutMarker

__all__ = [
    "MARKER_FILENAME",
    "MAX_MARKER_BYTES",
    "read_marker_at",
    "split_marker_relpath",
    "write_marker_bytes_nofollow",
]

MARKER_FILENAME: str = ".skm/project.json"
MAX_MARKER_BYTES: int = 16_384
_UNSUPPORTED_SYNC = {errno.EINVAL, errno.ENOTSUP, errno.EPERM, errno.EISDIR, errno.EBADF}
_DIR_OPEN_FLAGS: int = (
    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
)
_FILE_READ_FLAGS: int = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
_FILE_CREATE_FLAGS: int = (
    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
)


def _unsafe_marker(message: str, **details: JsonValue) -> NoReturn:
    raise ValidationFailed(ErrorCode.REPOSITORY_UNSAFE, message, details=details or None)


def _require_fd_owned_by_current_uid(st: os.stat_result, path: Path) -> None:
    euid = os.geteuid() if hasattr(os, "geteuid") else None
    if euid is not None and st.st_uid != euid:
        _unsafe_marker(
            "checkout marker path is not owned by the current effective UID",
            path=str(path),
            owner_uid=st.st_uid,
            expected_uid=euid,
        )


def _fsync_fd(fd: int) -> None:
    try:
        os.fsync(fd)
    except OSError as exc:
        if exc.errno not in _UNSUPPORTED_SYNC:
            raise


def split_marker_relpath(marker_relpath: str) -> tuple[tuple[str, ...], str]:
    if (
        not marker_relpath
        or "\x00" in marker_relpath
        or "\n" in marker_relpath
        or "\r" in marker_relpath
        or "\\" in marker_relpath
        or marker_relpath.startswith("/")
        or marker_relpath.endswith("/")
    ):
        _unsafe_marker(
            "marker_relpath must be a clean relative POSIX path inside the checkout root",
            marker_relpath=marker_relpath,
        )
    posix = PurePosixPath(marker_relpath)
    windows = PureWindowsPath(marker_relpath)
    if posix.is_absolute() or windows.drive or windows.root:
        _unsafe_marker("marker_relpath must not be an absolute path", marker_relpath=marker_relpath)
    parts = marker_relpath.split("/")
    if not parts or any(part in ("", ".", "..") for part in parts):
        _unsafe_marker(
            "marker_relpath must not contain empty, '.' or '..' segments",
            marker_relpath=marker_relpath,
        )
    return tuple(parts[:-1]), parts[-1]


def _open_marker_parent_fd(
    toplevel: Path,
    parent_segments: tuple[str, ...],
    *,
    create_dirs: bool,
) -> int | None:
    try:
        current_fd = os.open(toplevel, _DIR_OPEN_FLAGS)
    except OSError as exc:
        _unsafe_marker("unable to open checkout root directory safely", path=str(toplevel), errno=exc.errno)

    current_path = toplevel
    try:
        root_st = os.fstat(current_fd)
        if not stat.S_ISDIR(root_st.st_mode):
            _unsafe_marker("checkout root is not a directory", path=str(toplevel))
        _require_fd_owned_by_current_uid(root_st, toplevel)

        for seg in parent_segments:
            current_path = current_path / seg
            created = False
            try:
                next_fd = os.open(seg, _DIR_OPEN_FLAGS, dir_fd=current_fd)
            except FileNotFoundError:
                if not create_dirs:
                    os.close(current_fd)
                    return None
                try:
                    os.mkdir(seg, 0o700, dir_fd=current_fd)
                    created = True
                    next_fd = os.open(seg, _DIR_OPEN_FLAGS, dir_fd=current_fd)
                except OSError as mkdir_exc:
                    _unsafe_marker(
                        "unable to create or open intermediate checkout marker directory safely",
                        path=str(current_path),
                        errno=mkdir_exc.errno,
                    )
            except OSError as open_exc:
                _unsafe_marker(
                    "intermediate checkout marker path component is not a safe directory",
                    path=str(current_path),
                    errno=open_exc.errno,
                )

            try:
                seg_st = os.fstat(next_fd)
                if not stat.S_ISDIR(seg_st.st_mode):
                    _unsafe_marker(
                        "intermediate checkout marker path component is not a directory",
                        path=str(current_path),
                    )
                _require_fd_owned_by_current_uid(seg_st, current_path)
                if created:
                    os.fchmod(next_fd, 0o700)
                    _fsync_fd(current_fd)
            except BaseException:
                os.close(next_fd)
                raise

            os.close(current_fd)
            current_fd = next_fd
    except BaseException:
        os.close(current_fd)
        raise
    else:
        return current_fd


def _read_open_marker_fd(fd: int, marker_path: Path) -> bytes:
    open_st = os.fstat(fd)
    if not stat.S_ISREG(open_st.st_mode):
        _unsafe_marker("checkout marker must be a regular file", path=str(marker_path))
    _require_fd_owned_by_current_uid(open_st, marker_path)
    if open_st.st_size > MAX_MARKER_BYTES:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "checkout marker exceeds 16 KiB limit",
            details={"diagnostic": MARKER_INVALID, "size": open_st.st_size, "max_bytes": MAX_MARKER_BYTES},
        )
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = os.read(fd, MAX_MARKER_BYTES + 1 - total)
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > MAX_MARKER_BYTES:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "checkout marker exceeds 16 KiB limit",
                details={"diagnostic": MARKER_INVALID, "max_bytes": MAX_MARKER_BYTES},
            )
    return b"".join(chunks)


def _read_marker_bytes_nofollow(
    toplevel: Path, parent_segments: tuple[str, ...], leaf_name: str
) -> bytes | None:
    marker_path = toplevel.joinpath(*parent_segments, leaf_name)
    parent_fd = _open_marker_parent_fd(toplevel, parent_segments, create_dirs=False)
    if parent_fd is None:
        return None

    try:
        try:
            leaf_st = os.stat(leaf_name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            return None
        except OSError as exc:
            _unsafe_marker("unable to inspect checkout marker", path=str(marker_path), errno=exc.errno)

        if stat.S_ISLNK(leaf_st.st_mode) or not stat.S_ISREG(leaf_st.st_mode):
            _unsafe_marker("checkout marker must be a non-symlink regular file", path=str(marker_path))
        _require_fd_owned_by_current_uid(leaf_st, marker_path)

        try:
            fd = os.open(leaf_name, _FILE_READ_FLAGS, dir_fd=parent_fd)
        except OSError as exc:
            _unsafe_marker("unable to open checkout marker safely", path=str(marker_path), errno=exc.errno)

        try:
            return _read_open_marker_fd(fd, marker_path)
        finally:
            os.close(fd)
    finally:
        os.close(parent_fd)


def _assert_safe_leaf_target(parent_fd: int, leaf_name: str, marker_path: Path) -> None:
    try:
        leaf_st = os.stat(leaf_name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    except OSError as exc:
        _unsafe_marker(
            "unable to inspect checkout marker destination",
            path=str(marker_path),
            errno=exc.errno,
        )

    if stat.S_ISLNK(leaf_st.st_mode) or not stat.S_ISREG(leaf_st.st_mode) or leaf_st.st_nlink != 1:
        _unsafe_marker(
            "checkout marker destination must be a non-symlink regular file without hardlinks",
            path=str(marker_path),
        )
    _require_fd_owned_by_current_uid(leaf_st, marker_path)


def write_marker_bytes_nofollow(toplevel: Path, marker_relpath: str, payload: bytes) -> None:
    parent_segments, leaf_name = split_marker_relpath(marker_relpath)
    marker_path = toplevel.joinpath(*parent_segments, leaf_name)
    parent_fd = _open_marker_parent_fd(toplevel, parent_segments, create_dirs=True)
    if parent_fd is None:
        _unsafe_marker("unable to resolve checkout marker parent directory", path=str(marker_path))

    try:
        _assert_safe_leaf_target(parent_fd, leaf_name, marker_path)
        tmp_name = f".{leaf_name}.{os.getpid()}.{os.urandom(4).hex()}.tmp"
        try:
            fd = os.open(tmp_name, _FILE_CREATE_FLAGS, 0o600, dir_fd=parent_fd)
        except OSError as exc:
            _unsafe_marker(
                "unable to create temporary checkout marker file safely",
                path=str(marker_path),
                errno=exc.errno,
            )

        try:
            view = memoryview(payload)
            written = 0
            while written < len(view):
                n = os.write(fd, view[written:])
                if n <= 0:
                    raise OSError(errno.EIO, "short write to checkout marker temp file")
                written += n
            os.fchmod(fd, 0o600)
            os.fsync(fd)
        except BaseException:
            os.close(fd)
            with contextlib.suppress(OSError):
                os.unlink(tmp_name, dir_fd=parent_fd)
            raise
        os.close(fd)

        try:
            _assert_safe_leaf_target(parent_fd, leaf_name, marker_path)
            os.replace(tmp_name, leaf_name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
            _fsync_fd(parent_fd)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp_name, dir_fd=parent_fd)
            raise
    finally:
        os.close(parent_fd)


def read_marker_at(
    toplevel: str | Path, *, marker_relpath: str = MARKER_FILENAME, checkout_root: Path | None = None
) -> CheckoutMarker | None:
    """Read and validate ``<toplevel>/<marker_relpath>`` via descriptor-relative ``O_NOFOLLOW``."""
    parent_segments, leaf_name = split_marker_relpath(marker_relpath)
    validate_repository_trust(toplevel, checkout_root=checkout_root)
    top_path = Path(os.path.normpath(str(toplevel)))
    raw_bytes = _read_marker_bytes_nofollow(top_path, parent_segments, leaf_name)
    if raw_bytes is None:
        return None
    try:
        parsed = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "checkout marker is not valid JSON",
            details={"diagnostic": MARKER_INVALID},
        ) from exc
    if not isinstance(parsed, Mapping):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "checkout marker document must be a JSON object",
            details={"diagnostic": MARKER_INVALID},
        )
    return marker_from_document(cast(Mapping[str, Any], parsed))
