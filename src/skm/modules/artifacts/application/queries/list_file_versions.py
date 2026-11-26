"""``artifacts.list_file_versions`` (artifacts §8): the versions of one file, highest number first.

The bus resolves the stored file's own scope (``file_scope_of_file``) and authorises ``file.read`` there; the
handler binds itself to that scope and decides ``file.read`` on the stored file again. A worker lists only
the versions it holds an active grant on (the filter runs after the page is cut, so a page may be shorter
than ``limit``).
"""

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.artifacts.application.guards import (
    can_read_version,
    file_scope_of_file,
    require_bound,
    require_file,
)
from skm.modules.artifacts.application.reads import version_view_of
from skm.modules.artifacts.domain.file import FileId
from skm.modules.artifacts.generated.queries import ListFileVersions
from skm.modules.artifacts.generated.views import ListFileVersionsView
from skm.modules.artifacts.ports import FileRepository, FileVersionRepository

__all__ = ["SPEC", "handle"]


def handle(query: ListFileVersions, ctx: QueryContext, uow: UnitOfWork) -> ListFileVersionsView:
    file = uow.repo(FileRepository).get(FileId(query.file_id))
    require_bound(ctx, file)
    require_file(uow, ctx, "file.read", file)
    page = uow.repo(FileVersionRepository).list(file.id, after=query.after, limit=query.limit)
    readable = (version for version in page.items if can_read_version(uow, ctx, file, version))
    return ListFileVersionsView(
        items=tuple(version_view_of(uow, version) for version in readable), next=page.next
    )


SPEC = QuerySpec(
    name="artifacts.list_file_versions",
    dto=ListFileVersions,
    result=ListFileVersionsView,
    permission="file.read",
    scope_of=None,
    handler=handle,
    scope_resolver=file_scope_of_file,
)
