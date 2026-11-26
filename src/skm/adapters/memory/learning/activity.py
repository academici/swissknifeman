"""Transactional activity receipts and retained detector evidence."""

from collections import Counter
from copy import deepcopy
from datetime import datetime

from skm.adapters.memory.core.state import MemoryBackendState
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, NotFound
from skm.kernel.ids import ProjectId, ScopeId, WorkspaceId
from skm.modules.learning.domain.activity import ActivityRecord, ActivityRecordId
from skm.modules.learning.domain.pathology import PathologyCode

from .candidates import learning_state
from .constraints import activity_checks, project_scope

__all__ = ["MemoryActivityRecordRepository"]


class MemoryActivityRecordRepository:
    def __init__(self, state: MemoryBackendState) -> None:
        self._state = state
        self._rows = learning_state(state).activities

    def lock_project(self, project_id: ProjectId) -> None:  # noqa: ARG002 - memory serializes writers
        self._state.core.require_writable()

    def add(self, record: ActivityRecord) -> bool:
        self._state.core.require_writable()
        activity_checks(record)
        if self.exists(record.workspace_id, record.source_key):
            return False
        if record.id in self._rows:
            raise Conflict(ErrorCode.ALREADY_EXISTS, "Activity ID already exists")
        project_scope(self._state, record)
        self._rows[record.id] = deepcopy(record)
        return True

    def get(self, activity_id: ActivityRecordId) -> ActivityRecord:
        row = self._rows.get(activity_id)
        if row is None:
            raise NotFound(ErrorCode.NOT_FOUND, "Activity not found")
        return deepcopy(row)

    def by_source(self, workspace_id: WorkspaceId, source_key: str) -> ActivityRecordId | None:
        return next(
            (
                r.id
                for r in self._rows.values()
                if (r.workspace_id, r.source_key) == (workspace_id, source_key)
            ),
            None,
        )

    def exists(self, workspace_id: WorkspaceId, source_key: str) -> bool:
        return self.by_source(workspace_id, source_key) is not None

    def history_entries(
        self, scope_id: ScopeId, *, window: int, observed_at: datetime, activity_id: ActivityRecordId
    ) -> tuple[ActivityRecord, ...]:
        rows = sorted(
            (
                r
                for r in self._rows.values()
                if r.scope_id == scope_id and (r.observed_at, r.id) <= (observed_at, activity_id)
            ),
            key=lambda row: (row.observed_at, row.id),
            reverse=True,
        )
        return tuple(deepcopy(rows[:window]))

    def pathology_history(
        self, scope_id: ScopeId, *, window: int, including: ActivityRecordId
    ) -> dict[PathologyCode, int]:
        current = self.get(including)
        rows = self.history_entries(
            scope_id, window=window, observed_at=current.observed_at, activity_id=including
        )
        return dict(Counter(code for row in rows for code in set(row.pathology_codes)))

    def count_for_project(self, project_id: ProjectId) -> int:
        return sum(r.project_id == project_id for r in self._rows.values())

    def recent_for_project(self, project_id: ProjectId, *, window: int) -> tuple[ActivityRecord, ...]:
        rows = sorted(
            (r for r in self._rows.values() if r.project_id == project_id),
            key=lambda row: (row.observed_at, row.id),
            reverse=True,
        )
        return tuple(deepcopy(rows[:window]))

    def pathology_stats(self, project_id: ProjectId, *, window: int) -> dict[PathologyCode, int]:
        rows = self.recent_for_project(project_id, window=window)
        return dict(Counter(code for row in rows for code in set(row.pathology_codes)))
