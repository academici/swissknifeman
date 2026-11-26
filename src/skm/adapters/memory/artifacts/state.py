"""Tables of ``skm_artifacts`` in the memory backend state (artifacts §11).

The tables live in ``MemoryBackendState.modules["artifacts"]``; a unit of work works on a deep copy, so a
rollback drops them. The rows are the immutable domain values themselves. The byte store is not a table: it is
the one injected ``BlobStoreRef`` every copy shares.
"""

from dataclasses import dataclass, field
from typing import Final, Self

from skm.adapters.memory.core.state import MemoryBackendState
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError
from skm.kernel.ids import FileVersionId
from skm.modules.artifacts.domain.access_grant import AccessGrant, AccessGrantId
from skm.modules.artifacts.domain.blob import Blob, BlobId, BlobLocation
from skm.modules.artifacts.domain.file import File, FileId
from skm.modules.artifacts.domain.file_version import FileVersion
from skm.modules.artifacts.domain.staged_blob import StagedBlob, StagedBlobId
from skm.modules.artifacts.ports import BlobStore

__all__ = ["STATE_KEY", "BlobStoreRef", "MemoryArtifactsState", "artifacts_state"]

STATE_KEY: Final = "artifacts"


class BlobStoreRef:
    """The host-injected byte store inside the state; a copy of the state shares it instead of duplicating it.

    The memory backend binds it once (``artifacts_state(state).store.bind(store)``); until then reading bytes
    through a unit of work is ``CAPABILITY_UNAVAILABLE`` rather than a guess.
    """

    __slots__ = ("store",)

    def __init__(self) -> None:
        self.store: BlobStore | None = None

    def bind(self, store: BlobStore) -> None:
        self.store = store

    def __deepcopy__(self, memo: dict[int, object]) -> Self:
        return self

    def __copy__(self) -> Self:
        return self


@dataclass
class MemoryArtifactsState:
    staged: dict[StagedBlobId, StagedBlob] = field(default_factory=dict[StagedBlobId, StagedBlob])
    blobs: dict[BlobId, Blob] = field(default_factory=dict[BlobId, Blob])
    locations: dict[BlobId, tuple[BlobLocation, ...]] = field(
        default_factory=dict[BlobId, tuple[BlobLocation, ...]]
    )
    files: dict[FileId, File] = field(default_factory=dict[FileId, File])
    versions: dict[FileVersionId, FileVersion] = field(default_factory=dict[FileVersionId, FileVersion])
    grants: dict[AccessGrantId, AccessGrant] = field(default_factory=dict[AccessGrantId, AccessGrant])
    store: BlobStoreRef = field(default_factory=BlobStoreRef)


def artifacts_state(state: MemoryBackendState) -> MemoryArtifactsState:
    found = state.modules.get(STATE_KEY)
    if found is None:
        found = MemoryArtifactsState()
        state.modules[STATE_KEY] = found
    if not isinstance(found, MemoryArtifactsState):
        raise InternalError(
            ErrorCode.INTERNAL_ERROR, "artifacts memory state is malformed", details={"module": STATE_KEY}
        )
    return found
