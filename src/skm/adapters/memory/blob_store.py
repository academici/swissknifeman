"""In-memory ``BlobStore`` for tests (artifacts §3): the local store's contract without a filesystem.

Same storage keys, digest rules and admission as ``LocalBlobStore`` (adapters §4): every in-flight ``stage``
reserves the whole upload ceiling against ``capacity_bytes``; an existing object is accepted only when its
stored bytes hash to the staged digest and size; nothing replaces an object, only ``delete_unreferenced``
removes one. Like the local store it honours only a handle it issued, exactly as issued, and publishes the
issued claim: a changed workspace, digest or size is ``ValueError`` and leaves the staged bytes alone. Staged
bytes are immutable and live only in this instance. There is no ledger and no crash residue here:
``recover_staging`` only drops issued, unclaimed staged bytes older than its cutoff, timed by the injected
clock, under the same lock as promote/discard; an in-flight stage holds none yet. As with the local store a
forked child's copy is not the store: before its copied lock or staging is used, inherited handles are
``NotFound`` (discard is a no-op) and stage and recovery are ``staging_changed``. Unlike the local store,
whose finals are on a filesystem the child shares, the objects here are the parent's memory: the child's copy
is a snapshot no later promote or delete reaches, behind a lock a parent thread may have held at the fork. So
the object methods are ``staging_changed`` in the child too, checked before that lock, rather than stale.
"""

import hashlib
import io
import os
import re
import threading
import uuid
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import BinaryIO, ClassVar, cast

from skm.kernel.clock import Clock
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable, InternalError, NotFound, ValidationFailed
from skm.kernel.ids import WorkspaceId
from skm.modules.artifacts.domain.blob import ContentDigest
from skm.modules.artifacts.ports import BlobLocationRef, BlobObjectStat, StagingHandle

__all__ = ["MemoryBlobStore"]

_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_ID = re.compile(_UUID)  # workspace ids and staging ids
_KEY = re.compile(rf"{_UUID}/objects/(?P<shard>[0-9a-f]{{2}})/(?P<hex>[0-9a-f]{{64}})")


@dataclass(frozen=True, slots=True)
class _Object:
    """Stored bytes; ``created_at`` is the clock time of the first promote."""

    data: bytes
    created_at: datetime


@dataclass(frozen=True, slots=True)
class _Staged:
    """Staged bytes, the clock time of the stage and the handle issued for them."""

    handle: StagingHandle
    data: bytes
    created_at: datetime


def _workspace_name(workspace_id: WorkspaceId) -> str:
    name = str(workspace_id)
    if not _ID.fullmatch(name):
        raise ValueError(f"{name!r} is not a workspace id")
    return name


