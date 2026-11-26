"""``workspace.match_checkout`` (workspace §5.2, §8): the server's decision for an observed checkout.

Read-only: it looks up the repositories that share a remote, checks that the target named by the marker
exists in the server's own tables and asks ``decide_attach``. Nothing is written; the host op executes the
decision with commands.
"""

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound
from skm.kernel.ids import HostId, ProjectId, ScopeId, WorkspaceId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.workspace.application.views import attach_decision_view
from skm.modules.workspace.domain.attach import AttachInput, MarkerTarget, decide_attach_with_diagnostics
from skm.modules.workspace.domain.checkout_binding import ObservedCheckout
from skm.modules.workspace.domain.checkout_marker import CheckoutMarker, marker_from_document
from skm.modules.workspace.domain.remote_url import NormalizedRemote
from skm.modules.workspace.generated.queries import MatchCheckout
from skm.modules.workspace.generated.views import AttachDecisionView
from skm.modules.workspace.ports import (
    HostRepository,
    ProjectRepository,
    RepositoryRepository,
    WorkspaceRepository,
)

__all__ = ["SPEC", "handle"]


def _project_in(uow: UnitOfWork, workspace_id: WorkspaceId, project_id: ProjectId) -> bool:
    try:
        return uow.repo(ProjectRepository).get(project_id).workspace_id == workspace_id
    except NotFound:
        return False


def _marker_target(uow: UnitOfWork, marker: CheckoutMarker | None) -> MarkerTarget | None:
    if marker is None or not _project_in(uow, marker.workspace_id, marker.project_id):
        return None
    try:
        repository = uow.repo(RepositoryRepository).get(marker.repository_id)
    except NotFound:
        return None
    if repository.workspace_id != marker.workspace_id:
        return None
    return MarkerTarget(marker.workspace_id, marker.project_id, marker.repository_id)


def handle(query: MatchCheckout, ctx: QueryContext, uow: UnitOfWork) -> AttachDecisionView:
    workspace = uow.repo(WorkspaceRepository).get(WorkspaceId(query.workspace_id))
    uow.repo(HostRepository).get(HostId(query.host_id))
    requested = None if query.project_id is None else ProjectId(query.project_id)
    if requested is not None and not _project_in(uow, workspace.id, requested):
        raise NotFound(
            ErrorCode.NOT_FOUND, "project not found", details={"kind": "project", "ref": str(requested)}
        )
    marker = None if query.observed_marker is None else marker_from_document(dict(query.observed_marker))
    observed = ObservedCheckout(
        exists=query.observed_exists,
        toplevel=query.observed_toplevel,
        remotes=tuple(NormalizedRemote(item) for item in query.observed_remotes),
        head=query.observed_head,
        marker=marker,
        observed_at=ctx.clock.now(),
        dirty=None,
    )
    known = uow.repo(RepositoryRepository).match_remotes(workspace.id, observed.remotes)
    outcome = decide_attach_with_diagnostics(
        AttachInput(
            instance_id=ctx.scope_chain[0].id,
            workspace_id=workspace.id,
            requested_project_id=requested,
            observed=observed,
            known_repositories=known,
            marker_target=_marker_target(uow, marker),
            assume_yes=query.assume_yes,
        )
    )
    return attach_decision_view(outcome, mount_name=query.mount_name, requested_project_id=query.project_id)


SPEC = QuerySpec(
    name="workspace.match_checkout",
    dto=MatchCheckout,
    result=AttachDecisionView,
    permission="checkout.bind",
    scope_of=lambda query: ScopeRef(ScopeKind.WORKSPACE, ScopeId(query.workspace_id)),
    handler=handle,
)
