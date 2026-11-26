"""Memory adapters of the artifacts repository ports (artifacts §3, §6, §11).

``REPOSITORIES`` maps each port to its factory over the backend state. The byte store itself is a gateway
(``adapters/memory/blob_store.py``); ``BlobContentReader`` is the read-only view of it that a unit of work
hands to the facade, over the store the host bound with ``artifacts_state(state).store.bind(store)``.
"""

from collections.abc import Callable, Mapping
from types import MappingProxyType

from skm.adapters.memory.artifacts.blob_coordination import MemoryBlobDigestLock
from skm.adapters.memory.artifacts.repositories import (
    MemoryAccessGrantRepository,
    MemoryBlobContentReader,
    MemoryBlobRepository,
    MemoryFileRepository,
    MemoryFileVersionRepository,
    MemoryStagedBlobRepository,
)
from skm.adapters.memory.core.state import MemoryBackendState
from skm.modules.artifacts.ports import (
    AccessGrantRepository,
    BlobContentReader,
    BlobDigestLock,
    BlobRepository,
    FileRepository,
    FileVersionRepository,
    StagedBlobRepository,
)

__all__ = ["REPOSITORIES"]

REPOSITORIES: Mapping[type, Callable[[MemoryBackendState], object]] = MappingProxyType(
    {
        StagedBlobRepository: MemoryStagedBlobRepository,
        BlobRepository: MemoryBlobRepository,
        FileRepository: MemoryFileRepository,
        FileVersionRepository: MemoryFileVersionRepository,
        AccessGrantRepository: MemoryAccessGrantRepository,
        BlobContentReader: MemoryBlobContentReader,
        BlobDigestLock: MemoryBlobDigestLock,
    }
)
