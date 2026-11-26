"""Memory implementation of ``ProjectionRepository`` (integrations §6, §11; DDL ``0020``)."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from typing import Final, cast
from uuid import UUID

from skm.adapters.memory.artifacts.state import STATE_KEY as ARTIFACTS_KEY
from skm.adapters.memory.artifacts.state import artifacts_state
from skm.adapters.memory.core.state import MemoryBackendState
from skm.adapters.memory.integrations.state import (
    MemoryIntegrationsState,
    StoredProjection,
    integrations_state,
)
from skm.adapters.memory.workspace.state import STATE_KEY as WORKSPACE_KEY
from skm.adapters.memory.workspace.state import workspace_state
from skm.kernel.clock import Clock
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, NotFound, ValidationFailed, error_for
from skm.kernel.ids import ProjectId, WorkspaceId
from skm.kernel.pagination import CURSOR_MAX_LENGTH, Cursor, Page, validate_page_limit
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.integrations.domain.decisions import is_safe_relative_path
from skm.modules.integrations.domain.observed import AppliedFileRecord
from skm.modules.integrations.domain.ownership import ManagedBoundary, Ownership
from skm.modules.integrations.domain.projection import Projection, ProjectionId, ProjectionState
from skm.modules.integrations.domain.target import Surface, TargetId
from skm.modules.workspace.public import CheckoutBindingId
from skm.platform.system_clock import SystemClock

__all__ = ["MemoryProjectionRepository"]

_DIGEST_RE: Final = re.compile(r"^sha256:[0-9a-f]{64}$")
_RENDERER_VERSION_RE: Final = re.compile(r"^[a-z][a-z0-9_]{1,31}@[0-9]+$")
_FILE_RENDERER_RE: Final = re.compile(r"^[a-z][a-z0-9_]{1,31}\.[a-z_]{1,32}@[0-9]+$")
_PENDING_ELIGIBLE: Final = frozenset(
    {ProjectionState.IN_SYNC, ProjectionState.DRIFTED, ProjectionState.FAILED}
)


def _not_found(projection_id: ProjectionId) -> NotFound:
    return NotFound(
        ErrorCode.NOT_FOUND,
        "projection not found",
        details={"kind": "projection", "ref": str(projection_id)},
    )


def _version_conflict(expected: int, actual: int) -> Conflict:
    return Conflict(
        ErrorCode.VERSION_CONFLICT,
        "projection row_version mismatch",
        details={"kind": "projection", "expected": expected, "actual": actual},
    )


def _bad_cursor(reason: str) -> ValidationFailed:
    return ValidationFailed(
        ErrorCode.SCHEMA_INVALID,
        "cursor is not valid for this query",
        details={"field": "after", "reason": reason},
    )


def _query_digest(project_id: ProjectId) -> str:
    payload = json.dumps(
        {"kind": "project_projections", "project_id": str(project_id)},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _encode_cursor(updated_at: datetime, projection_id: ProjectionId, digest: str) -> Cursor:
    payload = json.dumps(
        {"v": 1, "k": [updated_at.isoformat(), str(projection_id)], "q": digest},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    text = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")
    if len(text) > CURSOR_MAX_LENGTH:
        raise ValueError(f"encoded cursor exceeds {CURSOR_MAX_LENGTH} characters")
    return Cursor(text)


def _decode_cursor(text: str | None, *, expected_digest: str) -> tuple[datetime, UUID] | None:
    if text is None:
        return None
    if not 1 <= len(text) <= CURSOR_MAX_LENGTH or not text.isascii():
        raise _bad_cursor("malformed")
    try:
        raw = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
        document: object = json.loads(raw.decode("utf-8"))
    except (binascii.Error, UnicodeDecodeError, ValueError):
        raise _bad_cursor("malformed") from None
    if not isinstance(document, dict):
        raise _bad_cursor("malformed")
    body = cast("dict[str, object]", document)
    if body.keys() != {"v", "k", "q"} or body["v"] != 1 or isinstance(body["v"], bool):
        raise _bad_cursor("malformed")
    keys = body.get("k")
    digest = body.get("q")
    if not isinstance(keys, list) or not isinstance(digest, str):
        raise _bad_cursor("malformed")
    items = cast("list[object]", keys)
    if len(items) != 2 or not all(isinstance(v, str) for v in items):
        raise _bad_cursor("key_mismatch")
    if digest != expected_digest:
        raise _bad_cursor("query_mismatch")
    try:
        ts = datetime.fromisoformat(cast("str", items[0]))
        uid = UUID(cast("str", items[1]))
    except ValueError:
        raise _bad_cursor("malformed") from None
    if ts.tzinfo is None:
        raise _bad_cursor("malformed")
    return ts, uid


def _validate_projection(projection: Projection) -> None:
    TargetId(projection.target)
    state = ProjectionState(projection.state)
    if projection.row_version < 1:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "row_version must be >= 1",
            details={"constraint": "ck_projections__row_version"},
        )
    if projection.desired_digest is not None and _DIGEST_RE.fullmatch(projection.desired_digest) is None:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "invalid desired_digest",
            details={"constraint": "ck_projections__desired_digest"},
        )
    if (
        projection.applied_desired_digest is not None
        and _DIGEST_RE.fullmatch(projection.applied_desired_digest) is None
    ):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "invalid applied_desired_digest",
            details={"constraint": "ck_projections__applied_desired_digest"},
        )
    if state is ProjectionState.IN_SYNC and (
        projection.applied_desired_digest is None
        or projection.applied_desired_digest != projection.desired_digest
    ):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "in_sync requires applied_desired_digest equal to desired_digest",
            details={"constraint": "ck_projections__in_sync"},
        )
    if (
        projection.renderer_version is not None
        and _RENDERER_VERSION_RE.fullmatch(projection.renderer_version) is None
    ):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "invalid renderer_version",
            details={"constraint": "ck_projections__renderer_version"},
        )


def _validate_boundary(boundary: ManagedBoundary) -> None:
    ownership = Ownership(boundary.ownership)
    if ownership is Ownership.MANAGED_BLOCK:
        valid = len(boundary.block_ids) >= 1 and len(boundary.owned_keys) == 0
    elif ownership in (Ownership.MERGED_JSON, Ownership.MERGED_TOML):
        valid = len(boundary.block_ids) == 0 and len(boundary.owned_keys) >= 1
    else:
        valid = len(boundary.block_ids) == 0 and len(boundary.owned_keys) == 0
    if not valid:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "boundary does not match ownership mode",
            details={"constraint": "ck_projection_files__boundary"},
        )


def _validate_file_record(projection_id: ProjectionId, record: AppliedFileRecord) -> None:
    if record.projection_id != projection_id:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "record projection_id does not match target projection",
            details={"field": "projection_id"},
        )
    rel = record.relative_path
    if not (1 <= len(rel) <= 1024) or "\n" in rel or "\r" in rel or not is_safe_relative_path(rel):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "invalid relative_path",
            details={"constraint": "ck_projection_files__relative_path"},
        )
    Surface(record.surface)
    _validate_boundary(record.boundary)
    if _DIGEST_RE.fullmatch(record.applied_managed_digest) is None:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "invalid applied_managed_digest",
            details={"constraint": "ck_projection_files__applied_managed_digest"},
        )
    if _DIGEST_RE.fullmatch(record.applied_whole_digest) is None:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "invalid applied_whole_digest",
            details={"constraint": "ck_projection_files__applied_whole_digest"},
        )
    if _FILE_RENDERER_RE.fullmatch(record.renderer) is None:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "invalid file renderer identifier",
            details={"constraint": "ck_projection_files__renderer"},
        )


class MemoryProjectionRepository:
    """In-memory ``ProjectionRepository`` matching DDL ``0020_integrations_projections.sql``."""

    def __init__(self, state: MemoryBackendState, *, clock: Clock | None = None) -> None:
        self._state = state
        self._tables: MemoryIntegrationsState = integrations_state(state)
        self._clock: Clock = clock if clock is not None else (state.core.clock.clock or SystemClock())

    def _writable(self) -> MemoryIntegrationsState:
        self._state.core.require_writable()
        return self._tables

    def _now(self) -> datetime:
        now = self._clock.now()
        return now if now.tzinfo is not None else now.replace(tzinfo=UTC)

    def _check_projection_fks(self, projection: Projection) -> None:
        if WORKSPACE_KEY not in self._state.modules:
            return
        ws = workspace_state(self._state)
        proj = ws.projects.get(projection.project_id)
        if proj is None or proj.workspace_id != projection.workspace_id:
            raise error_for(
                ErrorCode.INVALID_REFERENCE,
                "foreign key violated",
                details={"constraint": "fk_projections__projects"},
            )
        binding = ws.bindings.get(projection.checkout_binding_id)
        if binding is None or binding.workspace_id != projection.workspace_id:
            raise error_for(
                ErrorCode.INVALID_REFERENCE,
                "foreign key violated",
                details={"constraint": "fk_projections__checkout_bindings"},
            )

    def _check_file_fks(self, records: tuple[AppliedFileRecord, ...]) -> None:
        if ARTIFACTS_KEY not in self._state.modules:
            return
        versions = artifacts_state(self._state).versions
        for rec in records:
            if rec.pre_image_file_version_id is not None and rec.pre_image_file_version_id not in versions:
                raise error_for(
                    ErrorCode.INVALID_REFERENCE,
                    "foreign key violated",
                    details={"constraint": "fk_projection_files__file_versions"},
                )

    def get(self, projection_id: ProjectionId) -> Projection:
        stored = self._tables.projections.get(projection_id)
        if stored is None:
            raise _not_found(projection_id)
        return stored.projection

    def find(
        self, project_id: ProjectId, checkout_binding_id: CheckoutBindingId, target: TargetId
    ) -> Projection | None:
        wanted_target = TargetId(target)
        for stored in self._tables.projections.values():
            p = stored.projection
            if (
                p.project_id == project_id
                and p.checkout_binding_id == checkout_binding_id
                and p.target is wanted_target
            ):
                return p
        return None

    def list_for_project(
        self, project_id: ProjectId, *, after: Cursor | None, limit: int
    ) -> Page[Projection]:
        page_limit = validate_page_limit(limit)
        digest = _query_digest(project_id)
        boundary = _decode_cursor(after, expected_digest=digest)
        matching = [s for s in self._tables.projections.values() if s.projection.project_id == project_id]
        matching.sort(key=lambda s: (s.updated_at, UUID(str(s.projection.id))), reverse=True)
        if boundary is not None:
            after_ts, after_id = boundary
            matching = [
                s for s in matching if (s.updated_at, UUID(str(s.projection.id))) < (after_ts, after_id)
            ]
        sliced = matching[: page_limit + 1]
        if len(sliced) <= page_limit:
            return Page(items=tuple(s.projection for s in sliced), next=None)
        items = sliced[:page_limit]
        last = items[-1]
        return Page(
            items=tuple(s.projection for s in items),
            next=_encode_cursor(last.updated_at, last.projection.id, digest),
        )

    def add(self, projection: Projection) -> None:
        tables = self._writable()
        _validate_projection(projection)
        self._check_projection_fks(projection)
        if projection.id in tables.projections:
            raise Conflict(
                ErrorCode.ALREADY_EXISTS,
                "projection already exists",
                details={"constraint": "projections_pkey"},
            )
        target = TargetId(projection.target)
        for existing in tables.projections.values():
            p = existing.projection
            if p.checkout_binding_id == projection.checkout_binding_id and p.target is target:
                raise Conflict(
                    ErrorCode.ALREADY_EXISTS,
                    "unique constraint violated",
                    details={"constraint": "uq_projections__checkout_binding_id_target"},
                )
        now = self._now()
        normalized = replace(projection, target=target, state=ProjectionState(projection.state))
        tables.projections[projection.id] = StoredProjection(
            projection=normalized,
            created_at=now,
            updated_at=now,
        )

    def save(self, projection: Projection, *, expected_version: int) -> None:
        tables = self._writable()
        stored = tables.projections.get(projection.id)
        if stored is None:
            raise _not_found(projection.id)
        current = stored.projection
        if current.row_version != expected_version:
            raise _version_conflict(expected_version, current.row_version)
        for attr in ("workspace_id", "project_id", "checkout_binding_id", "target"):
            if getattr(current, attr) != getattr(projection, attr):
                raise ValueError(f"projection.{attr} is immutable")
        _validate_projection(projection)
        now = self._now()
        updated_at = max(stored.updated_at, now)
        normalized = replace(
            projection,
            target=TargetId(projection.target),
            state=ProjectionState(projection.state),
        )
        tables.projections[projection.id] = StoredProjection(
            projection=normalized,
            created_at=stored.created_at,
            updated_at=updated_at,
        )

    def files(self, projection_id: ProjectionId) -> tuple[AppliedFileRecord, ...]:
        return deepcopy(self._tables.files.get(projection_id, ()))

    def replace_files(self, projection_id: ProjectionId, records: tuple[AppliedFileRecord, ...]) -> None:
        tables = self._writable()
        if projection_id not in tables.projections:
            raise error_for(
                ErrorCode.INVALID_REFERENCE,
                "foreign key violated",
                details={"constraint": "fk_projection_files__projections"},
            )
        seen_paths: set[str] = set()
        normalized: list[AppliedFileRecord] = []
        for rec in records:
            _validate_file_record(projection_id, rec)
            if rec.relative_path in seen_paths:
                raise Conflict(
                    ErrorCode.ALREADY_EXISTS,
                    "unique constraint violated",
                    details={"constraint": "pk_projection_files"},
                )
            seen_paths.add(rec.relative_path)
            normalized.append(
                replace(
                    deepcopy(rec),
                    surface=Surface(rec.surface),
                    boundary=ManagedBoundary(
                        ownership=Ownership(rec.boundary.ownership),
                        block_ids=tuple(rec.boundary.block_ids),
                        owned_keys=tuple(rec.boundary.owned_keys),
                    ),
                )
            )
        self._check_file_fks(tuple(normalized))
        normalized.sort(key=lambda item: item.relative_path)
        tables.files[projection_id] = tuple(normalized)

    def managed_file_paths(self, project_id: ProjectId, target: TargetId) -> frozenset[str]:
        wanted_target = TargetId(target)
        paths: set[str] = set()
        for stored in self._tables.projections.values():
            p = stored.projection
            if (
                p.project_id == project_id
                and p.target is wanted_target
                and p.state is not ProjectionState.REMOVED
            ):
                for rec in self._tables.files.get(p.id, ()):
                    if rec.boundary.ownership is Ownership.MANAGED_FILE:
                        paths.add(rec.relative_path)
        return frozenset(paths)

    def mark_pending(self, scope: ScopeRef) -> int:
        tables = self._writable()
        if scope.kind is ScopeKind.PROJECT:
            target_project = ProjectId(scope.id)

            def _match_project(p: Projection) -> bool:
                return p.project_id == target_project

            match_fn = _match_project
        elif scope.kind is ScopeKind.WORKSPACE:
            target_workspace = WorkspaceId(scope.id)

            def _match_workspace(p: Projection) -> bool:
                return p.workspace_id == target_workspace

            match_fn = _match_workspace
        elif scope.kind is ScopeKind.INSTANCE:
            scope_rec = self._state.core.scopes.get(scope.id)
            if scope_rec is None or scope_rec.kind is not ScopeKind.INSTANCE:
                return 0

            def _match_instance(_p: Projection) -> bool:
                return True

            match_fn = _match_instance
        else:
            return 0

        now = self._now()
        updated_count = 0
        for proj_id, stored in list(tables.projections.items()):
            p = stored.projection
            if p.state in _PENDING_ELIGIBLE and match_fn(p):
                updated_proj = replace(
                    p,
                    state=ProjectionState.PENDING,
                    row_version=p.row_version + 1,
                )
                tables.projections[proj_id] = StoredProjection(
                    projection=updated_proj,
                    created_at=stored.created_at,
                    updated_at=max(stored.updated_at, now),
                )
                updated_count += 1
        return updated_count
