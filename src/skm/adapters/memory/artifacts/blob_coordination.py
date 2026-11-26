"""In-memory ``BlobCoordination`` and transaction digest lock (artifacts §6.1, adapters §2)."""

import hashlib
import threading
from collections.abc import Generator
from contextlib import contextmanager

from skm.adapters.memory.artifacts.state import artifacts_state
from skm.adapters.memory.blob_store import MemoryBlobStore
from skm.adapters.memory.core.state import MemoryBackendState
from skm.kernel.clock import Clock
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import WorkspaceId
from skm.modules.artifacts.domain.blob import ContentDigest
from skm.modules.artifacts.domain.staged_blob import StagedBlobId
from skm.modules.artifacts.ports import BlobCoordination, BlobStore

__all__ = [
    "MemoryBlobCoordination",
    "MemoryBlobDigestLock",
    "bind_memory_artifacts",
    "digest_lock_key",
]


def digest_lock_key(workspace_id: WorkspaceId, digest: ContentDigest, backend_id: str) -> int:
    """Signed 64-bit advisory lock key for ``(backend_id, workspace_id, digest)`` (artifacts §6.1)."""
    payload = (
        b"skm-blob-v1\0"
        + backend_id.encode("utf-8")
        + b"\0"
        + str(workspace_id).encode("utf-8")
        + b"\0"
        + digest.value.encode("utf-8")
    )
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big", signed=True)


class MemoryBlobCoordination:
    """Per-key re-entrant mutex coordinating promote/cleanup in the in-memory slice."""

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._locks: dict[int, threading.RLock] = {}

    @contextmanager
    def hold(self, workspace_id: WorkspaceId, digest: ContentDigest, backend_id: str) -> Generator[None]:
        key = digest_lock_key(workspace_id, digest, backend_id)
        with self._guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = threading.RLock()
                self._locks[key] = lock
        with lock:
            yield


class MemoryBlobDigestLock:
    """Transaction-scoped digest lock over the memory backend (already serialised by ``backend.lock``)."""

    def __init__(self, state: MemoryBackendState) -> None:
        self._state = state

    def lock_digest(self, workspace_id: WorkspaceId, digest: ContentDigest, backend_id: str) -> None:
        digest_lock_key(workspace_id, digest, backend_id)

    def lock_staged(self, workspace_id: WorkspaceId, staged_blob_id: StagedBlobId) -> None:
        staged = artifacts_state(self._state).staged.get(staged_blob_id)
        if staged is not None and staged.workspace_id == workspace_id:
            self.lock_digest(workspace_id, staged.digest, staged.backend_id)


def bind_memory_artifacts(
    committed: MemoryBackendState, supplied: GatewayTable | None, clock: Clock
) -> dict[type[object], object]:
    store: BlobStore = (
        supplied.get(BlobStore)
        if supplied is not None and supplied.has(BlobStore)
        else MemoryBlobStore(clock, max_bytes=68_719_476_736, min_free_bytes=0)
    )
    artifacts_state(committed).store.bind(store)
    return {BlobStore: store, BlobCoordination: MemoryBlobCoordination()}
