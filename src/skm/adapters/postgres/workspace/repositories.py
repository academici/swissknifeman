"""PostgreSQL ``RepositoryRepository`` (workspace §6, §11; DDL ``0007``): repositories, remotes, matching.

Repositories. ``(workspace_id, canonical_remote)`` is unique and ``(workspace_id, id)`` is the target of the
composite FKs of remotes, mounts and bindings. ``add`` runs ``ON CONFLICT DO NOTHING``; ``save`` locks the
row, compares ``row_version`` and never moves a repository to another workspace (``ValueError``).

Remotes. ``replace_remotes`` makes the stored remotes exactly the given ones: a remote that belongs to another
repository of the workspace is ``ALREADY_EXISTS`` (``uq_repository_remotes__workspace_id_normalized_url``), a
duplicate or a second primary is ``SCHEMA_INVALID``, as in the memory adapter. The rows are rewritten in one
transaction so the one-primary index never sees two primaries. Remotes keep the order the domain gave them:
``added_at`` of a kept remote is kept, a new one gets the clock time, strictly after the remote before it.

``match_remotes`` is the query of workspace §11: the repositories of the workspace owning one of the remotes,
the remotes that matched (in stored order) and the projects each repository is mounted in. Pages ascend by
``(created_at, id)``, filtered in SQL by workspace and the lower-case hex ``id_prefix``.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Final, cast
from uuid import UUID

import psycopg

from skm.adapters.postgres.pagination import page_of, query_digest
from skm.adapters.postgres.workspace.mapping import (
    STEP,
    Row,
    damaged,
    ensure_kept,
    keyset,
    not_found,
    run,
    time_key,
    version_conflict,
)
from skm.kernel.clock import Clock
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, ValidationFailed
from skm.kernel.ids import ProjectId, RepositoryId, WorkspaceId
from skm.kernel.pagination import Page, validate_page_limit
from skm.modules.workspace.domain.attach import RepositoryMatchView
from skm.modules.workspace.domain.remote_url import NormalizedRemote, RepositoryProvider
from skm.modules.workspace.domain.repository import Repository, RepositoryRemote
from skm.platform.system_clock import SystemClock

__all__ = ["PostgresRepositoryRepository"]

_COLUMNS: Final = (
    "SELECT id, workspace_id, title, canonical_remote, provider, external_id, row_version, created_at "
    "FROM skm_workspace.repositories "
)
_GET: Final = _COLUMNS + "WHERE id = %s"
_LOCKED: Final = _GET + " FOR UPDATE"
_INSERT: Final = """
INSERT INTO skm_workspace.repositories
    (id, workspace_id, title, canonical_remote, provider, external_id, row_version, created_at, updated_at)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT DO NOTHING RETURNING id
"""
_UPDATE: Final = """
UPDATE skm_workspace.repositories
   SET title = %s, canonical_remote = %s, provider = %s, external_id = %s, row_version = %s,
       updated_at = greatest(updated_at, %s)
 WHERE id = %s AND row_version = %s
"""
_LIST: Final = (
    _COLUMNS
    + """
 WHERE workspace_id = %(workspace)s
   AND (%(prefix)s::text IS NULL
        OR left(replace(id::text, '-', ''), length(%(prefix)s::text)) = %(prefix)s::text)
   AND (%(at)s::timestamptz IS NULL OR (created_at, id) > (%(at)s::timestamptz, %(id)s::uuid))
 ORDER BY created_at, id
 LIMIT %(limit)s
"""
)
_REMOTES: Final = """
SELECT repository_id, normalized_url, display_url, is_primary, added_at
  FROM skm_workspace.repository_remotes
 WHERE repository_id = %s
 ORDER BY added_at, normalized_url COLLATE "C"
"""
_OWNED_ELSEWHERE: Final = """
SELECT repository_id FROM skm_workspace.repository_remotes
 WHERE workspace_id = %s AND normalized_url = ANY(%s) AND repository_id <> %s
 ORDER BY normalized_url COLLATE "C"
 LIMIT 1
