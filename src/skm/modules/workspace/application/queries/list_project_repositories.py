"""``workspace.list_project_repositories`` (workspace §8): the mounts of a project.

``local_locator`` is part of a binding only for a caller who holds ``checkout.read_locator`` on the project;
otherwise the field is absent. Without ``host_id`` no binding is listed (a binding belongs to one host).
"""

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.ids import HostId, ProjectId, ScopeId
from skm.kernel.ports_uow import Surface, UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.workspace.application.guards import holds, stale_after_days
from skm.modules.workspace.application.views import binding_variant, mount_view
from skm.modules.workspace.domain.checkout_binding import checkout_id_from_locator
from skm.modules.workspace.domain.mount import ProjectRepository as ProjectMount
from skm.modules.workspace.generated.queries import ListProjectRepositories
from skm.modules.workspace.generated.views import ListProjectRepositoriesView, MountView
from skm.modules.workspace.ports import (
    CheckoutBindingRepository,
    MountRepository,
    ProjectRepository,
    RepositoryRepository,
)

__all__ = ["SPEC", "handle"]


def handle(query: ListProjectRepositories, ctx: QueryContext, uow: UnitOfWork) -> ListProjectRepositoriesView:
    project = uow.repo(ProjectRepository).get(ProjectId(query.project_id))
    locator = holds(uow, ctx.clock, ctx.actor, "checkout.read_locator", project.id)
    repositories = uow.repo(RepositoryRepository)
    bindings = uow.repo(CheckoutBindingRepository)
    now, days = ctx.clock.now(), stale_after_days(ctx)

    def mounted(mount: ProjectMount) -> MountView:
        repository = repositories.get(mount.repository_id)
        binding = None if query.host_id is None else bindings.find(HostId(query.host_id), repository.id)
        visible_locator = locator and (
            ctx.meta.surface is not Surface.API
            or (binding is not None and checkout_id_from_locator(binding.local_locator) is not None)
        )
        shown = (
            None
            if binding is None
            else binding_variant(binding, now=now, stale_days=days, locator=visible_locator)
        )
        return mount_view(mount, repository, shown)

    mounts = sorted(uow.repo(MountRepository).for_project(project.id), key=lambda item: item.mount_name.value)
    items = tuple(mounted(mount) for mount in mounts)
    return ListProjectRepositoriesView(items=items)


SPEC = QuerySpec(
    name="workspace.list_project_repositories",
    dto=ListProjectRepositories,
    result=ListProjectRepositoriesView,
    permission="project.read",
    scope_of=lambda query: ScopeRef(ScopeKind.PROJECT, ScopeId(query.project_id)),
    handler=handle,
)
