"""Memory implementations of the artifacts repository ports (artifacts §6, §11).

Rows are the immutable domain values themselves. The checks PostgreSQL gets from constraints are made here
too: unique blob per ``(workspace, digest, size)``, unique location per ``(backend, storage_key)``, unique
``(file, version_no)``, immutable file versions (the port offers no update or delete), at most one active
grant per ``(principal, version, reason, ref)`` and optimistic ``row_version`` updates of files. Composite
FKs and triggers are not imitated (adapters §2.2): their contract cases run on PostgreSQL only.

``FileRepository.list`` and ``FileVersionRepository.list`` return a kernel ``Page``. Cursors are opaque
base64 JSON arrays of text: ``[created_at, id]`` for files (newest first) and ``[version_no]`` for versions
(highest first). A files cursor carries an offset-aware timestamp: a naive one is an invalid cursor.
"""

import base64
import binascii
import json
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime
from typing import BinaryIO, cast

from skm.adapters.memory.artifacts.state import MemoryArtifactsState, artifacts_state
from skm.adapters.memory.core.state import MemoryBackendState
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, Conflict, InternalError, NotFound, ValidationFailed
from skm.kernel.ids import FileVersionId, PrincipalId, ProjectId, WorkspaceId
from skm.kernel.pagination import Cursor, Page, validate_cursor, validate_page_limit
from skm.modules.artifacts.domain.access_grant import AccessGrant, GrantReason, grant_is_active
from skm.modules.artifacts.domain.blob import Blob, BlobId, BlobLocation, ContentDigest, LocationState
from skm.modules.artifacts.domain.file import File, FileId, FileOrigin, FileState
from skm.modules.artifacts.domain.file_version import FileVersion
from skm.modules.artifacts.domain.staged_blob import StagedBlob, StagedBlobId
from skm.modules.artifacts.ports import BlobLocationRef

__all__ = [
    "MemoryAccessGrantRepository",
    "MemoryBlobContentReader",
    "MemoryBlobRepository",
    "MemoryFileRepository",
    "MemoryFileVersionRepository",
    "MemoryStagedBlobRepository",
]


