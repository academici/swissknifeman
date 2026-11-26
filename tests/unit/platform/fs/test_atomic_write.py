"""Durability order, unsafe targets, and primary/secondary failure contracts."""

import errno
import os
import stat
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from skm.platform.fs import atomic_write as io


def test_atomic_replace_order_and_modes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "nested" / "data"
    events: list[str] = []
    sync, replace = os.fsync, os.replace

    def synced(fd: int) -> None:
        events.append("dir_sync" if stat.S_ISDIR(os.fstat(fd).st_mode) else "file_sync")
        sync(fd)

    def replaced(src: Path, dst: Path) -> None:
        assert src.parent == dst.parent
        assert src.read_bytes() == b"new"
        assert stat.S_IMODE(src.stat().st_mode) == 0o640
        events.append("replace")
        replace(src, dst)

    monkeypatch.setattr(os, "fsync", synced)
    monkeypatch.setattr(os, "replace", replaced)
    io.atomic_write(target, b"new", private=True, mode=0o640)
    assert target.read_bytes() == b"new"
    assert events == ["file_sync", "replace", "dir_sync"]
    monkeypatch.setattr(os, "replace", replace)
    io.atomic_write(target, b"private", private=True)
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


@pytest.mark.parametrize("kind", ["symlink", "not_regular", "hard_link"])
def test_unsafe_targets_are_rejected(tmp_path: Path, kind: str) -> None:
    target, other = tmp_path / "target", tmp_path / "other"
    other.write_bytes(b"original")
    if kind == "symlink":
        target.symlink_to(other)
    elif kind == "not_regular":
        target.mkdir()
    else:
        os.link(other, target)
    with pytest.raises(io.UnsafePathError) as caught:
        io.atomic_write(target, b"bad")
    assert caught.value.reason == kind
    assert other.read_bytes() == b"original"
    assert not list(tmp_path.glob(".*.tmp"))


def test_explicit_unchecked_replace_replaces_link_not_referent(tmp_path: Path) -> None:
    other, target = tmp_path / "other", tmp_path / "target"
    other.write_bytes(b"keep")
    target.symlink_to(other)
    io.atomic_write(target, b"new", check_target=False)
    assert not target.is_symlink()
    assert other.read_bytes() == b"keep"


def test_an_explicit_mode_never_leaves_the_content_readable_before_it_applies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # mode=0o600 callers write private state: a umask-wide temp would expose it until the chmod.
    seen: list[int] = []
    write = io._write_temp

    def observed(fd: int, data: bytes) -> None:
        seen.append(stat.S_IMODE(os.fstat(fd).st_mode))
        write(fd, data)

    monkeypatch.setattr(io, "_write_temp", observed)
    old = os.umask(0o022)
    try:
        io.atomic_write(tmp_path / "state", b"private", mode=0o600)
        io.atomic_write(tmp_path / "shared", b"shared", mode=0o644)
    finally:
        os.umask(old)
    assert seen == [0o600, 0o600]
    assert stat.S_IMODE((tmp_path / "state").stat().st_mode) == 0o600
    assert stat.S_IMODE((tmp_path / "shared").stat().st_mode) == 0o644


def test_default_mode_obeys_umask(tmp_path: Path) -> None:
    previous = os.umask(0o027)
    try:
        io.atomic_write(tmp_path / "data", b"x")
    finally:
        os.umask(previous)
    assert stat.S_IMODE((tmp_path / "data").stat().st_mode) == 0o640


@pytest.mark.parametrize("stage", ["open", "sync"])
@pytest.mark.parametrize("code", [errno.EACCES, errno.EIO, errno.ENOSPC])
def test_directory_io_errors_are_not_unsupported_sync(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str, code: int
) -> None:
    primary = OSError(code, "directory IO")

    def failed(*args: object) -> int:
        raise primary

    monkeypatch.setattr(os, "open" if stage == "open" else "fsync", failed)
    with pytest.raises(OSError, match="directory IO") as caught:
        io.fsync_dir(tmp_path)
    assert caught.value is primary


@pytest.mark.parametrize(
    "stage", ["open", "fdopen", "write", "flush", "fsync", "chmod", "replace", "dir_sync"]
)
def test_faults_never_report_success_and_cleanup_preserves_primary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    target = tmp_path / "target"
    target.write_bytes(b"old")
    primary = OSError(errno.ENOSPC, stage)
    original_fdopen = os.fdopen

    def fail(*args: object, **kwargs: object) -> None:
        raise primary

    class FailingStream:
        def __init__(self, fd: int) -> None:
            self.stream = original_fdopen(fd, "wb")

        def write(self, data: bytes) -> int:
            if stage == "write":
                raise primary
            return self.stream.write(data)

        def flush(self) -> None:
            if stage == "flush":
                raise primary
            self.stream.flush()

        def fileno(self) -> int:
            return self.stream.fileno()

        def close(self) -> None:
            self.stream.close()

    if stage in {"write", "flush"}:
        monkeypatch.setattr(os, "fdopen", lambda fd, *_: FailingStream(fd))
    elif stage == "dir_sync":
        monkeypatch.setattr(io, "fsync_dir", fail)
    else:
        monkeypatch.setattr(os, stage, fail)
    with pytest.raises(OSError, match=stage) as caught:
        io.atomic_write(target, b"new", mode=0o600)
    assert caught.value is primary
    assert target.read_bytes() == (b"new" if stage == "dir_sync" else b"old")
    assert not list(tmp_path.glob(".*.tmp"))


