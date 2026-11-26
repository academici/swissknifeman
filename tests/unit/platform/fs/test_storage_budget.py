"""Admission, bounded IO, owner recovery and concurrency without settings/worker."""

import errno
import hashlib
import json
import multiprocessing
import os
import stat
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from skm.kernel.errors import BackendUnavailable
from skm.platform.fs import storage_budget as storage
from skm.platform.fs.file_lock import FileLock
from skm.platform.fs.storage_budget import ReservationExceeded, StorageBudget, StorageOwnerIdentity


def identity() -> StorageOwnerIdentity:
    return StorageOwnerIdentity("boot", os.getpid(), "birth")


def budget_at(tmp_path: Path, *, free: int = 1_000_000, alive: bool | None = True) -> StorageBudget:
    return StorageBudget(
        tmp_path / "locks", free_bytes=lambda _: free, identity=identity, owner_alive=lambda _: alive
    )


def test_global_reserve_across_roots_and_floors(tmp_path: Path) -> None:
    other = tmp_path / "other"
    other.mkdir()
    budget = budget_at(tmp_path, free=100_000)
    first = budget.reserve(tmp_path, owner_id="first", max_bytes=20_000, min_free_bytes=40_000)
    held = budget.snapshot(other, min_free_bytes=0)
    assert held.reserved_bytes > 20_000
    assert held.available_bytes == 100_000 - held.reserved_bytes - 40_000
    with pytest.raises(BackendUnavailable) as caught:
        budget.reserve(other, owner_id="low-floor", max_bytes=30_000, min_free_bytes=0)
    assert caught.value.details["reason"] == "disk_low"
    second = budget.reserve(other, owner_id="small", max_bytes=1, min_free_bytes=0)
    assert budget.snapshot(tmp_path, min_free_bytes=50_000).available_bytes < held.available_bytes
    first.close()
    second.close()
    assert budget.snapshot(tmp_path, min_free_bytes=0).reserved_bytes == 0


def test_denial_before_file_creation_includes_file_overhead(tmp_path: Path) -> None:
    budget = budget_at(tmp_path, free=1)
    with pytest.raises(BackendUnavailable) as caught:
        budget.reserve(tmp_path, owner_id="denied", max_bytes=0, max_files=1, min_free_bytes=0)
    assert caught.value.details["reason"] == "disk_low"
    assert not (tmp_path / "data").exists()
    assert budget.snapshot(tmp_path, min_free_bytes=0).reserved_bytes == 0


def test_registration_before_exclusive_create_and_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    budget = budget_at(tmp_path)
    reservation = budget.reserve(tmp_path, owner_id="owner", max_bytes=8, min_free_bytes=0)
    path = tmp_path / "data"
    original_open, original_write = os.open, os.write
    created = False

    def open_file(
        name: str | bytes | os.PathLike[str] | os.PathLike[bytes], flags: int, mode: int = 0o777
    ) -> int:
        nonlocal created
        if name == path:
            ledger = json.loads((tmp_path / "locks/storage-budget.json").read_bytes())
            registered = ledger["reservations"][0]["paths"][0]
            assert registered == {"path": str(path), "dev": None, "ino": None}
            assert flags & os.O_EXCL
            assert flags & os.O_NOFOLLOW
            assert flags & os.O_CLOEXEC
            assert mode == 0o600
            created = True
        return original_open(name, flags, mode)

    monkeypatch.setattr(os, "open", open_file)
    writer = reservation.open_file(path)
    assert created
    assert not os.get_inheritable(writer._fd)

    def write_file(fd: int, data: bytes) -> int:
        ledger = json.loads((tmp_path / "locks/storage-budget.json").read_bytes())
        registered = ledger["reservations"][0]["paths"][0]
        assert (registered["dev"], registered["ino"]) == (os.fstat(fd).st_dev, os.fstat(fd).st_ino)
        return original_write(fd, data)

    monkeypatch.setattr(os, "write", write_file)
    writer.write(b"payload")
    reservation.close()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_full_reserve_through_fsync_close_and_deferred_free(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw_free = [1_000_000]
    budget = StorageBudget(
        tmp_path / "locks", free_bytes=lambda _: raw_free[0], identity=identity, owner_alive=lambda _: True
    )
    reservation = budget.reserve(tmp_path, owner_id="streams", max_bytes=12, max_files=2, min_free_bytes=7)
    first, second = reservation.open_file(tmp_path / "out"), reservation.open_file(tmp_path / "err")
    held = budget.snapshot(tmp_path, min_free_bytes=0).reserved_bytes
    first.write(b"1234")
    second.write(b"5678")
    assert budget.snapshot(tmp_path, min_free_bytes=0).reserved_bytes == held
    # Delayed statvfs accounting must not be compensated by decrementing reserve.
    assert budget.snapshot(tmp_path, min_free_bytes=0).free_bytes == 1_000_000
    raw_free[0] -= 8
    assert budget.snapshot(tmp_path, min_free_bytes=0).available_bytes == raw_free[0] - held - 7
    sync, close = os.fsync, os.close
    observed: list[str] = []
    watched = {first._fd, second._fd}

    def synced(fd: int) -> None:
        if fd in watched:
            assert budget.snapshot(tmp_path, min_free_bytes=0).reserved_bytes == held
            observed.append("sync")
        sync(fd)

    def closed(fd: int) -> None:
        if fd in watched:
            watched.remove(fd)
            assert budget.snapshot(tmp_path, min_free_bytes=0).reserved_bytes == held
            observed.append("close")
        close(fd)

    monkeypatch.setattr(os, "fsync", synced)
    monkeypatch.setattr(os, "close", closed)
    first.close()
    assert budget.snapshot(tmp_path, min_free_bytes=0).reserved_bytes == held
    reservation.close()
    reservation.close()
    first.close()
    assert observed == ["sync", "close", "sync", "close"]
    assert budget.snapshot(tmp_path, min_free_bytes=0).reserved_bytes == 0


def test_shared_byte_and_file_ceiling_under_threads(tmp_path: Path) -> None:
    budget = budget_at(tmp_path)
    reservation = budget.reserve(tmp_path, owner_id="two", max_bytes=10, max_files=2, min_free_bytes=0)
    writers = [reservation.open_file(tmp_path / name) for name in ("out", "err")]
    barrier = threading.Barrier(2)

    def write(index: int) -> bool:
        barrier.wait(timeout=2)
        try:
            writers[index].write(b"123456")
        except ReservationExceeded:
            return False
        return True

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, range(2)))
    assert sorted(results) == [False, True]
    with pytest.raises(ReservationExceeded):
        reservation.open_file(tmp_path / "third")
    reservation.close()
    assert sum((tmp_path / name).stat().st_size for name in ("out", "err")) == 6
    with pytest.raises(RuntimeError):
        writers[0].write(b"x")


