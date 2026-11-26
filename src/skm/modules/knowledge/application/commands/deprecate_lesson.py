"""Deprecate a workspace-owned lesson by row version."""

from typing import Any, cast
from uuid import UUID

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict
from skm.kernel.ids import WorkspaceId
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.knowledge.application.lesson_operations import deprecate_in_uow, require_lesson
from skm.modules.knowledge.application.scopes import workspace_ref
from skm.modules.knowledge.domain.lesson import LessonId
from skm.modules.knowledge.generated.commands import DeprecateLesson
from skm.modules.knowledge.generated.results import DeprecateLessonResult


def handle(cmd: dict[str, Any], ctx: CommandContext, uow: UnitOfWork) -> DeprecateLessonResult:
    lesson = require_lesson(uow, LessonId(UUID(cmd["lesson_id"])), WorkspaceId(UUID(cmd["workspace_id"])))
    if lesson.row_version != cmd["expected_row_version"]:
        raise Conflict(ErrorCode.VERSION_CONFLICT, "Lesson version changed")
    updated = deprecate_in_uow(uow, lesson, actor=ctx.actor, reason=cmd["reason"], now=ctx.clock.now())
    return DeprecateLessonResult(lesson_id=str(updated.id), state=updated.state.value)


SPEC = CommandSpec(
    name="knowledge.deprecate_lesson",
    dto=cast("type[dict[str, Any]]", DeprecateLesson),
    result=DeprecateLessonResult,
    permission="lesson.curate",
    scope_of=lambda cmd: workspace_ref(cmd["workspace_id"]),
    handler=handle,
    allowed_kinds=frozenset({PrincipalKind.HUMAN}),
    idempotency=IdempotencyMode.REQUIRED,
)
