"""POSIX flock tied to a current inode and the acquiring process/thread."""

import errno
import fcntl
import os
import stat
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

_registry_guard = threading.Lock()
_held: dict[tuple[int, int], tuple[int, int]] = {}  # inode -> (thread, fd)


def _before_fork() -> None:
    _registry_guard.acquire()


def _parent_after_fork() -> None:
    _registry_guard.release()


def _after_fork() -> None:
    global _registry_guard  # noqa: PLW0603 - a child must not inherit a locked thread mutex
    # Closing the child's copies does not unlock the parent's open file description.
    for _, fd in _held.values():
        os.close(fd)
    _held.clear()
    _registry_guard = threading.Lock()


os.register_at_fork(before=_before_fork, after_in_parent=_parent_after_fork, after_in_child=_after_fork)


class LockTimeout(Exception):
    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"lock timeout: {path}")


class FileLock:
    def __init__(self, path: Path, *, create: bool = True, readonly: bool = False) -> None:
        self.path, self.create, self.readonly = Path(path), create, readonly
        self.fd: int | None = None
        self._owner: tuple[int, int] | None = None
        self._inode: tuple[int, int] | None = None
        self._releasing = False

    def _try_lock(self, fd: int) -> bool | None:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError(f"lock is not a regular file: {self.path}")
        inode = (info.st_dev, info.st_ino)
        thread = threading.get_ident()
        with _registry_guard:
            held = _held.get(inode)
            if held is not None and held[0] == thread:
                raise RuntimeError("lock already held by this thread")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                if error.errno in (errno.EAGAIN, errno.EACCES):
                    return False
                raise
            try:
                current = os.path.samestat(info, self.path.lstat())
            except FileNotFoundError:
                current = False
            if not current:
                return None
            _held[inode] = (thread, fd)
            self.fd, self._inode, self._owner = fd, inode, (os.getpid(), thread)
            self._releasing = False
            return True

    def acquire(
        self, *, blocking: bool = False, timeout_seconds: float | None = None, poll_seconds: float = 0.02
    ) -> bool:
        if self._owner is not None and self._owner[0] != os.getpid():
            self.fd, self._owner, self._inode = None, None, None
        if self.fd is not None:
            raise RuntimeError(
                "lock already held by this thread"
                if self._owner == (os.getpid(), threading.get_ident())
                else "lock object already acquired"
            )
        if poll_seconds <= 0 or (timeout_seconds is not None and timeout_seconds < 0):
            raise ValueError("invalid lock timeout/poll")
        deadline = None if timeout_seconds is None else time.monotonic() + timeout_seconds
        while True:
            flags = (os.O_RDONLY if self.readonly else os.O_RDWR) | os.O_CLOEXEC | os.O_NOFOLLOW
            fd = os.open(self.path, flags | (os.O_CREAT if self.create else 0), 0o600)
            try:
                acquired = self._try_lock(fd)
                if acquired:
                    return True
            except BaseException as primary:
                try:
                    os.close(fd)
                except OSError as error:
                    primary.add_note(f"lock descriptor close failed for {self.path}: {error}")
                raise
            os.close(fd)
            if (not blocking and acquired is False) or (
                deadline is not None and time.monotonic() >= deadline
            ):
                return False
            if acquired is False:
                time.sleep(
                    poll_seconds
                    if deadline is None
                    else min(poll_seconds, max(0, deadline - time.monotonic()))
                )

    def assert_owned_for(self, path: Path) -> None:
        if self.fd is None or self._releasing or self._owner != (os.getpid(), threading.get_ident()):
            raise RuntimeError("lock is not owned by this process/thread")
        held = os.fstat(self.fd)
        if not os.path.samestat(held, self.path.lstat()) or not os.path.samestat(held, path.lstat()):
            raise RuntimeError("lock resource identity changed or mismatched")

    def release(self) -> None:
        if self.fd is None:
            return
        if self._owner is not None and self._owner[0] != os.getpid():
            self.fd, self._owner, self._inode = None, None, None
            return
        if self._owner != (os.getpid(), threading.get_ident()):
            raise RuntimeError("lock is not owned by this process/thread")
        fd, inode, owner = self.fd, self._inode, self._owner
        self._releasing = True
        primary: OSError | None = None
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError as error:
            primary = error
        with _registry_guard:
            still_open = False
            try:
                os.close(fd)
            except OSError as error:
                if primary is None:
                    primary = error
                else:
                    primary.add_note(f"lock close failed for {self.path}: {error}")
                try:
                    info = os.fstat(fd)
                    still_open = (info.st_dev, info.st_ino) == inode
                except OSError as probe:
                    still_open = probe.errno != errno.EBADF
                    if still_open:
                        primary.add_note(f"lock close outcome unknown for {self.path}: {probe}")
            if not still_open:
                self.fd, self._inode, self._owner = None, None, None
                # A waiting thread may already own the inode after LOCK_UN.
                if inode is not None and owner is not None and _held.get(inode) == (owner[1], fd):
                    _held.pop(inode, None)
        if primary is not None:
            raise primary

    @contextmanager
    def hold(self, *, timeout_seconds: float | None) -> Generator["FileLock"]:
        if not self.acquire(blocking=True, timeout_seconds=timeout_seconds):
            raise LockTimeout(self.path)
        try:
            yield self
        except BaseException as primary:
            try:
                self.release()
            except OSError as error:
                primary.add_note(f"lock release failed for {self.path}: {error}")
                for note in getattr(error, "__notes__", ()):
                    primary.add_note(note)
            raise
        else:
            self.release()