def test_short_writes_and_eintr_then_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    reservation = budget_at(tmp_path).reserve(tmp_path, owner_id="writer", max_bytes=6, min_free_bytes=0)
    writer = reservation.open_file(tmp_path / "data")
    write = os.write
    calls = 0

    def short(fd: int, data: bytes) -> int:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise InterruptedError(errno.EINTR, "interrupted")
        return write(fd, data[:2])

    monkeypatch.setattr(os, "write", short)
    writer.write(b"abcdef")
    with pytest.raises(ReservationExceeded):
        writer.write(b"x")
    reservation.close()
    assert (tmp_path / "data").read_bytes() == b"abcdef"
    assert calls == 4


@pytest.mark.parametrize("failure", ["enospc", "zero", "eintr"])
@pytest.mark.parametrize("close_file_first", [False, True])
def test_failed_write_cannot_later_release_as_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str, close_file_first: bool
) -> None:
    budget = budget_at(tmp_path)
    reservation = budget.reserve(tmp_path, owner_id="writer", max_bytes=6, min_free_bytes=0)
    writer = reservation.open_file(tmp_path / "data")
    write = os.write
    calls = 0

    def failed(fd: int, data: bytes) -> int:
        nonlocal calls
        calls += 1
        if failure == "enospc":
            if calls == 1:
                return write(fd, data[:2])
            raise OSError(errno.ENOSPC, "full")
        if failure == "eintr":
            raise InterruptedError(errno.EINTR, "interrupted")
        return 0

    monkeypatch.setattr(os, "write", failed)
    with pytest.raises(OSError, match=r"full|interrupted|invalid/zero") as caught:
        writer.write(b"abcdef")
    if close_file_first:
        with pytest.raises(OSError, match=r"full|interrupted|invalid/zero") as file_closed:
            writer.close()
        assert file_closed.value is caught.value
        assert budget.snapshot(tmp_path, min_free_bytes=0).reserved_bytes > 6
    with pytest.raises(OSError, match=r"full|interrupted|invalid/zero") as closed:
        reservation.close()
    assert closed.value is caught.value
    assert budget.snapshot(tmp_path, min_free_bytes=0).reserved_bytes == 0
    assert (tmp_path / "data").stat().st_size == (2 if failure == "enospc" else 0)
    assert calls <= 64
    reservation.close()


@pytest.mark.parametrize("stage", ["fsync", "close", "directory", "ledger", "unlock"])
@pytest.mark.parametrize("body_error", [False, True])
def test_close_failure_retains_reserve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str, body_error: bool
) -> None:
    budget = budget_at(tmp_path)
    reservation = budget.reserve(tmp_path, owner_id="writer", max_bytes=6, min_free_bytes=0)
    writer = reservation.open_file(tmp_path / "data")
    writer.write(b"data")
    primary = OSError(errno.EIO, stage)
    operation_error = ValueError("body")
    sync, close, save, release = os.fsync, os.close, budget._save, FileLock.release
    fired = False

    def failed_file(fd: int) -> None:
        nonlocal fired
        if fd == writer._fd and not fired:
            fired = True
            if stage == "close":
                close(fd)
            raise primary
        (sync if stage == "fsync" else close)(fd)

    def failed_save(entries: list[storage._Entry]) -> None:
        nonlocal fired
        if not fired:
            fired = True
            raise primary
        save(entries)

    def failed_release(lock: FileLock) -> None:
        nonlocal fired
        release(lock)
        if not fired:
            fired = True
            raise primary

    def failed_directory(path: Path) -> None:
        raise primary

    def finish() -> None:
        if body_error:
            with reservation:
                raise operation_error
        else:
            reservation.close()

    with monkeypatch.context() as patch:
        if stage in {"fsync", "close"}:
            patch.setattr(os, stage, failed_file)
        elif stage == "directory":
            patch.setattr(storage, "fsync_dir", failed_directory)
        elif stage == "ledger":
            patch.setattr(budget, "_save", failed_save)
        else:
            patch.setattr(FileLock, "release", failed_release)
        with pytest.raises((OSError, ValueError), match="body" if body_error else stage) as caught:
            finish()
    assert caught.value is (operation_error if body_error else primary)
    if body_error:
        assert stage in " ".join(operation_error.__notes__)
    assert budget.snapshot(tmp_path, min_free_bytes=0).reserved_bytes > 6
    reservation.close()


