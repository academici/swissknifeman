"""Append-only in-memory empirical signals, deduplicated by activity."""

from skm.adapters.memory.core.state import MemoryBackendState
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict
from skm.kernel.ids import ProjectId
from skm.kernel.pagination import Cursor, Page
from skm.modules.learning.domain.candidate import CandidateId, Signal

from .candidates import learning_state, page_rows, time_key
from .constraints import reference, signal_checks

__all__ = ["MemorySignalRepository"]


def _key(signal: Signal) -> tuple[str, str]:
    return time_key(signal.observed_at, signal.id)


class MemorySignalRepository:
    def __init__(self, state: MemoryBackendState) -> None:
        self._core = state.core
        self._tables = learning_state(state)

    def add(self, s: Signal) -> bool:
        self._core.require_writable()
        signal_checks(s)
        if any(
            (row.candidate_id, row.activity_record_id, row.source)
            == (s.candidate_id, s.activity_record_id, s.source)
            for row in self._tables.signals.values()
        ):
            return False
        if s.id in self._tables.signals:
            raise Conflict(ErrorCode.ALREADY_EXISTS, "Signal ID already exists")
        reference(s.candidate_id in self._tables.candidates, "candidate_id")
        reference(s.activity_record_id in self._tables.activities, "activity_record_id")
        self._tables.signals[s.id] = s
        return True

    def for_candidate(self, candidate_id: CandidateId) -> tuple[Signal, ...]:
        return tuple(
            sorted(
                (row for row in self._tables.signals.values() if row.candidate_id == candidate_id), key=_key
            )
        )

    def count_activities_for_project(self, project_id: ProjectId) -> int:
        return sum(row.project_id == project_id for row in self._tables.activities.values())

    def list(self, candidate_id: CandidateId, *, after: Cursor | None, limit: int) -> Page[Signal]:
        return page_rows(
            self.for_candidate(candidate_id),
            after=after,
            limit=limit,
            filters={"signals": str(candidate_id)},
            key_of=_key,
        )