def test_cleanup_failure_names_orphan_and_keeps_primary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    primary = OSError(errno.EIO, "replace")

    def failed_replace(*args: object) -> None:
        raise primary

    def failed_unlink(*args: object) -> None:
        raise OSError(errno.EACCES, "unlink")

    monkeypatch.setattr(os, "replace", failed_replace)
    monkeypatch.setattr(os, "unlink", failed_unlink)
    with pytest.raises(OSError, match="replace") as caught:
        io.atomic_write(tmp_path / "target", b"new")
    (orphan,) = tmp_path.glob(".*.tmp")
    assert caught.value is primary
    assert str(orphan) in " ".join(caught.value.__notes__)


def test_exclusive_create_does_not_remove_foreign_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(os, "urandom", lambda _: bytes(4))
    temp = tmp_path / f".target.{os.getpid()}.00000000.tmp"
    other = tmp_path / "other"
    other.write_bytes(b"foreign")
    temp.symlink_to(other)
    with pytest.raises(FileExistsError):
        io.atomic_write(tmp_path / "target", b"bad")
    assert temp.is_symlink()
    assert other.read_bytes() == b"foreign"


@pytest.mark.parametrize("code", [errno.EINVAL, errno.ENOTSUP, errno.EPERM, errno.EISDIR, errno.EBADF])
def test_only_documented_unsupported_directory_sync_is_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    def fail(fd: int) -> None:
        raise OSError(code, "unsupported")

    monkeypatch.setattr(os, "fsync", fail)
    io.fsync_dir(tmp_path)


def test_directory_sync_preserves_primary_over_close(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    primary = OSError(errno.EIO, "sync")
    close = os.close

    def fail_sync(fd: int) -> None:
        raise primary

    def fail_close(fd: int) -> None:
        close(fd)
        raise OSError(errno.EBADF, "close")

    monkeypatch.setattr(os, "fsync", fail_sync)
    monkeypatch.setattr(os, "close", fail_close)
    with pytest.raises(OSError, match="sync") as caught:
        io.fsync_dir(tmp_path)
    assert caught.value is primary
    assert "close" in " ".join(caught.value.__notes__)


def test_concurrent_atomic_writers_have_distinct_temps(tmp_path: Path) -> None:
    target = tmp_path / "target"
    payloads = [bytes([i]) * 8192 for i in range(20)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda data: io.atomic_write(target, data), payloads))
    assert target.read_bytes() in payloads
    assert not list(tmp_path.glob(".*.tmp"))


def test_lstat_of_concurrently_unlinked_inode_is_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.write_bytes(b"old")
    real_lstat = Path.lstat
    calls = 0

    def raced(path: Path) -> os.stat_result:
        nonlocal calls
        result = real_lstat(path)
        if path == target:
            calls += 1
            if calls == 1:
                values = list(result)
                values[3] = 0  # st_nlink of the just-unlinked inode
                return os.stat_result(values)
        return result

    monkeypatch.setattr(Path, "lstat", raced)
    io.atomic_write(target, b"new")
    assert target.read_bytes() == b"new"
    assert calls >= 2


def test_a_target_replaced_many_times_in_a_row_is_still_judged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Under contention every lstat may copy the attributes of an inode another writer just replaced.
    target = tmp_path / "target"
    target.write_bytes(b"old")
    real_lstat = Path.lstat
    unlinked = 50

    def raced(path: Path) -> os.stat_result:
        nonlocal unlinked
        result = real_lstat(path)
        if path == target and unlinked:
            unlinked -= 1
            values = list(result)
            values[3] = 0
            return os.stat_result(values)
        return result

    monkeypatch.setattr(Path, "lstat", raced)
    io.atomic_write(target, b"new")
    assert target.read_bytes() == b"new"


def test_directory_sync_cancellation_survives_secondary_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    primary = KeyboardInterrupt("sync cancelled")
    close = os.close

    def cancelled(fd: int) -> None:
        raise primary

    def bad_close(fd: int) -> None:
        close(fd)
        raise OSError(errno.EIO, "close")

    monkeypatch.setattr(os, "fsync", cancelled)
    monkeypatch.setattr(os, "close", bad_close)
    with pytest.raises(KeyboardInterrupt, match="sync cancelled") as caught:
        io.fsync_dir(tmp_path)
    assert caught.value is primary
    assert "close" in " ".join(primary.__notes__)