def test_body_primary_survives_sync_and_close_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    budget = budget_at(tmp_path)
    primary = ValueError("body")
    reservation = budget.reserve(tmp_path, owner_id="writer", max_bytes=6, min_free_bytes=0)
    writer = reservation.open_file(tmp_path / "data")
    close = os.close

    def bad_sync(fd: int) -> None:
        raise OSError(errno.EIO, "sync")

    def bad_close(fd: int) -> None:
        close(fd)
        raise OSError(errno.EBADF, "close")

    def body() -> None:
        with monkeypatch.context() as patch, reservation:
            patch.setattr(os, "fsync", bad_sync)
            patch.setattr(os, "close", bad_close)
            writer.write(b"x")
            raise primary

    with pytest.raises(ValueError, match="body") as caught:
        body()
    assert caught.value is primary
    assert "close" in " ".join(caught.value.__notes__)
    assert budget.snapshot(tmp_path, min_free_bytes=0).reserved_bytes > 6


@pytest.mark.parametrize("kind", ["outside", "symlink", "existing"])
def test_owned_file_api_rejects_unsafe_or_existing_paths(tmp_path: Path, kind: str) -> None:
    root = tmp_path / "root"
    root.mkdir()
    reservation = budget_at(tmp_path).reserve(root, owner_id="writer", max_bytes=1, min_free_bytes=0)
    outside = tmp_path / "outside"
    outside.write_bytes(b"keep")
    path = root / "data"
    if kind == "outside":
        path = outside
    elif kind == "symlink":
        (root / "link").symlink_to(tmp_path, target_is_directory=True)
        path = root / "link/outside"
    else:
        path.write_bytes(b"keep")
    with pytest.raises((ValueError, FileExistsError)):
        reservation.open_file(path)
    assert outside.read_bytes() == b"keep"
    if kind == "existing":
        with pytest.raises(FileExistsError):
            reservation.close()
    else:
        reservation.close()
    assert budget_at(tmp_path).snapshot(root, min_free_bytes=0).reserved_bytes == 0


@pytest.mark.parametrize("state", [True, False, None])
def test_reconcile_live_dead_unknown_owner_and_retained_files(tmp_path: Path, state: bool | None) -> None:
    budget = budget_at(tmp_path)
    reservation = budget.reserve(tmp_path, owner_id="logical", max_bytes=1, min_free_bytes=0)
    writer = reservation.open_file(tmp_path / "data")
    writer.write(b"x")
    writer.close()
    recovered = budget_at(tmp_path, alive=state)
    snapshot = recovered.reconcile(tmp_path)
    assert (snapshot.reserved_bytes == 0) is (state is False)
    assert snapshot.unknown_owners == (("logical",) if state is None else ())
    assert (tmp_path / "data").read_bytes() == b"x"
    if state is not False:
        # Unknown ownership holds only its own reserve, not all future admission.
        other = recovered.reserve(tmp_path, owner_id="other", max_bytes=1, min_free_bytes=0)
        other.close()
        reservation.close()


@pytest.mark.parametrize(
    "current",
    [StorageOwnerIdentity("new-boot", 123, "old"), StorageOwnerIdentity("old-boot", 123, "new-birth")],
)
def test_pid_reuse_and_reboot_are_not_old_live_owner(tmp_path: Path, current: StorageOwnerIdentity) -> None:
    old = StorageOwnerIdentity("old-boot", 123, "old")
    budget = StorageBudget(
        tmp_path / "locks",
        free_bytes=lambda _: 100_000,
        identity=lambda: old,
        owner_alive=lambda owner: owner == current,
    )
    budget.reserve(tmp_path, owner_id="old", max_bytes=1, min_free_bytes=0)
    assert budget.reconcile(tmp_path).reserved_bytes == 0


def test_reconcile_does_not_delete_or_free_replaced_inode(tmp_path: Path) -> None:
    reservation = budget_at(tmp_path).reserve(tmp_path, owner_id="old", max_bytes=1, min_free_bytes=0)
    writer = reservation.open_file(tmp_path / "data")
    writer.close()
    (tmp_path / "data").rename(tmp_path / "owned-old")
    (tmp_path / "data").write_bytes(b"foreign")
    snapshot = budget_at(tmp_path, alive=False).reconcile(tmp_path)
    assert snapshot.reserved_bytes > 0
    assert (tmp_path / "data").read_bytes() == b"foreign"


@pytest.mark.parametrize(
    "corrupt", [b"{broken", b"{}", b'{"version":1,"reservations":{}}', b'{"version":true,"reservations":[]}']
)
def test_corrupt_ledger_blocks_admission_without_repair(tmp_path: Path, corrupt: bytes) -> None:
    budget = budget_at(tmp_path)
    ledger = tmp_path / "locks/storage-budget.json"
    ledger.write_bytes(corrupt)
    with pytest.raises(BackendUnavailable) as caught:
        budget.reserve(tmp_path, owner_id="new", max_bytes=0, min_free_bytes=0)
    assert caught.value.details["reason"] == "storage_ledger_corrupt"
    assert ledger.read_bytes() == corrupt


def test_corrupt_reservation_amount_rejected(tmp_path: Path) -> None:
    budget = budget_at(tmp_path)
    budget.reserve(tmp_path, owner_id="owner", max_bytes=1, min_free_bytes=0)
    ledger = tmp_path / "locks/storage-budget.json"
    data = json.loads(ledger.read_bytes())
    data["reservations"][0]["ceiling"] = -1
    data.pop("checksum")
    data["checksum"] = hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    ledger.write_text(json.dumps(data))
    with pytest.raises(BackendUnavailable, match="unavailable"):
        budget.snapshot(tmp_path, min_free_bytes=0)


