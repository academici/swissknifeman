"""Declarative contract; behavior belongs to the owning implementation leaf."""

from collections.abc import Iterable, Iterator, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import BinaryIO, Protocol

from skm.kernel.gateways import control_plane_gateway, host_gateway
from skm.kernel.ids import FileVersionId, PrincipalId, ProjectId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.kernel.pagination import Page
from skm.kernel.ports_uow import repository_port

from .domain.access_grant import AccessGrant, GrantReason
from .domain.blob import Blob, BlobId, BlobLocation, ContentDigest, LocationState
from .domain.file import File, FileId, FileOrigin, FileState
from .domain.file_version import FileVersion
from .domain.materialization import MaterialEntry
from .domain.staged_blob import StagedBlob, StagedBlobId

__all__ = [
    "AccessGrantRepository",
    "BlobContentReader",
    "BlobCoordination",
    "BlobDigestLock",
    "BlobLocationRef",
    "BlobObjectStat",
    "BlobRepository",
    "BlobStore",
    "FileRepository",
    "FileVersionRepository",
    "MaterialWriter",
    "StagedBlobRepository",
    "StagingHandle",
]

# {backend_id, storage_key, storage_version}: the address part of a blob_locations row (artifacts §6).
type BlobLocationRef = JsonObject


@dataclass(frozen=True, slots=True)
class StagingHandle:
    """Fsynced bytes in BlobStore staging before promote; not the ``staged_blobs`` row (``StagedBlob``).

    ``staging_id`` is opaque and private to the store that issued it (never a path); it stays in the
    control plane and is never sent to clients.
    """

    workspace_id: WorkspaceId
    digest: str  # "sha256:" + 64 hex of the received bytes
    size_bytes: int
    staging_id: str


@dataclass(frozen=True, slots=True)
class BlobObjectStat:
    size_bytes: int
    created_at: datetime  # UTC, never earlier than the object's creation: orphan age is never overstated


@control_plane_gateway
class BlobStore(Protocol):  # control-plane gateway (artifacts §6)
    def delete_unreferenced(self, location: BlobLocationRef) -> None:
        """Only staged cleanup/manual orphan prune under the digest guard (artifacts §6.1, §18)."""
        ...

    def recover_staging(self, *, stale_before: datetime) -> int:
        """Startup and ``staging_gc``: staging remnants older than the cutoff; never objects (adapters §4)."""
        ...

    def stage(self, workspace_id: WorkspaceId, chunks: Iterable[bytes]) -> StagingHandle: ...
    def promote(self, staged: StagingHandle, *, expected_digest: str | None = None) -> BlobLocationRef: ...
    def open(self, location: BlobLocationRef) -> BinaryIO: ...
    def exists(self, location: BlobLocationRef) -> bool: ...
    def verify(self, location: BlobLocationRef, digest: str) -> bool: ...
    def stat(self, location: BlobLocationRef) -> BlobObjectStat: ...  # find_orphan_blobs (artifacts §8)
    def discard(self, staged: StagingHandle) -> None: ...
    def iter_objects(self, workspace_id: WorkspaceId) -> Iterator[BlobLocationRef]: ...


@repository_port
class BlobContentReader(Protocol):
    """Read-only access to stored bytes, bound to the unit of work by the host composition.

    A facade function that must read bytes (``read_text_content``) reaches the store through
    ``uow.repo(BlobContentReader)``: the host that builds the unit of work injects the store, the facade has
    no parameter, global or process singleton for it. It opens an address only; the caller has already
    authorised the read, and the address is never an access token.
    """

    def open(self, location: BlobLocationRef) -> BinaryIO: ...


@repository_port
class StagedBlobRepository(Protocol):
    def add(self, staged: StagedBlob) -> None: ...
    def get_for_update(
        self, staged_blob_id: StagedBlobId
    ) -> StagedBlob: ...  # SELECT … FOR UPDATE; NotFound(kind="staged_blob")
    def save(self, staged: StagedBlob) -> None: ...
    def expired_digests(
        self, now: datetime, *, limit: int
    ) -> tuple[tuple[WorkspaceId, ContentDigest, str], ...]: ...
    def expired(self, now: datetime, *, limit: int) -> tuple[StagedBlob, ...]: ...  # FOR UPDATE SKIP LOCKED
    def purge_consumed(self, before: datetime, *, limit: int) -> int: ...
    def delete(self, staged_blob_id: StagedBlobId) -> None: ...
    def key_referenced(
        self, backend_id: str, storage_key: str
    ) -> bool: ...  # Any blob location or live staged reference to this key.


