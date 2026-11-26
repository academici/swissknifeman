"""``artifacts.get_file_version`` (artifacts §8): the metadata of one version.

The bus resolves the scope of the version's stored file (``file_scope_of_version``) and authorises
``file.read`` there; the handler binds itself to that scope and decides ``file.read`` on the scope **of the
stored file** again, never on a digest. An actor of kind worker also needs an active assignment grant on
exactly this version (of its own assignment, for an assignment token), so a grant on version A opens nothing
of version B even when both hold the same bytes.
"""

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.ids import FileVersionId
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.artifacts.application import views
from skm.modules.artifacts.application.guards import (
    file_scope_of_version,
    require_bound,
    require_version_read,
)
from skm.modules.artifacts.application.reads import version_blob
from skm.modules.artifacts.generated.queries import GetFileVersion
from skm.modules.artifacts.generated.views import GetFileVersionView
from skm.modules.artifacts.ports import FileRepository, FileVersionRepository

__all__ = ["SPEC", "handle"]


def handle(query: GetFileVersion, ctx: QueryContext, uow: UnitOfWork) -> GetFileVersionView:
    version = uow.repo(FileVersionRepository).get(FileVersionId(query.file_version_id))
    file = uow.repo(FileRepository).get(version.file_id)
    require_bound(ctx, file)
    require_version_read(uow, ctx, file, version)
    return views.get_file_version_view(version, version_blob(uow, version), file)


SPEC = QuerySpec(
    name="artifacts.get_file_version",
    dto=GetFileVersion,
    result=GetFileVersionView,
    permission="file.read",
    scope_of=None,
    handler=handle,
    scope_resolver=file_scope_of_version,
)
