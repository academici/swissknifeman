"""BlobStore contract: local store and memory double (adapters §4; artifacts §6, §6.1; lifecycle §8).

Both stores implement the ``BlobStore`` port as declared, and ``stage`` returns the port's ``StagingHandle``
(not the ``staged_blobs`` row) whose opaque ``staging_id`` never reaches outside staging. Duplicate bytes give
one object per workspace; promote never replaces an object; a same-size bit flip in an existing object is
refused with ``INTERNAL_ERROR(reason=blob_corrupt)`` without a location, and that object stays as it was;
digest mismatch, the size ceiling and a failing producer remove the staged bytes; a consumed handle is
``NotFound``; a handle altered after issue (workspace, digest or size) is refused before any IO, publishes
nothing and leaves the staging to its real handle; two concurrent stages with budget left for one are not both
admitted; keys outside the object layout are refused; ``recover_staging`` drops only staging older than its
cutoff, never objects. A store belongs to the process that made it: a forked child's copy (run for real, also
while the parent holds the store lock) honours no inherited handle and refuses stage and recovery, so it never
consumes, deletes or recovers the parent's staging, which the parent still promotes. Its object methods never
wait on the copied lock: the local copy acts on the finals the child shares, the memory copy, whose objects
are a snapshot of the parent's memory, refuses them too.

Local only: the whole ceiling is reserved before the 0600 ``O_EXCL`` staging file exists and held until
fsync/close; finals are born 0444 and their directory is fsynced after the link; every directory ensure
syncs its parent, also when a racing promote created it or an earlier sync failed, and every new store
syncs each entry on its root's path up to ``/`` itself, made or found, before it can promote: also one a
racing first creator made and has not synced or failed to sync (that failure propagates), also on a retry,
also when the directory holding it is no longer writable; a directory on that path it cannot open fails the
store, and no directory sync error, not even one ``fsync_dir`` would take as unsupported, passes as synced;
the ``FileExistsError`` race is
verified like any existing final; a symlink, FIFO or directory at a final name is never followed; only the
issuing store honours a handle; staged bytes changed in place after stage are never published; a crashed stage
never becomes a final; crash temps and a restarted store stay inside the shared ledger, the staging TTL never
releases an unknown owner's reserve, recovery goes on past a staging file that vanishes after the listing, and
neither an admission refusal nor staging recovery removes a final. Recovery removes only staging proven
abandoned: never a live peer's in-flight or issued staging, whatever its age, never the staging of a running
promote, never the staging a forked child's fresh store finds locked by the parent, and a directory it wins
before the new store's lock is replaced, not used. Entries outside the instance layout, such as legacy flat
``staging/<id>.part`` files, are left for their owner.
"""

import errno
import hashlib
import inspect
import multiprocessing
import os
import stat
import sys
import threading
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, fields, replace
from datetime import UTC, datetime, timedelta
from functools import partial
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any, BinaryIO, cast
from uuid import UUID

import pytest

from fakes.clock import FrozenClock
from skm.adapters.blobs.local import store as local_store
from skm.adapters.blobs.local.store import LocalBlobStore
from skm.adapters.memory.blob_store import MemoryBlobStore
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable, InternalError, NotFound, ValidationFailed
from skm.kernel.ids import WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.modules.artifacts.domain.staged_blob import StagedBlob
from skm.modules.artifacts.ports import BlobObjectStat, BlobStore, StagingHandle
from skm.platform.fs.atomic_write import UnsafePathError
from skm.platform.fs.storage_budget import StorageBudget, StorageOwnerIdentity

WS = WorkspaceId(UUID("0192f5c5-0a10-7b22-8f00-1a2b3c4d5e6f"))
OTHER = WorkspaceId(UUID("0192f5c5-0b33-7c44-9a00-2b3c4d5e6f70"))
MAX = 64 * 1024
DATA = b"storage design audit\n" * 50
FUTURE = datetime(2999, 1, 1, tzinfo=UTC)  # every staging file is older: age alone proves nothing


def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def key_of(workspace_id: WorkspaceId, data: bytes) -> str:
    hex_digest = hashlib.sha256(data).hexdigest()
    return f"{workspace_id}/objects/{hex_digest[:2]}/{hex_digest}"


def location_of(key: str) -> JsonObject:
    return {"backend_id": "local-primary", "storage_key": key, "storage_version": None}


def flipped(data: bytes) -> bytes:
    changed = bytearray(data)
    changed[len(changed) // 2] ^= 0x01
    return bytes(changed)


class Disk:
    """A fake volume: ``free_bytes`` is capacity minus the bytes of distinct inodes under the root."""

    def __init__(self, root: Path, capacity: int) -> None:
        self.root, self.capacity = root, capacity

    def free(self, _: Path) -> int:
        seen: set[tuple[int, int]] = set()
        used = 0
        for folder, _dirs, names in os.walk(self.root):
            for name in names:
                try:
                    info = os.lstat(os.path.join(folder, name))
                except FileNotFoundError:
                    continue
                if stat.S_ISREG(info.st_mode) and (info.st_dev, info.st_ino) not in seen:
                    seen.add((info.st_dev, info.st_ino))
                    used += info.st_size
        return max(0, self.capacity - used)


def identity() -> StorageOwnerIdentity:
    return StorageOwnerIdentity("boot", os.getpid(), "birth")


@dataclass
class Backend:
    kind: str
    store: BlobStore
    peer: Callable[[], BlobStore]  # another instance over the same storage and ledger (memory: the same one)
    staged_count: Callable[[], int]
    reserved: Callable[[], int]
    corrupt: Callable[[JsonObject], None]  # same-size bit flip of an object in place
    raw: Callable[[JsonObject], tuple[bytes, object]]  # bytes plus an identity of the stored object
    ceiling: int


@dataclass
class Local:
    root: Path
    ledger: Path
    disk: Disk
    ceiling: int

    def budget(self, alive: bool | None = True) -> StorageBudget:
        return StorageBudget(
            self.ledger, free_bytes=self.disk.free, identity=identity, owner_alive=lambda _: alive
        )

    def make(self, alive: bool | None = True) -> LocalBlobStore:
        return LocalBlobStore(self.root, max_bytes=MAX, min_free_bytes=0, storage_budget=self.budget(alive))

    @property
    def staging(self) -> Path:
        return self.root / "staging"

    def parts(self) -> list[Path]:
        """Staging files of every store over this root (each writes under its own ``staging/<instance>/``)."""
        return sorted(self.staging.resolve().glob("*/*.part"))

    def part(self, staged: StagingHandle) -> Path:
        (found,) = self.staging.resolve().glob(f"*/{staged.staging_id}.part")
        return found

    def final(self, location: JsonObject) -> Path:
        return self.root / str(location["storage_key"])


def local_env(tmp_path: Path, *, capacity: int | None = None) -> Local:
    block = max(4096, os.statvfs(tmp_path).f_frsize)
    ceiling = MAX + 2 * block  # the reservation helper's per-file allowance (storage_budget.reserve)
    root = tmp_path / "blobs"
    disk = Disk(root, 1 << 40 if capacity is None else capacity)
    return Local(root, tmp_path / "locks", disk, ceiling)


def local_backend(env: Local) -> Backend:
    store = env.make()

    def corrupt(location: JsonObject) -> None:
        path = env.final(location)
        path.chmod(0o600)
        data = flipped(path.read_bytes())
        with path.open("r+b") as stream:  # same inode, same size
            stream.write(data)
        path.chmod(0o444)

    def raw(location: JsonObject) -> tuple[bytes, object]:
        path = env.final(location)
        info = path.lstat()
        return path.read_bytes(), (info.st_dev, info.st_ino, stat.S_IMODE(info.st_mode))

    return Backend(
        "local",
        store,
        env.make,
        lambda: len(env.parts()),
        lambda: env.budget().snapshot(env.root, min_free_bytes=0).reserved_bytes,
        corrupt,
        raw,
        env.ceiling,
    )


def memory_backend(*, capacity: int | None = None) -> Backend:
    store = MemoryBlobStore(FrozenClock(), max_bytes=MAX, capacity_bytes=capacity)

    def corrupt(location: JsonObject) -> None:
        key = str(location["storage_key"])
        found = store._objects[key]
        store._objects[key] = replace(found, data=flipped(found.data))

    def raw(location: JsonObject) -> tuple[bytes, object]:
        found = store._objects[str(location["storage_key"])]
        return found.data, found.created_at

    return Backend(
        "memory",
        store,
        lambda: store,
        lambda: len(store._staging),
        lambda: store._reserved,
        corrupt,
        raw,
        MAX,
    )


def make_backend(kind: str, tmp_path: Path, *, capacity: Callable[[int], int] | None = None) -> Backend:
    if kind == "local":
        probe = local_env(tmp_path)
        env = local_env(tmp_path, capacity=None if capacity is None else capacity(probe.ceiling))
        return local_backend(env)
    return memory_backend(capacity=None if capacity is None else capacity(MAX))


@pytest.fixture(params=["local", "memory"])
def backend(request: pytest.FixtureRequest, tmp_path: Path) -> Backend:
    return make_backend(request.param, tmp_path)


@pytest.fixture
def local(tmp_path: Path) -> Local:
    return local_env(tmp_path)


def pieces(data: bytes, size: int = 7) -> Iterator[bytes]:
    for start in range(0, len(data), size):
        yield data[start : start + size]


def outcome_of(call: Callable[[], object]) -> tuple[str, object]:
    """What ``call`` returned, or the type and details of what it raised."""
    try:
        return ("returned", call())
    except Exception as error:  # noqa: BLE001 - the outcome is what is asserted
        return (type(error).__name__, dict(getattr(error, "details", None) or {}))


def _answer(sender: Connection, call: Callable[[], object]) -> None:
    sender.send(call())


def in_fork(call: Callable[[], object]) -> object:
    """What ``call`` returns in a real forked child, which holds a copy of the parent and its stores."""
    context = multiprocessing.get_context("fork")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_answer, args=(sender, call))
    process.start()
    sender.close()
    try:
        answered = receiver.poll(10)  # a child waiting on an inherited lock never answers
        answer = receiver.recv() if answered else None
    finally:
        process.join(10)
        if process.is_alive():
            process.kill()
            process.join(5)
        receiver.close()
    assert answered, "the forked child never answered"
    assert process.exitcode == 0
    return answer