@repository_port
class BlobRepository(Protocol):
    def find(self, workspace_id: WorkspaceId, digest: ContentDigest, size_bytes: int) -> Blob | None: ...
    def get(self, blob_id: BlobId) -> Blob: ...
    def add(
        self, blob: Blob, location: BlobLocation
    ) -> None: ...  # ALREADY_EXISTS при гонке → вызывающий перечитывает find
    def locations(self, blob_id: BlobId) -> tuple[BlobLocation, ...]: ...
    def mark_location(self, blob_id: BlobId, backend_id: str, state: LocationState, at: datetime) -> None: ...
    def all_keys(
        self, workspace_id: WorkspaceId, backend_id: str
    ) -> frozenset[str]: ...  # для find_orphan_blobs
    def entries_in_backend(
        self, workspace_id: WorkspaceId, backend_id: str
    ) -> tuple[tuple[BlobId, str], ...]: ...


@repository_port
class FileRepository(Protocol):
    def get(self, file_id: FileId) -> File: ...
    def add(self, file: File) -> None: ...
    def save(self, file: File, *, expected_version: int) -> None: ...
    def list(
        self,
        workspace_id: WorkspaceId,
        *,
        project_id: ProjectId | None,
        state: FileState | None,
        origin: FileOrigin | None,
        after: str | None,
        limit: int,
    ) -> Page[File]: ...


@repository_port
class FileVersionRepository(Protocol):
    def get(self, version_id: FileVersionId) -> FileVersion: ...
    def last_no(self, file_id: FileId) -> int: ...  # 0 если версий нет; FOR UPDATE строки files
    def add(self, version: FileVersion) -> None: ...
    def list(self, file_id: FileId, *, after: str | None, limit: int) -> Page[FileVersion]: ...
    def many(self, ids: Sequence[FileVersionId]) -> tuple[FileVersion, ...]: ...


@repository_port
class AccessGrantRepository(Protocol):
    def add_many(self, grants: Sequence[AccessGrant]) -> None: ...
    def active_for(
        self,
        principal_id: PrincipalId,
        version_id: FileVersionId,
        now: datetime,
        *,
        reason: GrantReason | None = None,
        ref: str | None = None,
    ) -> AccessGrant | None:
        """The latest-expiring active grant of the principal on exactly this version.

        Every given ``reason`` and ``ref`` must match before the pick, so an exact claim is found even when
        another claim of the same principal and version expires later.
        """
        ...

    def held_claims(
        self,
        principal_id: PrincipalId,
        version_ids: Sequence[FileVersionId],
        now: datetime,
        *,
        reason: GrantReason,
        ref: str,
    ) -> frozenset[FileVersionId]:
        """The versions among ``version_ids`` the principal holds an active grant of exactly this claim on."""
        ...

    def revoke_by_ref(self, reason: GrantReason, ref: str, at: datetime) -> int: ...
    def extend_by_ref(self, reason: GrantReason, ref: str, expires_at: datetime, now: datetime) -> int: ...


@host_gateway
class MaterialWriter(Protocol):
    def write(
        self, target_dir: Path | str, entry: MaterialEntry, stream: BinaryIO
    ) -> None: ...  # §4.4: safe-root, digest-check, create-only, 0444
    def seal(self, target_dir: Path | str) -> None: ...  # каталоги 0555


@control_plane_gateway
class BlobCoordination(Protocol):
    def hold(
        self, workspace_id: WorkspaceId, digest: ContentDigest, backend_id: str
    ) -> AbstractContextManager[None]: ...


class BlobDigestLock(Protocol):
    """Transaction-scoped digest lock acquired before metadata row locks (artifacts §6.1)."""

    def lock_digest(self, workspace_id: WorkspaceId, digest: ContentDigest, backend_id: str) -> None: ...
    def lock_staged(self, workspace_id: WorkspaceId, staged_blob_id: StagedBlobId) -> None: ...
