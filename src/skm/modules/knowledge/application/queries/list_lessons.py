"""List lesson history inside a workspace, optionally constrained to one project."""

from typing import Any, cast
from uuid import UUID

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound
from skm.kernel.ids import ProjectId, ScopeId, WorkspaceId
from skm.kernel.pagination import DEFAULT_PAGE_LIMIT, Cursor
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.knowledge.application.scopes import project_ref, workspace_ref
from skm.modules.knowledge.application.views import lesson_view
from skm.modules.knowledge.domain.lesson import LessonKind, LessonState
from skm.modules.knowledge.generated.queries import ListLessons
from skm.modules.knowledge.generated.views import LessonsView, lessons_view_from_json
from skm.modules.knowledge.ports import LessonRepository
from skm.modules.workspace.public import workspace_of_project


def handle(query: dict[str, Any], _ctx: QueryContext, uow: UnitOfWork) -> LessonsView:
    workspace = WorkspaceId(UUID(query["workspace_id"]))
    scopes = None
    if (project_id := query.get("project_id")) is not None:
        project = ProjectId(UUID(project_id))
        if workspace_of_project(uow, project) != workspace:
            raise NotFound(ErrorCode.NOT_FOUND, "Project not found")
        scopes = (ScopeId(project),)
    after, state, kind = query.get("after"), query.get("state"), query.get("kind")
    page = uow.repo(LessonRepository).list(
        scopes,
        workspace_id=workspace,
        state=LessonState(state) if state is not None else None,
        kind=LessonKind(kind) if kind is not None else None,
        after=Cursor(after) if after is not None else None,
        limit=query.get("limit", DEFAULT_PAGE_LIMIT),
    )
    return lessons_view_from_json(
        {
            "items": [lesson_view(row) for row in page.items],
            "next_cursor": page.next,
            "has_more": page.next is not None,
        }
    )


SPEC = QuerySpec(
    name="knowledge.list_lessons",
    dto=cast("type[dict[str, Any]]", ListLessons),
    result=LessonsView,
    permission="lesson.read",
    scope_of=lambda query: (
        project_ref(query["project_id"])
        if query.get("project_id") is not None
        else workspace_ref(query["workspace_id"])
    ),
    handler=handle,
)
