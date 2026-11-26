"""``artifacts.list_files`` (artifacts §8): the files of a workspace or of one project, newest first.

The bus authorises ``file.read`` on the named project, else on the workspace; a project of another workspace
simply matches no file. The summaries carry no version data.
"""

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.ids import ProjectId, ScopeId, WorkspaceId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.artifacts.application.views import file_summary
from skm.modules.artifacts.domain.file import FileOrigin, FileState
from skm.modules.artifacts.generated.queries import ListFiles
from skm.modules.artifacts.generated.views import ListFilesView
from skm.modules.artifacts.ports import FileRepository

__all__ = ["SPEC", "handle", "scope_of"]


def scope_of(query: ListFiles) -> ScopeRef:
    if query.project_id is not None:
        return ScopeRef(ScopeKind.PROJECT, ScopeId(query.project_id))
    return ScopeRef(ScopeKind.WORKSPACE, ScopeId(query.workspace_id))


def handle(query: ListFiles, ctx: QueryContext, uow: UnitOfWork) -> ListFilesView:
    del ctx
    page = uow.repo(FileRepository).list(
        WorkspaceId(query.workspace_id),
        project_id=None if query.project_id is None else ProjectId(query.project_id),
        state=None if query.state is None else FileState(query.state),
        origin=None if query.origin is None else FileOrigin(query.origin),
        after=query.after,
        limit=query.limit,
    )
    return ListFilesView(items=tuple(file_summary(file) for file in page.items), next=page.next)


SPEC = QuerySpec(
    name="artifacts.list_files",
    dto=ListFiles,
    result=ListFilesView,
    permission="file.read",
    scope_of=scope_of,
    handler=handle,
)