def _encode_cursor(parts: Sequence[str]) -> Cursor:
    raw = json.dumps(list(parts), separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return validate_cursor(base64.urlsafe_b64encode(raw).decode("ascii"))


def _decode_cursor(cursor: str | None, size: int) -> tuple[str, ...] | None:
    if cursor is None:
        return None
    try:
        parts = json.loads(base64.urlsafe_b64decode(validate_cursor(cursor).encode("ascii")))
        items = cast("list[object]", parts) if isinstance(parts, list) else []
        if len(items) != size or not all(isinstance(item, str) for item in items):
            raise ValueError("cursor shape")
        return tuple(cast("list[str]", items))
    except (ValueError, TypeError, binascii.Error, UnicodeError):
        raise _bad_cursor() from None


def _bad_cursor() -> ValidationFailed:
    return ValidationFailed(ErrorCode.SCHEMA_INVALID, "invalid page cursor", details={"field": "after"})


def _not_found(kind: str, ref: object) -> NotFound:
    return NotFound(ErrorCode.NOT_FOUND, f"{kind} not found", details={"kind": kind, "ref": str(ref)})


def _exists(kind: str, **details: str) -> Conflict:
    return Conflict(ErrorCode.ALREADY_EXISTS, f"{kind} already exists", details={"kind": kind, **details})


class _Tables:
    def __init__(self, state: MemoryBackendState) -> None:
        self._state = state
        self._tables: MemoryArtifactsState = artifacts_state(state)

    def _writable(self) -> MemoryArtifactsState:
        self._state.core.require_writable()
        return self._tables


class MemoryBlobContentReader(_Tables):
    """``BlobContentReader`` over the store the host bound into the backend state (``BlobStoreRef``)."""

    def open(self, location: BlobLocationRef) -> BinaryIO:
        store = self._tables.store.store
        if store is None:
            raise CapabilityUnavailable(
                ErrorCode.CAPABILITY_UNAVAILABLE,
                "no blob store is bound to this backend",
                details={"capability": "blob_content"},
            )
        return store.open(location)


class MemoryStagedBlobRepository(_Tables):
    def add(self, staged: StagedBlob) -> None:
        tables = self._writable()
        if staged.id in tables.staged:
            raise _exists("staged_blob", ref=str(staged.id))
        tables.staged[staged.id] = staged

    def get_for_update(self, staged_blob_id: StagedBlobId) -> StagedBlob:
        found = self._tables.staged.get(staged_blob_id)
        if found is None:
            raise _not_found("staged_blob", staged_blob_id)
        return found

    def save(self, staged: StagedBlob) -> None:
        tables = self._writable()
        stored = tables.staged.get(staged.id)
        if stored is None:
            raise _not_found("staged_blob", staged.id)
        if stored.consumed_at is not None and staged.consumed_at != stored.consumed_at:
            # ``consumed_at`` is set once (CHECK + domain rule): a second consume is a defect of the caller.
            raise InternalError(
                ErrorCode.INTERNAL_ERROR,
                "staged blob is already consumed",
                details={"reason": "consumed_twice", "staged_blob_id": str(staged.id)},
            )
        tables.staged[staged.id] = staged

    def expired_digests(
        self, now: datetime, *, limit: int
    ) -> tuple[tuple[WorkspaceId, ContentDigest, str], ...]:
        rows = self.expired(now, limit=limit)
        seen: dict[tuple[str, str, str], tuple[WorkspaceId, ContentDigest, str]] = {}
        for row in rows:
            key = (row.backend_id, str(row.workspace_id), row.digest.value)
            seen[key] = (row.workspace_id, row.digest, row.backend_id)
        return tuple(seen[key] for key in sorted(seen))

    def expired(self, now: datetime, *, limit: int) -> tuple[StagedBlob, ...]:
        rows = sorted(
            (
                row
                for row in self._tables.staged.values()
                if row.consumed_at is None and row.expires_at <= now
            ),
            key=lambda row: (row.expires_at, str(row.id)),
        )
        return tuple(rows[: max(limit, 0)])

    def purge_consumed(self, before: datetime, *, limit: int) -> int:
        tables = self._writable()
        rows = sorted(
            (
                row
                for row in tables.staged.values()
                if row.consumed_at is not None and row.consumed_at <= before
            ),
            key=lambda row: (row.consumed_at or before, str(row.id)),
        )[: max(limit, 0)]
        for row in rows:
            tables.staged.pop(row.id, None)
        return len(rows)

    def delete(self, staged_blob_id: StagedBlobId) -> None:
        self._writable().staged.pop(staged_blob_id, None)

    def key_referenced(self, backend_id: str, storage_key: str) -> bool:
        located = any(
            location.backend_id == backend_id and location.storage_key == storage_key
            for locations in self._tables.locations.values()
            for location in locations
        )
        live = any(
            row.consumed_at is None and row.backend_id == backend_id and row.storage_key == storage_key
            for row in self._tables.staged.values()
        )
        return located or live


class MemoryBlobRepository(_Tables):
    def find(self, workspace_id: WorkspaceId, digest: ContentDigest, size_bytes: int) -> Blob | None:
        return next(
            (
                blob
                for blob in self._tables.blobs.values()
                if blob.workspace_id == workspace_id
                and blob.digest == digest
                and blob.size_bytes == size_bytes
            ),
            None,
        )

    def get(self, blob_id: BlobId) -> Blob:
        found = self._tables.blobs.get(blob_id)
        if found is None:
            raise _not_found("blob", blob_id)
        return found

    def add(self, blob: Blob, location: BlobLocation) -> None:
        tables = self._writable()
        if location.blob_id != blob.id:
            raise InternalError(
                ErrorCode.INTERNAL_ERROR,
                "blob location names another blob",
                details={"reason": "foreign_location"},
            )
        taken = any(
            other.backend_id == location.backend_id and other.storage_key == location.storage_key
            for locations in tables.locations.values()
            for other in locations
        )
        if blob.id in tables.blobs or taken or self.find(blob.workspace_id, blob.digest, blob.size_bytes):
            raise _exists("blob", digest=blob.digest.value)
        tables.blobs[blob.id] = blob
        tables.locations[blob.id] = (location,)

    def locations(self, blob_id: BlobId) -> tuple[BlobLocation, ...]:
        return self._tables.locations.get(blob_id, ())

    def mark_location(self, blob_id: BlobId, backend_id: str, state: LocationState, at: datetime) -> None:
        tables = self._writable()
        current = tables.locations.get(blob_id, ())
        if not any(location.backend_id == backend_id for location in current):
            raise _not_found("blob_location", f"{blob_id}/{backend_id}")
        tables.locations[blob_id] = tuple(
            replace(location, state=state, verified_at=at) if location.backend_id == backend_id else location
            for location in current
        )

    def all_keys(self, workspace_id: WorkspaceId, backend_id: str) -> frozenset[str]:
        return frozenset(
            location.storage_key
            for blob_id, locations in self._tables.locations.items()
            if self._tables.blobs[blob_id].workspace_id == workspace_id
            for location in locations
            if location.backend_id == backend_id
        )

    def entries_in_backend(
        self, workspace_id: WorkspaceId, backend_id: str
    ) -> tuple[tuple[BlobId, str], ...]:
        items = [
            (blob_id, location.storage_key)
            for blob_id, locations in self._tables.locations.items()
            if self._tables.blobs[blob_id].workspace_id == workspace_id
            for location in locations
            if location.backend_id == backend_id
        ]
        items.sort(key=lambda pair: (pair[1], str(pair[0])))
        return tuple(items)


class MemoryFileRepository(_Tables):
    def get(self, file_id: FileId) -> File:
        found = self._tables.files.get(file_id)
        if found is None:
            raise _not_found("file", file_id)
        return found

    def add(self, file: File) -> None:
        tables = self._writable()
        if file.id in tables.files:
            raise _exists("file", ref=str(file.id))
        tables.files[file.id] = file

    def save(self, file: File, *, expected_version: int) -> None:
        tables = self._writable()
        actual = self.get(file.id).row_version
        if actual != expected_version:
            raise Conflict(
                ErrorCode.VERSION_CONFLICT,
                f"version conflict: expected {expected_version}, actual {actual}",
                details={"kind": "file", "expected": expected_version, "actual": actual},
            )
        tables.files[file.id] = file

    def list(
        self,
        workspace_id: WorkspaceId,
        *,
        project_id: ProjectId | None,
        state: FileState | None,
        origin: FileOrigin | None,
        after: str | None,
        limit: int,
    ) -> Page[File]:
        limit = validate_page_limit(limit)
        start = _decode_cursor(after, 2)
        rows = sorted(
            (
                row
                for row in self._tables.files.values()
                if row.workspace_id == workspace_id
                and (project_id is None or row.project_id == project_id)
                and (state is None or row.state is state)
                and (origin is None or row.origin is origin)
            ),
            key=lambda row: (row.created_at, str(row.id)),
            reverse=True,
        )
        if start is not None:
            try:
                created = datetime.fromisoformat(start[0])
            except ValueError:
                raise _bad_cursor() from None
            if created.tzinfo is None or created.utcoffset() is None:  # never comparable with a stored row
                raise _bad_cursor()
            bound = (created, start[1])
            rows = [row for row in rows if (row.created_at, str(row.id)) < bound]
        items = rows[:limit]
        following = (
            _encode_cursor((items[-1].created_at.isoformat(), str(items[-1].id)))
            if len(rows) > limit
            else None
        )
        return Page(items=tuple(items), next=following)


class MemoryFileVersionRepository(_Tables):
    def get(self, version_id: FileVersionId) -> FileVersion:
        found = self._tables.versions.get(version_id)
        if found is None:
            raise _not_found("file_version", version_id)
        return found

    def last_no(self, file_id: FileId) -> int:
        return max((v.version_no for v in self._tables.versions.values() if v.file_id == file_id), default=0)

    def add(self, version: FileVersion) -> None:
        tables = self._writable()
        file = tables.files.get(version.file_id)
        if file is None or file.workspace_id != version.workspace_id:
            raise _not_found("file", version.file_id)
        if version.id in tables.versions or any(
            other.file_id == version.file_id and other.version_no == version.version_no
            for other in tables.versions.values()
        ):
            raise _exists("file_version", file_id=str(version.file_id), version_no=str(version.version_no))
        tables.versions[version.id] = version

    def list(self, file_id: FileId, *, after: str | None, limit: int) -> Page[FileVersion]:
        limit = validate_page_limit(limit)
        start = _decode_cursor(after, 1)
        rows = sorted(
            (row for row in self._tables.versions.values() if row.file_id == file_id),
            key=lambda row: row.version_no,
            reverse=True,
        )
        if start is not None:
            if not start[0].isdecimal():
                raise _bad_cursor()
            rows = [row for row in rows if row.version_no < int(start[0])]
        items = rows[:limit]
        following = _encode_cursor((str(items[-1].version_no),)) if len(rows) > limit else None
        return Page(items=tuple(items), next=following)

    def many(self, ids: Sequence[FileVersionId]) -> tuple[FileVersion, ...]:
        """The existing versions among ``ids``, in the order asked; unknown ids are simply absent."""
        found = (self._tables.versions.get(version_id) for version_id in dict.fromkeys(ids))
        return tuple(row for row in found if row is not None)


class MemoryAccessGrantRepository(_Tables):
    def add_many(self, grants: Sequence[AccessGrant]) -> None:
        """All or none: a stored id or a second active grant of one claim is ``ALREADY_EXISTS``."""
        tables = self._writable()
        held = [g for g in tables.grants.values() if g.revoked_at is None]
        batch: list[AccessGrant] = []
        for grant in grants:
            claim = (grant.principal_id, grant.file_version_id, grant.reason, grant.ref)
            # An expired row no longer blocks its claim: only an unrevoked grant still active at the new
            # grant's own issue time does ("at most one active grant per claim", artifacts §11).
            clash = grant.revoked_at is None and any(
                (other.principal_id, other.file_version_id, other.reason, other.ref) == claim
                and other.expires_at > grant.created_at
                for other in (*held, *batch)
            )
            if grant.id in tables.grants or clash:
                raise _exists("access_grant", file_version_id=str(grant.file_version_id))
            batch.append(grant)
        for grant in grants:
            tables.grants[grant.id] = grant

    def active_for(
        self,
        principal_id: PrincipalId,
        version_id: FileVersionId,
        now: datetime,
        *,
        reason: GrantReason | None = None,
        ref: str | None = None,
    ) -> AccessGrant | None:
        """The active grant of this principal on exactly this version, the latest-expiring one.

        ``reason`` and ``ref``, when given, select the claim first: another claim that expires later never
        hides an exact one.
        """
        active = [
            grant
            for grant in self._tables.grants.values()
            if grant.principal_id == principal_id
            and grant.file_version_id == version_id
            and (reason is None or grant.reason is reason)
            and (ref is None or grant.ref == ref)
            and grant_is_active(grant, now)
        ]
        return max(
            active, key=lambda grant: (grant.expires_at, grant.created_at, str(grant.id)), default=None
        )

    def held_claims(
        self,
        principal_id: PrincipalId,
        version_ids: Sequence[FileVersionId],
        now: datetime,
        *,
        reason: GrantReason,
        ref: str,
    ) -> frozenset[FileVersionId]:
        wanted = frozenset(version_ids)
        return frozenset(
            grant.file_version_id
            for grant in self._tables.grants.values()
            if grant.principal_id == principal_id
            and grant.file_version_id in wanted
            and grant.reason is reason
            and grant.ref == ref
            and grant_is_active(grant, now)
        )

    def revoke_by_ref(self, reason: GrantReason, ref: str, at: datetime) -> int:
        """Close every not yet revoked grant of the claim (expired ones too); returns how many were closed."""
        tables = self._writable()
        open_rows = [
            g for g in tables.grants.values() if g.reason is reason and g.ref == ref and g.revoked_at is None
        ]
        for grant in open_rows:
            tables.grants[grant.id] = replace(grant, revoked_at=at)
        return len(open_rows)

    def extend_by_ref(self, reason: GrantReason, ref: str, expires_at: datetime, now: datetime) -> int:
        """Move the expiry of the still-active grants of the claim to ``expires_at`` (never earlier).

        Revoked and expired grants stay as they are: renewal never revives. Rows are updated in place, so a
        renewal appends nothing. Returns the number of active grants of the claim.
        """
        tables = self._writable()
        active = [
            g
            for g in tables.grants.values()
            if g.reason is reason and g.ref == ref and grant_is_active(g, now)
        ]
        for grant in active:
            tables.grants[grant.id] = replace(grant, expires_at=max(grant.expires_at, expires_at))
        return len(active)
