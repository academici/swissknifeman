"""PostgreSQL files repositories with local parameterized SQL (artifacts §6, §11).

Connections belong to the surrounding UoW; checked row decoding lives in mapping.py.
"""

from collections.abc import Sequence
from typing import Final, cast

import psycopg

from skm.adapters.postgres.artifacts import mapping
from skm.adapters.postgres.jsonb import require_aware, to_jsonb
from skm.adapters.postgres.pagination import page_of, query_digest
from skm.kernel.clock import Clock
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict
from skm.kernel.ids import FileVersionId, ProjectId, WorkspaceId
from skm.kernel.pagination import Page, validate_page_limit
from skm.modules.artifacts.domain.classification import Classification
from skm.modules.artifacts.domain.file import File, FileId, FileOrigin, FileState
from skm.modules.artifacts.domain.file_version import FileVersion
from skm.platform.system_clock import SystemClock

__all__ = ["PostgresFileRepository", "PostgresFileVersionRepository"]

_FILE_COLS: Final = (
    "SELECT id, workspace_id, project_id, title, origin, classification, current_version_id, state, "
    "row_version, created_at, created_by FROM skm_artifacts.files "
)

_FILE_GET: Final = _FILE_COLS + "WHERE id = %s"

_FILE_FOR_UPDATE: Final = _FILE_GET + " FOR UPDATE"

_FILE_LOCK_ONLY: Final = "SELECT 1 FROM skm_artifacts.files WHERE id = %s FOR UPDATE"

_FILE_INSERT: Final = (
    "INSERT INTO skm_artifacts.files (id, workspace_id, project_id, title, origin, classification, "
    "current_version_id, state, row_version, created_at, created_by, updated_at) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING RETURNING id"
)

_FILE_UPDATE: Final = (
    "UPDATE skm_artifacts.files SET title = %s, classification = %s, current_version_id = %s, state = %s, "
    "row_version = %s, updated_at = greatest(updated_at, %s) WHERE id = %s AND row_version = %s"
)

_FILE_LIST: Final = (
    _FILE_COLS + "WHERE workspace_id = %(workspace)s "
    "AND (%(project)s::uuid IS NULL OR project_id = %(project)s::uuid) "
    "AND (%(state)s::text IS NULL OR state = %(state)s::text) "
    "AND (%(origin)s::text IS NULL OR origin = %(origin)s::text) "
    "AND (%(after_at)s::timestamptz IS NULL "
    "OR (created_at, id) < (%(after_at)s::timestamptz, %(after_id)s::uuid)) "
    "ORDER BY created_at DESC, id DESC LIMIT %(limit)s"
)

_VERSION_COLS: Final = (
    "SELECT id, workspace_id, file_id, version_no, blob_id, original_filename, declared_media_type, "
    "description, source, safety, created_by, created_at FROM skm_artifacts.file_versions "
)

_VERSION_GET: Final = _VERSION_COLS + "WHERE id = %s"

_VERSION_MANY: Final = _VERSION_COLS + "WHERE id = ANY(%s)"

_VERSION_LAST_NO: Final = (
    "SELECT coalesce(max(version_no), 0) FROM skm_artifacts.file_versions WHERE file_id = %s"
)

_VERSION_INSERT: Final = (
    "INSERT INTO skm_artifacts.file_versions (id, workspace_id, file_id, version_no, blob_id, "
    "original_filename, declared_media_type, description, source, safety, created_by, created_at) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING RETURNING id"
)

_VERSION_LIST: Final = (
    _VERSION_COLS
    + "WHERE file_id = %(file)s AND (%(after_no)s::integer IS NULL OR version_no < %(after_no)s::integer) "
    "ORDER BY version_no DESC LIMIT %(limit)s"
)


