"""Repository contracts for learning evidence and curation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from skm.kernel.ids import ProjectId, ScopeId, WorkspaceId
from skm.kernel.pagination import Cursor, Page
from skm.kernel.ports_uow import repository_port

from .domain.activity import ActivityRecord, ActivityRecordId
from .domain.candidate import Candidate, CandidateId, CandidateState, Signal
from .domain.contracts import CandidateRef
from .domain.pathology import PathologyCode
from .domain.review import CandidateProposal, CandidateProposalId, CandidateReview


@repository_port
class ActivityRecordRepository(Protocol):
    def add(self, record: ActivityRecord) -> bool: ...

    def exists(self, workspace_id: WorkspaceId, source_key: str) -> bool: ...

    def pathology_history(
        self, scope_id: ScopeId, *, window: int, including: ActivityRecordId
    ) -> Mapping[PathologyCode, int]: ...

    def count_for_project(self, project_id: ProjectId) -> int: ...

    def pathology_stats(self, project_id: ProjectId, *, window: int) -> Mapping[PathologyCode, int]: ...


@repository_port
class CandidateRepository(Protocol):
    def add(self, c: Candidate) -> None: ...

    def get(self, candidate_id: CandidateId) -> Candidate: ...

    def save(self, c: Candidate, *, expected_version: int) -> None: ...

    def by_fingerprint(self, scope_id: ScopeId, fingerprint: str) -> Candidate | None: ...

    def shortlist_pool(self, scope_id: ScopeId, *, limit: int) -> tuple[CandidateRef, ...]: ...

    def list(
        self,
        scope_ids: tuple[ScopeId, ...],
        *,
        states: frozenset[CandidateState],
        after: Cursor | None,
        limit: int,
    ) -> Page[Candidate]: ...

    def ids_for_recompute(
        self, workspace_id: WorkspaceId, *, after: CandidateId | None, limit: int
    ) -> tuple[CandidateId, ...]: ...


@repository_port
class SignalRepository(Protocol):
    def add(self, s: Signal) -> bool: ...

    def for_candidate(self, candidate_id: CandidateId) -> tuple[Signal, ...]: ...

    def count_activities_for_project(self, project_id: ProjectId) -> int: ...

    def list(self, candidate_id: CandidateId, *, after: Cursor | None, limit: int) -> Page[Signal]: ...


@repository_port
class CandidateReviewRepository(Protocol):
    def add(self, r: CandidateReview) -> None: ...

    def for_candidate(self, candidate_id: CandidateId) -> tuple[CandidateReview, ...]: ...


@repository_port
class CandidateProposalRepository(Protocol):
    def add(self, p: CandidateProposal) -> bool: ...

    def get(self, proposal_id: CandidateProposalId) -> CandidateProposal: ...

    def list(
        self, candidate_id: CandidateId, *, after: Cursor | None, limit: int
    ) -> Page[CandidateProposal]: ...