"""
_REMOTES_DELETE: Final = "DELETE FROM skm_workspace.repository_remotes WHERE repository_id = %s"
_REMOTE_INSERT: Final = """
INSERT INTO skm_workspace.repository_remotes
    (workspace_id, repository_id, normalized_url, display_url, is_primary, added_at)
VALUES (%s, %s, %s, %s, %s, %s)
"""
_MATCH: Final = """
SELECT r.id, r.title,
       ARRAY(SELECT rr.normalized_url FROM skm_workspace.repository_remotes rr
              WHERE rr.repository_id = r.id AND rr.normalized_url = ANY(%(remotes)s)
              ORDER BY rr.added_at, rr.normalized_url COLLATE "C") AS matched,
       ARRAY(SELECT DISTINCT m.project_id FROM skm_workspace.project_repositories m
              WHERE m.workspace_id = r.workspace_id AND m.repository_id = r.id
              ORDER BY m.project_id) AS projects
  FROM skm_workspace.repositories r
 WHERE r.workspace_id = %(workspace)s
   AND EXISTS (SELECT 1 FROM skm_workspace.repository_remotes rr
                WHERE rr.workspace_id = r.workspace_id AND rr.repository_id = r.id
                  AND rr.normalized_url = ANY(%(remotes)s))
 ORDER BY r.id