def test_plausible_ledger_corruption_cannot_discard_reserves(tmp_path: Path) -> None:
    budget = budget_at(tmp_path)
    budget.reserve(tmp_path, owner_id="owner", max_bytes=1, min_free_bytes=0)
    ledger = tmp_path / "locks/storage-budget.json"
    data = json.loads(ledger.read_bytes())
    data["reservations"] = []
    ledger.write_text(json.dumps(data))
    with pytest.raises(BackendUnavailable) as caught:
        budget.reserve(tmp_path, owner_id="new", max_bytes=1, min_free_bytes=0)
    assert caught.value.details["reason"] == "storage_ledger_corrupt"


@pytest.mark.parametrize("failure", [False, True])
def test_reconcile_syncs_dead_owned_files_outside_ledger_lock_before_freeing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: bool
) -> None:
    reservation = budget_at(tmp_path).reserve(tmp_path, owner_id="dead", max_bytes=1, min_free_bytes=0)
    writer = reservation.open_file(tmp_path / "data")
    writer.write(b"x")
    writer.close()
    dead = budget_at(tmp_path, alive=False)
    data_inode = (tmp_path / "data").stat().st_ino
    sync = os.fsync
    primary = OSError(errno.EIO, "dead file fsync")
    observed = False

    def synced(fd: int) -> None:
        nonlocal observed
        if os.fstat(fd).st_ino == data_inode:
            observed = True
            assert dead.snapshot(tmp_path, min_free_bytes=0).reserved_bytes > 1
            if failure:
                raise primary
        sync(fd)

    with monkeypatch.context() as patch:
        patch.setattr(os, "fsync", synced)
        if failure:
            with pytest.raises(OSError, match="dead file fsync") as caught:
                dead.reconcile(tmp_path)
            assert caught.value is primary
        else:
            assert dead.reconcile(tmp_path).reserved_bytes == 0
    assert observed
    assert (dead.snapshot(tmp_path, min_free_bytes=0).reserved_bytes > 0) is failure


@pytest.mark.parametrize("created", [False, True])
def test_pending_creation_crash_does_not_claim_foreign_inode(tmp_path: Path, created: bool) -> None:
    budget = budget_at(tmp_path)
    budget.reserve(tmp_path, owner_id="pending", max_bytes=1, min_free_bytes=0)
    ledger = tmp_path / "locks/storage-budget.json"
    data = json.loads(ledger.read_bytes())
    path = tmp_path / "pending"
    data["reservations"][0]["paths"] = [{"path": str(path), "dev": None, "ino": None}]
    data.pop("checksum")
    data["checksum"] = hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    ledger.write_text(json.dumps(data))
    if created:
        path.write_bytes(b"unknown")
    snapshot = budget_at(tmp_path, alive=False).reconcile(tmp_path)
    assert (snapshot.reserved_bytes > 0) is created
    if created:
        assert path.read_bytes() == b"unknown"


