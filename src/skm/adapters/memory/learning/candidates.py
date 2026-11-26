"""Transactional in-memory candidates and their pending proposal projection."""

from collections.abc import Callable, Iterable
from copy import deepcopy
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from hashlib import sha256
from json import dumps
from uuid import UUID

from skm.adapters.memory.core.state import MemoryBackendState
from skm.adapters.memory.knowledge.mapping import knowledge_state
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, InternalError, NotFound, ValidationFailed
from skm.kernel.ids import ProjectId, ScopeId, WorkspaceId
from skm.kernel.pagination import Cursor, Page, validate_cursor, validate_page_limit
from skm.modules.learning.domain.activity import ActivityRecord, ActivityRecordId
from skm.modules.learning.domain.candidate import Candidate, CandidateId, CandidateState, Signal, SignalId
from skm.modules.learning.domain.contracts import CandidateProposalView, CandidateRef
from skm.modules.learning.domain.review import (
    CandidateProposal,
    CandidateProposalId,
    CandidateReview,
    CandidateReviewId,
    proposed_update,
    review_status,
)

from .constraints import candidate_checks, project_scope, reference

__all__ = ["MemoryCandidateRepository"]


@dataclass
class _LearningState:
    candidates: dict[CandidateId, Candidate] = field(default_factory=dict[CandidateId, Candidate])
    activities: dict[ActivityRecordId, ActivityRecord] = field(
        default_factory=dict[ActivityRecordId, ActivityRecord]
    )
    updates: dict[CandidateId, datetime] = field(default_factory=dict[CandidateId, datetime])
    signals: dict[SignalId, Signal] = field(default_factory=dict[SignalId, Signal])
    reviews: dict[CandidateReviewId, CandidateReview] = field(
        default_factory=dict[CandidateReviewId, CandidateReview]
    )
    proposals: dict[CandidateProposalId, CandidateProposal] = field(
        default_factory=dict[CandidateProposalId, CandidateProposal]
    )


def learning_state(state: MemoryBackendState) -> _LearningState:
    found = state.modules.get("learning")
    if found is None:
        found = _LearningState()
        state.modules["learning"] = found
    if not isinstance(found, _LearningState):
        raise InternalError(ErrorCode.INTERNAL_ERROR, "Invalid learning backend state")
    return found


def page_rows[T](
    rows: Iterable[T],
    *,
    after: Cursor | None,
    limit: int,
    filters: dict[str, object],
    key_of: Callable[[T], tuple[str, str]],
) -> Page[T]:
    try:
        limit = validate_page_limit(limit, maximum=200)
    except (ValueError, TypeError) as exc:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Invalid learning page limit") from exc
    digest = sha256(dumps(filters, sort_keys=True).encode()).hexdigest()[:16]
    ordered = sorted(rows, key=key_of, reverse=True)
    if after is not None:
        try:
            cursor_digest, when, row_id = validate_cursor(after).split("|")
            if cursor_digest != digest or (when, row_id) != time_key(
                datetime.fromisoformat(when), UUID(row_id)
            ):
                raise ValueError("invalid cursor key or filters")
        except (ValueError, TypeError) as exc:
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Invalid learning page cursor") from exc
        start = (when, row_id)
        ordered = [row for row in ordered if key_of(row) < start]
    items = tuple(ordered[:limit])
    following = Cursor("|".join((digest, *key_of(items[-1])))) if len(ordered) > limit else None
    return Page(items, following)


def time_key(when: datetime, row_id: UUID) -> tuple[str, str]:
    return when.astimezone(UTC).isoformat(timespec="microseconds"), str(row_id)


def _proposal_view(proposal: CandidateProposal) -> CandidateProposalView:
    return {
        "id": str(proposal.id),
        "scope_id": str(proposal.scope_id),
        "candidate_id": str(proposal.candidate_id),
        "source_candidate_id": str(proposal.source_candidate_id),
        "source_activity_id": str(proposal.source_activity_id),
        "source_key": proposal.source_key,
        "observed_at": proposal.observed_at.isoformat(),
        "received_at": proposal.received_at.isoformat(),
        "kind": proposal.kind.value,
        "trigger": proposal.trigger,
        "action": proposal.action,
        "fingerprint": proposal.fingerprint,
        "detector_version": proposal.detector_version,
        "relation": proposal.relation,
        "status": "pending",
    }