"""


def _repository(row: Row) -> Repository:
    try:
        return Repository(
            id=RepositoryId(cast("UUID", row[0])),
            workspace_id=WorkspaceId(cast("UUID", row[1])),
            title=cast("str", row[2]),
            canonical_remote=None if row[3] is None else NormalizedRemote(cast("str", row[3])),
            provider=RepositoryProvider(cast("str", row[4])),
            external_id=cast("str | None", row[5]),
            row_version=cast("int", row[6]),
            created_at=cast("datetime", row[7]),
        )
    except (TypeError, ValueError, ValidationFailed) as exc:
        raise damaged("repositories", row[0], exc) from exc


def _remote(row: Row) -> tuple[RepositoryRemote, datetime]:
    try:
        remote = RepositoryRemote(
            repository_id=RepositoryId(cast("UUID", row[0])),
            normalized=NormalizedRemote(cast("str", row[1])),
            display_url=cast("str", row[2]),
            is_primary=cast("bool", row[3]),
        )
    except (TypeError, ValueError, ValidationFailed) as exc:
        raise damaged("repository_remotes", f"{row[0]}/{row[1]}", exc) from exc
    return remote, cast("datetime", row[4])


def _match(row: Row) -> RepositoryMatchView:
    try:
        return RepositoryMatchView(
            RepositoryId(cast("UUID", row[0])),
            cast("str", row[1]),
            tuple(NormalizedRemote(text) for text in cast("list[str]", row[2])),
            tuple(ProjectId(item) for item in cast("list[UUID]", row[3])),
        )
    except (TypeError, ValueError, ValidationFailed) as exc:
        raise damaged("repository_remotes", row[0], exc) from exc


def _canonical(repository: Repository) -> str | None:
    return None if repository.canonical_remote is None else repository.canonical_remote.value


class PostgresRepositoryRepository:
    def __init__(self, conn: psycopg.Connection, *, clock: Clock | None = None) -> None:
        self._conn = conn
        self._clock: Clock = clock if clock is not None else SystemClock()

    def get(self, repository_id: RepositoryId) -> Repository:
        row = run(lambda: self._conn.execute(_GET, (repository_id,)).fetchone())
        if row is None:
            raise not_found("repository", repository_id)
        return _repository(row)

    def add(self, repository: Repository) -> None:
        params = (
            repository.id,
            repository.workspace_id,
            repository.title,
            _canonical(repository),
            RepositoryProvider(repository.provider).value,
            repository.external_id,
            repository.row_version,
            repository.created_at,
            repository.created_at,
        )
        if run(lambda: self._conn.execute(_INSERT, params).fetchone()) is None:
            raise Conflict(
                ErrorCode.ALREADY_EXISTS,
                "repository already exists",
                details={"kind": "repository", "repository_id": str(repository.id)},
            )

    def save(self, repository: Repository, *, expected_version: int) -> None:
        row = run(lambda: self._conn.execute(_LOCKED, (repository.id,)).fetchone())
        if row is None:
            raise not_found("repository", repository.id)
        current = _repository(row)
        if current.row_version != expected_version:
            raise version_conflict("repository", expected_version, current.row_version)
        ensure_kept("repository", current, repository, ("workspace_id", "created_at"))
        params = (
            repository.title,
            _canonical(repository),
            RepositoryProvider(repository.provider).value,
            repository.external_id,
            repository.row_version,
            self._clock.now(),
            repository.id,
            expected_version,
        )
        run(lambda: self._conn.execute(_UPDATE, params))

    def _stored_remotes(self, repository_id: RepositoryId) -> list[tuple[RepositoryRemote, datetime]]:
        rows = run(lambda: self._conn.execute(_REMOTES, (repository_id,)).fetchall())
        return [_remote(row) for row in rows]

    def remotes(self, repository_id: RepositoryId) -> tuple[RepositoryRemote, ...]:
        self.get(repository_id)
        return tuple(item for item, _ in self._stored_remotes(repository_id))

    def replace_remotes(self, repository_id: RepositoryId, remotes: Sequence[RepositoryRemote]) -> None:
        """The remotes of the repository become exactly ``remotes``, in that order."""
        repository = self.get(repository_id)
        wanted = [item.normalized.value for item in remotes]
        if len(set(wanted)) != len(wanted) or sum(1 for item in remotes if item.is_primary) > 1:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID, "duplicate or several primary remotes", details={"field": "remotes"}
            )
        if any(item.repository_id != repository_id for item in remotes):
            raise ValueError("every remote must belong to the repository it is stored for")
        if wanted:
            taken = run(
                lambda: self._conn.execute(
                    _OWNED_ELSEWHERE, (repository.workspace_id, wanted, repository_id)
                ).fetchone()
            )
            if taken is not None:
                raise Conflict(
                    ErrorCode.ALREADY_EXISTS,
                    "the remote belongs to another repository of the workspace",
                    details={"kind": "remote", "repository_id": str(cast("UUID", taken[0]))},
                )
        kept = {item.normalized.value: added for item, added in self._stored_remotes(repository_id)}
        now = self._clock.now()
        rows: list[tuple[object, ...]] = []
        previous: datetime | None = None
        for item in remotes:
            added = kept.get(item.normalized.value)
            if added is None or (previous is not None and added <= previous):
                added = now if previous is None or now > previous else previous + STEP
            previous = added
            rows.append(
                (
                    repository.workspace_id,
                    repository_id,
                    item.normalized.value,
                    item.display_url,
                    item.is_primary,
                    added,
                )
            )

        def rewrite() -> None:
            with self._conn.cursor() as cur:
                cur.execute(_REMOTES_DELETE, (repository_id,))
                if rows:
                    cur.executemany(_REMOTE_INSERT, rows)

        run(rewrite)

    def match_remotes(
        self, workspace_id: WorkspaceId, remotes: Sequence[NormalizedRemote]
    ) -> tuple[RepositoryMatchView, ...]:
        wanted = sorted({item.value for item in remotes})
        if not wanted:
            return ()
        params = {"workspace": workspace_id, "remotes": wanted}
        rows = run(lambda: self._conn.execute(_MATCH, params).fetchall())
        return tuple(_match(row) for row in rows)

    def list(
        self, workspace_id: WorkspaceId, *, id_prefix: str | None, after: str | None, limit: int
    ) -> Page[Repository]:
        limit = validate_page_limit(limit)
        digest = query_digest(
            {"kind": "workspace_repositories", "workspace_id": str(workspace_id), "id_prefix": id_prefix}
        )
        at, start = keyset(after, digest, time_key)
        params = {"workspace": workspace_id, "prefix": id_prefix, "at": at, "id": start, "limit": limit + 1}
        rows = run(lambda: self._conn.execute(_LIST, params).fetchall())
        return page_of(
            [_repository(row) for row in rows],
            limit=limit,
            digest=digest,
            key_of=lambda item: (item.created_at.isoformat(), str(item.id)),
        )
