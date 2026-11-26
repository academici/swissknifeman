"""Handler for ``integrations.get_applied_state`` (integrations §8)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from skm.application_bus.registry import QuerySpec
from skm.kernel.ids import ProjectId
from skm.modules.integrations.application.projection_views import (
    project_scope,
    resolve_project_binding_host,
    to_applied_file_view,
    to_projection_summary_view,
)
from skm.modules.integrations.domain.target import TargetId
from skm.modules.integrations.generated.queries import GetAppliedState
from skm.modules.integrations.generated.views import AppliedStateView
from skm.modules.integrations.ports import ProjectionRepository
from skm.modules.workspace.public import CheckoutBindingId

if TYPE_CHECKING:
    from skm.application_bus.context import QueryContext
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["SPEC", "handle"]


def handle(query: GetAppliedState, ctx: QueryContext, uow: UnitOfWork) -> AppliedStateView:
    project_id = ProjectId(query.project_id)
    checkout_binding_id = CheckoutBindingId(query.checkout_binding_id)
    target = TargetId(query.target)
    now = ctx.clock.now()

    _workspace_id, host_id = resolve_project_binding_host(uow, project_id, checkout_binding_id, now=now)

    repo = uow.repo(ProjectionRepository)
    projection = repo.find(project_id, checkout_binding_id, target)
    if projection is None:
        return AppliedStateView(projection=None, files=())

    files = repo.files(projection.id)
    return AppliedStateView(
        projection=to_projection_summary_view(projection, host_id=host_id),
        files=tuple(to_applied_file_view(rec) for rec in files),
    )


SPEC = QuerySpec(
    name="integrations.get_applied_state",
    dto=GetAppliedState,
    result=AppliedStateView,
    permission="integration.read",
    scope_of=project_scope,
    handler=handle,
)
