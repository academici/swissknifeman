"""Transactional lesson operations used by the facade and bus handlers."""

from datetime import datetime

from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, Forbidden, NotFound
from skm.kernel.ids import WorkspaceId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRegistry
from skm.modules.knowledge.domain.events import LessonDeprecated, LessonPromoted
from skm.modules.knowledge.domain.lesson import (
    Lesson,
    LessonApplicability,
    LessonId,
    deprecate,
    new_lesson_from_candidate,
)
from skm.modules.knowledge.domain.promotion import CandidateForPromotion
from skm.modules.knowledge.ports import LessonRepository

from .views import validate_lesson_storage


def require_lesson(uow: UnitOfWork, lesson_id: LessonId, workspace_id: WorkspaceId) -> Lesson:
    lesson = uow.repo(LessonRepository).get(lesson_id)
    if lesson.workspace_id != workspace_id:
        raise NotFound(ErrorCode.NOT_FOUND, "Lesson not found")
    return lesson


def promote(
    uow: UnitOfWork,
    candidate: CandidateForPromotion,
    *,
    actor: Actor,
    lesson_id: LessonId,
    now: datetime,
    supersedes: LessonId | None,
    applicability: LessonApplicability | None,
) -> Lesson:
    if actor.kind is not PrincipalKind.HUMAN:
        raise Forbidden(
            ErrorCode.FORBIDDEN, "Lesson curation requires a human", details={"reason": "human_gate"}
        )
    repo = uow.repo(LessonRepository)
    scope = uow.repo(ScopeRegistry).get(candidate.scope_id)
    if scope.workspace_id != candidate.workspace_id or scope.kind not in (
        ScopeKind.PROJECT,
        ScopeKind.WORKSPACE,
    ):
        raise NotFound(ErrorCode.NOT_FOUND, "Candidate scope not found")
    if repo.by_candidate(candidate.candidate_id) is not None:
        raise Conflict(ErrorCode.ALREADY_EXISTS, "A lesson already exists for this candidate")
    predecessor = None if supersedes is None else require_lesson(uow, supersedes, candidate.workspace_id)
    lesson = new_lesson_from_candidate(
        candidate,
        lesson_id=lesson_id,
        actor=actor,
        now=now,
        supersedes=predecessor,
        applicability=applicability,
    )
    validate_lesson_storage(lesson)
    repo.add(lesson)
    uow.record(LessonPromoted(lesson.id, lesson.workspace_id, lesson.candidate_id))
    return lesson


def deprecate_in_uow(uow: UnitOfWork, lesson: Lesson, *, actor: Actor, reason: str, now: datetime) -> Lesson:
    updated = deprecate(lesson, actor=actor, reason=reason, now=now)
    if updated is not lesson:
        uow.repo(LessonRepository).save(updated, expected_version=lesson.row_version, now=now)
        uow.record(LessonDeprecated(lesson.id, lesson.workspace_id, reason.strip()))
    return updated