def test_failed_post_create_registration_closes_descriptor_and_retains_primary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    budget = budget_at(tmp_path)
    reservation = budget.reserve(tmp_path, owner_id="writer", max_bytes=1, min_free_bytes=0)
    update = reservation._update
    primary = OSError(errno.EIO, "ownership persist")
    calls = 0

    def failed_update(*args: object, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise primary
        update(*args, **kwargs)

    monkeypatch.setattr(reservation, "_update", failed_update)
    with pytest.raises(OSError, match="ownership persist") as caught:
        reservation.open_file(tmp_path / "data")
    assert caught.value is primary
    (writer,) = reservation._files
    with pytest.raises(OSError, match="Bad file descriptor"):
        os.fstat(writer._fd)
    assert budget.snapshot(tmp_path, min_free_bytes=0).reserved_bytes > 1


def test_write_primary_survives_direct_file_close_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    budget = budget_at(tmp_path)
    reservation = budget.reserve(tmp_path, owner_id="writer", max_bytes=1, min_free_bytes=0)
    writer = reservation.open_file(tmp_path / "data")
    primary = OSError(errno.ENOSPC, "write")

    def failed_write(*args: object) -> int:
        raise primary

    def failed_sync(fd: int) -> None:
        raise OSError(errno.EIO, "sync")

    with monkeypatch.context() as patch:
        patch.setattr(os, "write", failed_write)
        patch.setattr(os, "fsync", failed_sync)
        with pytest.raises(OSError, match="write"):
            writer.write(b"x")
        with pytest.raises(OSError, match="write") as caught:
            writer.close()
    assert caught.value is primary
    assert "sync" in " ".join(primary.__notes__)
    with pytest.raises(OSError, match="write"):
        reservation.close()


def test_reservation_release_post_replace_error_restores_full_amount(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    budget = budget_at(tmp_path)
    reservation = budget.reserve(tmp_path, owner_id="writer", max_bytes=1, min_free_bytes=0)
    reserved = budget.snapshot(tmp_path, min_free_bytes=0).reserved_bytes
    replace = storage.atomic_write
    primary = OSError(errno.EIO, "ledger directory fsync")
    fired = False

    def failed_save(path: Path, data: bytes, *, private: bool) -> None:
        nonlocal fired
        replace(path, data, private=private)
        if path.name == "storage-budget.json" and not fired:
            fired = True
            raise primary

    with monkeypatch.context() as patch:
        patch.setattr(storage, "atomic_write", failed_save)
        with pytest.raises(OSError, match="ledger directory fsync") as caught:
            reservation.close()
    assert caught.value is primary
    assert budget.snapshot(tmp_path, min_free_bytes=0).reserved_bytes == reserved


def test_release_guard_survives_lock_and_ledger_failures_without_restore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    budget = budget_at(tmp_path)
    reservation = budget.reserve(tmp_path, owner_id="writer", max_bytes=1, min_free_bytes=0)
    reserved = budget.snapshot(tmp_path, min_free_bytes=0).reserved_bytes
    release = FileLock.release
    primary = OSError(errno.EIO, "lock release")

    def failed_release(lock: FileLock) -> None:
        release(lock)
        raise primary

    with monkeypatch.context() as patch:
        patch.setattr(FileLock, "release", failed_release)
        with pytest.raises(OSError, match="lock release") as caught:
            reservation.close()
    assert caught.value is primary
    assert budget.snapshot(tmp_path, min_free_bytes=0).reserved_bytes == reserved
    assert list((tmp_path / "locks").glob(".storage-budget-release.*.json"))
    assert budget_at(tmp_path, alive=False).reconcile(tmp_path).reserved_bytes == 0


def test_guard_cleanup_failure_retains_reserve(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    budget = budget_at(tmp_path)
    reservation = budget.reserve(tmp_path, owner_id="writer", max_bytes=1, min_free_bytes=0)
    reserved = budget.snapshot(tmp_path, min_free_bytes=0).reserved_bytes
    unlink = os.unlink

    def failed_unlink(path: str | os.PathLike[str], *, dir_fd: int | None = None) -> None:
        if Path(path).name.startswith(".storage-budget-release."):
            raise OSError(errno.EACCES, "release guard cleanup")
        unlink(path, dir_fd=dir_fd)

    with monkeypatch.context() as patch:
        patch.setattr(os, "unlink", failed_unlink)
        with pytest.raises(OSError, match="release guard cleanup"):
            reservation.close()
    assert budget.snapshot(tmp_path, min_free_bytes=0).reserved_bytes == reserved
    assert budget_at(tmp_path, alive=False).reconcile(tmp_path).reserved_bytes == 0


@pytest.mark.parametrize("unlink_before_save", [False, True])
def test_concurrent_admission_during_release_does_not_resurrect_completed_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, unlink_before_save: bool
) -> None:
    budget = budget_at(tmp_path)
    reservation = budget.reserve(tmp_path, owner_id="first", max_bytes=10, min_free_bytes=0)
    finish = budget._finish_release
    admitted: list[storage.WriteReservation] = []

    def concurrent_admission(entries: list[storage._Entry]) -> None:
        save = budget._save

        def finish_before_save(current: list[storage._Entry]) -> None:
            if unlink_before_save:
                finish(entries)
            save(current)

        with monkeypatch.context() as patch:
            patch.setattr(budget, "_save", finish_before_save)
            admitted.append(budget.reserve(tmp_path, owner_id="second", max_bytes=1, min_free_bytes=0))
        finish(entries)

    with monkeypatch.context() as patch:
        patch.setattr(budget, "_finish_release", concurrent_admission)
        reservation.close()
    ledger = json.loads((tmp_path / "locks/storage-budget.json").read_bytes())
    assert [entry["owner_id"] for entry in ledger["reservations"]] == ["second"]
    assert budget.snapshot(tmp_path, min_free_bytes=0).reserved_bytes == admitted[0]._entry.ceiling
    admitted[0].close()


def test_lock_timeout_is_backend_unavailable(tmp_path: Path) -> None:
    budget = budget_at(tmp_path)
    with (
        FileLock(tmp_path / "locks/storage-budget.lock").hold(timeout_seconds=1),
        ThreadPoolExecutor(max_workers=1) as pool,
    ):
        future = pool.submit(budget.snapshot, tmp_path, min_free_bytes=0)
        with pytest.raises(BackendUnavailable) as caught:
            future.result(timeout=3)
    assert caught.value.details["reason"] == "storage_lock_timeout"


def test_two_threads_reserve_atomically(tmp_path: Path) -> None:
    budget = budget_at(tmp_path, free=40_000)
    start = threading.Barrier(2)

    def reserve(index: int) -> object:
        start.wait(timeout=2)
        try:
            return budget.reserve(tmp_path, owner_id=str(index), max_bytes=20_000, min_free_bytes=0)
        except BackendUnavailable:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reserve, range(2)))
    successful = [item for item in results if isinstance(item, storage.WriteReservation)]
    assert len(successful) == 1
    successful[0].close()


def test_two_processes_reserve_one_shared_host_ledger(tmp_path: Path) -> None:
    ctx = multiprocessing.get_context("fork")
    channels = [ctx.Pipe() for _ in range(2)]
    roots = [tmp_path / "one", tmp_path / "two"]
    for root in roots:
        root.mkdir()

    def worker(index: int) -> None:
        budget = budget_at(tmp_path, free=40_000)
        connection = channels[index][1]
        connection.send("ready")
        connection.recv()
        try:
            reservation = budget.reserve(
                roots[index], owner_id=str(index), max_bytes=20_000, min_free_bytes=0
            )
        except BackendUnavailable:
            reservation = None
        connection.send(reservation is not None)
        connection.recv()
        if reservation is not None:
            reservation.close()

    processes = [ctx.Process(target=worker, args=(index,)) for index in range(2)]
    for process in processes:
        process.start()
    try:
        for connection, _ in channels:
            assert connection.poll(3)
            assert connection.recv() == "ready"
        for connection, _ in channels:
            connection.send("go")
        outcomes = []
        for connection, _ in channels:
            assert connection.poll(3)
            outcomes.append(connection.recv())
        assert sorted(outcomes) == [False, True]
        assert budget_at(tmp_path).snapshot(tmp_path, min_free_bytes=0).reserved_bytes > 20_000
        for connection, _ in channels:
            connection.send("close")
        for process in processes:
            process.join(timeout=3)
            assert process.exitcode == 0
    finally:
        for process in processes:
            if process.is_alive():
                process.kill()
                process.join(timeout=3)
        for parent, child in channels:
            parent.close()
            child.close()


