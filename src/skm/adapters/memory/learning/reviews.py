"""Append-only in-memory reviews."""

from skm.adapters.memory.access.state import access_state
from skm.adapters.memory.core.state import MemoryBackendState
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict
from skm.modules.learning.domain.candidate import CandidateId
from skm.modules.learning.domain.review import CandidateReview

from .candidates import learning_state
from .constraints import reference, review_checks

__all__ = ["MemoryCandidateReviewRepository"]


class MemoryCandidateReviewRepository:
    def __init__(self, state: MemoryBackendState) -> None:
        self._core = state.core
        self._state = state
        self._tables = learning_state(state)
        self._rows = self._tables.reviews

    def add(self, r: CandidateReview) -> None:
        self._core.require_writable()
        review_checks(r)
        if r.id in self._rows:
            raise Conflict(ErrorCode.ALREADY_EXISTS, "Candidate review already exists")
        reference(r.candidate_id in self._tables.candidates, "candidate_id")
        reference(r.proposal_id is None or r.proposal_id in self._tables.proposals, "proposal_id")
        reference(r.reviewer_id in access_state(self._state).principals, "reviewer_id")
        self._rows[r.id] = r

    def for_proposals(self, candidate_id: CandidateId) -> tuple[CandidateReview, ...]:
        ids = {p.id for p in self._tables.proposals.values() if p.candidate_id == candidate_id}
        return tuple(r for r in self._rows.values() if r.proposal_id in ids)

    def for_candidate(self, candidate_id: CandidateId) -> tuple[CandidateReview, ...]:
        return tuple(
            sorted(
                (row for row in self._rows.values() if row.candidate_id == candidate_id),
                key=lambda row: (row.created_at, row.id),
            )
        )