# -- both stores -------------------------------------------------------------------------------------------


def _port_methods() -> dict[str, inspect.Signature]:
    return {
        name: inspect.signature(member)
        for name, member in vars(BlobStore).items()
        if inspect.isfunction(member) and not name.startswith("_")
    }


@pytest.mark.parametrize("adapter", [LocalBlobStore, MemoryBlobStore])
def test_stores_implement_the_port_as_declared(adapter: type) -> None:
    port = _port_methods()
    assert set(port) == {
        "stage",
        "promote",
        "open",
        "exists",
        "verify",
        "stat",
        "discard",
        "iter_objects",
        "delete_unreferenced",
        "recover_staging",
    }
    for name, declared in port.items():
        implemented = inspect.signature(getattr(adapter, name))
        assert [(p.name, p.kind) for p in implemented.parameters.values()] == [
            (p.name, p.kind) for p in declared.parameters.values()
        ], name
    # The handle is the port's own type, distinct from the staged_blobs row.
    assert [field.name for field in fields(StagingHandle)] == [
        "workspace_id",
        "digest",
        "size_bytes",
        "staging_id",
    ]
    assert StagingHandle is not StagedBlob


def test_duplicate_bytes_promote_to_one_object(backend: Backend) -> None:
    store = backend.store
    staged = store.stage(WS, pieces(DATA))
    assert isinstance(staged, StagingHandle)
    assert (staged.workspace_id, staged.digest, staged.size_bytes) == (WS, digest(DATA), len(DATA))
    first = store.promote(staged)
    second = store.promote(store.stage(WS, [DATA]), expected_digest=digest(DATA))
    assert first == second == location_of(key_of(WS, DATA))
    assert list(store.iter_objects(WS)) == [first]
    assert list(store.iter_objects(OTHER)) == []
    assert backend.staged_count() == 0
    assert backend.reserved() == 0
    with store.open(first) as stream:
        assert stream.read() == DATA
    assert store.exists(first)
    assert store.verify(first, digest(DATA))
    assert not store.verify(first, digest(b"other"))
    info = store.stat(first)
    assert info == BlobObjectStat(len(DATA), info.created_at)
    assert info.created_at.utcoffset() == timedelta(0)
    # Content addressing is per workspace: the same bytes elsewhere are a separate object.
    elsewhere = store.promote(store.stage(OTHER, [DATA]))
    assert elsewhere == location_of(key_of(OTHER, DATA))
    assert list(store.iter_objects(WS)) == [first]


def test_empty_upload_is_a_valid_object(backend: Backend) -> None:
    location = backend.store.promote(backend.store.stage(WS, []))
    assert location == location_of(key_of(WS, b""))
    with backend.store.open(location) as stream:
        assert stream.read() == b""


def test_digest_mismatch_discards_staging_without_object(backend: Backend) -> None:
    store = backend.store
    staged = store.stage(WS, [b"hello world!"])
    expected = "sha256:" + "0" * 64
    with pytest.raises(ValidationFailed) as caught:
        store.promote(staged, expected_digest=expected)
    assert caught.value.code is ErrorCode.BLOB_DIGEST_MISMATCH
    assert dict(caught.value.details) == {"expected": expected, "actual": digest(b"hello world!")}
    assert backend.staged_count() == 0
    assert list(store.iter_objects(WS)) == []
    assert not store.exists(location_of(key_of(WS, b"hello world!")))


def test_size_ceiling_removes_staging_and_releases_reserve(backend: Backend) -> None:
    store = backend.store
    with pytest.raises(ValidationFailed) as caught:
        store.stage(WS, [b"a" * (MAX - 1), b"bc"])
    assert caught.value.code is ErrorCode.BLOB_TOO_LARGE
    assert dict(caught.value.details) == {"limit": MAX, "received_at_least": MAX + 1}
    assert backend.staged_count() == 0
    assert backend.reserved() == 0
    assert list(store.iter_objects(WS)) == []
    exact = store.stage(WS, [b"a" * MAX])
    assert exact.size_bytes == MAX


def _dies() -> Iterator[bytes]:
    yield b"partial"
    raise RuntimeError("producer died")


@pytest.mark.parametrize(
    ("chunks", "error"),
    [
        (_dies, RuntimeError),
        (lambda: iter([b"ok", "text"]), TypeError),
        (lambda: iter([b"ok", 104]), TypeError),  # never 104 zero bytes
    ],
    ids=["producer-exception", "str-chunk", "int-chunk"],
)
def test_failing_producer_removes_staging(
    backend: Backend, chunks: Callable[[], Iterator[Any]], error: type[Exception]
) -> None:
    with pytest.raises(error):
        backend.store.stage(WS, chunks())
    assert backend.staged_count() == 0
    assert backend.reserved() == 0
    assert list(backend.store.iter_objects(WS)) == []


def test_discard_removes_staged_bytes_and_is_idempotent(backend: Backend) -> None:
    staged = backend.store.stage(WS, [DATA])
    assert backend.staged_count() == 1
    backend.store.discard(staged)
    backend.store.discard(staged)
    assert backend.staged_count() == 0
    assert list(backend.store.iter_objects(WS)) == []