@pytest.mark.parametrize("stage", ["reserve", "register", "created", "write", "fsync", "close"])
def test_crash_never_frees_reserve_before_files_settled(tmp_path: Path, stage: str) -> None:
    ctx = multiprocessing.get_context("fork")

    def crash() -> None:
        budget = budget_at(tmp_path)
        reservation = budget.reserve(tmp_path, owner_id="crashed", max_bytes=10, min_free_bytes=0)
        if stage == "reserve":
            os._exit(31)
        if stage in {"register", "created"}:
            update = reservation._update
            calls = 0

            def crash_update(*args: object, **kwargs: object) -> None:
                nonlocal calls
                update(*args, **kwargs)
                calls += 1
                if calls == (1 if stage == "register" else 2):
                    os._exit(31)

            reservation._update = crash_update
        writer = reservation.open_file(tmp_path / "data")
        writer.write(b"partial")
        if stage == "fsync":
            os.fsync(writer._fd)
        elif stage == "close":
            writer.close()
        os._exit(31)

    process = ctx.Process(target=crash)
    process.start()
    process.join(timeout=3)
    assert process.exitcode == 31
    uncertain = budget_at(tmp_path, alive=None)
    snapshot = uncertain.reconcile(tmp_path)
    assert snapshot.reserved_bytes > 10
    assert snapshot.unknown_owners == ("crashed",)
    assert budget_at(tmp_path, alive=False).reconcile(tmp_path).reserved_bytes == 0


def test_corrupt_ledger_primary_survives_read_close_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    budget = budget_at(tmp_path)
    (tmp_path / "locks/storage-budget.json").write_bytes(b"{broken")
    fdopen = os.fdopen

    class BadClose:
        def __init__(self, fd: int) -> None:
            self.stream = fdopen(fd, "rb")

        def read(self) -> bytes:
            return self.stream.read()

        def close(self) -> None:
            self.stream.close()
            raise OSError(errno.EIO, "ledger read close")

    monkeypatch.setattr(os, "fdopen", lambda fd, *_: BadClose(fd))
    with pytest.raises(BackendUnavailable) as caught:
        budget.snapshot(tmp_path, min_free_bytes=0)
    assert caught.value.details["reason"] == "storage_ledger_corrupt"
    assert isinstance(caught.value.__cause__, json.JSONDecodeError)
    assert "ledger read close" in " ".join(caught.value.__cause__.__notes__)


@pytest.mark.parametrize("after_guard_unlink", [False, True])
def test_crash_during_release_uses_durable_guard(tmp_path: Path, after_guard_unlink: bool) -> None:
    ctx = multiprocessing.get_context("fork")

    def crash() -> None:
        budget = budget_at(tmp_path)
        reservation = budget.reserve(tmp_path, owner_id="crashed", max_bytes=10, min_free_bytes=0)
        writer = reservation.open_file(tmp_path / "data")
        writer.write(b"complete")
        finish = budget._finish_release

        def crash_finish(entries: list[storage._Entry]) -> None:
            if after_guard_unlink:
                finish(entries)
            os._exit(33)

        budget._finish_release = crash_finish
        reservation.close()

    process = ctx.Process(target=crash)
    process.start()
    process.join(timeout=3)
    assert process.exitcode == 33
    snapshot = budget_at(tmp_path, alive=None).snapshot(tmp_path, min_free_bytes=0)
    assert (snapshot.reserved_bytes > 10) is (not after_guard_unlink)
    assert (tmp_path / "data").read_bytes() == b"complete"
    assert budget_at(tmp_path, alive=False).reconcile(tmp_path).reserved_bytes == 0


@pytest.mark.parametrize("failure", ["ceiling", "body", "enospc", "eintr", "zero"])
def test_context_operation_error_releases_only_after_all_file_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    budget = budget_at(tmp_path)
    other = tmp_path / "other-root"
    other.mkdir()
    reservation = budget.reserve(tmp_path, owner_id="writer", max_bytes=6, max_files=2, min_free_bytes=0)
    writers = [reservation.open_file(tmp_path / name) for name in ("out", "err")]
    for writer in writers:
        writer.write(b"x")
    held = budget.snapshot(other, min_free_bytes=0).reserved_bytes
    watched = {writer._fd for writer in writers}
    sync, close, directory_sync = os.fsync, os.close, storage.fsync_dir
    events: list[str] = []
    primary: list[BaseException] = []

    def synced(fd: int) -> None:
        if fd in watched:
            assert budget.snapshot(other, min_free_bytes=0).reserved_bytes == held
            events.append("fsync")
        sync(fd)

    def closed(fd: int) -> None:
        if fd in watched:
            watched.remove(fd)
            assert budget.snapshot(other, min_free_bytes=0).reserved_bytes == held
            events.append("close")
        close(fd)

    def dir_synced(path: Path) -> None:
        assert budget.snapshot(other, min_free_bytes=0).reserved_bytes == held
        events.append("directory")
        directory_sync(path)

    def failed_write(fd: int, data: bytes) -> int:
        if failure == "enospc":
            raise OSError(errno.ENOSPC, "write failed")
        if failure == "eintr":
            raise InterruptedError(errno.EINTR, "write interrupted")
        return 0

    def body() -> None:
        with reservation:
            try:
                if failure == "body":
                    raise ValueError("body failed")
                if failure == "ceiling":
                    writers[0].write(b"too large")
                else:
                    writers[0].write(b"abc")
            except (ValueError, OSError) as error:
                primary.append(error)
                raise

    with monkeypatch.context() as patch:
        patch.setattr(os, "fsync", synced)
        patch.setattr(os, "close", closed)
        patch.setattr(storage, "fsync_dir", dir_synced)
        patch.setattr(os, "write", failed_write)
        with pytest.raises((ValueError, OSError)) as caught:
            body()
    assert caught.value is primary[0]
    assert events == ["fsync", "close", "directory"] * 2
    assert not watched
    assert budget.snapshot(other, min_free_bytes=0).reserved_bytes == 0
    assert budget.reconcile(tmp_path).reserved_bytes == 0  # owner is still alive
    reservation.close()
    for writer in writers:
        writer.close()


