"""PostgreSQL implementation of ``ProjectionRepository`` (integrations §6, §11; DDL ``0020``)."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Final, cast
from uuid import UUID

import psycopg

from skm.adapters.postgres.errors import translate_pg_error
from skm.adapters.postgres.pagination import decode_cursor, page_of, query_digest
from skm.kernel.clock import Clock
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, InternalError, NotFound, ValidationFailed, error_for
from skm.kernel.ids import FileVersionId, ProjectId, WorkspaceId
from skm.kernel.pagination import Cursor, Page, validate_page_limit
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.integrations.domain.merged_json import OwnedKeyPath
from skm.modules.integrations.domain.observed import AppliedFileRecord
from skm.modules.integrations.domain.ownership import ManagedBoundary, Ownership
from skm.modules.integrations.domain.projection import Projection, ProjectionId, ProjectionState
from skm.modules.integrations.domain.target import Surface, TargetId
from skm.modules.workspace.public import CheckoutBindingId
from skm.platform.system_clock import SystemClock

__all__ = ["PostgresProjectionRepository"]

type _Row = tuple[object, ...]

_SELECT_BY_ID: Final = """
SELECT id, workspace_id, project_id, checkout_binding_id, target, state,
       desired_digest, applied_desired_digest, renderer_version,
       applied_at, drift_checked_at, row_version, updated_at
  FROM skm_integrations.projections
 WHERE id = %s
"""

_SELECT_FOR_UPDATE: Final = """
SELECT id, workspace_id, project_id, checkout_binding_id, target, state,
       desired_digest, applied_desired_digest, renderer_version,
       applied_at, drift_checked_at, row_version, updated_at
  FROM skm_integrations.projections
 WHERE id = %s
   FOR UPDATE
"""

_SELECT_FIND: Final = """
SELECT id, workspace_id, project_id, checkout_binding_id, target, state,
       desired_digest, applied_desired_digest, renderer_version,
       applied_at, drift_checked_at, row_version, updated_at
  FROM skm_integrations.projections
 WHERE project_id = %s AND checkout_binding_id = %s AND target = %s
"""

_LIST_FOR_PROJECT: Final = """
SELECT id, workspace_id, project_id, checkout_binding_id, target, state,
       desired_digest, applied_desired_digest, renderer_version,
       applied_at, drift_checked_at, row_version, updated_at
  FROM skm_integrations.projections
 WHERE project_id = %(project_id)s
   AND (
       %(after_at)s::timestamptz IS NULL
       OR (updated_at, id) < (%(after_at)s::timestamptz, %(after_id)s::uuid)
   )
 ORDER BY updated_at DESC, id DESC
 LIMIT %(limit)s