def test_consumed_handle_is_not_found(backend: Backend) -> None:
    store = backend.store
    promoted, discarded = store.stage(WS, [DATA]), store.stage(WS, [b"discarded"])
    location = store.promote(promoted)
    store.discard(discarded)
    for handle in (promoted, discarded):
        with pytest.raises(NotFound) as caught:
            store.promote(handle)
        assert dict(caught.value.details) == {"kind": "staged_blob"}
    assert list(store.iter_objects(WS)) == [location]
    assert backend.staged_count() == 0


@pytest.mark.parametrize(
    "staging_id",
    [
        "../victim",
        "../../victim.part",
        "/var/victim",
        "0192f5cb-6001-4a01-8000-0a1b2c3d4e60.part",
        "0192F5CB-6001-4A01-8000-0A1B2C3D4E60",
        "0192f5cb-6001-4a01-8000-0a1b2c3d4e60/../victim",
        "",
        104,
    ],
)
def test_forged_staging_id_is_refused(backend: Backend, staging_id: object) -> None:
    store = backend.store
    kept = store.stage(WS, [DATA])
    forged = StagingHandle(WS, digest(DATA), len(DATA), cast(str, staging_id))
    for call in (lambda: store.promote(forged), lambda: store.discard(forged)):
        with pytest.raises(ValueError, match=r"escapes_root|not a staging id"):
            call()
    assert list(store.iter_objects(WS)) == []
    assert backend.staged_count() == 1
    assert store.promote(kept) == location_of(key_of(WS, DATA))


FORGERIES: dict[str, Callable[[StagingHandle], StagingHandle]] = {
    "digest": lambda staged: replace(staged, digest=digest(flipped(DATA))),
    "workspace": lambda staged: replace(staged, workspace_id=OTHER),
    "workspace-and-digest": lambda staged: replace(staged, workspace_id=OTHER, digest=digest(flipped(DATA))),
    "size": lambda staged: replace(staged, size_bytes=len(DATA) - 1),
}


@pytest.mark.parametrize("forgery", FORGERIES)
def test_altered_handle_never_publishes_or_drops_the_staging(backend: Backend, forgery: str) -> None:
    store = backend.store
    staged = store.stage(WS, [DATA])
    forged = FORGERIES[forgery](staged)  # the issued staging_id under a claim the store never made
    calls: list[Callable[[], object]] = [
        lambda: store.promote(forged),
        lambda: store.promote(forged, expected_digest=forged.digest),
        lambda: store.discard(forged),
    ]
    for call in calls:
        with pytest.raises(ValueError, match="not issued"):
            call()
    for workspace in (WS, OTHER):
        assert list(store.iter_objects(workspace)) == []
    assert backend.staged_count() == 1  # refused before IO: neither published nor dropped
    # Nothing was taken under the false claim: the real bytes of that digest promote cleanly everywhere.
    for workspace in (WS, OTHER):
        real = store.promote(store.stage(workspace, [flipped(DATA)]), expected_digest=digest(flipped(DATA)))
        assert real == location_of(key_of(workspace, flipped(DATA)))
    assert store.promote(staged) == location_of(key_of(WS, DATA))
    assert list(store.iter_objects(OTHER)) == [location_of(key_of(OTHER, flipped(DATA)))]


def test_recover_staging_drops_only_stale_staging(backend: Backend) -> None:
    store = backend.store
    location = store.promote(store.stage(WS, [DATA]))
    staged = store.stage(WS, [b"in flight"])
    assert store.recover_staging(stale_before=datetime(2000, 1, 1, tzinfo=UTC)) == 0
    assert backend.staged_count() == 1
    assert store.recover_staging(stale_before=datetime(2999, 1, 1, tzinfo=UTC)) == 1
    assert backend.staged_count() == 0
    with pytest.raises(NotFound):
        store.promote(staged)
    assert list(store.iter_objects(WS)) == [location]  # objects are never staging remnants
    assert store.verify(location, digest(DATA))


# What a forked child gets from its copy of the parent's store: no inherited handle, no stage, no recovery.
INHERITED: dict[str, tuple[Callable[[BlobStore, StagingHandle], object], tuple[str, object]]] = {
    "promote": (lambda store, staged: store.promote(staged), ("NotFound", {"kind": "staged_blob"})),
    "discard": (lambda store, staged: store.discard(staged), ("returned", None)),
    "stage": (lambda store, _: store.stage(WS, [b"child"]), ("InternalError", {"reason": "staging_changed"})),
    "recover": (
        lambda store, _: store.recover_staging(stale_before=FUTURE),
        ("InternalError", {"reason": "staging_changed"}),
    ),
}


@pytest.mark.parametrize("operation", INHERITED)
def test_forked_child_never_acts_on_the_parent_staging(backend: Backend, operation: str) -> None:
    store = backend.store
    staged = store.stage(WS, [DATA])
    call, expected = INHERITED[operation]
    assert in_fork(lambda: outcome_of(partial(call, store, staged))) == expected
    assert backend.staged_count() == 1  # neither consumed, deleted nor recovered by the child
    assert backend.reserved() == 0
    for workspace in (WS, OTHER):
        assert list(store.iter_objects(workspace)) == []
    assert store.promote(staged) == location_of(key_of(WS, DATA))  # the parent still holds its claim
    assert backend.staged_count() == 0


def test_forked_child_refuses_before_taking_an_inherited_lock(backend: Backend) -> None:
    store = backend.store
    staged = store.stage(WS, [DATA])

    def every_operation() -> list[tuple[str, object]]:
        return [outcome_of(partial(call, store, staged)) for call, _ in INHERITED.values()]

    with cast(LocalBlobStore | MemoryBlobStore, store)._lock:  # forked held: the child's copy never frees
        answers = in_fork(every_operation)
    assert answers == [expected for _, expected in INHERITED.values()]
    assert store.promote(staged) == location_of(key_of(WS, DATA))


def read_all(stream: BinaryIO) -> bytes:
    with stream:
        return stream.read()


# The object methods in a forked child, run in this order (the delete last).
OBJECT_METHODS: dict[str, Callable[[BlobStore, JsonObject], object]] = {
    "exists": lambda store, location: store.exists(location),
    "verify": lambda store, location: store.verify(location, digest(DATA)),
    "open": lambda store, location: read_all(store.open(location)),
    "stat": lambda store, location: store.stat(location).size_bytes,
    "iter_objects": lambda store, _: list(store.iter_objects(WS)),
    "delete_unreferenced": lambda store, location: store.delete_unreferenced(location),
}


def test_forked_child_object_methods_never_wait_on_the_copied_lock(backend: Backend) -> None:
    store = backend.store
    location = store.promote(store.stage(WS, [DATA]))

    def every_method() -> list[tuple[str, object]]:
        return [outcome_of(partial(call, store, location)) for call in OBJECT_METHODS.values()]

    with cast(LocalBlobStore | MemoryBlobStore, store)._lock:  # forked held: the child's copy never frees
        answers = in_fork(every_method)
    if backend.kind == "local":
        # The finals are on the filesystem the child shares: it reads them, and its delete is the real one.
        assert answers == [("returned", value) for value in (True, True, DATA, len(DATA), [location], None)]
        assert not store.exists(location)
    else:
        # A snapshot of the parent's memory, which no later promote or delete reaches: refused, never stale.
        assert answers == [("InternalError", {"reason": "staging_changed"})] * len(OBJECT_METHODS)
        assert backend.raw(location)[0] == DATA
        assert list(store.iter_objects(WS)) == [location]


def test_same_size_bit_flip_is_refused_and_kept(backend: Backend) -> None:
    store = backend.store
    location = store.promote(store.stage(WS, [DATA]))
    backend.corrupt(location)
    kept = backend.raw(location)
    assert len(kept[0]) == len(DATA)
    registered: list[JsonObject] = []  # what an upload coordinator would record as staged metadata
    for _ in range(2):  # retries do not mask the corruption
        staged = store.stage(WS, [DATA])
        with pytest.raises(InternalError) as caught:
            registered.append(store.promote(staged, expected_digest=digest(DATA)))
        assert caught.value.code is ErrorCode.INTERNAL_ERROR
        assert dict(caught.value.details) == {
            "reason": "blob_corrupt",
            "backend_id": "local-primary",
            "storage_key": location["storage_key"],
        }
        assert backend.staged_count() == 0
    assert registered == []
    assert backend.raw(location) == kept  # not overwritten, deleted or renamed
    assert not store.verify(location, digest(DATA))
    assert list(store.iter_objects(WS)) == [location]


