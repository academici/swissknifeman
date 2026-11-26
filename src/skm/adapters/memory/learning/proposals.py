"""Append-only in-memory proposal snapshots."""

from skm.adapters.memory.core.state import MemoryBackendState
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, NotFound
from skm.kernel.pagination import Cursor, Page
from skm.modules.learning.domain.candidate import CandidateId
from skm.modules.learning.domain.review import CandidateProposal, CandidateProposalId

from .candidates import learning_state, page_rows, time_key
from .constraints import proposal_checks, reference

__all__ = ["MemoryCandidateProposalRepository"]


class MemoryCandidateProposalRepository:
    def __init__(self, state: MemoryBackendState) -> None:
        self._core = state.core
        self._tables = learning_state(state)
        self._rows = self._tables.proposals

    def add(self, p: CandidateProposal) -> bool:
        self._core.require_writable()
        proposal_checks(p)
        if any(
            (row.candidate_id, row.source_activity_id, row.fingerprint)
            == (p.candidate_id, p.source_activity_id, p.fingerprint)
            for row in self._rows.values()
        ):
            return False
        if p.id in self._rows:
            raise Conflict(ErrorCode.ALREADY_EXISTS, "Candidate proposal ID already exists")
        for candidate_id in (p.candidate_id, p.source_candidate_id):
            candidate = self._tables.candidates.get(candidate_id)
            reference(candidate is not None and p.scope_id == candidate.scope_id, "candidate_id")
        reference(p.source_activity_id in self._tables.activities, "source_activity_id")
        self._rows[p.id] = p
        return True

    def get(self, proposal_id: CandidateProposalId) -> CandidateProposal:
        row = self._rows.get(proposal_id)
        if row is None:
            raise NotFound(ErrorCode.NOT_FOUND, "Candidate proposal not found")
        return row

    def list(self, candidate_id: CandidateId, *, after: Cursor | None, limit: int) -> Page[CandidateProposal]:
        return page_rows(
            (row for row in self._rows.values() if row.candidate_id == candidate_id),
            after=after,
            limit=limit,
            filters={"proposals": str(candidate_id)},
            key_of=lambda row: time_key(row.observed_at, row.id),
        )