"""

_INSERT_PROJECTION: Final = """
INSERT INTO skm_integrations.projections (
    id, workspace_id, project_id, checkout_binding_id, target, state,
    desired_digest, applied_desired_digest, renderer_version,
    applied_at, drift_checked_at, row_version, created_at, updated_at
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

_UPDATE_PROJECTION: Final = """
UPDATE skm_integrations.projections
   SET state = %s,
       desired_digest = %s,
       applied_desired_digest = %s,
       renderer_version = %s,
       applied_at = %s,
       drift_checked_at = %s,
       row_version = %s,
       updated_at = greatest(updated_at, %s)
 WHERE id = %s AND row_version = %s
"""

_SELECT_PROJECTION_EXISTS: Final = "SELECT 1 FROM skm_integrations.projections WHERE id = %s"

_SELECT_FILES: Final = """
SELECT projection_id, relative_path, surface, ownership, block_ids, owned_keys,
       applied_managed_digest, applied_whole_digest, pre_image_file_version_id,
       renderer, applied_at
  FROM skm_integrations.projection_files
 WHERE projection_id = %s
 ORDER BY relative_path COLLATE "C" ASC
"""

_DELETE_FILES: Final = "DELETE FROM skm_integrations.projection_files WHERE projection_id = %s"

_INSERT_FILE: Final = """
INSERT INTO skm_integrations.projection_files (
    projection_id, relative_path, surface, ownership, block_ids, owned_keys,
    applied_managed_digest, applied_whole_digest, pre_image_file_version_id,
    renderer, applied_at
)
VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s)
"""

_MANAGED_FILE_PATHS: Final = """
SELECT pf.relative_path
  FROM skm_integrations.projection_files AS pf
  JOIN skm_integrations.projections AS p ON p.id = pf.projection_id
 WHERE p.project_id = %s
   AND p.target = %s
   AND p.state <> 'removed'
   AND pf.ownership = 'managed_file'
"""

_MARK_PENDING_PROJECT: Final = """
UPDATE skm_integrations.projections
   SET state = 'pending',
       row_version = row_version + 1,
       updated_at = greatest(updated_at, %s)
 WHERE project_id = %s
   AND state IN ('in_sync', 'drifted', 'failed')
"""

_MARK_PENDING_WORKSPACE: Final = """
UPDATE skm_integrations.projections
   SET state = 'pending',
       row_version = row_version + 1,
       updated_at = greatest(updated_at, %s)
 WHERE workspace_id = %s
   AND state IN ('in_sync', 'drifted', 'failed')
"""

_MARK_PENDING_INSTANCE: Final = """
UPDATE skm_integrations.projections
   SET state = 'pending',
       row_version = row_version + 1,
       updated_at = greatest(updated_at, %s)
 WHERE state IN ('in_sync', 'drifted', 'failed')
   AND EXISTS (
       SELECT 1 FROM skm_core.scopes WHERE id = %s AND kind = 'instance'
   )
"""


def _run[T](call: Callable[[], T]) -> T:
    try:
        return call()
    except psycopg.Error as exc:
        raise translate_pg_error(exc) from exc


def _damaged(table: str, ref: object, exc: Exception) -> InternalError:
    error = InternalError(
        ErrorCode.INTERNAL_ERROR,
        f"skm_integrations.{table} row is malformed",
        details={"table": f"skm_integrations.{table}", "id": str(ref)},
    )
    error.__cause__ = exc
    return error


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


def _projection_from_row(row: _Row) -> tuple[Projection, datetime]:
    try:
        projection = Projection(
            id=ProjectionId(cast("UUID", row[0])),
            workspace_id=WorkspaceId(cast("UUID", row[1])),
            project_id=ProjectId(cast("UUID", row[2])),
            checkout_binding_id=CheckoutBindingId(cast("UUID", row[3])),
            target=TargetId(cast("str", row[4])),
            state=ProjectionState(cast("str", row[5])),
            desired_digest=cast("str | None", row[6]),
            applied_desired_digest=cast("str | None", row[7]),
            renderer_version=cast("str | None", row[8]),
            applied_at=cast("datetime | None", row[9]),
            drift_checked_at=cast("datetime | None", row[10]),
            row_version=cast("int", row[11]),
        )
        updated_at = cast("datetime", row[12])
    except (TypeError, ValueError, ValidationFailed) as exc:
        raise _damaged("projections", row[0], exc) from exc
    return projection, updated_at


def _owned_keys_to_json(owned_keys: tuple[OwnedKeyPath, ...]) -> str:
    payload = [{"path": list(item.path), "mode": item.mode} for item in owned_keys]
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _owned_keys_from_raw(raw: object) -> tuple[OwnedKeyPath, ...]:
    parsed: object = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(parsed, Sequence) or isinstance(parsed, (str, bytes)):
        raise ValueError("owned_keys is not a JSON array")
    items: list[OwnedKeyPath] = []
    for entry in cast("Sequence[object]", parsed):
        if not isinstance(entry, Mapping):
            raise ValueError("owned_keys item is not a JSON object")
        mapping_entry = cast("Mapping[str, object]", entry)
        raw_path = mapping_entry.get("path")
        raw_mode = mapping_entry.get("mode")
        if (
            not isinstance(raw_path, Sequence)
            or isinstance(raw_path, (str, bytes))
            or not raw_path
            or not all(isinstance(seg, str) for seg in cast("Sequence[object]", raw_path))
        ):
            raise ValueError("owned_keys.path must be a non-empty string array")
        if raw_mode not in ("replace", "list_union_tagged"):
            raise ValueError(f"invalid owned_keys.mode {raw_mode!r}")
        items.append(OwnedKeyPath(path=tuple(cast("Sequence[str]", raw_path)), mode=raw_mode))
    return tuple(items)


def _file_from_row(row: _Row) -> AppliedFileRecord:
    try:
        raw_blocks = row[4]
        if not isinstance(raw_blocks, Sequence) or isinstance(raw_blocks, (str, bytes)):
            raise ValueError("block_ids is not a string sequence")
        block_ids = tuple(cast("Sequence[str]", raw_blocks))
        owned_keys = _owned_keys_from_raw(row[5])
        boundary = ManagedBoundary(
            ownership=Ownership(cast("str", row[3])),
            block_ids=block_ids,
            owned_keys=owned_keys,
        )
        raw_pre_image = cast("UUID | None", row[8])
        return AppliedFileRecord(
            projection_id=ProjectionId(cast("UUID", row[0])),
            relative_path=cast("str", row[1]),
            surface=Surface(cast("str", row[2])),
            boundary=boundary,
            applied_managed_digest=cast("str", row[6]),
            applied_whole_digest=cast("str", row[7]),
            pre_image_file_version_id=None if raw_pre_image is None else FileVersionId(raw_pre_image),
            renderer=cast("str", row[9]),
            applied_at=cast("datetime", row[10]),
        )
    except (TypeError, ValueError, ValidationFailed) as exc:
        raise _damaged("projection_files", f"{row[0]}:{row[1]}", exc) from exc


class PostgresProjectionRepository:
    """PostgreSQL ``ProjectionRepository`` over ``skm_integrations`` (DDL ``0020``)."""

    def __init__(self, conn: psycopg.Connection, *, clock: Clock | None = None) -> None:
        self._conn = conn
        self._clock: Clock = clock if clock is not None else SystemClock()

    def get(self, projection_id: ProjectionId) -> Projection:
        row = _run(lambda: self._conn.execute(_SELECT_BY_ID, (projection_id,)).fetchone())
        if row is None:
            raise _not_found(projection_id)
        projection, _ = _projection_from_row(row)
        return projection

    def find(
        self, project_id: ProjectId, checkout_binding_id: CheckoutBindingId, target: TargetId
    ) -> Projection | None:
        target_val = TargetId(target).value
        row = _run(
            lambda: self._conn.execute(_SELECT_FIND, (project_id, checkout_binding_id, target_val)).fetchone()
        )
        if row is None:
            return None
        projection, _ = _projection_from_row(row)
        return projection

    def list_for_project(
        self, project_id: ProjectId, *, after: Cursor | None, limit: int
    ) -> Page[Projection]:
        page_limit = validate_page_limit(limit)
        digest = query_digest({"kind": "project_projections", "project_id": str(project_id)})
        after_at: datetime | None = None
        after_id: UUID | None = None
        if after is not None:
            decoded = decode_cursor(after, expected_query_digest=digest)
            if len(decoded.sort_values) != 2 or not all(isinstance(v, str) for v in decoded.sort_values):
                raise _bad_cursor("key_mismatch")
            try:
                after_at = datetime.fromisoformat(cast("str", decoded.sort_values[0]))
                after_id = UUID(cast("str", decoded.sort_values[1]))
            except ValueError:
                raise _bad_cursor("malformed") from None
            if after_at.tzinfo is None:
                raise _bad_cursor("malformed")
        params = {
            "project_id": project_id,
            "after_at": after_at,
            "after_id": after_id,
            "limit": page_limit + 1,
        }
        rows = _run(lambda: self._conn.execute(_LIST_FOR_PROJECT, params).fetchall())
        decoded_rows = [_projection_from_row(row) for row in rows]
        built = page_of(
            decoded_rows,
            limit=page_limit,
            digest=digest,
            key_of=lambda pair: (pair[1].isoformat(), str(pair[0].id)),
        )
        return Page(items=tuple(pair[0] for pair in built.items), next=built.next)

    def add(self, projection: Projection) -> None:
        now = self._clock.now()
        params = (
            projection.id,
            projection.workspace_id,
            projection.project_id,
            projection.checkout_binding_id,
            TargetId(projection.target).value,
            ProjectionState(projection.state).value,
            projection.desired_digest,
            projection.applied_desired_digest,
            projection.renderer_version,
            projection.applied_at,
            projection.drift_checked_at,
            projection.row_version,
            now,
            now,
        )
        _run(lambda: self._conn.execute(_INSERT_PROJECTION, params))

    def save(self, projection: Projection, *, expected_version: int) -> None:
        row = _run(lambda: self._conn.execute(_SELECT_FOR_UPDATE, (projection.id,)).fetchone())
        if row is None:
            raise _not_found(projection.id)
        current, _ = _projection_from_row(row)
        if current.row_version != expected_version:
            raise _version_conflict(expected_version, current.row_version)
        for attr in ("workspace_id", "project_id", "checkout_binding_id", "target"):
            if getattr(current, attr) != getattr(projection, attr):
                raise ValueError(f"projection.{attr} is immutable")
        now = self._clock.now()
        params = (
            ProjectionState(projection.state).value,
            projection.desired_digest,
            projection.applied_desired_digest,
            projection.renderer_version,
            projection.applied_at,
            projection.drift_checked_at,
            projection.row_version,
            now,
            projection.id,
            expected_version,
        )
        _run(lambda: self._conn.execute(_UPDATE_PROJECTION, params))

    def files(self, projection_id: ProjectionId) -> tuple[AppliedFileRecord, ...]:
        rows = _run(lambda: self._conn.execute(_SELECT_FILES, (projection_id,)).fetchall())
        return tuple(_file_from_row(row) for row in rows)

    def replace_files(self, projection_id: ProjectionId, records: tuple[AppliedFileRecord, ...]) -> None:
        for rec in records:
            if rec.projection_id != projection_id:
                raise ValidationFailed(
                    ErrorCode.SCHEMA_INVALID,
                    "record projection_id does not match target projection",
                    details={"field": "projection_id"},
                )
        if not records:
            exists = _run(lambda: self._conn.execute(_SELECT_PROJECTION_EXISTS, (projection_id,)).fetchone())
            if exists is None:
                raise error_for(
                    ErrorCode.INVALID_REFERENCE,
                    "foreign key violated",
                    details={"constraint": "fk_projection_files__projections"},
                )
        _run(lambda: self._conn.execute(_DELETE_FILES, (projection_id,)))
        if not records:
            return
        batch = [
            (
                projection_id,
                rec.relative_path,
                Surface(rec.surface).value,
                Ownership(rec.boundary.ownership).value,
                list(rec.boundary.block_ids),
                _owned_keys_to_json(rec.boundary.owned_keys),
                rec.applied_managed_digest,
                rec.applied_whole_digest,
                rec.pre_image_file_version_id,
                rec.renderer,
                rec.applied_at,
            )
            for rec in sorted(records, key=lambda item: item.relative_path)
        ]

        def _insert_batch() -> None:
            with self._conn.cursor() as cur:
                cur.executemany(_INSERT_FILE, batch)

        _run(_insert_batch)

    def managed_file_paths(self, project_id: ProjectId, target: TargetId) -> frozenset[str]:
        target_val = TargetId(target).value
        rows = _run(lambda: self._conn.execute(_MANAGED_FILE_PATHS, (project_id, target_val)).fetchall())
        return frozenset(cast("str", row[0]) for row in rows)

    def mark_pending(self, scope: ScopeRef) -> int:
        now = self._clock.now()
        if scope.kind is ScopeKind.PROJECT:
            cur = _run(lambda: self._conn.execute(_MARK_PENDING_PROJECT, (now, scope.id)))
            return cur.rowcount
        if scope.kind is ScopeKind.WORKSPACE:
            cur = _run(lambda: self._conn.execute(_MARK_PENDING_WORKSPACE, (now, scope.id)))
            return cur.rowcount
        if scope.kind is ScopeKind.INSTANCE:
            cur = _run(lambda: self._conn.execute(_MARK_PENDING_INSTANCE, (now, scope.id)))
            return cur.rowcount
        return 0
