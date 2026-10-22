"""Advisory file locks (POSIX ``flock``) shared by every module. Lock files are never unlinked.

Protocol: the lock file is opened ``O_CLOEXEC|O_NOFOLLOW`` (0600), ``flock(LOCK_EX|LOCK_NB)`` is taken in a loop, and
the descriptor counts only while ``os.path.samestat(fstat(fd), stat(path))`` holds: a lock file replaced or removed
between ``open`` and ``flock`` guards a dead inode, so the lock is taken again on the new file. Release is ``LOCK_UN``
then ``close``. stdlib only.
"""
from __future__ import annotations

import errno
import fcntl
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

DEFAULT_POLL_S = 0.02
_BUSY = (errno.EAGAIN, errno.EACCES)  # EWOULDBLOCK == EAGAIN


class LockTimeout(Exception):
    """A lock stayed busy for the whole timeout; ``code`` is the reason code and ``path`` the lock file."""

    def __init__(self, code: str, path):
        self.code, self.path = code, Path(path)
        super().__init__(f"{code}: {self.path} is held by another process")


class FileLock:
    """A flock on the inode currently at ``path``, on a descriptor closed by exec."""

    def __init__(self, path, *, create: bool = True, readonly: bool = False):
        # ``readonly`` opens the lock file O_RDONLY: flock works on it, so a probe needs no write access
        self.path, self.create, self.readonly, self.fd = Path(path), create, readonly, None

    def acquire(self, blocking: bool = False, timeout: Optional[float] = None, poll: float = DEFAULT_POLL_S) -> bool:
        """``True`` when held. A busy lock gives ``False`` at once (not ``blocking``) or after ``timeout`` seconds
        (``None``: wait for ever). ``OSError`` for anything but a busy lock (a symlink, a missing file, no access)."""
        if self.fd is not None:
            raise RuntimeError("lock already acquired")
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            flags = (os.O_RDONLY if self.readonly else os.O_RDWR) | os.O_CLOEXEC | os.O_NOFOLLOW
            fd = os.open(self.path, flags | (os.O_CREAT if self.create else 0), 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                try:
                    current = os.path.samestat(os.fstat(fd), os.stat(self.path))
                except FileNotFoundError:
                    current = False
                if current:
                    self.fd = fd
                    return True
            except OSError as error:
                if error.errno not in _BUSY:
                    raise
                if not blocking or (deadline is not None and time.monotonic() >= deadline):
                    return False
                time.sleep(poll)
            finally:
                if self.fd != fd:
                    os.close(fd)
            # A replaced inode is retried even for a nonblocking acquisition.
            if deadline is not None and time.monotonic() >= deadline:
                return False

    def release(self) -> None:
        if self.fd is not None:
            fd, self.fd = self.fd, None
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

    @contextmanager
    def hold(self, *, timeout: Optional[float], poll: float = DEFAULT_POLL_S, code: str = "LOCK_TIMEOUT") -> Iterator["FileLock"]:
        """Hold the lock for the block, waiting up to ``timeout`` seconds; ``LockTimeout(code, path)`` when it stays busy."""
        if not self.acquire(blocking=True, timeout=timeout, poll=poll):
            raise LockTimeout(code, self.path)
        try:
            yield self
        finally:
            self.release()


@contextmanager
def hold(path, *, timeout: Optional[float], poll: float = DEFAULT_POLL_S, code: str = "LOCK_TIMEOUT") -> Iterator[FileLock]:
    """``FileLock(path)`` held for the block (see :meth:`FileLock.hold`)."""
    with FileLock(path).hold(timeout=timeout, poll=poll, code=code) as lock:
        yield lock


def lock_descriptor(fd: int, *, timeout: float = 0.0, poll: float = DEFAULT_POLL_S) -> bool:
    """``flock(LOCK_EX)`` on an open descriptor (a directory, say) that the caller owns: ``True`` when taken within
    ``timeout`` seconds, ``False`` when it stays busy. Closing the descriptor releases the lock. No inode check: the
    caller opened the object and keeps it open."""
    deadline = time.monotonic() + max(timeout, 0.0)
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError as error:
            if error.errno not in _BUSY:
                raise
        if time.monotonic() >= deadline:
            return False
        time.sleep(poll)


def probe_free(path) -> Optional[bool]:
    """Probe on a separate read-only fd without creating a file or changing owner metadata: ``True`` free (a missing
    lock file is free too), ``False`` held, ``None`` when the lock file cannot be opened (a read-only context that may
    not even read it)."""
    lock = FileLock(path, create=False, readonly=True)
    try:
        return lock.acquire()
    except FileNotFoundError:
        return True
    except OSError:
        return None
    finally:
        lock.release()