def _sha256(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


class MemoryBlobStore:
    BACKEND_ID: ClassVar[str] = "local-primary"

    def __init__(
        self, clock: Clock, *, max_bytes: int, capacity_bytes: int | None = None, min_free_bytes: int = 0
    ) -> None:
        self._clock = clock
        self._max_bytes, self._capacity, self._min_free_bytes = max_bytes, capacity_bytes, min_free_bytes
        self._pid = os.getpid()
        self._lock = threading.Lock()
        self._reserved = 0
        self._staging: dict[str, _Staged] = {}
        self._objects: dict[str, _Object] = {}

    def _reserve(self) -> None:
        with self._lock:
            if self._capacity is not None:
                used = sum(len(o.data) for o in (*self._staging.values(), *self._objects.values()))
                if self._capacity - used - self._reserved < self._max_bytes + self._min_free_bytes:
                    raise BackendUnavailable(
                        ErrorCode.BACKEND_UNAVAILABLE,
                        "blob storage budget exhausted",
                        details={"reason": "disk_low"},
                    )
            self._reserved += self._max_bytes

    def _require_creator(self) -> None:
        """Checked before the lock, staging or objects are used: a forked copy is not the store."""
        if os.getpid() != self._pid:
            raise InternalError(
                ErrorCode.INTERNAL_ERROR,
                "blob store belongs to the process that created it; create a fresh one",
                details={"reason": "staging_changed"},
            )

    def stage(self, workspace_id: WorkspaceId, chunks: Iterable[bytes]) -> StagingHandle:
        _workspace_name(workspace_id)
        self._require_creator()
        self._reserve()
        try:
            buffer = bytearray()
            for chunk in chunks:
                data = chunk if type(chunk) is bytes else memoryview(chunk).tobytes()
                if len(data) > self._max_bytes - len(buffer):
                    raise ValidationFailed(
                        ErrorCode.BLOB_TOO_LARGE,
                        "blob exceeds artifacts.upload.max_bytes",
                        details={"limit": self._max_bytes, "received_at_least": len(buffer) + len(data)},
                    )
                buffer += data
            data = bytes(buffer)
            handle = StagingHandle(workspace_id, _sha256(data), len(data), str(uuid.uuid4()))
            with self._lock:
                self._staging[handle.staging_id] = _Staged(handle, data, self._clock.now())
        finally:
            with self._lock:
                self._reserved -= self._max_bytes
        return handle

    def discard(self, staged: StagingHandle) -> None:
        if self._inherited(staged):
            return  # nothing of the parent's to drop
        with self._lock:
            self._take(staged)

    def _inherited(self, staged: StagingHandle) -> bool:
        """``True`` in a forked copy, which holds no handle; checked after the id format, before the lock."""
        self._staging_id(staged)
        return os.getpid() != self._pid

    @staticmethod
    def _staging_id(staged: StagingHandle) -> str:
        staging_id = staged.staging_id
        if not (isinstance(cast(object, staging_id), str) and _ID.fullmatch(staging_id)):
            raise ValueError(f"{staging_id!r} is not a staging id of this store")
        return staging_id

    def _take(self, staged: StagingHandle) -> _Staged | None:
        """Under the lock: pop the staging issued as exactly ``staged``; ``None`` if consumed or never issued.

        A changed workspace, digest or size would publish the staged bytes under a claim nobody verified:
        it is refused and the issued staging stays for its real handle.
        """
        staging_id = self._staging_id(staged)
        found = self._staging.get(staging_id)
        if found is not None and found.handle != staged:
            raise ValueError("staging handle was not issued by this store")
        return self._staging.pop(staging_id, None)

    def promote(self, staged: StagingHandle, *, expected_digest: str | None = None) -> BlobLocationRef:
        if self._inherited(staged):
            raise NotFound(ErrorCode.NOT_FOUND, "staged blob not found", details={"kind": "staged_blob"})
        with self._lock:
            taken = self._take(staged)  # consumed whatever the outcome
            if taken is None:
                raise NotFound(ErrorCode.NOT_FOUND, "staged blob not found", details={"kind": "staged_blob"})
            data, issued = taken.data, taken.handle  # the issued claim, never the caller's copy
            hex_digest = ContentDigest(issued.digest).value.removeprefix("sha256:")
            key = f"{_workspace_name(issued.workspace_id)}/objects/{hex_digest[:2]}/{hex_digest}"
            if expected_digest is not None and expected_digest != issued.digest:
                raise ValidationFailed(
                    ErrorCode.BLOB_DIGEST_MISMATCH,
                    "received bytes do not match the expected digest",
                    details={"expected": expected_digest, "actual": issued.digest},
                )
            existing = self._objects.get(key)
            if existing is None:
                self._objects[key] = _Object(data, self._clock.now())
            elif len(existing.data) != issued.size_bytes or _sha256(existing.data) != issued.digest:
                raise self._corrupt(key)
        return self._location(key)

    def _corrupt(self, key: str) -> InternalError:
        return InternalError(
            ErrorCode.INTERNAL_ERROR,
            "stored blob object does not match its digest",
            details={"reason": "blob_corrupt", "backend_id": self.BACKEND_ID, "storage_key": key},
        )

    def _location(self, key: str) -> BlobLocationRef:
        return {"backend_id": self.BACKEND_ID, "storage_key": key, "storage_version": None}

    def _key(self, location: BlobLocationRef) -> str:
        if location.get("backend_id") != self.BACKEND_ID:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "blob location belongs to another backend",
                details={"field": "backend_id"},
            )
        key = location.get("storage_key")
        match = _KEY.fullmatch(key) if isinstance(key, str) else None
        if match is None or match["shard"] != match["hex"][:2]:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "blob storage key is not a workspace object key",
                details={"field": "storage_key", "reason": "unsafe"},
            )
        return match.string

    def _object(self, location: BlobLocationRef) -> _Object:
        key = self._key(location)
        self._require_creator()
        with self._lock:
            found = self._objects.get(key)
        if found is None:
            raise NotFound(ErrorCode.NOT_FOUND, "blob object not found", details={"kind": "blob_location"})
        return found

    def open(self, location: BlobLocationRef) -> BinaryIO:
        return io.BytesIO(self._object(location).data)

    def exists(self, location: BlobLocationRef) -> bool:
        key = self._key(location)
        self._require_creator()
        with self._lock:
            return key in self._objects

    def verify(self, location: BlobLocationRef, digest: str) -> bool:
        return _sha256(self._object(location).data) == digest

    def stat(self, location: BlobLocationRef) -> BlobObjectStat:
        found = self._object(location)
        return BlobObjectStat(len(found.data), found.created_at.astimezone(UTC))

    def iter_objects(self, workspace_id: WorkspaceId) -> Iterator[BlobLocationRef]:
        prefix = f"{_workspace_name(workspace_id)}/objects/"
        self._require_creator()
        with self._lock:
            keys = sorted(key for key in self._objects if key.startswith(prefix))
        for key in keys:
            yield self._location(key)

    def delete_unreferenced(self, location: BlobLocationRef) -> None:
        """Only janitor/prune under the digest guard after the reference recheck (artifacts §6.1, §11.1)."""
        key = self._key(location)
        self._require_creator()
        with self._lock:
            self._objects.pop(key, None)

    def recover_staging(self, *, stale_before: datetime) -> int:
        """Drop staged bytes staged before the cutoff; objects are never touched."""
        self._require_creator()
        with self._lock:
            stale = [key for key, staged in self._staging.items() if staged.created_at < stale_before]
            for key in stale:
                del self._staging[key]
        return len(stale)
