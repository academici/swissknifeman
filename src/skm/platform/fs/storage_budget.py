"""Host-wide conservative admission for managed local writes.

The private ledger directory is shared by every writer in an instance. Data IO
never holds its flock. Uncertain ownership or failed cleanup retains the reserve;
there is deliberately no automatic repair/reset of an untrusted ledger.
"""

import errno
import hashlib
import json
import os
import stat
import threading
import uuid
from collections.abc import Callable, Generator
from contextlib import contextmanager, suppress
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Final, cast

from skm.kernel.errors import BackendUnavailable, ErrorCode
from skm.platform.fs.atomic_write import atomic_write, fsync_dir
from skm.platform.fs.file_lock import FileLock, LockTimeout
from skm.platform.fs.safe_paths import safe_join

_LOCK_TIMEOUT_SECONDS: Final = 1.0


@dataclass(frozen=True, slots=True)
class StorageOwnerIdentity:
    boot_id: str
    pid: int
    start_identity: str


@dataclass(frozen=True, slots=True)
class StorageSnapshot:
    free_bytes: int
    reserved_bytes: int
    available_bytes: int
    unknown_owners: tuple[str, ...]


class ReservationExceeded(ValueError):
    """A chunk/file would exceed the reservation; none of that chunk is written."""


def _unavailable(reason: str) -> BackendUnavailable:
    return BackendUnavailable(
        ErrorCode.BACKEND_UNAVAILABLE, "storage budget unavailable", details={"reason": reason}
    )


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("expected object")
    result = cast("dict[object, object]", value)
    if not all(isinstance(key, str) for key in result):
        raise ValueError("expected string keys")
    return cast("dict[str, object]", result)


