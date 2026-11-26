"""PostgreSQL activity receipts, scoped history and detector evidence."""

from collections import Counter
from datetime import datetime
from typing import Final

import psycopg
from psycopg.types.json import Jsonb

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound
from skm.kernel.ids import ProjectId, ScopeId, WorkspaceId
from skm.modules.learning.domain.activity import ActivityRecord, ActivityRecordId, detector_evidence_json
from skm.modules.learning.domain.pathology import PathologyCode

from .mapping import activity_from_row, rows, run

__all__ = ["PostgresActivityRecordRepository"]

_LOCK: Final = "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))"
_ADD: Final = """
INSERT INTO skm_learning.activity_records (
    id, workspace_id, project_id, scope_id, source_kind, source_key, run_id, task_id, attempt_id,
    outcome, task_outcome, exposure_coverage, exposed_lesson_refs, detector_evidence, pathology_codes,
    summary_digest, observed_at, created_at
) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
ON CONFLICT (workspace_id, source_key) DO NOTHING
"""
_GET: Final = "SELECT * FROM skm_learning.activity_records WHERE id = %s"
_SOURCE: Final = "SELECT id FROM skm_learning.activity_records WHERE workspace_id = %s AND source_key = %s"
_HISTORY: Final = """
SELECT * FROM skm_learning.activity_records
WHERE scope_id = %s AND (observed_at, id) <= (%s, %s)
ORDER BY observed_at DESC, id DESC LIMIT %s
"""
_COUNT: Final = "SELECT count(*) AS total FROM skm_learning.activity_records WHERE project_id = %s"
_RECENT: Final = """
SELECT * FROM skm_learning.activity_records WHERE project_id = %s
ORDER BY observed_at DESC, id DESC LIMIT %s
"""


class PostgresActivityRecordRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def lock_project(self, project_id: ProjectId) -> None:
        run(lambda: self._conn.execute(_LOCK, (f"learning:{project_id}",)))

    def add(self, record: ActivityRecord) -> bool:
        return run(
            lambda: (
                self._conn.execute(
                    _ADD,
                    (
                        record.id,
                        record.workspace_id,
                        record.project_id,
                        record.scope_id,
                        record.source_kind,
                        record.source_key,
                        record.run_id,
                        record.task_id,
                        record.attempt_id,
                        record.outcome,
                        record.task_outcome,
                        record.exposure_coverage,
                        Jsonb(
                            [
                                {
                                    "id": str(ref.id),
                                    "version": ref.version,
                                    "content_digest": ref.content_digest,
                                }
                                for ref in record.exposed_lesson_refs
                            ]
                        ),
                        Jsonb([detector_evidence_json(e) for e in record.detector_evidence]),
                        [code.value for code in record.pathology_codes],
                        record.summary_digest,
                        record.observed_at,
                    ),
                ).rowcount
                == 1
            )
        )

    def get(self, activity_id: ActivityRecordId) -> ActivityRecord:
        found = rows(lambda: self._conn.execute(_GET, (activity_id,)))
        if not found:
            raise NotFound(ErrorCode.NOT_FOUND, "Activity not found")
        return activity_from_row(found[0])

    def by_source(self, workspace_id: WorkspaceId, source_key: str) -> ActivityRecordId | None:
        found = rows(lambda: self._conn.execute(_SOURCE, (workspace_id, source_key)))
        return found[0]["id"] if found else None

    def exists(self, workspace_id: WorkspaceId, source_key: str) -> bool:
        return self.by_source(workspace_id, source_key) is not None

    def history_entries(
        self, scope_id: ScopeId, *, window: int, observed_at: datetime, activity_id: ActivityRecordId
    ) -> tuple[ActivityRecord, ...]:
        return tuple(
            activity_from_row(row)
            for row in rows(
                lambda: self._conn.execute(_HISTORY, (scope_id, observed_at, activity_id, window))
            )
        )

    def pathology_history(
        self, scope_id: ScopeId, *, window: int, including: ActivityRecordId
    ) -> dict[PathologyCode, int]:
        current = self.get(including)
        history = self.history_entries(
            scope_id, window=window, observed_at=current.observed_at, activity_id=including
        )
        return dict(Counter(code for row in history for code in set(row.pathology_codes)))

    def count_for_project(self, project_id: ProjectId) -> int:
        return int(rows(lambda: self._conn.execute(_COUNT, (project_id,)))[0]["total"])

    def recent_for_project(self, project_id: ProjectId, *, window: int) -> tuple[ActivityRecord, ...]:
        return tuple(
            activity_from_row(row) for row in rows(lambda: self._conn.execute(_RECENT, (project_id, window)))
        )

    def pathology_stats(self, project_id: ProjectId, *, window: int) -> dict[PathologyCode, int]:
        recent = self.recent_for_project(project_id, window=window)
        return dict(Counter(code for row in recent for code in set(row.pathology_codes)))
