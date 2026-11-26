"""Record authenticated reviews and apply human wording decisions."""

from dataclasses import dataclass, replace
from typing import Any, ClassVar, Literal, cast, override
from uuid import UUID

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, NotFound, PreconditionFailed, ValidationFailed
from skm.kernel.events import DomainEvent
from skm.kernel.ids import PrincipalId, ScopeId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.knowledge.public import LessonKind
from skm.modules.learning.domain.candidate import Candidate, CandidateId, CandidateState
from skm.modules.learning.domain.consolidation import fingerprint
from skm.modules.learning.domain.events import (
    CANDIDATE_STREAM_KIND,
    candidate_reviewed_payload,
    candidate_state_changed_payload,
)
from skm.modules.learning.domain.review import (
    CandidateProposalId,
    CandidateReview,
    CandidateReviewId,
    ReviewVerdict,
    validate_review,
)
from skm.modules.learning.generated.commands import ReviewCandidate
from skm.modules.learning.generated.results import ReviewCandidateResult
from skm.modules.learning.ports import (
    CandidateProposalRepository,
    CandidateRepository,
    CandidateReviewRepository,
)


@dataclass(frozen=True, slots=True)
class CandidateReviewed(DomainEvent):
    event_type: ClassVar[str] = "urn:skm:learning:event:candidate-reviewed:v1"
    stream_kind: ClassVar[str] = CANDIDATE_STREAM_KIND
    candidate_id: CandidateId
    workspace_id: WorkspaceId
    review_id: CandidateReviewId
    verdict: ReviewVerdict
    reviewer_id: PrincipalId

    @override
    def stream_id(self) -> UUID:
        return self.candidate_id

    @override
    def scope_workspace_id(self) -> WorkspaceId:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return candidate_reviewed_payload(self.candidate_id, self.review_id, self.verdict, self.reviewer_id)


@dataclass(frozen=True, slots=True)
class CandidateStateChanged(DomainEvent):
    event_type: ClassVar[str] = "urn:skm:learning:event:candidate-state-changed:v1"
    stream_kind: ClassVar[str] = CANDIDATE_STREAM_KIND
    candidate_id: CandidateId
    workspace_id: WorkspaceId
    from_state: CandidateState
    to_state: CandidateState
    reason: Literal["numeric_gate", "source_support_low", "reobserved", "rejected"]

    @override
    def stream_id(self) -> UUID:
        return self.candidate_id

    @override
    def scope_workspace_id(self) -> WorkspaceId:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return candidate_state_changed_payload(self.candidate_id, self.from_state, self.to_state, self.reason)


def workspace_ref(workspace_id: str) -> ScopeRef:
    return ScopeRef(ScopeKind.WORKSPACE, ScopeId(UUID(workspace_id)))


def require_candidate(
    repo: CandidateRepository, candidate_id: CandidateId, workspace_id: WorkspaceId
) -> Candidate:
    candidate = repo.get(candidate_id)
    if candidate.workspace_id != workspace_id:
        raise NotFound(ErrorCode.NOT_FOUND, "Candidate not found")
    return candidate


def check_version(candidate: Candidate, expected: int) -> None:
    if candidate.row_version != expected:
        raise Conflict(ErrorCode.VERSION_CONFLICT, "Candidate version changed")


def _review_subject(uow: UnitOfWork, target: Candidate, proposal_id: CandidateProposalId) -> Candidate:
    proposal = uow.repo(CandidateProposalRepository).get(proposal_id)
    if (proposal.scope_id, proposal.candidate_id) != (target.scope_id, target.id):
        raise NotFound(ErrorCode.NOT_FOUND, "Candidate proposal not found")
    source = require_candidate(
        uow.repo(CandidateRepository), proposal.source_candidate_id, target.workspace_id
    )
    if source.scope_id != target.scope_id or source.id == target.id:
        raise NotFound(ErrorCode.NOT_FOUND, "Candidate proposal not found")
    if any(
        r.proposal_id == proposal.id for r in uow.repo(CandidateReviewRepository).for_candidate(source.id)
    ):
        raise PreconditionFailed(ErrorCode.INVALID_TRANSITION, "Candidate proposal already addressed")
    return source


def _apply_review(candidate: Candidate, review: CandidateReview) -> Candidate:
    edited = (review.edited_trigger, review.edited_action, review.edited_kind)
    if review.verdict is ReviewVerdict.EDIT:
        if all(value is None for value in edited):
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Edit requires new wording or kind")
        trigger = candidate.trigger if review.edited_trigger is None else review.edited_trigger
        action = candidate.action if review.edited_action is None else review.edited_action
        kind = candidate.kind if review.edited_kind is None else review.edited_kind
        if not trigger.strip() or not action.strip():
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Candidate wording cannot be blank")
        return replace(
            candidate,
            trigger=trigger,
            action=action,
            kind=kind,
            fingerprint=fingerprint(kind, trigger, action),
        )
    if any(value is not None for value in edited):
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Edited fields require an edit verdict")
    if review.verdict is ReviewVerdict.REJECT:
        return replace(candidate, state=CandidateState.REJECTED)
    return candidate


def handle(cmd: dict[str, Any], ctx: CommandContext, uow: UnitOfWork) -> ReviewCandidateResult:
    repo = uow.repo(CandidateRepository)
    target = require_candidate(
        repo, CandidateId(UUID(cmd["candidate_id"])), WorkspaceId(UUID(cmd["workspace_id"]))
    )
    check_version(target, cmd["expected_row_version"])
    verdict = ReviewVerdict(cmd["verdict"])
    proposal_id = CandidateProposalId(UUID(cmd["proposal_id"])) if "proposal_id" in cmd else None
    validate_review(ctx.actor, verdict, proposal_id=proposal_id)
    candidate = target if proposal_id is None else _review_subject(uow, target, proposal_id)
    if candidate.state is CandidateState.PROMOTED:
        raise PreconditionFailed(ErrorCode.INVALID_TRANSITION, "Promoted candidates cannot be reviewed")

    review = CandidateReview(
        id=CandidateReviewId(ctx.ids.new_id()),
        candidate_id=candidate.id,
        reviewer_id=ctx.actor.principal_id,
        reviewer_kind=ctx.actor.kind,
        verdict=verdict,
        note=cmd.get("note"),
        edited_trigger=cmd.get("edited_trigger"),
        edited_action=cmd.get("edited_action"),
        edited_kind=LessonKind(cmd["edited_kind"]) if "edited_kind" in cmd else None,
        proposal_id=proposal_id,
        created_at=ctx.clock.now(),
    )
    updated = _apply_review(candidate, review)
    repo.save(updated, expected_version=candidate.row_version)
    uow.repo(CandidateReviewRepository).add(review)
    uow.record(
        CandidateReviewed(candidate.id, candidate.workspace_id, review.id, verdict, review.reviewer_id)
    )
    if updated.state is not candidate.state:
        uow.record(
            CandidateStateChanged(
                candidate.id, candidate.workspace_id, candidate.state, updated.state, "rejected"
            )
        )
    return ReviewCandidateResult(review_id=str(review.id), state=updated.state.value)


SPEC = CommandSpec(
    name="learning.review_candidate",
    dto=cast("type[dict[str, Any]]", ReviewCandidate),
    result=ReviewCandidateResult,
    permission="lesson.curate",
    scope_of=lambda cmd: workspace_ref(cmd["workspace_id"]),
    handler=handle,
    idempotency=IdempotencyMode.REQUIRED,
)