class PostgresFileRepository:
    def __init__(self, conn: psycopg.Connection, *, clock: Clock | None = None) -> None:
        self._conn = conn
        self._clock: Clock = clock if clock is not None else SystemClock()

    def get(self, file_id: FileId) -> File:
        row = mapping.run(lambda: self._conn.execute(_FILE_GET, (file_id,)).fetchone())
        if row is None:
            raise mapping.not_found("file", file_id)
        return mapping.file_from_row(row)

    def add(self, file: File) -> None:
        created_at = require_aware(file.created_at)
        f = file
        params = (
            f.id, f.workspace_id, f.project_id, f.title, FileOrigin(f.origin).value,
            Classification(f.classification).value, f.current_version_id, FileState(f.state).value,
            f.row_version, created_at, f.created_by, created_at,
        )  # fmt: skip
        row = mapping.in_savepoint(
            self._conn, lambda: mapping.run(lambda: self._conn.execute(_FILE_INSERT, params).fetchone())
        )
        if row is None:
            raise mapping.exists("file", ref=str(file.id))

    def save(self, file: File, *, expected_version: int) -> None:
        row = mapping.run(lambda: self._conn.execute(_FILE_FOR_UPDATE, (file.id,)).fetchone())
        if row is None:
            raise mapping.not_found("file", file.id)
        current = mapping.file_from_row(row)
        if current.row_version != expected_version:
            raise Conflict(
                ErrorCode.VERSION_CONFLICT,
                f"version conflict: expected {expected_version}, actual {current.row_version}",
                details={"kind": "file", "expected": expected_version, "actual": current.row_version},
            )
        kept = ("workspace_id", "project_id", "origin", "created_at", "created_by")
        mapping.ensure_kept("file", current, file, kept)
        params = (
            file.title, Classification(file.classification).value, file.current_version_id,
            FileState(file.state).value, file.row_version, require_aware(self._clock.now()),
            file.id, expected_version,
        )  # fmt: skip
        mapping.in_savepoint(
            self._conn, lambda: mapping.run(lambda: self._conn.execute(_FILE_UPDATE, params))
        )

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
        state_val = None if state is None else FileState(state).value
        origin_val = None if origin is None else FileOrigin(origin).value
        digest = query_digest(
            {
                "kind": "artifacts_files",
                "workspace_id": str(workspace_id),
                "project_id": None if project_id is None else str(project_id),
                "state": state_val,
                "origin": origin_val,
            }
        )
        after_at, after_id = mapping.file_keyset(after, digest=digest)
        params = {
            "workspace": workspace_id, "project": project_id, "state": state_val, "origin": origin_val,
            "after_at": after_at, "after_id": after_id, "limit": limit + 1,
        }  # fmt: skip
        rows = mapping.run(lambda: self._conn.execute(_FILE_LIST, params).fetchall())
        return page_of(
            [mapping.file_from_row(row) for row in rows],
            limit=limit,
            digest=digest,
            key_of=lambda item: (item.created_at.isoformat(), str(item.id)),
        )


class PostgresFileVersionRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def get(self, version_id: FileVersionId) -> FileVersion:
        row = mapping.run(lambda: self._conn.execute(_VERSION_GET, (version_id,)).fetchone())
        if row is None:
            raise mapping.not_found("file_version", version_id)
        return mapping.file_version_from_row(row)

    def last_no(self, file_id: FileId) -> int:
        mapping.run(lambda: self._conn.execute(_FILE_LOCK_ONLY, (file_id,)).fetchone())
        row = mapping.run(lambda: self._conn.execute(_VERSION_LAST_NO, (file_id,)).fetchone())
        return 0 if row is None else cast("int", row[0])

    def add(self, version: FileVersion) -> None:
        v = version
        params = (
            v.id, v.workspace_id, v.file_id, v.version_no, v.blob_id, v.original_filename,
            v.declared_media_type, v.description, to_jsonb(mapping.source_to_json(v.source)),
            to_jsonb(mapping.safety_to_json(v.safety)), v.created_by, require_aware(v.created_at),
        )  # fmt: skip
        row = mapping.in_savepoint(
            self._conn, lambda: mapping.run(lambda: self._conn.execute(_VERSION_INSERT, params).fetchone())
        )
        if row is None:
            raise mapping.exists(
                "file_version", file_id=str(version.file_id), version_no=str(version.version_no)
            )

    def list(self, file_id: FileId, *, after: str | None, limit: int) -> Page[FileVersion]:
        limit = validate_page_limit(limit)
        digest = query_digest({"kind": "artifacts_file_versions", "file_id": str(file_id)})
        after_no = mapping.version_keyset(after, digest=digest)
        params = {"file": file_id, "after_no": after_no, "limit": limit + 1}
        rows = mapping.run(lambda: self._conn.execute(_VERSION_LIST, params).fetchall())
        return page_of(
            [mapping.file_version_from_row(row) for row in rows],
            limit=limit,
            digest=digest,
            key_of=lambda item: (item.version_no,),
        )

    def many(self, ids: Sequence[FileVersionId]) -> tuple[FileVersion, ...]:
        wanted = list(dict.fromkeys(ids))
        if not wanted:
            return ()
        rows = mapping.run(lambda: self._conn.execute(_VERSION_MANY, (wanted,)).fetchall())
        by_id = {version.id: version for version in (mapping.file_version_from_row(row) for row in rows)}
        return tuple(by_id[item] for item in wanted if item in by_id)