def _integer(value: object, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError("invalid integer")
    return value


def _text(value: object) -> str:
    if not isinstance(value, str) or not value or "\0" in value:
        raise ValueError("invalid string")
    return value


def _paths() -> list["_OwnedPath"]:
    return []


def _read_json(fd: int) -> object:
    try:
        stream = os.fdopen(fd, "rb")
    except BaseException as primary:
        try:
            os.close(fd)
        except OSError as error:
            primary.add_note(f"ledger descriptor close failed: {error}")
        raise
    try:
        value: object = json.load(stream)
    except BaseException as primary:
        try:
            stream.close()
        except OSError as error:
            primary.add_note(f"ledger close failed: {error}")
        raise
    else:
        stream.close()
        return value


@dataclass(slots=True)
class _OwnedPath:
    path: str
    dev: int | None = None
    ino: int | None = None


@dataclass(slots=True)
class _Entry:
    token: str
    owner_id: str
    identity: StorageOwnerIdentity
    root: str
    filesystem: int
    ceiling: int
    floor: int
    max_bytes: int
    max_files: int
    allocation_block: int
    paths: list[_OwnedPath] = field(default_factory=_paths)
    release_pending: bool = field(default=False, compare=False, repr=False)

    @classmethod
    def decode(cls, value: object) -> "_Entry":
        obj = _mapping(value)
        owner = _mapping(obj["identity"])
        identity = StorageOwnerIdentity(
            _text(owner["boot_id"]), _integer(owner["pid"], 1), _text(owner["start_identity"])
        )
        entry = cls(
            _text(obj["token"]),
            _text(obj["owner_id"]),
            identity,
            _text(obj["root"]),
            _integer(obj["filesystem"]),
            _integer(obj["ceiling"]),
            _integer(obj["floor"]),
            _integer(obj["max_bytes"]),
            _integer(obj["max_files"], 1),
            _integer(obj["allocation_block"], 4096),
        )
        if (
            not Path(entry.root).is_absolute()
            or entry.ceiling != entry.max_bytes + 2 * entry.allocation_block * entry.max_files
            or len(entry.token) != 32
            or any(ch not in "0123456789abcdef" for ch in entry.token)
        ):
            raise ValueError("invalid reserve/root")
        paths = obj["paths"]
        if not isinstance(paths, list):
            raise ValueError("invalid paths")
        paths = cast("list[object]", paths)
        if len(paths) > entry.max_files:
            raise ValueError("too many paths")
        for value in paths:
            item = _mapping(value)
            path = Path(_text(item["path"]))
            if not path.is_absolute() or ".." in path.parts or not path.is_relative_to(entry.root):
                raise ValueError("path outside reservation root")
            dev, ino = item["dev"], item["ino"]
            if (dev is None) != (ino is None):
                raise ValueError("incomplete file identity")
            entry.paths.append(
                _OwnedPath(
                    str(path),
                    None if dev is None else _integer(dev),
                    None if ino is None else _integer(ino, 1),
                )
            )
        if len({item.path for item in entry.paths}) != len(entry.paths):
            raise ValueError("duplicate paths")
        return entry


class StorageBudget:
    def __init__(
        self,
        ledger_dir: Path,
        *,
        free_bytes: Callable[[Path], int],
        identity: Callable[[], StorageOwnerIdentity],
        owner_alive: Callable[[StorageOwnerIdentity], bool | None],
    ) -> None:
        self.ledger_dir = ledger_dir.resolve()
        self.ledger_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = self.ledger_dir.stat()
        if info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise ValueError("storage ledger directory must be private and owned by this user")
        self._ledger = self.ledger_dir / "storage-budget.json"
        self._lock = self.ledger_dir / "storage-budget.lock"
        self._free_bytes, self._identity, self._owner_alive = free_bytes, identity, owner_alive

    def _read(self, path: Path) -> list[_Entry]:
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        except FileNotFoundError:
            return []
        try:
            obj = _mapping(_read_json(fd))
            checksum = obj.pop("checksum")
            encoded = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
            if checksum != hashlib.sha256(encoded).hexdigest() or set(obj) != {"version", "reservations"}:
                raise ValueError("ledger integrity check failed")
            if obj["version"] != 1 or type(obj["version"]) is not int:
                raise ValueError("unsupported ledger version")
            values = obj["reservations"]
            if not isinstance(values, list):
                raise ValueError("invalid reservations")
            entries = [_Entry.decode(value) for value in cast("list[object]", values)]
            if len({entry.token for entry in entries}) != len(entries):
                raise ValueError("duplicate reservation")
        except (ValueError, KeyError, TypeError, UnicodeError) as error:
            raise _unavailable("storage_ledger_corrupt") from error
        else:
            return entries

    def _load(self) -> list[_Entry]:
        entries = {entry.token: entry for entry in self._read(self._ledger)}
        for path in self.ledger_dir.glob(".storage-budget-release.*.json"):
            guarded = self._read(path)
            if not guarded and not path.exists():
                continue  # a concurrent successful release finished after glob
            if len(guarded) != 1 or self._release_guard(guarded[0]) != path:
                raise _unavailable("storage_ledger_corrupt")
            for entry in guarded:
                if entry.token in entries and entries[entry.token] != entry:
                    raise _unavailable("storage_ledger_corrupt")
                entry.release_pending = True
                entries[entry.token] = entry
        return list(entries.values())

    def _save(self, entries: list[_Entry]) -> None:
        # Do not copy an in-flight release back into the main ledger when another
        # admission runs between flock release and guard unlink.
        self._save_at(self._ledger, [entry for entry in entries if not entry.release_pending])

    @staticmethod
    def _save_at(path: Path, entries: list[_Entry]) -> None:
        records: list[dict[str, object]] = []
        for entry in entries:
            record = asdict(entry)
            record.pop("release_pending")
            records.append(record)
        data: dict[str, object] = {"version": 1, "reservations": records}
        encoded = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
        data["checksum"] = hashlib.sha256(encoded).hexdigest()
        atomic_write(path, json.dumps(data, separators=(",", ":")).encode(), private=True)

    def _release_guard(self, entry: _Entry) -> Path:
        # A separate durable copy remains authoritative across ledger replace,
        # lock release and close failures. Admission takes the union by token.
        if len(entry.token) != 32 or any(ch not in "0123456789abcdef" for ch in entry.token):
            raise _unavailable("storage_ledger_corrupt")
        return self.ledger_dir / f".storage-budget-release.{entry.token}.json"

    def _finish_release(self, entries: list[_Entry]) -> None:
        for entry in entries:
            # Another successful reconcile may have finished this release.
            with suppress(FileNotFoundError):
                self._release_guard(entry).unlink()
        # Intentionally no directory fsync after unlink: crash resurrection of a
        # guard is conservative. Unlink is the final fallible commit operation.

    @contextmanager
    def _locked(self) -> Generator[list[_Entry]]:
        lock = FileLock(self._lock)
        try:
            acquired = lock.acquire(blocking=True, timeout_seconds=_LOCK_TIMEOUT_SECONDS)
            if not acquired:
                raise LockTimeout(self._lock)
        except LockTimeout as error:
            raise _unavailable("storage_lock_timeout") from error
        try:
            yield self._load()
        except BaseException as primary:
            try:
                lock.release()
            except OSError as error:
                primary.add_note(f"storage ledger lock release failed: {error}")
                for note in getattr(error, "__notes__", ()):
                    primary.add_note(note)
            raise
        else:
            lock.release()

    def _snapshot(self, root: Path, entries: list[_Entry], floor: int) -> StorageSnapshot:
        free = _integer(self._free_bytes(root))
        reserved = sum(entry.ceiling for entry in entries)
        floor = max([floor, *(entry.floor for entry in entries)])
        unknown = tuple(
            sorted({entry.owner_id for entry in entries if self._owner_alive(entry.identity) is None})
        )
        return StorageSnapshot(free, reserved, max(0, free - reserved - floor), unknown)

    def snapshot(self, root: Path, *, min_free_bytes: int) -> StorageSnapshot:
        _integer(min_free_bytes)
        with self._locked() as entries:
            return self._snapshot(root, entries, min_free_bytes)

    @staticmethod
    def _files_settled(entry: _Entry) -> bool:
        for owned in entry.paths:
            try:
                path = Path(owned.path)
                safe_join(Path(entry.root), str(path.relative_to(entry.root)))
                info = path.lstat()
            except FileNotFoundError:
                continue
            except (OSError, ValueError):
                return False
            if (owned.dev, owned.ino) != (info.st_dev, info.st_ino) or not stat.S_ISREG(info.st_mode):
                return False
            # A dead writer may have left delayed allocation. Force allocation
            # and close our verified fd before trusting free_bytes again.
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
            try:
                verified = os.path.samestat(info, os.fstat(fd))
                if verified:
                    os.fsync(fd)
            except BaseException as primary:
                try:
                    os.close(fd)
                except OSError as error:
                    primary.add_note(f"reconcile close failed for {path}: {error}")
                raise
            else:
                os.close(fd)
            if not verified:
                return False
            fsync_dir(path.parent)
        return True

    def reconcile(self, root: Path) -> StorageSnapshot:
        with self._locked() as entries:
            dead = [entry for entry in entries if self._owner_alive(entry.identity) is False]
        # Data fsync is deliberately outside the ledger lock.
        settled = {entry.token: entry for entry in dead if self._files_settled(entry)}
        with self._locked() as entries:
            kept = [
                entry
                for entry in entries
                if settled.get(entry.token) != entry or self._owner_alive(entry.identity) is not False
            ]
            removed = [entry for entry in entries if entry not in kept]
            if len(kept) != len(entries):
                for entry in removed:
                    self._save_at(self._release_guard(entry), [entry])
                self._save(kept)
        self._finish_release(removed)
        return self.snapshot(root, min_free_bytes=0)

    def reserve(
        self,
        root: Path,
        *,
        owner_id: str,
        max_bytes: int,
        min_free_bytes: int,
        max_files: int = 1,
    ) -> "WriteReservation":
        _text(owner_id)
        _integer(max_bytes)
        _integer(min_free_bytes)
        _integer(max_files, 1)
        root = root.resolve(strict=True)
        block = max(4096, os.statvfs(root).f_frsize)
        # One partial allocation block plus inode/directory metadata per file.
        ceiling = max_bytes + 2 * block * max_files
        owner = self._identity()
        _text(owner.boot_id)
        _integer(owner.pid, 1)
        _text(owner.start_identity)
        entry = _Entry(
            uuid.uuid4().hex,
            owner_id,
            owner,
            str(root),
            root.stat().st_dev,
            ceiling,
            min_free_bytes,
            max_bytes,
            max_files,
            block,
        )
        with self._locked() as entries:
            free = _integer(self._free_bytes(root))
            floor = max([min_free_bytes, *(item.floor for item in entries)])
            if free - sum(item.ceiling for item in entries) < ceiling + floor:
                raise _unavailable("disk_low")
            entries.append(entry)
            self._save(entries)
        return WriteReservation(entry, self._update)

    def _update(self, entry: _Entry, *, release: bool = False) -> None:
        with self._locked() as entries:
            for index, current in enumerate(entries):
                if current.token == entry.token and current.identity == entry.identity:
                    if release:
                        break
                    entries[index] = entry
                    self._save(entries)
                    return
            else:
                raise RuntimeError("reservation missing or ownership changed")
            self._save_at(self._release_guard(entry), [entry])
            entries.pop(index)
            self._save(entries)
        self._finish_release([entry])


class _ReservationState:
    def __init__(self, entry: _Entry) -> None:
        self.entry = entry
        self.guard = threading.RLock()
        self.written = 0
        self.closed = False
        self.failed: BaseException | None = None
        self.cleanup_failed = False
        self.pid = os.getpid()

    def require_open(self) -> None:
        if self.pid != os.getpid():
            raise RuntimeError("reservation belongs to another process")
        if self.closed or self.failed is not None:
            raise RuntimeError("reservation is closed or failed")


def _record_cleanup_failure(state: _ReservationState, error: BaseException, context: str) -> None:
    state.cleanup_failed = True
    if state.failed is None:
        state.failed = error
    elif error is not state.failed:
        state.failed.add_note(f"{context}: {error}")
        for note in getattr(error, "__notes__", ()):
            state.failed.add_note(note)


class WriteReservation:
    def __init__(self, entry: _Entry, update: Callable[..., None]) -> None:
        self._state = _ReservationState(entry)
        self._entry, self._update = entry, update
        self._files: list[BudgetedFile] = []

    def _create_file(self, path: Path, owned: _OwnedPath) -> int:
        try:
            return os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        except OSError as primary:
            if primary.errno in (errno.EEXIST, errno.EISDIR, errno.ENOENT, errno.ENOTDIR, errno.ELOOP):
                # Exclusive-create/path-lookup refusals establish no creation.
                # Only undo this call's intent; never modify the refused path.
                # ENOSPC/EIO and unclassified failures keep the uncertain intent.
                self._entry.paths.remove(owned)
                try:
                    self._update(self._entry)
                except BaseException as error:  # noqa: BLE001 - preserve the original open refusal
                    self._state.cleanup_failed = True
                    primary.add_note(f"pending registration rollback failed for {path}: {error}")
                    for note in getattr(error, "__notes__", ()):
                        primary.add_note(note)
            raise

    def open_file(self, path: Path) -> "BudgetedFile":
        with self._state.guard:
            self._state.require_open()
            root = Path(self._entry.root)
            path = Path(os.path.abspath(path))
            path = safe_join(root, str(path.relative_to(root)))
            if len(self._entry.paths) >= self._entry.max_files:
                raise ReservationExceeded("reservation file ceiling exceeded")
            if any(item.path == str(path) for item in self._entry.paths):
                raise ValueError("path already registered")
            owned = _OwnedPath(str(path))
            self._entry.paths.append(owned)
            try:
                self._update(self._entry)
                fd = self._create_file(path, owned)
                writer = BudgetedFile(self._state, fd, path)
                self._files.append(writer)
                info = os.fstat(fd)
                owned.dev, owned.ino = info.st_dev, info.st_ino
                self._update(self._entry)
            except BaseException as error:
                self._state.failed = error
                if owned in self._entry.paths:
                    # Creation/ownership persistence remains uncertain. In
                    # particular, do not erase an intent after a successful open.
                    self._state.cleanup_failed = True
                for writer in self._files:
                    try:
                        writer.close()
                    except BaseException as cleanup:  # noqa: BLE001 - preserve failed open/registration
                        if cleanup is not error:
                            error.add_note(f"open_file cleanup failed for {writer.path}: {cleanup}")
                raise
            return writer

    def close(self) -> None:
        with self._state.guard:
            if self._state.closed:
                return
            if self._state.pid != os.getpid():
                raise RuntimeError("reservation belongs to another process")
            self._state.closed = True
            for writer in self._files:
                try:
                    writer.close()
                except BaseException as error:  # noqa: BLE001 - close all files while preserving primary
                    # BudgetedFile.close also re-raises an earlier operation
                    # error after successful cleanup; that is not a new failure.
                    if error is not self._state.failed:
                        _record_cleanup_failure(self._state, error, f"file close failed for {writer.path}")
            if not self._state.cleanup_failed:
                try:
                    self._update(self._entry, release=True)
                except BaseException as error:  # noqa: BLE001 - preserve operation error through ledger cleanup
                    _record_cleanup_failure(self._state, error, "reservation release failed")
            if self._state.failed is not None:
                raise self._state.failed

    def __enter__(self) -> "WriteReservation":
        self._state.require_open()
        return self

    def __exit__(self, *exc: object) -> None:
        primary = exc[1]
        if isinstance(primary, BaseException):
            self._state.failed = primary
        try:
            self.close()
        except BaseException as error:
            if not isinstance(primary, BaseException):
                raise
            if error is not primary:
                primary.add_note(f"reservation close failed: {error}")


class BudgetedFile:
    def __init__(self, reservation: _ReservationState, fd: int, path: Path) -> None:
        self._reservation, self._fd, self.path = reservation, fd, path
        self._closed = False

    def write(self, data: bytes) -> None:
        reservation = self._reservation
        with reservation.guard:
            reservation.require_open()
            if self._closed:
                raise ValueError("write to closed budgeted file")
            if len(data) > reservation.entry.max_bytes - reservation.written:
                raise ReservationExceeded("reservation byte ceiling exceeded")
            view = memoryview(data)
            retries = 0
            try:
                while view:
                    try:
                        size = os.write(self._fd, view)
                    except InterruptedError:
                        retries += 1
                        if retries >= 64:
                            raise
                        continue
                    if size <= 0 or size > len(view):
                        raise OSError(errno.EIO, "invalid/zero-length write")
                    reservation.written += size
                    view = view[size:]
            except BaseException as error:
                reservation.failed = error
                raise

    def close(self) -> None:
        reservation = self._reservation
        with reservation.guard:
            if self._closed:
                return
            if reservation.pid != os.getpid():
                raise RuntimeError("reservation belongs to another process")
            self._closed = True
            try:
                # Writes use unbuffered os.write, so no userspace flush is needed.
                os.fsync(self._fd)
            except BaseException as error:  # noqa: BLE001 - close fd even on cancellation
                _record_cleanup_failure(reservation, error, f"file fsync failed for {self.path}")
            try:
                os.close(self._fd)
            except BaseException as error:  # noqa: BLE001 - finish remaining cleanup despite cancellation
                _record_cleanup_failure(reservation, error, f"file close failed for {self.path}")
            try:
                fsync_dir(self.path.parent)
            except BaseException as error:  # noqa: BLE001 - retain reserve and the original operation error
                _record_cleanup_failure(reservation, error, f"directory fsync failed for {self.path.parent}")
            if reservation.failed is not None:
                raise reservation.failed