@pytest.mark.parametrize("kind", ["file", "directory"])
@pytest.mark.parametrize("open_errno", [None, errno.EEXIST, errno.EISDIR])
@pytest.mark.parametrize("finish", ["close", "reconcile"])
@pytest.mark.parametrize("already_owned", [False, True])
def test_exclusive_creation_refusal_rolls_back_only_pending_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    open_errno: int | None,
    finish: str,
    already_owned: bool,
) -> None:
    budget = budget_at(tmp_path)
    reservation = budget.reserve(tmp_path, owner_id="writer", max_bytes=10, max_files=2, min_free_bytes=0)
    if already_owned:
        reservation.open_file(tmp_path / "owned").write(b"ours")
    registered = json.loads((tmp_path / "locks/storage-budget.json").read_bytes())["reservations"][0]["paths"]
    other = tmp_path / "other-root"
    other.mkdir()
    path = tmp_path / "foreign"
    if kind == "directory":
        path.mkdir()
        (path / "child").write_bytes(b"foreign")
    else:
        path.write_bytes(b"foreign")
    original = path.stat()
    native_open = os.open
    refusal = OSError(open_errno, "exclusive creation refused", str(path))

    def refused(name: Path, flags: int, mode: int = 0o777) -> int:
        if name == path and open_errno is not None:
            raise refusal
        return native_open(name, flags, mode)

    with monkeypatch.context() as patch:
        patch.setattr(os, "open", refused)
        with pytest.raises(OSError, match=r"exist|refused") as caught:
            reservation.open_file(path)
    if open_errno is not None:
        assert caught.value is refusal
    ledger = json.loads((tmp_path / "locks/storage-budget.json").read_bytes())
    assert ledger["reservations"][0]["paths"] == registered
    assert [item.path for item in reservation._entry.paths] == [item["path"] for item in registered]
    if finish == "close":
        with pytest.raises(OSError, match=r"exist|refused") as closed:
            reservation.close()
        assert closed.value is caught.value
        reservation.close()
    else:
        assert budget_at(tmp_path, alive=False).reconcile(other).reserved_bytes == 0
    assert budget.snapshot(other, min_free_bytes=0).reserved_bytes == 0
    assert os.path.samestat(original, path.stat())
    assert (path / "child" if kind == "directory" else path).read_bytes() == b"foreign"
    if already_owned:
        assert (tmp_path / "owned").read_bytes() == b"ours"


