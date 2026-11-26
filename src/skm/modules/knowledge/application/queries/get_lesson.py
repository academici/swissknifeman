"""Get one lesson only from its named workspace."""

from typing import Any, cast
from uuid import UUID

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.ids import WorkspaceId
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.knowledge.application.lesson_operations import require_lesson
from skm.modules.knowledge.application.scopes import workspace_ref
from skm.modules.knowledge.application.views import lesson_view
from skm.modules.knowledge.domain.lesson import LessonId
from skm.modules.knowledge.generated.queries import GetLesson
from skm.modules.knowledge.generated.views import LessonView, LessonViewDefsLessonView, lesson_view_from_json


def handle(query: dict[str, Any], _ctx: QueryContext, uow: UnitOfWork) -> LessonView:
    row = require_lesson(uow, LessonId(UUID(query["lesson_id"])), WorkspaceId(UUID(query["workspace_id"])))
    return lesson_view_from_json(lesson_view(row))


SPEC = QuerySpec(
    name="knowledge.get_lesson",
    dto=cast("type[dict[str, Any]]", GetLesson),
    result=LessonViewDefsLessonView,
    permission="lesson.read",
    scope_of=lambda query: workspace_ref(query["workspace_id"]),
    handler=handle,
)
