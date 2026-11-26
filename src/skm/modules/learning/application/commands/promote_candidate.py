"""Promote a reviewed wording and its knowledge lesson in one transaction."""

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, ClassVar, cast, override
from uuid import UUID

from skm.application_bus.context import CommandContext
from skm.application_bus.ports import AuditLog, AuditRecord
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed, ValidationFailed
from skm.kernel.events import DomainEvent
from skm.kernel.ids import PrincipalId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import Isolation, UnitOfWork
from skm.modules.knowledge import public as knowledge
from skm.modules.learning.domain.candidate import Candidate, CandidateId, CandidateState
from skm.modules.learning.domain.events import CANDIDATE_STREAM_KIND, candidate_promoted_payload
from skm.modules.learning.domain.promotion import require_human, validate_promotion
from skm.modules.learning.domain.review import CandidateReview, CandidateReviewId, ReviewVerdict
from skm.modules.learning.generated.commands import PromoteCandidate
from skm.modules.learning.generated.results import PromoteCandidateResult
from skm.modules.learning.ports import CandidateRepository, CandidateReviewRepository

from .review_candidate import check_version, require_candidate, workspace_ref

_COMMAND = "learning.promote_candidate"
_PERMISSION = "lesson.curate"


@dataclass(frozen=True, slots=True)
class CandidatePromoted(DomainEvent):
    event_type: ClassVar[str] = "urn:skm:learning:event:candidate-promoted:v1"
    stream_kind: ClassVar[str] = CANDIDATE_STREAM_KIND
    candidate_id: CandidateId
    workspace_id: WorkspaceId
    lesson_id: knowledge.LessonId
    promoted_by: PrincipalId
    override_low_confidence: bool

    @override
    def stream_id(self) -> UUID:
        return self.candidate_id

    @override
    def scope_workspace_id(self) -> WorkspaceId:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return candidate_promoted_payload(
            self.candidate_id,
            self.lesson_id,
            self.promoted_by,
            override_low_confidence=self.override_low_confidence,
        )


def _applicability(value: dict[str, Any] | None) -> knowledge.LessonApplicability | None:
    if value is None:
        return None
    review_after: str | None = value.get("review_after")
    versions: list[list[str]] = value.get("validated_versions", [])
    return knowledge.LessonApplicability(
        applies_to=value.get("applies_to"),
        validated_versions=tuple((key, version) for key, version in versions),
        review_after=datetime.fromisoformat(review_after) if review_after is not None else None,
    )


def _supersession(
    cmd: dict[str, Any], candidate: Candidate, repo: CandidateRepository
) -> knowledge.LessonId | None:
    explicit = (
        knowledge.LessonId(UUID(cmd["supersedes_lesson_id"])) if "supersedes_lesson_id" in cmd else None
    )
    if candidate.conflicts_with_id is None:
        if cmd.get("resolve_conflict") == "supersede":
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Supersede requires a promoted conflict target")
        return explicit
    target = require_candidate(repo, candidate.conflicts_with_id, candidate.workspace_id)
    if target.scope_id != candidate.scope_id:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Conflicting candidate must be in the exact scope")
    if cmd["resolve_conflict"] == "keep_both":
        if explicit is not None and explicit == target.lesson_id:
            raise PreconditionFailed(
                ErrorCode.INVALID_TRANSITION, "Cannot keep and supersede the same lesson"
            )
        return explicit
    if target.state is not CandidateState.PROMOTED or target.lesson_id is None:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Supersede requires a promoted conflict target")
    if explicit is not None and explicit != target.lesson_id:
        raise PreconditionFailed(
            ErrorCode.INVALID_TRANSITION, "Supersedes lesson differs from the conflict target"
        )
    return target.lesson_id


def handle(cmd: dict[str, Any], ctx: CommandContext, uow: UnitOfWork) -> PromoteCandidateResult:
    require_human(ctx.actor)
    repo = uow.repo(CandidateRepository)
    candidate = require_candidate(
        repo, CandidateId(UUID(cmd["candidate_id"])), WorkspaceId(UUID(cmd["workspace_id"]))
    )
    check_version(candidate, cmd["expected_row_version"])
    override_low_confidence = cmd.get("override_low_confidence", False)
    reason = cmd.get("override_reason")
    resolution = cmd.get("resolve_conflict")
    validate_promotion(
        candidate,
        ctx.actor,
        override_low_confidence=override_low_confidence,
        override_reason=reason,
        resolve_conflict=resolution,
    )
    note = reason.strip() if override_low_confidence and reason is not None else None
    if note is not None and len(note) > 2000:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Override reason exceeds the review note limit")
    supersedes = _supersession(cmd, candidate, repo)
    now = ctx.clock.now()
    lesson = knowledge.promote_lesson(
        uow,
        knowledge.CandidateForPromotion(
            candidate.id,
            candidate.workspace_id,
            candidate.scope_id,
            candidate.kind,
            candidate.trigger,
            candidate.action,
            candidate.evidence,
            candidate.confidence,
            knowledge.ConfidenceTier(candidate.confidence_tier.value),
        ),
        actor=ctx.actor,
        supersedes=supersedes,
        applicability=_applicability(cmd.get("applicability")),
        now=now,
        lesson_id=knowledge.LessonId(ctx.ids.new_id()),
    )
    if resolution == "supersede" and supersedes is not None:
        knowledge.deprecate_lesson(
            uow, supersedes, actor=ctx.actor, reason=f"superseded by {lesson.lesson_id}", now=now
        )
    repo.save(
        replace(candidate, state=CandidateState.PROMOTED, lesson_id=lesson.lesson_id),
        expected_version=candidate.row_version,
    )
    uow.repo(CandidateReviewRepository).add(
        CandidateReview(
            id=CandidateReviewId(ctx.ids.new_id()),
            candidate_id=candidate.id,
            reviewer_id=ctx.actor.principal_id,
            reviewer_kind=ctx.actor.kind,
            verdict=ReviewVerdict.APPROVE,
            note=note,
            edited_trigger=None,
            edited_action=None,
            edited_kind=None,
            proposal_id=None,
            created_at=now,
        )
    )
    if resolution is not None:
        uow.repo(AuditLog).append(
            AuditRecord(
                id=ctx.ids.new_id(),
                workspace_id=candidate.workspace_id,
                actor_id=ctx.actor.principal_id,
                action=_COMMAND,
                target={
                    "scope": {"kind": ctx.scope.kind.value, "id": str(ctx.scope.id)},
                    "permission": _PERMISSION,
                    "candidate_id": str(candidate.id),
                    "lesson_id": str(lesson.lesson_id),
                    "resolve_conflict": resolution,
                },
                decision="allowed",
                reason_code=None,
                request_id=ctx.meta.request_id,
                recorded_at=now,
            )
        )
    uow.record(
        CandidatePromoted(
            candidate.id,
            candidate.workspace_id,
            lesson.lesson_id,
            ctx.actor.principal_id,
            override_low_confidence,
        )
    )
    return PromoteCandidateResult(lesson_id=str(lesson.lesson_id))


SPEC = CommandSpec(
    name=_COMMAND,
    dto=cast("type[dict[str, Any]]", PromoteCandidate),
    result=PromoteCandidateResult,
    permission=_PERMISSION,
    scope_of=lambda cmd: workspace_ref(cmd["workspace_id"]),
    handler=handle,
    isolation=Isolation.SERIALIZABLE,
    idempotency=IdempotencyMode.REQUIRED,
)
