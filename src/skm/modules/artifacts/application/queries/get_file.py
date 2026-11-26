"""``artifacts.get_file`` (artifacts §8): the file with its current version.

The bus resolves the stored file's own scope (``file_scope_of_file``) and authorises ``file.read`` there; the
handler binds itself to that scope and decides ``file.read`` on the stored file again. The view carries the
current version's metadata, so a worker reads it only with an active grant on that version.
"""

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.artifacts.application import views
from skm.modules.artifacts.application.guards import file_scope_of_file, require_bound, require_version_read
from skm.modules.artifacts.application.reads import version_view_of
from skm.modules.artifacts.domain.file import FileId
from skm.modules.artifacts.generated.queries import GetFile
from skm.modules.artifacts.generated.views import GetFileView
from skm.modules.artifacts.ports import FileRepository, FileVersionRepository

__all__ = ["SPEC", "handle"]


def handle(query: GetFile, ctx: QueryContext, uow: UnitOfWork) -> GetFileView:
    file = uow.repo(FileRepository).get(FileId(query.file_id))
    require_bound(ctx, file)
    if file.current_version_id is None:  # only between the two inserts of one transaction
        raise InternalError(
            ErrorCode.INTERNAL_ERROR, "file has no current version", details={"file_id": str(file.id)}
        )
    current = uow.repo(FileVersionRepository).get(file.current_version_id)
    require_version_read(uow, ctx, file, current)
    return views.file_view(file, version_view_of(uow, current))


SPEC = QuerySpec(
    name="artifacts.get_file",
    dto=GetFile,
    result=GetFileView,
    permission="file.read",
    scope_of=None,
    handler=handle,
    scope_resolver=file_scope_of_file,
)