class MemoryCandidateRepository:
    def __init__(self, state: MemoryBackendState) -> None:
        self._state = state
        self._core = state.core
        self._tables = learning_state(state)

    def _store(self, c: Candidate) -> None:
        candidate_checks(c)
        project_scope(self._state, c)
        target = self._tables.candidates.get(c.conflicts_with_id) if c.conflicts_with_id is not None else None
        reference(
            c.conflicts_with_id is None or (target is not None and target.scope_id == c.scope_id),
            "conflicts_with_id",
        )
        reference(c.lesson_id is None or c.lesson_id in knowledge_state(self._state).lessons, "lesson_id")
        if any(
            row.id != c.id and (row.project_id, row.display_key) == (c.project_id, c.display_key)
            for row in self._tables.candidates.values()
        ):
            raise Conflict(ErrorCode.ALREADY_EXISTS, "Candidate display key already exists")
        self._tables.candidates[c.id] = deepcopy(replace(c, proposed_update=None, review_status="unreviewed"))
        self._tables.updates[c.id] = self._core.clock.now()

    def _project(self, c: Candidate) -> Candidate:
        pending = proposed_update(
            (
                p
                for p in self._tables.proposals.values()
                if p.candidate_id == c.id and p.scope_id == c.scope_id
            ),
            self._tables.reviews.values(),
        )
        return replace(
            deepcopy(c),
            proposed_update=None if pending is None else _proposal_view(pending),
            review_status=review_status(r for r in self._tables.reviews.values() if r.candidate_id == c.id),
        )

    def add(self, c: Candidate) -> None:
        self._core.require_writable()
        if c.id in self._tables.candidates or self.by_fingerprint(c.scope_id, c.fingerprint) is not None:
            raise Conflict(ErrorCode.ALREADY_EXISTS, "Candidate already exists")
        self._store(c)

    def get(self, candidate_id: CandidateId) -> Candidate:
        row = self._tables.candidates.get(candidate_id)
        if row is None:
            raise NotFound(ErrorCode.NOT_FOUND, "Candidate not found")
        return self._project(row)

    def save(self, c: Candidate, *, expected_version: int) -> None:
        self._core.require_writable()
        current = self.get(c.id)
        if current.row_version != expected_version:
            raise Conflict(ErrorCode.VERSION_CONFLICT, "Candidate version changed")
        if (c.workspace_id, c.scope_id, c.project_id) != (
            current.workspace_id,
            current.scope_id,
            current.project_id,
        ):
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Candidate scope cannot change")
        duplicate = self.by_fingerprint(c.scope_id, c.fingerprint)
        if duplicate is not None and duplicate.id != c.id:
            raise Conflict(ErrorCode.ALREADY_EXISTS, "Candidate wording already exists in this scope")
        self._store(replace(c, row_version=expected_version + 1))

    def by_fingerprint(self, scope_id: ScopeId, fingerprint: str) -> Candidate | None:
        for row in self._tables.candidates.values():
            if (row.scope_id, row.fingerprint) == (scope_id, fingerprint):
                return self._project(row)
        return None

    def updated_at(self, candidate_id: CandidateId) -> datetime:
        return self._tables.updates[candidate_id]

    def next_display_key(self, project_id: ProjectId) -> str:
        number = max(
            (
                int(row.display_key[3:])
                for row in self._tables.candidates.values()
                if row.project_id == project_id
            ),
            default=0,
        )
        return f"LC-{number + 1}"

    def _key(self, row: Candidate) -> tuple[str, str]:
        return time_key(self._tables.updates[row.id], row.id)

    def shortlist_pool(self, scope_id: ScopeId, *, limit: int) -> tuple[CandidateRef, ...]:
        rows = (row for row in self._tables.candidates.values() if row.scope_id == scope_id)
        return tuple(
            {
                "candidate_id": str(row.id),
                "kind": row.kind.value,
                "trigger": row.trigger,
                "action": row.action,
                "fingerprint": row.fingerprint,
                "state": row.state.value,
            }
            for row in sorted(rows, key=self._key, reverse=True)[: max(0, min(limit, 2000))]
        )

    def list(
        self,
        scope_ids: tuple[ScopeId, ...],
        *,
        states: frozenset[CandidateState],
        after: Cursor | None,
        limit: int,
    ) -> Page[Candidate]:
        rows = (
            row
            for row in self._tables.candidates.values()
            if row.scope_id in scope_ids and (not states or row.state in states)
        )
        page = page_rows(
            rows,
            after=after,
            limit=limit,
            filters={"scopes": sorted(map(str, scope_ids)), "states": sorted(states)},
            key_of=self._key,
        )
        return Page(tuple(self._project(row) for row in page.items), page.next)

    def ids_for_recompute(
        self, workspace_id: WorkspaceId, *, after: CandidateId | None, limit: int
    ) -> tuple[CandidateId, ...]:
        return tuple(
            sorted(
                row.id
                for row in self._tables.candidates.values()
                if row.workspace_id == workspace_id and (after is None or row.id > after)
            )[:limit]
        )