def test_concurrent_promotes_of_same_bytes_share_one_object(backend: Backend) -> None:
    store = backend.store
    staged = [store.stage(WS, [DATA]) for _ in range(6)]
    barrier = threading.Barrier(len(staged))

    def promote(item: StagingHandle) -> JsonObject:
        barrier.wait(timeout=5)
        return store.promote(item, expected_digest=digest(DATA))

    with ThreadPoolExecutor(len(staged)) as pool:
        locations = list(pool.map(promote, staged))
    assert locations == [location_of(key_of(WS, DATA))] * len(staged)
    assert list(store.iter_objects(WS)) == [locations[0]]
    assert backend.staged_count() == 0
    assert backend.raw(locations[0])[0] == DATA


@pytest.mark.parametrize("kind", ["local", "memory"])
def test_two_concurrent_stages_with_budget_for_one(tmp_path: Path, kind: str) -> None:
    backend = make_backend(kind, tmp_path, capacity=lambda ceiling: ceiling + MAX // 2)
    referenced = backend.store.promote(backend.store.stage(WS, [DATA]))
    kept = backend.raw(referenced)
    started, release = threading.Event(), threading.Event()
    result: dict[str, Any] = {}

    def slow() -> Iterator[bytes]:
        yield b"first"
        started.set()
        assert release.wait(5)
        yield b"-done"

    def first() -> None:
        result["staged"] = backend.store.stage(WS, slow())

    thread = threading.Thread(target=first)
    thread.start()
    try:
        assert started.wait(5)
        peer = backend.peer()  # another ingress over the same ledger/storage
        before = backend.staged_count()
        with pytest.raises(BackendUnavailable) as caught:
            peer.stage(WS, [b"second"])
        assert caught.value.code is ErrorCode.BACKEND_UNAVAILABLE
        assert caught.value.details["reason"] == "disk_low"
        assert backend.staged_count() == before  # refused before any staging write
        assert backend.raw(referenced) == kept  # admission never frees space by removing objects
    finally:
        release.set()
        thread.join(5)
    assert result["staged"].size_bytes == len(b"first-done")
    second = peer.stage(WS, [b"second"])  # the first reserve ends with its fsync/close
    assert peer.promote(second) == location_of(key_of(WS, b"second"))
    assert backend.store.promote(result["staged"]) == location_of(key_of(WS, b"first-done"))
    assert backend.reserved() == 0


@pytest.mark.parametrize(
    "key",
    [
        f"../{key_of(WS, DATA)}",
        f"/{key_of(WS, DATA)}",
        f"{key_of(WS, DATA)}/../../escape",
        f"{key_of(WS, DATA)}\0",
        key_of(WS, DATA).upper(),
        f"{WS}/objects/zz/{hashlib.sha256(DATA).hexdigest()}",
        f"{WS}/{hashlib.sha256(DATA).hexdigest()}",
        f"workspace/objects/{key_of(WS, DATA).split('/', 2)[2]}",
        "staging/0192f5cb-6001-4a01-8000-0a1b2c3d4e60.part",
        "",
        104,
    ],
)
def test_keys_outside_the_object_layout_are_refused(backend: Backend, key: object) -> None:
    location = cast(JsonObject, {"backend_id": "local-primary", "storage_key": key, "storage_version": None})
    calls: list[Callable[[], object]] = [
        lambda: backend.store.open(location),
        lambda: backend.store.exists(location),
        lambda: backend.store.verify(location, digest(DATA)),
        lambda: backend.store.stat(location),
        lambda: backend.store.delete_unreferenced(location),
    ]
    for call in calls:
        with pytest.raises(ValidationFailed) as caught:
            call()
        assert caught.value.code is ErrorCode.SCHEMA_INVALID
        assert caught.value.details["field"] == "storage_key"


def test_foreign_backend_location_is_refused(backend: Backend) -> None:
    location = backend.store.promote(backend.store.stage(WS, [DATA]))
    foreign = {**location, "backend_id": "s3-archive"}
    with pytest.raises(ValidationFailed) as caught:
        backend.store.open(foreign)
    assert caught.value.details["field"] == "backend_id"
    with pytest.raises(ValidationFailed):
        backend.store.delete_unreferenced(foreign)
    assert backend.store.exists(location)


def test_missing_object_is_not_found(backend: Backend) -> None:
    location = location_of(key_of(WS, DATA))
    for call in (backend.store.open, backend.store.stat, lambda loc: backend.store.verify(loc, digest(DATA))):
        with pytest.raises(NotFound) as caught:
            call(location)
        assert dict(caught.value.details) == {"kind": "blob_location"}
    assert not backend.store.exists(location)
    backend.store.delete_unreferenced(location)  # idempotent no-op


def test_delete_unreferenced_removes_only_that_object(backend: Backend) -> None:
    store = backend.store
    gone = store.promote(store.stage(WS, [DATA]))
    kept = store.promote(store.stage(WS, [b"kept"]))
    store.delete_unreferenced(gone)
    store.delete_unreferenced(gone)
    assert list(store.iter_objects(WS)) == [kept]
    assert not store.exists(gone)
    assert store.promote(store.stage(WS, [DATA])) == gone  # a later upload recreates it


# -- local store -------------------------------------------------------------------------------------------


def test_stage_reserves_ceiling_before_private_exclusive_staging(local: Local) -> None:
    backend = local_backend(local)
    seen: dict[str, int] = {}

    def chunks() -> Iterator[bytes]:
        yield b"abc"
        (part,) = local.parts()
        seen["mode"] = stat.S_IMODE(part.lstat().st_mode)
        seen["reserved"] = backend.reserved()
        yield b"def"

    staged = backend.store.stage(WS, chunks())
    assert seen == {"mode": 0o600, "reserved": local.ceiling}
    assert backend.reserved() == 0
    assert isinstance(staged, StagingHandle)
    assert str(UUID(staged.staging_id, version=4)) == staged.staging_id  # an id, not a path
    assert local.parts() == [local.part(staged)]
    assert local.part(staged).read_bytes() == b"abcdef"
    for folder in (local.root, local.staging, local.part(staged).parent):
        assert stat.S_IMODE(folder.lstat().st_mode) == 0o700


def test_exclusive_create_never_touches_a_foreign_staging_file(
    local: Local, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = local.make()
    fixed = UUID("0192f5cb-6001-4a01-8000-0a1b2c3d4e60")
    monkeypatch.setattr(local_store.uuid, "uuid4", lambda: fixed)
    (own,) = local.staging.iterdir()
    foreign = own / f"{fixed}.part"
    foreign.write_bytes(b"foreign")
    with pytest.raises(FileExistsError):
        store.stage(WS, [DATA])
    assert foreign.read_bytes() == b"foreign"
    assert local.budget().snapshot(local.root, min_free_bytes=0).reserved_bytes == 0


def test_disk_low_refuses_before_any_staging_and_keeps_finals(local: Local) -> None:
    backend = local_backend(local)
    referenced = backend.store.promote(backend.store.stage(WS, [DATA]))
    kept = backend.raw(referenced)
    local.disk.capacity = local.ceiling  # one byte short once the final is counted
    with pytest.raises(BackendUnavailable) as caught:
        backend.store.stage(WS, [b"next"])
    assert caught.value.details["reason"] == "disk_low"
    assert backend.staged_count() == 0
    assert backend.reserved() == 0
    assert backend.raw(referenced) == kept


def test_promote_links_read_only_final_then_fsyncs_its_directory(
    local: Local, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = local.make()
    staged = store.stage(WS, [DATA])
    staged_inode = local.part(staged).lstat().st_ino
    events: list[object] = []
    real_link, real_sync_dir = os.link, local_store._sync_dir

    def link(src: str | Path, dst: str | Path, **kwargs: Any) -> None:
        events.append(("link", stat.S_IMODE(os.lstat(src).st_mode)))
        real_link(src, dst, **kwargs)

    def sync_dir(folder: Path) -> None:
        events.append(Path(folder))
        real_sync_dir(folder)

    monkeypatch.setattr(os, "link", link)
    monkeypatch.setattr(local_store, "_sync_dir", sync_dir)
    location = store.promote(staged)
    final = local.final(location).resolve()
    info = final.lstat()
    assert stat.S_IMODE(info.st_mode) == 0o444
    assert info.st_ino == staged_inode
    assert info.st_nlink == 1  # staging name removed
    assert ("link", 0o444) in events  # born read-only
    assert events.index(final.parent) > events.index(("link", 0o444))
    for folder in (final.parent, final.parent.parent, final.parent.parent.parent):
        assert stat.S_IMODE(folder.lstat().st_mode) == 0o700
    assert final.read_bytes() == DATA


def test_every_directory_ensure_syncs_its_parent_under_racing_promotes(
    local: Local, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = local.make()
    staged = [store.stage(WS, [DATA + bytes([n])]) for n in range(6)]
    root = local.root.resolve()
    above = [root, root / str(WS), root / str(WS) / "objects"]  # parents of the directories a promote ensures
    events: dict[int, list[object]] = {}
    real_link, real_sync_dir = os.link, local_store._sync_dir

    def link(src: str | Path, dst: str | Path, **kwargs: Any) -> None:
        real_link(src, dst, **kwargs)
        events.setdefault(threading.get_ident(), []).append(("link", Path(dst)))

    def sync_dir(folder: Path) -> None:
        real_sync_dir(folder)
        events.setdefault(threading.get_ident(), []).append(Path(folder))

    monkeypatch.setattr(os, "link", link)
    monkeypatch.setattr(local_store, "_sync_dir", sync_dir)
    barrier = threading.Barrier(len(staged))

    def promote(item: StagingHandle) -> JsonObject:
        barrier.wait(timeout=5)  # all promotes race for the same new workspace directories
        return store.promote(item)

    with ThreadPoolExecutor(len(staged)) as pool:
        locations = list(pool.map(promote, staged))
    assert locations == [location_of(key_of(WS, DATA + bytes([n]))) for n in range(6)]
    assert len(events) == len(staged)
    for seen in events.values():
        # Each promote, winner or loser of a mkdir, made every entry above its final durable before linking.
        (linked,) = [event for event in seen if isinstance(event, tuple)]
        at = seen.index(linked)
        assert all(folder in seen[:at] for folder in above), seen
        assert cast(Path, linked[1]).parent in seen[at:]


@pytest.mark.parametrize("failing", ["root", "workspace", "objects", "shard"])
def test_directory_sync_is_retried_after_a_failed_fsync(
    local: Local, monkeypatch: pytest.MonkeyPatch, failing: str
) -> None:
    store = local.make()
    root = local.root.resolve()
    final = root / key_of(WS, DATA)
    folder = {
        "root": root,
        "workspace": root / str(WS),
        "objects": final.parent.parent,
        "shard": final.parent,
    }
    real_sync_dir = local_store._sync_dir
    synced: list[Path] = []

    def broken(path: Path) -> None:
        if Path(path) == folder[failing]:
            raise OSError(errno.EIO, "injected fsync failure")
        real_sync_dir(path)

    def recording(path: Path) -> None:
        real_sync_dir(path)
        synced.append(Path(path))

    staged = store.stage(WS, [DATA])
    monkeypatch.setattr(local_store, "_sync_dir", broken)
    with pytest.raises(OSError, match="injected fsync failure") as caught:
        store.promote(staged)
    assert caught.value.errno == errno.EIO
    assert local.parts() == []
    assert final.exists() == (failing == "shard")  # only the last sync comes after the link
    monkeypatch.setattr(local_store, "_sync_dir", recording)
    retry = store.stage(WS, [DATA])
    synced.clear()
    assert store.promote(retry) == location_of(key_of(WS, DATA))
    assert folder[failing] in synced  # the directory left unsynced is synced before success is reported
    assert final.read_bytes() == DATA


def test_new_root_and_its_new_parents_are_synced_in_their_parents(
    tmp_path: Path, local: Local, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_sync_dir = local_store._sync_dir
    base = tmp_path.resolve()
    synced: list[Path] = []

    def recording(path: Path) -> None:
        real_sync_dir(path)
        synced.append(Path(path).resolve())

    monkeypatch.setattr(local_store, "_sync_dir", recording)
    root = base / "a" / "b" / "blobs"
    LocalBlobStore(root, max_bytes=MAX, min_free_bytes=0, storage_budget=local.budget())
    # Every entry from ``/`` down, then staging under the root, then this store's own directory under staging.
    chain = [*reversed(base.parents), base, base / "a", base / "a" / "b", root, root / "staging"]
    assert synced == chain
    assert stat.S_IMODE(root.lstat().st_mode) == 0o700
    synced.clear()
    LocalBlobStore(root, max_bytes=MAX, min_free_bytes=0, storage_budget=local.budget())
    # Any existing entry may be a racing creator's unsynced one: the whole path again, and an own directory.
    assert synced == chain
    assert len(list((root / "staging").iterdir())) == 2


@pytest.mark.skipif(os.geteuid() == 0, reason="permission bits do not fence the root user")
@pytest.mark.parametrize("after", ["retry", "peer"])
def test_root_path_sync_never_trusts_the_current_permissions(
    tmp_path: Path, local: Local, monkeypatch: pytest.MonkeyPatch, after: str
) -> None:
    base = tmp_path.resolve() / "base"
    base.mkdir(mode=0o700)
    root = base / "a" / "b" / "blobs"
    real_sync_dir = local_store._sync_dir
    paused, resume = threading.Event(), threading.Event()
    synced: list[Path] = []
    failed: list[OSError] = []

    def first_fails_in_base(path: Path) -> None:
        if threading.current_thread() is first and Path(path) == base:
            if after == "peer":  # still racing: ``a`` is made in base and not synced there yet
                paused.set()
                assert resume.wait(5)
            raise OSError(errno.EIO, "injected fsync failure")
        real_sync_dir(path)
        if threading.current_thread() is threading.main_thread():
            synced.append(Path(path))

    def create() -> None:
        try:
            LocalBlobStore(root, max_bytes=MAX, min_free_bytes=0, storage_budget=local.budget())
        except OSError as error:
            failed.append(error)

    monkeypatch.setattr(local_store, "_sync_dir", first_fails_in_base)
    first = threading.Thread(target=create)
    first.start()
    try:
        if after == "retry":
            first.join(5)
        else:
            assert paused.wait(5)
        base.chmod(0o500)  # since ``a`` was made in it, base is no longer writable by this user
        second = LocalBlobStore(root, max_bytes=MAX, min_free_bytes=0, storage_budget=local.budget())
    finally:
        base.chmod(0o700)
        resume.set()
        first.join(5)
    # The unwritable base still holds the entry this user's store made: synced before success, as all above.
    assert synced == [*reversed(base.parents), base, base / "a", base / "a" / "b", root, root / "staging"]
    assert [error.errno for error in failed] == [errno.EIO]
    monkeypatch.undo()
    assert second.promote(second.stage(WS, [DATA])) == location_of(key_of(WS, DATA))


@pytest.mark.skipif(os.geteuid() == 0, reason="permission bits do not fence the root user")
def test_root_path_sync_fails_closed_on_a_directory_it_cannot_open(tmp_path: Path, local: Local) -> None:
    sealed = tmp_path.resolve() / "sealed"
    root = sealed / "a" / "blobs"
    root.mkdir(parents=True, mode=0o700)  # ``a`` in sealed: this user's entry, made while sealed was writable
    sealed.chmod(0o100)  # search only now: the path resolves, sealed cannot be opened to sync ``a`` in it
    try:
        with pytest.raises(PermissionError) as caught:
            LocalBlobStore(root, max_bytes=MAX, min_free_bytes=0, storage_budget=local.budget())
    finally:
        sealed.chmod(0o700)
    assert caught.value.errno == errno.EACCES  # durability that cannot be established is a refusal
    assert not (root / "staging").exists()  # no store


# What ``fsync_dir`` takes as "nothing to sync"; no blob store sync passes any of them as done.
UNSUPPORTED_SYNC = [errno.EINVAL, errno.ENOTSUP, errno.EPERM, errno.EISDIR, errno.EBADF]


def fail_directory(monkeypatch: pytest.MonkeyPatch, directory: Path, step: str, code: int) -> None:
    """Make the ``open`` or the ``fsync`` of exactly ``directory`` fail with ``code``."""
    real_open, real_fsync = os.open, os.fsync
    target = directory.stat()

    def open_(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        if step == "open" and flags & os.O_DIRECTORY and Path(path) == directory:
            raise OSError(code, os.strerror(code), str(path))
        return real_open(path, flags, *args, **kwargs)

    def fsync(fd: int) -> None:
        if step == "fsync" and os.path.samestat(os.fstat(fd), target):
            raise OSError(code, os.strerror(code))
        real_fsync(fd)

    monkeypatch.setattr(os, "open", open_)
    monkeypatch.setattr(os, "fsync", fsync)


@pytest.mark.parametrize("code", UNSUPPORTED_SYNC, ids=errno.errorcode.get)
@pytest.mark.parametrize("step", ["open", "fsync"])
def test_no_directory_sync_error_passes_as_synced(
    local: Local, monkeypatch: pytest.MonkeyPatch, step: str, code: int
) -> None:
    ancestor = local.root.resolve().parent  # holds the root's entry
    fail_directory(monkeypatch, ancestor, step, code)
    with pytest.raises(OSError, match=os.strerror(code)) as caught:
        local.make()
    assert caught.value.errno == code  # no store
    assert not local.staging.exists()
    monkeypatch.undo()
    store = local.make()
    final = local.root.resolve() / key_of(WS, DATA)
    final.parent.mkdir(parents=True, mode=0o700)
    final.parent.parent.chmod(0o700)
    final.parent.parent.parent.chmod(0o700)
    fail_directory(monkeypatch, final.parent, step, code)
    with pytest.raises(OSError, match=os.strerror(code)) as caught:
        store.promote(store.stage(WS, [DATA]))  # the link is made, its entry cannot be shown durable
    assert caught.value.errno == code  # no location
    monkeypatch.undo()
    assert store.promote(store.stage(WS, [DATA])) == location_of(key_of(WS, DATA))


@pytest.mark.parametrize("failing", ["base", "a", "b"])
def test_new_root_retry_syncs_the_entry_a_failed_parent_sync_left(
    tmp_path: Path, local: Local, monkeypatch: pytest.MonkeyPatch, failing: str
) -> None:
    base = tmp_path.resolve()
    root = base / "a" / "b" / "blobs"
    chain = [base, base / "a", base / "a" / "b", root, root / "staging"]  # each synced for the entry below it
    parent = {"base": base, "a": base / "a", "b": base / "a" / "b"}[failing]
    real_sync_dir = local_store._sync_dir
    synced: list[Path] = []

    def broken(path: Path) -> None:
        if Path(path).resolve() == parent:
            raise OSError(errno.EIO, "injected fsync failure")
        real_sync_dir(path)

    def recording(path: Path) -> None:
        real_sync_dir(path)
        if Path(path).resolve().is_relative_to(base):
            synced.append(Path(path).resolve())

    monkeypatch.setattr(local_store, "_sync_dir", broken)
    with pytest.raises(OSError, match="injected fsync failure") as caught:
        LocalBlobStore(root, max_bytes=MAX, min_free_bytes=0, storage_budget=local.budget())
    assert caught.value.errno == errno.EIO  # propagated as it came, no store
    assert not (root / "staging").exists()
    monkeypatch.setattr(local_store, "_sync_dir", recording)
    LocalBlobStore(root, max_bytes=MAX, min_free_bytes=0, storage_budget=local.budget())
    # The entry whose sync failed is made durable by the retry, not taken as an ancestor that already was.
    assert synced == chain
    assert stat.S_IMODE(root.lstat().st_mode) == 0o700


def test_concurrent_first_root_creation_syncs_every_entry_it_descends_through(
    tmp_path: Path, local: Local, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path.resolve()
    root = base / "a" / "b" / "blobs"
    real_sync_dir = local_store._sync_dir
    paused, resume = threading.Event(), threading.Event()
    synced: list[Path] = []
    failed: list[OSError] = []

    def racing(path: Path) -> None:
        if threading.current_thread() is first and Path(path).resolve() == base:
            paused.set()  # the first creator has made ``a`` in base and not synced it there yet
            assert resume.wait(5)
            raise OSError(errno.EIO, "injected fsync failure")  # and that sync fails
        real_sync_dir(path)
        if threading.current_thread() is threading.main_thread():
            synced.append(Path(path).resolve())

    def create() -> None:
        try:
            LocalBlobStore(root, max_bytes=MAX, min_free_bytes=0, storage_budget=local.budget())
        except OSError as error:
            failed.append(error)

    monkeypatch.setattr(local_store, "_sync_dir", racing)
    first = threading.Thread(target=create)
    first.start()
    try:
        assert paused.wait(5)
        assert (base / "a").is_dir()
        # The second creator descends through the unsynced ``a`` and builds on it.
        second = LocalBlobStore(root, max_bytes=MAX, min_free_bytes=0, storage_budget=local.budget())
    finally:
        resume.set()
        first.join(5)
    # Its success came only after it synced each entry itself, ``a`` in base included.
    chain = [base, base / "a", base / "a" / "b", root, root / "staging"]
    assert [path for path in synced if path.is_relative_to(base)] == chain
    assert [error.errno for error in failed] == [errno.EIO]  # the failed sync propagates, nothing hides it
    monkeypatch.undo()
    assert second.promote(second.stage(WS, [DATA])) == location_of(key_of(WS, DATA))


def test_file_exists_race_with_corrupt_final_is_refused(
    local: Local, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = local.make()
    staged = store.stage(WS, [DATA])
    final = local.root.resolve() / key_of(WS, DATA)
    real_link = os.link

    def racing_link(src: str | Path, dst: str | Path, **kwargs: Any) -> None:
        if Path(dst) == final:  # a same-size bit flip appears after the existence check
            fd = os.open(final, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
            os.write(fd, flipped(DATA))
            os.close(fd)
        real_link(src, dst, **kwargs)

    monkeypatch.setattr(os, "link", racing_link)
    registered: list[JsonObject] = []
    with pytest.raises(InternalError) as caught:
        registered.append(store.promote(staged))
    assert caught.value.details["reason"] == "blob_corrupt"
    assert registered == []
    assert final.read_bytes() == flipped(DATA)
    assert final.lstat().st_nlink == 1
    assert local.parts() == []


def test_file_exists_race_with_matching_final_keeps_the_winner(
    local: Local, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = local.make()
    loser, winner = store.stage(WS, [DATA]), store.stage(WS, [DATA])
    winner_inode = local.part(winner).lstat().st_ino
    real_link = os.link
    raced: list[JsonObject] = []

    def racing_link(src: str | Path, dst: str | Path, **kwargs: Any) -> None:
        if not raced and Path(src) == local.part(loser):
            monkeypatch.setattr(os, "link", real_link)
            raced.append(store.promote(winner))
        real_link(src, dst, **kwargs)

    monkeypatch.setattr(os, "link", racing_link)
    location = store.promote(loser)
    assert raced == [location]
    final = local.final(location)
    assert final.lstat().st_ino == winner_inode  # no overwrite: the first link stays
    assert final.read_bytes() == DATA
    assert local.parts() == []


@pytest.mark.parametrize("kind", ["symlink", "fifo", "directory"])
def test_non_regular_final_name_is_never_followed(local: Local, tmp_path: Path, kind: str) -> None:
    store = local.make()
    location = location_of(key_of(WS, DATA))
    final = local.root / key_of(WS, DATA)
    for folder in (final.parent.parent.parent, final.parent.parent, final.parent):
        folder.mkdir(mode=0o700)
    outside = tmp_path / "outside"
    outside.write_bytes(DATA)  # even the right bytes are not trusted through a symlink
    if kind == "symlink":
        final.symlink_to(outside)
    elif kind == "fifo":
        os.mkfifo(final, 0o600)
    else:
        final.mkdir(mode=0o700)
    with pytest.raises(InternalError) as caught:
        store.promote(store.stage(WS, [DATA]))
    assert caught.value.details["reason"] == "blob_corrupt"
    for call in (store.open, store.exists, store.stat, store.delete_unreferenced):
        with pytest.raises(InternalError):
            call(location)
    assert not store.verify(location, digest(DATA))
    assert list(store.iter_objects(WS)) == []
    kept = {"symlink": stat.S_ISLNK, "fifo": stat.S_ISFIFO, "directory": stat.S_ISDIR}[kind]
    assert kept(final.lstat().st_mode)  # not replaced, removed or repaired
    assert outside.read_bytes() == DATA
    assert local.parts() == []


def test_symlinked_storage_directory_is_refused(local: Local, tmp_path: Path) -> None:
    store = local.make()
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o700)
    (local.root / str(WS)).symlink_to(outside, target_is_directory=True)
    with pytest.raises(UnsafePathError):
        store.promote(store.stage(WS, [DATA]))
    with pytest.raises(UnsafePathError):
        list(store.iter_objects(WS))
    with pytest.raises(InternalError):
        store.open(location_of(key_of(WS, DATA)))
    assert list(outside.iterdir()) == []
    assert local.parts() == []


@pytest.mark.parametrize("name", ["victim", "victim.part"])
def test_forged_staging_id_never_reaches_outside_staging(local: Local, tmp_path: Path, name: str) -> None:
    store = local.make()
    victim = tmp_path / name
    victim.write_bytes(DATA)
    for staging_id in (str(victim), str(victim.with_suffix("")), f"../../{victim.stem}"):
        forged = StagingHandle(WS, digest(DATA), len(DATA), staging_id)
        with pytest.raises(UnsafePathError):
            store.promote(forged)
        with pytest.raises(UnsafePathError):
            store.discard(forged)
    assert victim.read_bytes() == DATA
    assert list(store.iter_objects(WS)) == []


def test_only_the_issuing_store_honours_a_handle(local: Local) -> None:
    store, issuer = local.make(), local.make()
    staged = issuer.stage(WS, [DATA])  # its staging file exists under the shared root
    forged = (replace(staged, digest=digest(flipped(DATA))), replace(staged, workspace_id=OTHER))
    for handle in (staged, *forged):
        with pytest.raises(NotFound) as caught:
            store.promote(handle)
        assert dict(caught.value.details) == {"kind": "staged_blob"}
        store.discard(handle)  # nothing this store issued: a no-op
    assert local.part(staged).read_bytes() == DATA
    for workspace in (WS, OTHER):
        assert list(store.iter_objects(workspace)) == []
    assert issuer.promote(staged) == location_of(key_of(WS, DATA))


def test_staging_changed_in_place_after_stage_is_never_published(local: Local) -> None:
    store = local.make()
    staged = store.stage(WS, [DATA])
    with local.part(staged).open("r+b") as stream:  # same inode, same size: only a rehash sees it
        stream.write(flipped(DATA))
    with pytest.raises(InternalError) as caught:
        store.promote(staged, expected_digest=digest(DATA))
    assert dict(caught.value.details) == {"reason": "staging_changed"}
    assert list(store.iter_objects(WS)) == []
    assert not store.exists(location_of(key_of(WS, DATA)))
    assert local.parts() == []
    with pytest.raises(NotFound):
        store.promote(staged)
    location = store.promote(store.stage(WS, [DATA]))  # the real bytes still publish under their digest
    assert location == location_of(key_of(WS, DATA))
    assert local.final(location).read_bytes() == DATA


def test_recovery_never_removes_a_live_peer_staging(local: Local) -> None:
    peer, cleaner = local.make(), local.make()
    issued = peer.stage(WS, [DATA])  # staged, promote still to come
    started, release = threading.Event(), threading.Event()
    result: dict[str, StagingHandle] = {}

    def slow() -> Iterator[bytes]:
        yield b"in flight"
        started.set()
        assert release.wait(5)
        yield b"-done"

    def in_flight() -> None:
        result["staged"] = peer.stage(WS, slow())

    thread = threading.Thread(target=in_flight)
    thread.start()
    try:
        assert started.wait(5)
        assert cleaner.recover_staging(stale_before=FUTURE) == 0
        assert len(local.parts()) == 2
    finally:
        release.set()
        thread.join(5)
    assert cleaner.recover_staging(stale_before=FUTURE) == 0
    assert peer.promote(issued) == location_of(key_of(WS, DATA))
    assert peer.promote(result["staged"]) == location_of(key_of(WS, b"in flight-done"))
    assert local.parts() == []


def test_forked_child_needs_and_gets_a_fresh_store(local: Local) -> None:
    store = local.make()
    staged = store.stage(WS, [DATA])

    def fresh_store() -> tuple[int, JsonObject]:
        fresh = local.make()  # its own directory and lock; the parent's directory stays locked by the parent
        return fresh.recover_staging(stale_before=FUTURE), fresh.promote(fresh.stage(WS, [b"child"]))

    assert in_fork(lambda: outcome_of(fresh_store)) == ("returned", (0, location_of(key_of(WS, b"child"))))
    assert local.parts() == [local.part(staged)]  # the child's recovery never reached the parent's staging
    assert store.promote(staged) == location_of(key_of(WS, DATA))
    assert store.recover_staging(stale_before=FUTURE) == 0  # the ended child's empty directory goes
    assert len(list(local.staging.iterdir())) == 1  # only the parent's own directory is left
    assert local.parts() == []


def test_recovery_leaves_entries_outside_the_instance_layout(local: Local) -> None:
    store = local.make()
    legacy = local.staging / "0192f5cb-6001-4a01-8000-0a1b2c3d4e60.part"  # flat, before instance directories
    unknown = local.staging / "0192f5cb-6001-4a01-8000-0a1b2c3d4e61"  # an instance name that is no directory
    old = datetime(2000, 1, 1, tzinfo=UTC).timestamp()
    for path in (legacy, unknown):
        path.write_bytes(DATA)
        os.utime(path, (old, old))
    assert store.recover_staging(stale_before=FUTURE) == 0
    assert legacy.read_bytes() == DATA  # kept for its owner to settle, whatever its age
    assert unknown.read_bytes() == DATA


def test_recovery_of_own_handles_never_races_a_promote(local: Local, monkeypatch: pytest.MonkeyPatch) -> None:
    store = local.make()
    staged, idle = store.stage(WS, [DATA]), store.stage(WS, [b"idle"])
    linking, release = threading.Event(), threading.Event()
    real_link = os.link

    def paused_link(src: str | Path, dst: str | Path, **kwargs: Any) -> None:
        linking.set()
        assert release.wait(5)
        real_link(src, dst, **kwargs)

    monkeypatch.setattr(os, "link", paused_link)
    with ThreadPoolExecutor(1) as pool:
        promoting = pool.submit(store.promote, staged)
        try:
            assert linking.wait(5)
            # The promote holds its claim: only the idle handle nobody promotes is recovered.
            assert store.recover_staging(stale_before=FUTURE) == 1
            assert local.parts() == [local.part(staged)]
        finally:
            release.set()
        assert promoting.result(5) == location_of(key_of(WS, DATA))
    assert local.parts() == []
    with pytest.raises(NotFound):
        store.promote(idle)
    assert list(store.iter_objects(WS)) == [location_of(key_of(WS, DATA))]


def test_instance_directory_lost_to_a_recovery_is_replaced(
    local: Local, monkeypatch: pytest.MonkeyPatch
) -> None:
    cleaner = local.make()
    real_uuid4, real_flock = local_store.uuid.uuid4, local_store.flock
    made: list[str] = []
    raced: list[int] = []

    def recording_uuid4() -> UUID:
        made.append(str(value := real_uuid4()))
        return value

    def racing_flock(fd: int, operation: int) -> None:
        if not raced:  # the new store's first lock: a recovery wins its empty directory first
            raced.append(fd)
            assert cleaner.recover_staging(stale_before=FUTURE) == 0
        real_flock(fd, operation)

    monkeypatch.setattr(local_store.uuid, "uuid4", recording_uuid4)
    monkeypatch.setattr(local_store, "flock", racing_flock)
    store = local.make()
    monkeypatch.undo()
    lost, own = made
    assert not (local.staging / lost).exists()
    assert (local.staging / own).is_dir()
    staged = store.stage(WS, [DATA])
    assert local.part(staged).parent == (local.staging / own).resolve()
    assert cleaner.recover_staging(stale_before=FUTURE) == 0  # the replacement is held: never swept
    assert store.promote(staged) == location_of(key_of(WS, DATA))


def test_shared_or_foreign_root_is_refused(tmp_path: Path, local: Local) -> None:
    shared = tmp_path / "shared"
    shared.mkdir(mode=0o755)
    shared.chmod(0o755)
    with pytest.raises(ValueError, match="private"):
        LocalBlobStore(shared, max_bytes=MAX, min_free_bytes=0, storage_budget=local.budget())


def _crash_mid_stage(env: Local, size: int) -> None:
    def chunks() -> Iterator[bytes]:
        yield b"p" * size
        os._exit(31)

    env.make().stage(WS, chunks())


def test_crash_temp_and_restart_stay_inside_the_ledger(tmp_path: Path) -> None:
    env = local_env(tmp_path)
    env.disk.capacity = env.ceiling + MAX // 2  # one stage at a time
    backend = local_backend(env)
    referenced = backend.store.promote(backend.store.stage(WS, [DATA]))
    kept = backend.raw(referenced)

    process = multiprocessing.get_context("fork").Process(target=_crash_mid_stage, args=(env, MAX - 1))
    process.start()
    process.join(timeout=10)
    assert process.exitcode == 31
    (part,) = env.parts()
    assert part.stat().st_size == MAX - 1
    assert list(backend.store.iter_objects(WS)) == [referenced]  # a partial stage is never a final
    written = datetime.fromtimestamp(part.stat().st_mtime, tz=UTC)
    young, expired = written - timedelta(hours=24), written + timedelta(seconds=1)

    def refused(store: LocalBlobStore) -> None:
        with pytest.raises(BackendUnavailable) as caught:
            store.stage(WS, [b"next"])
        assert caught.value.details["reason"] == "disk_low"
        assert backend.raw(referenced) == kept

    # Restart while the crashed owner is unknown: its whole reserve still counts.
    restarted = env.make(alive=None)
    refused(restarted)
    assert restarted.recover_staging(stale_before=young) == 0
    refused(restarted)
    # Proven dead: the reserve is released, but its temp file is still counted by the filesystem.
    recovered = env.make(alive=False)
    assert recovered.recover_staging(stale_before=young) == 0
    assert backend.reserved() == 0
    assert part.exists()
    refused(recovered)
    # The staging TTL has passed: only then is the temp removed and admission possible again.
    assert recovered.recover_staging(stale_before=expired) == 1
    assert not part.exists()
    assert not part.parent.exists()  # the crashed store's directory goes once empty
    location = recovered.promote(recovered.stage(WS, [b"next"]))
    assert list(recovered.iter_objects(WS)) == sorted(
        [referenced, location], key=lambda x: str(x["storage_key"])
    )
    assert backend.raw(referenced) == kept


def test_staging_ttl_never_releases_an_unknown_owner_reserve(tmp_path: Path) -> None:
    env = local_env(tmp_path)
    env.disk.capacity = env.ceiling + MAX // 2  # one stage at a time
    backend = local_backend(env)
    process = multiprocessing.get_context("fork").Process(target=_crash_mid_stage, args=(env, 16))
    process.start()
    process.join(timeout=10)
    assert process.exitcode == 31
    (part,) = env.parts()
    expired = datetime.fromtimestamp(part.stat().st_mtime, tz=UTC) + timedelta(seconds=1)
    # The crashed store's lock is free, so its expired temp goes; neither that nor the TTL tells the ledger
    # that the owner ended: the reserve stays.
    unknown = env.make(alive=None)
    assert unknown.recover_staging(stale_before=expired) == 1
    assert not part.exists()
    assert backend.reserved() == env.ceiling
    with pytest.raises(BackendUnavailable) as caught:
        unknown.stage(WS, [b"next"])
    assert caught.value.details["reason"] == "disk_low"
    # Proven dead later: its reserve is released although the file is already gone.
    dead = env.make(alive=False)
    assert dead.recover_staging(stale_before=expired) == 0
    assert backend.reserved() == 0
    assert dead.promote(dead.stage(WS, [b"next"])) == location_of(key_of(WS, b"next"))


class Listing:
    """A finished ``os.scandir`` listing, usable as iterator or context manager like the real one."""

    def __init__(self, entries: list[os.DirEntry[str]]) -> None:
        self.entries = entries

    def __iter__(self) -> Iterator[os.DirEntry[str]]:
        return iter(self.entries)

    def __enter__(self) -> Iterator[os.DirEntry[str]]:
        return iter(self.entries)

    def __exit__(self, *_: object) -> None:
        return None


def _crash_after_stages(env: Local, count: int) -> None:
    store = env.make()
    for n in range(count):
        store.stage(WS, [bytes([n]) * 16])  # issued handles that die with the process
    os._exit(32)


def test_recovery_continues_past_a_staging_file_that_vanishes(
    local: Local, monkeypatch: pytest.MonkeyPatch
) -> None:
    process = multiprocessing.get_context("fork").Process(target=_crash_after_stages, args=(local, 3))
    process.start()
    process.join(timeout=10)
    assert process.exitcode == 32
    parts = local.parts()
    assert len(parts) == 3
    (dead,) = {part.parent for part in parts}
    store = local.make()
    real_scandir = os.scandir
    vanished: list[str] = []

    def scandir(path: Any) -> Any:
        if sys._getframe(1).f_code is not LocalBlobStore._recover_instance.__code__ or vanished:
            return real_scandir(path)  # the budget's own walks see the real directory
        with real_scandir(path) as listing:
            entries = sorted(listing, key=lambda entry: entry.name)
        # Someone else removes one file after the listing, before its stat.
        (dead / entries[0].name).unlink()
        vanished.append(entries[0].name)
        return Listing(entries)

    monkeypatch.setattr(os, "scandir", scandir)
    assert store.recover_staging(stale_before=FUTURE) == 2
    assert vanished
    assert local.parts() == []
    assert not dead.exists()
    assert list(store.iter_objects(WS)) == []