@pytest.mark.parametrize("after_commit", [False, True])
@pytest.mark.parametrize("refusal_errno", [errno.EEXIST, errno.ENOENT, errno.ENOTDIR, errno.ELOOP])
@pytest.mark.parametrize("already_owned", [False, True])
def test_pending_registration_rollback_failure_retains_reserve_and_open_primary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    after_commit: bool,
    refusal_errno: int,
    already_owned: bool,
) -> None:
    budget = budget_at(tmp_path)
    reservation = budget.reserve(tmp_path, owner_id="writer", max_bytes=4, max_files=2, min_free_bytes=0)
    if already_owned:
        reservation.open_file(tmp_path / "owned").write(b"ours")
    path = tmp_path / "foreign"
    path.write_bytes(b"keep")
    original = path.stat()
    update = reservation._update
    calls = 0
    native_open = os.open
    refusal = OSError(refusal_errno, "exclusive creation refused", str(path))

    def refused(name: Path, flags: int, mode: int = 0o777) -> int:
        if name == path:
            raise refusal
        return native_open(name, flags, mode)

    def failed_update(*args: object, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            if after_commit:
                update(*args, **kwargs)
            raise OSError(errno.EIO, "rollback persistence failed")
        update(*args, **kwargs)

    monkeypatch.setattr(reservation, "_update", failed_update)
    monkeypatch.setattr(os, "open", refused)
    with pytest.raises(OSError, match="exclusive creation refused") as caught:
        reservation.open_file(path)
    assert caught.value is refusal
    assert "rollback persistence failed" in " ".join(caught.value.__notes__)
    with pytest.raises(OSError, match="exclusive creation refused") as closed:
        reservation.close()
    assert closed.value is caught.value
    assert budget.snapshot(tmp_path, min_free_bytes=0).reserved_bytes > 1
    reservation.close()
    assert os.path.samestat(original, path.stat())
    assert path.read_bytes() == b"keep"
    if already_owned:
        assert (tmp_path / "owned").read_bytes() == b"ours"


def _unblock_refused_parent(parent: Path, refusal_errno: int, blocker: os.stat_result | None) -> None:
    if blocker is not None:
        assert os.path.samestat(blocker, parent.lstat())
        if refusal_errno == errno.ENOTDIR:
            assert parent.read_bytes() == b"foreign"
        else:
            assert parent.readlink() == Path(parent.name)
        # An external actor preserves the blocker and makes the path usable later.
        parent.rename(parent.with_name("former-parent"))
    else:
        assert not parent.exists()
    parent.mkdir()


@pytest.mark.parametrize("refusal_errno", [errno.ENOENT, errno.ENOTDIR, errno.ELOOP])
@pytest.mark.parametrize("already_owned", [False, True])
@pytest.mark.parametrize("finish", ["close", "context", "reconcile"])
def test_native_lookup_refusal_does_not_pin_reserve_after_later_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, refusal_errno: int, already_owned: bool, finish: str
) -> None:
    budget = budget_at(tmp_path)
    reservation = budget.reserve(tmp_path, owner_id="original", max_bytes=10, max_files=2, min_free_bytes=0)
    if already_owned:
        reservation.open_file(tmp_path / "owned").write(b"ours")
    registered = json.loads((tmp_path / "locks/storage-budget.json").read_bytes())["reservations"][0]["paths"]
    other = tmp_path / "other-root"
    other.mkdir()
    held = budget.snapshot(other, min_free_bytes=0).reserved_bytes
    parent, path = tmp_path / "spool", tmp_path / "spool/out.bin"
    update = reservation._update
    calls = 0
    blocker: list[os.stat_result] = []
    rollback_seen = False

    def persisted(*args: object, **kwargs: object) -> None:
        nonlocal calls, rollback_seen
        update(*args, **kwargs)
        calls += 1
        if calls == 1:
            # safe_join has passed and the intent is durable. These changes
            # produce native lookup errors at os.open, without bypassing checks.
            if refusal_errno == errno.ENOTDIR:
                parent.write_bytes(b"foreign")
            elif refusal_errno == errno.ELOOP:
                parent.symlink_to(parent.name, target_is_directory=True)
            if refusal_errno != errno.ENOENT:
                blocker.append(parent.lstat())
        elif calls == 2:
            ledger = json.loads((tmp_path / "locks/storage-budget.json").read_bytes())
            assert ledger["reservations"][0]["paths"] == registered
            rollback_seen = True

    def attempted_open() -> None:
        if finish == "context":
            with reservation:
                reservation.open_file(path)
        else:
            reservation.open_file(path)

    with monkeypatch.context() as patch:
        patch.setattr(reservation, "_update", persisted)
        with pytest.raises(OSError, match=os.strerror(refusal_errno)) as caught:
            attempted_open()
    assert caught.value.errno == refusal_errno
    assert rollback_seen
    assert [item.path for item in reservation._entry.paths] == [item["path"] for item in registered]
    if finish == "close":
        with pytest.raises(OSError, match=os.strerror(refusal_errno)) as closed:
            reservation.close()
        assert closed.value is caught.value
    if finish != "reconcile":
        reservation.close()
        assert budget.reconcile(other).reserved_bytes == 0
    else:
        assert budget.reconcile(other).reserved_bytes == held  # cleanup has not run yet
    _unblock_refused_parent(parent, refusal_errno, blocker[0] if blocker else None)
    with budget.reserve(tmp_path, owner_id="later", max_bytes=4, min_free_bytes=0) as later:
        later.open_file(path).write(b"new")
    assert budget_at(tmp_path, alive=False).reconcile(other).reserved_bytes == 0
    assert budget.snapshot(other, min_free_bytes=0).reserved_bytes == 0
    assert path.read_bytes() == b"new"
    if already_owned:
        assert (tmp_path / "owned").read_bytes() == b"ours"


@pytest.mark.parametrize("refusal_errno", [errno.ENOSPC, errno.EIO])
@pytest.mark.parametrize("possibly_created", [False, True])
def test_uncertain_open_failure_keeps_pending_registration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, refusal_errno: int, possibly_created: bool
) -> None:
    budget = budget_at(tmp_path)
    reservation = budget.reserve(tmp_path, owner_id="uncertain", max_bytes=16, min_free_bytes=0)
    path = tmp_path / "data"
    native_open = os.open
    primary = OSError(refusal_errno, "uncertain open", str(path))

    def uncertain(name: Path, flags: int, mode: int = 0o777) -> int:
        if name == path:
            if possibly_created:
                fd = native_open(name, flags, mode)
                os.write(fd, b"uncertain")
                os.close(fd)
            raise primary
        return native_open(name, flags, mode)

    with monkeypatch.context() as patch:
        patch.setattr(os, "open", uncertain)
        with pytest.raises(OSError, match="uncertain open") as caught:
            reservation.open_file(path)
    assert caught.value is primary
    ledger = json.loads((tmp_path / "locks/storage-budget.json").read_bytes())
    assert ledger["reservations"][0]["paths"] == [{"path": str(path), "dev": None, "ino": None}]
    with pytest.raises(OSError, match="uncertain open") as closed:
        reservation.close()
    assert closed.value is primary
    reservation.close()
    held = budget.snapshot(tmp_path, min_free_bytes=0).reserved_bytes
    assert held > 16
    assert budget.reconcile(tmp_path).reserved_bytes == held
    assert budget_at(tmp_path, alive=False).reconcile(tmp_path).reserved_bytes == (
        held if possibly_created else 0
    )
    if possibly_created:
        assert path.read_bytes() == b"uncertain"
