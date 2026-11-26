"""PostgreSQL repositories for execution environments and sealed outputs (DDL ``0014``)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from skm.adapters.postgres.execution.codecs import environment_from_row, output_from_row
from skm.adapters.postgres.execution.mapping import opt_aware, run
from skm.adapters.postgres.jsonb import require_aware, to_jsonb
from skm.kernel.ids import AttemptId, HostId, ProjectId, RepositoryId
from skm.modules.execution.domain.environment import (
    EnvironmentKind,
    EnvironmentState,
    ExecutionEnvironment,
)
from skm.modules.execution.domain.ids import EnvironmentId, OutputId
from skm.modules.execution.domain.output import Output, manifest_to_json
from skm.modules.execution.domain.stored_payloads import (
    invalid_ref,
    invalid_transition,
    not_found,
    schema_invalid,
)

if TYPE_CHECKING:
    from skm.modules.execution.domain.contracts import RetainPolicy

__all__ = [
    "PostgresEnvironmentRepository",
    "PostgresOutputRepository",
]


class PostgresEnvironmentRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def upsert(self, env: ExecutionEnvironment) -> None:
        if (env.state in {EnvironmentState.DISCARDED, EnvironmentState.REMOVED}) != (
            env.discarded_at is not None
        ):
            raise schema_invalid("discarded_at is set iff state is discarded or removed")
        base_doc = [
            {
                "mount": b.mount,
                "repository_id": str(b.repository_id),
                "commit_sha": b.commit_sha,
                "source_head_sha": b.source_head_sha,
                "dirty_patch_file_version_id": (
                    None if b.dirty_patch_file_version_id is None else str(b.dirty_patch_file_version_id)
                ),
            }
            for b in env.baseline
        ]
        dirty_fv = next(
            (UUID(str(b.dirty_patch_file_version_id)) for b in env.baseline if b.dirty_patch_file_version_id),
            None,
        )

        def _ups() -> None:
            with self._conn.cursor() as cur:
                cur.execute(
                    "SELECT workspace_id FROM skm_execution.attempts WHERE id = %s",
                    (UUID(str(env.attempt_id)),),
                )
                arow = cur.fetchone()
                if arow is None:
                    raise invalid_ref("fk_execution_environments__attempts", attempt_id=str(env.attempt_id))
                cur.execute(
                    """
                    INSERT INTO skm_execution.execution_environments (
                        id, attempt_id, workspace_id, host_id, kind, baseline,
                        dirty_patch_file_version_id, branch, local_locator, state,
                        created_at, discarded_at, removed_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE
                       SET state = EXCLUDED.state,
                           local_locator = EXCLUDED.local_locator,
                           discarded_at = EXCLUDED.discarded_at,
                           removed_at = EXCLUDED.removed_at
                    """,
                    (
                        UUID(str(env.id)),
                        UUID(str(env.attempt_id)),
                        arow[0],
                        UUID(str(env.host_id)),
                        env.kind.value,
                        to_jsonb(base_doc),
                        dirty_fv if env.kind is EnvironmentKind.EXISTING_CHECKOUT else None,
                        env.branch,
                        env.local_locator,
                        env.state.value,
                        require_aware(env.created_at),
                        opt_aware(env.discarded_at),
                        opt_aware(env.removed_at),
                    ),
                )

        run(_ups)

    def for_attempt(self, attempt_id: AttemptId) -> ExecutionEnvironment | None:
        def _q() -> ExecutionEnvironment | None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT * FROM skm_execution.execution_environments WHERE attempt_id = %s",
                    (UUID(str(attempt_id)),),
                )
                row = cur.fetchone()
            return None if row is None else environment_from_row(row)

        return run(_q)

    def removable(
        self, host_id: HostId, retain: RetainPolicy, now: datetime, *, limit: int
    ) -> tuple[ExecutionEnvironment, ...]:
        ttl_raw = retain.get("retain_seconds", 0)
        ttl_sec = int(ttl_raw) if isinstance(ttl_raw, int | float) and not isinstance(ttl_raw, bool) else 0
        cutoff = require_aware(now - timedelta(seconds=max(0, ttl_sec)))

        def _q() -> tuple[ExecutionEnvironment, ...]:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT * FROM skm_execution.execution_environments
                     WHERE host_id = %s
                       AND state = 'discarded'
                       AND COALESCE(discarded_at, created_at) <= %s
                     ORDER BY COALESCE(discarded_at, created_at) ASC, id ASC
                     LIMIT %s
                    """,
                    (UUID(str(host_id)), cutoff, max(0, limit)),
                )
                return tuple(environment_from_row(r) for r in cur.fetchall())

        return run(_q)

    def mark_removed(self, environment_ids: Sequence[EnvironmentId], host_id: HostId, at: datetime) -> int:
        if not environment_ids:
            return 0
        at_aw = require_aware(at)
        ids_arr = [UUID(str(eid)) for eid in environment_ids]

        def _upd() -> int:
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE skm_execution.execution_environments
                       SET state = 'removed',
                           discarded_at = COALESCE(discarded_at, %s),
                           removed_at = %s
                     WHERE id = ANY(%s::uuid[])
                       AND host_id = %s
                       AND state <> 'removed'
                    """,
                    (at_aw, at_aw, ids_arr, UUID(str(host_id))),
                )
                return cur.rowcount

        return run(_upd)

    def busy_existing_checkout_repos(
        self, project_id: ProjectId, *, exclude_attempt_id: AttemptId | None = None
    ) -> frozenset[RepositoryId]:
        def _q() -> frozenset[RepositoryId]:
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT ee.baseline
                      FROM skm_execution.execution_environments ee
                      JOIN skm_execution.attempts att ON att.id = ee.attempt_id
                      JOIN skm_execution.runs r ON r.id = att.run_id
                     WHERE r.project_id = %s
                       AND ee.kind = 'existing_checkout'
                       AND ee.state IN ('preparing', 'ready')
                       AND ee.attempt_id <> ALL(%s::uuid[])
                    """,
                    (UUID(str(project_id)), [] if exclude_attempt_id is None else [exclude_attempt_id]),
                )
                out: set[RepositoryId] = set()
                for (baseline,) in cur.fetchall():
                    for b in baseline or ():
                        out.add(RepositoryId(UUID(str(b["repository_id"]))))
                return frozenset(out)

        return run(_q)


class PostgresOutputRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def add(self, output: Output) -> None:
        m_doc = manifest_to_json(output.manifest)

        def _ins() -> None:
            with self._conn.cursor() as cur:
                cur.execute(
                    "SELECT workspace_id, state FROM skm_execution.attempts WHERE id = %s",
                    (UUID(str(output.attempt_id)),),
                )
                arow = cur.fetchone()
                if arow is None:
                    raise invalid_ref("fk_attempt_outputs__attempts", attempt_id=str(output.attempt_id))
                ws_id, att_state = arow
                if att_state in {"completed", "ownership_lost", "abandoned"}:
                    raise invalid_transition(
                        "terminal attempt cannot seal outputs", attempt_id=str(output.attempt_id)
                    )
                cur.execute(
                    """
                    INSERT INTO skm_execution.attempt_outputs (
                        id, attempt_id, task_id, run_id, workspace_id, seq, source,
                        manifest, manifest_digest, tree_digest,
                        outside_write_scope, excluded_paths,
                        produced_by_step_id, patch_file_version_id, sealed_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        UUID(str(output.id)),
                        UUID(str(output.attempt_id)),
                        UUID(str(output.task_id)),
                        UUID(str(output.run_id)),
                        ws_id,
                        output.seq,
                        output.source.value,
                        to_jsonb(m_doc),
                        output.manifest_digest,
                        output.manifest.tree_digest,
                        to_jsonb(m_doc["outside_write_scope"]),
                        to_jsonb(m_doc["excluded_paths"]),
                        None if output.produced_by_step_id is None else UUID(str(output.produced_by_step_id)),
                        (
                            None
                            if output.manifest.patch_file_version_id is None
                            else UUID(str(output.manifest.patch_file_version_id))
                        ),
                        require_aware(output.sealed_at),
                    ),
                )

        run(_ins)

    def get(self, output_id: OutputId) -> Output:
        def _q() -> Output:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT * FROM skm_execution.attempt_outputs WHERE id = %s",
                    (UUID(str(output_id)),),
                )
                row = cur.fetchone()
            if row is None:
                raise not_found("output", output_id)
            return output_from_row(row)

        return run(_q)

    def latest(self, attempt_id: AttemptId) -> Output | None:
        def _q() -> Output | None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT * FROM skm_execution.attempt_outputs
                     WHERE attempt_id = %s
                     ORDER BY seq DESC
                     LIMIT 1
                    """,
                    (UUID(str(attempt_id)),),
                )
                row = cur.fetchone()
            return None if row is None else output_from_row(row)

        return run(_q)
