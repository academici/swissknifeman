"""Durable same-directory replacement with explicit secondary cleanup diagnostics."""

import errno
import os
import stat
from contextlib import ExitStack
from pathlib import Path
from typing import Literal

type UnsafeReason = Literal["symlink", "not_regular", "hard_link", "escapes_root", "absolute", "nul", "empty"]


class UnsafePathError(ValueError):
    def __init__(self, path: Path | str, reason: UnsafeReason) -> None:
        self.path, self.reason = Path(path), reason
        super().__init__(f"{path}: unsafe path ({reason})")


# A reading of nlink 0 means another writer completed a replace between the lookup and the attribute copy.
# Concurrent writers finish, so this only bounds a replace loop that never stops.
_UNLINKED_RETRIES = 1000


def assert_safe_replace_target(path: Path, *, dir_fd: int | None = None) -> None:
    for _ in range(_UNLINKED_RETRIES):
        try:
            info = path.lstat() if dir_fd is None else os.stat(path, dir_fd=dir_fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        if stat.S_ISLNK(info.st_mode):
            raise UnsafePathError(path, "symlink")
        if not stat.S_ISREG(info.st_mode):
            raise UnsafePathError(path, "not_regular")
        if info.st_nlink == 0:
            # A concurrent replace unlinked the inode while lstat copied its
            # attributes. Let the writer finish, then validate the current entry.
            os.sched_yield()
            continue
        if info.st_nlink != 1:
            raise UnsafePathError(path, "hard_link")
        return
    raise UnsafePathError(path, "hard_link")


_UNSUPPORTED_SYNC = {errno.EINVAL, errno.ENOTSUP, errno.EPERM, errno.EISDIR, errno.EBADF}


def fsync_dir(folder: Path, *, strict: bool = False) -> None:
    try:
        fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    except OSError as error:
        if not strict and error.errno in _UNSUPPORTED_SYNC:
            return
        raise
    primary: BaseException | None = None
    try:
        os.fsync(fd)
    except BaseException as error:
        if strict or not isinstance(error, OSError) or error.errno not in _UNSUPPORTED_SYNC:
            primary = error
            raise
    finally:
        try:
            os.close(fd)
        except OSError as error:
            if primary is None:
                raise
            primary.add_note(f"directory close failed for {folder}: {error}")


def _write_temp(fd: int, data: bytes) -> None:
    try:
        stream = os.fdopen(fd, "wb")
    except BaseException as primary:
        try:
            os.close(fd)
        except OSError as error:
            primary.add_note(f"temp descriptor close failed: {error}")
        raise
    try:
        if stream.write(data) != len(data):
            raise OSError(errno.EIO, "short buffered write")
        stream.flush()
        os.fsync(stream.fileno())
    except BaseException as primary:
        try:
            stream.close()
        except OSError as error:
            primary.add_note(f"temp close failed: {error}")
        raise
    else:
        stream.close()


def atomic_write(
    path: Path,
    data: bytes,
    *,
    mode: int | None = None,
    private: bool = False,
    check_target: bool = True,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if check_target:
        assert_safe_replace_target(path)
    temp = path.with_name(f".{path.name}.{os.getpid()}.{os.urandom(4).hex()}.tmp")
    # Do not unlink a pre-existing entry if exclusive creation itself fails. An explicit mode is applied
    # only after the write, so until then the bytes stay owner-only rather than umask-wide.
    initial = 0o600 if private or mode is not None else 0o666
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, initial)
    try:
        _write_temp(fd, data)
        if mode is not None:
            os.chmod(temp, mode)
        if check_target:
            assert_safe_replace_target(path)
        os.replace(temp, path)
        fsync_dir(path.parent)
    except BaseException as primary:
        try:
            os.unlink(temp)
        except FileNotFoundError:
            pass
        except OSError as error:
            primary.add_note(f"temp cleanup failed; recovery required for {temp}: {error}")
        raise


def _open_parent(path: Path, stack: ExitStack) -> int:
    directory = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open(path.anchor, directory)
    stack.callback(os.close, fd)
    for part in path.parts[1:-1]:
        try:
            fd = os.open(part, directory, dir_fd=fd)
        except OSError as exc:
            if exc.errno in (errno.ELOOP, errno.ENOTDIR):
                raise UnsafePathError(path, "escapes_root") from exc
            raise
        stack.callback(os.close, fd)
    return fd


def atomic_write_nofollow(destination: str, data: bytes) -> None:
    """Replace a file under existing directories, with every operation anchored to its parent fd."""
    if "\x00" in destination:
        raise UnsafePathError(destination, "nul")
    if not destination.startswith("/") or any(part in {"", ".", ".."} for part in destination[1:].split("/")):
        raise UnsafePathError(destination, "escapes_root")
    path = Path(destination)
    name = Path(path.name)
    with ExitStack() as stack:
        parent = _open_parent(path, stack)
        assert_safe_replace_target(name, dir_fd=parent)
        temp = f".skm-write.{os.urandom(16).hex()}.tmp"
        fd = os.open(
            temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=parent
        )
        stack.callback(os.close, fd)
        try:
            _write_temp(os.dup(fd), data)
            with ExitStack() as check:
                current_parent = _open_parent(path, check)
                if not os.path.samestat(os.fstat(parent), os.fstat(current_parent)):
                    raise UnsafePathError(path, "escapes_root")
                assert_safe_replace_target(name, dir_fd=parent)
                staged = os.stat(temp, dir_fd=parent, follow_symlinks=False)
                if staged.st_nlink != 1 or not os.path.samestat(staged, os.fstat(fd)):
                    raise UnsafePathError(path, "not_regular")
                os.replace(temp, name, src_dir_fd=parent, dst_dir_fd=parent)
            try:
                os.fsync(parent)
            except OSError as error:
                if error.errno not in _UNSUPPORTED_SYNC:
                    raise
        except BaseException as primary:
            try:
                os.unlink(temp, dir_fd=parent)
            except FileNotFoundError:
                pass
            except OSError as error:
                primary.add_note(f"temp cleanup failed for {path}: {error}")
            raise
