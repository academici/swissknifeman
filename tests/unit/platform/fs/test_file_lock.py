import errno
import fcntl
import multiprocessing
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from skm.platform.fs.file_lock import FileLock, LockTimeout


def test_reentrant_alias_and_resource_ownership(tmp_path: Path) -> None:
    path = tmp_path / "lock"
    lock = FileLock(path)
    with lock.hold(timeout_seconds=1):
        assert lock.fd is not None
        assert not os.get_inheritable(lock.fd)
        lock.assert_owned_for(path)
        alias = tmp_path / "alias"
        os.link(path, alias)
        for candidate in (lock, FileLock(path), FileLock(alias)):
            with pytest.raises(RuntimeError, match="already held by this thread"):
                candidate.acquire(blocking=True, timeout_seconds=None)
        other = tmp_path / "other"
        other.touch()
        with pytest.raises(RuntimeError, match="mismatched"):
            lock.assert_owned_for(other)
    lock.release()
    assert path.exists()
    with pytest.raises(RuntimeError, match="not owned"):
        lock.assert_owned_for(path)


def test_thread_timeout_and_wrong_owner(tmp_path: Path) -> None:
    path = tmp_path / "lock"
    with FileLock(path).hold(timeout_seconds=1) as lock:

        def other_thread() -> None:
            assert not FileLock(path).acquire()
            with pytest.raises(LockTimeout) as caught, FileLock(path).hold(timeout_seconds=0.03):
                pytest.fail("busy lock entered")
            assert caught.value.path == path
            for operation in (lock.release, lambda: lock.assert_owned_for(path)):
                with pytest.raises(RuntimeError, match="not owned"):
                    operation()

        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(other_thread).result(timeout=3)


@pytest.mark.parametrize("removed", [False, True])
def test_replaced_or_removed_inode_retried_even_nonblocking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, removed: bool
) -> None:
    path = tmp_path / "lock"
    flock = fcntl.flock
    changed = False

    def replace(fd: int, flags: int) -> None:
        nonlocal changed
        flock(fd, flags)
        if not changed:
            changed = True
            path.rename(tmp_path / "old")
            if not removed:
                path.touch()

    monkeypatch.setattr(fcntl, "flock", replace)
    lock = FileLock(path)
    try:
        assert lock.acquire()
        assert lock.fd is not None
        assert os.path.samestat(os.fstat(lock.fd), path.stat())
    finally:
        lock.release()


def test_symlink_and_readonly_probe(tmp_path: Path) -> None:
    path, link = tmp_path / "lock", tmp_path / "link"
    with pytest.raises(FileNotFoundError):
        FileLock(path, create=False, readonly=True).acquire()
    path.touch()
    link.symlink_to(path)
    with pytest.raises(OSError, match="Too many levels"):
        FileLock(link).acquire()
    lock = FileLock(path, create=False, readonly=True)
    assert lock.acquire()
    lock.release()


def test_unlock_and_close_errors_preserve_body_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    primary = ValueError("body failed")
    flock, close = fcntl.flock, os.close

    def bad_unlock(fd: int, flags: int) -> None:
        if flags == fcntl.LOCK_UN:
            raise OSError(errno.EIO, "unlock")
        flock(fd, flags)

    def bad_close(fd: int) -> None:
        close(fd)
        raise OSError(errno.EBADF, "close")

    def body() -> None:
        with FileLock(tmp_path / "lock").hold(timeout_seconds=1):
            monkeypatch.setattr(fcntl, "flock", bad_unlock)
            monkeypatch.setattr(os, "close", bad_close)
            raise primary

    with pytest.raises(ValueError, match="body failed") as caught:
        body()
    assert caught.value is primary
    assert "release" in " ".join(caught.value.__notes__)


def test_waiting_thread_acquires_after_release(tmp_path: Path) -> None:
    ready = threading.Event()
    path = tmp_path / "lock"

    def worker() -> bool:
        ready.set()
        with FileLock(path).hold(timeout_seconds=2):
            return True

    with ThreadPoolExecutor(max_workers=1) as pool:
        with FileLock(path).hold(timeout_seconds=1):
            result = pool.submit(worker)
            assert ready.wait(timeout=1)
            assert not result.done()
        assert result.result(timeout=3)


def test_killed_process_releases_lock_and_fork_does_not_unlock_parent(tmp_path: Path) -> None:
    ctx = multiprocessing.get_context("fork")
    parent, child = ctx.Pipe()
    path = tmp_path / "lock"

    def holder() -> None:
        with FileLock(path).hold(timeout_seconds=1):
            child.send(True)
            child.recv()

    process = ctx.Process(target=holder)
    process.start()
    try:
        assert parent.poll(3)
        assert parent.recv()
        assert not FileLock(path).acquire()
    finally:
        process.kill()
        process.join(timeout=3)
        child.close()
        parent.close()
    with FileLock(path).hold(timeout_seconds=1) as owned:

        def inherited() -> None:
            owned.release()
            assert not FileLock(path).acquire()

        process = ctx.Process(target=inherited)
        process.start()
        process.join(timeout=3)
        assert process.exitcode == 0
        owned.assert_owned_for(path)


def test_release_does_not_remove_new_holder_from_process_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "lock"
    first = FileLock(path)
    assert first.acquire()
    first_fd = first.fd
    unlocked, acquired, finished = threading.Event(), threading.Event(), threading.Event()
    flock = fcntl.flock

    def interleaved(fd: int, flags: int) -> None:
        flock(fd, flags)
        if fd == first_fd and flags == fcntl.LOCK_UN:
            unlocked.set()
            assert acquired.wait(timeout=2)

    def next_holder() -> None:
        assert unlocked.wait(timeout=2)
        with FileLock(path).hold(timeout_seconds=1):
            acquired.set()
            assert finished.wait(timeout=2)
            with pytest.raises(RuntimeError, match="already held by this thread"):
                FileLock(path).acquire(blocking=True, timeout_seconds=0.01)

    monkeypatch.setattr(fcntl, "flock", interleaved)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(next_holder)
        try:
            first.release()
        finally:
            finished.set()
        future.result(timeout=3)


def test_failed_close_keeps_reentrant_guard_for_still_open_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "lock"
    lock = FileLock(path)
    assert lock.acquire()
    primary = OSError(errno.EIO, "unlock")

    def failed_unlock(fd: int, flags: int) -> None:
        raise primary

    def failed_close(fd: int) -> None:
        raise OSError(errno.EIO, "close")

    with monkeypatch.context() as patch:
        patch.setattr(fcntl, "flock", failed_unlock)
        patch.setattr(os, "close", failed_close)
        with pytest.raises(OSError, match="unlock") as caught:
            lock.release()
    assert caught.value is primary
    assert "close" in " ".join(primary.__notes__)
    with pytest.raises(RuntimeError, match="already held by this thread"):
        FileLock(path).acquire(blocking=True, timeout_seconds=None)
    lock.release()
    with FileLock(path).hold(timeout_seconds=1):
        pass
