"""Handler for ``integrations.list_projections`` (integrations §8)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from skm.application_bus.registry import QuerySpec
from skm.kernel.ids import HostId, ProjectId
from skm.kernel.pagination import DEFAULT_PAGE_LIMIT, Cursor, validate_page_limit
from skm.modules.integrations.application.projection_views import (
    host_map_for_project,
    project_scope,
    to_projection_summary_view,
)
from skm.modules.integrations.generated.queries import ListProjections
from skm.modules.integrations.generated.views import ProjectionsView
from skm.modules.integrations.ports import ProjectionRepository
from skm.modules.workspace import public as workspace

if TYPE_CHECKING:
    from skm.application_bus.context import QueryContext
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["SPEC", "handle"]


def handle(query: ListProjections, ctx: QueryContext, uow: UnitOfWork) -> ProjectionsView:
    project_id = ProjectId(query.project_id)
    limit = validate_page_limit(DEFAULT_PAGE_LIMIT if query.limit is None else query.limit)
    now = ctx.clock.now()

    workspace.workspace_of_project(uow, project_id)
    host_by_binding = host_map_for_project(uow, project_id, now=now)

    repo = uow.repo(ProjectionRepository)
    cursor = None if query.after is None else Cursor(query.after)
    page = repo.list_for_project(project_id, after=cursor, limit=limit)

    items = tuple(
        to_projection_summary_view(
            proj,
            host_id=host_by_binding.get(proj.checkout_binding_id, HostId(UUID(int=0))),
        )
        for proj in page.items
    )
    return ProjectionsView(
        items=items,
        next_cursor=None if page.next is None else str(page.next),
        has_more=page.next is not None,
    )


SPEC = QuerySpec(
    name="integrations.list_projections",
    dto=ListProjections,
    result=ProjectionsView,
    permission="integration.read",
    scope_of=project_scope,
    handler=handle,
)
