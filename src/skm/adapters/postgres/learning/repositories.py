"""Append-only PostgreSQL learning signals, proposal snapshots and reviews."""

from dataclasses import astuple
from typing import Final

import psycopg

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound
from skm.kernel.ids import ProjectId
from skm.kernel.pagination import Cursor, Page
from skm.modules.knowledge.ports import page_of
from skm.modules.knowledge.public import LessonKind
from skm.modules.learning.domain.candidate import CandidateId, Signal
from skm.modules.learning.domain.review import CandidateProposal, CandidateProposalId, CandidateReview

from .activity import PostgresActivityRecordRepository
from .mapping import Row, paging, review_from_row, rows, run

__all__ = [
    "PostgresActivityRecordRepository",
    "PostgresCandidateProposalRepository",
    "PostgresCandidateReviewRepository",
    "PostgresSignalRepository",
]

_SIGNAL_ADD: Final = """
INSERT INTO skm_learning.signals (
  id, candidate_id, activity_record_id, source, sessions_total, sessions_known, sessions_success,
  evidence_dependency, tests_total, tests_passed, observed_at, created_at
) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
ON CONFLICT (candidate_id, activity_record_id, source) DO NOTHING
"""
_SIGNALS: Final = """
SELECT id, candidate_id, activity_record_id, source, sessions_total, sessions_known, sessions_success,
       evidence_dependency, tests_total, tests_passed, observed_at
FROM skm_learning.signals WHERE candidate_id = %s
"""
_SIGNALS_ALL: Final = _SIGNALS + " ORDER BY observed_at, id"
_SIGNALS_PAGE: Final = (
    _SIGNALS
    + """
AND (%s::timestamptz IS NULL OR (observed_at, id) < (%s, %s))
ORDER BY observed_at DESC, id DESC LIMIT %s
"""
)
_PROPOSAL_ADD: Final = """
INSERT INTO skm_learning.candidate_proposals (
  id, scope_id, candidate_id, source_candidate_id, source_activity_id, source_key, observed_at, received_at,
  kind, trigger, action, fingerprint, detector_version, relation
) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
ON CONFLICT (candidate_id, source_activity_id, fingerprint) DO NOTHING
"""
_PROPOSAL_GET: Final = "SELECT * FROM skm_learning.candidate_proposals WHERE id = %s"
_PROPOSALS_ALL: Final = "SELECT * FROM skm_learning.candidate_proposals WHERE candidate_id = %s"
_PROPOSALS_PAGE: Final = (
    _PROPOSALS_ALL
    + """
AND (%s::timestamptz IS NULL OR (observed_at, id) < (%s, %s))
ORDER BY observed_at DESC, id DESC LIMIT %s
"""
)
_REVIEW_ADD: Final = """
INSERT INTO skm_learning.candidate_reviews (
  id, candidate_id, reviewer_id, reviewer_kind, verdict, note, edited_trigger, edited_action,
  edited_kind, proposal_id, created_at
) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
"""
_REVIEWS: Final = """
SELECT * FROM skm_learning.candidate_reviews WHERE candidate_id = %s ORDER BY created_at, id
"""
_PROPOSAL_REVIEWS: Final = """
SELECT r.* FROM skm_learning.candidate_reviews r
JOIN skm_learning.candidate_proposals p ON p.id = r.proposal_id
WHERE p.candidate_id = %s ORDER BY r.created_at, r.id
"""


class PostgresSignalRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def add(self, s: Signal) -> bool:
        return run(lambda: self._conn.execute(_SIGNAL_ADD, astuple(s)).rowcount == 1)

    def for_candidate(self, candidate_id: CandidateId) -> tuple[Signal, ...]:
        return tuple(Signal(**row) for row in rows(lambda: self._conn.execute(_SIGNALS_ALL, (candidate_id,))))

    def count_activities_for_project(self, project_id: ProjectId) -> int:
        return PostgresActivityRecordRepository(self._conn).count_for_project(project_id)

    def list(self, candidate_id: CandidateId, *, after: Cursor | None, limit: int) -> Page[Signal]:
        key, when, row_id = paging(after, limit, {"signals": str(candidate_id)})
        found = rows(lambda: self._conn.execute(_SIGNALS_PAGE, (candidate_id, when, when, row_id, limit + 1)))
        return page_of([Signal(**row) for row in found], limit, key, lambda s: (s.observed_at, s.id))


def _proposal(row: Row) -> CandidateProposal:
    values = {**row}
    values["kind"] = LessonKind(row["kind"])
    return CandidateProposal(**values)


class PostgresCandidateProposalRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def add(self, p: CandidateProposal) -> bool:
        return run(lambda: self._conn.execute(_PROPOSAL_ADD, astuple(p)).rowcount == 1)

    def get(self, proposal_id: CandidateProposalId) -> CandidateProposal:
        found = rows(lambda: self._conn.execute(_PROPOSAL_GET, (proposal_id,)))
        if not found:
            raise NotFound(ErrorCode.NOT_FOUND, "Candidate proposal not found")
        return _proposal(found[0])

    def for_candidate(self, candidate_id: CandidateId) -> tuple[CandidateProposal, ...]:
        return tuple(
            _proposal(row) for row in rows(lambda: self._conn.execute(_PROPOSALS_ALL, (candidate_id,)))
        )

    def list(self, candidate_id: CandidateId, *, after: Cursor | None, limit: int) -> Page[CandidateProposal]:
        key, when, row_id = paging(after, limit, {"proposals": str(candidate_id)})
        found = rows(
            lambda: self._conn.execute(_PROPOSALS_PAGE, (candidate_id, when, when, row_id, limit + 1))
        )
        return page_of([_proposal(row) for row in found], limit, key, lambda p: (p.observed_at, p.id))


class PostgresCandidateReviewRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def add(self, r: CandidateReview) -> None:
        run(lambda: self._conn.execute(_REVIEW_ADD, astuple(r)))

    def for_candidate(self, candidate_id: CandidateId) -> tuple[CandidateReview, ...]:
        return tuple(
            review_from_row(row) for row in rows(lambda: self._conn.execute(_REVIEWS, (candidate_id,)))
        )

    def for_proposals(self, candidate_id: CandidateId) -> tuple[CandidateReview, ...]:
        return tuple(
            review_from_row(row)
            for row in rows(lambda: self._conn.execute(_PROPOSAL_REVIEWS, (candidate_id,)))
        )
