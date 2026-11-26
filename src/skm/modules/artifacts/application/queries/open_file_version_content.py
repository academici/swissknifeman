"""``artifacts.open_file_version_content`` (artifacts §8, §14): the handle a surface streams the bytes from.

Authorised exactly like ``get_file_version`` (resolved stored file scope plus the worker grant). The
handle carries the address of the bytes, never an access token: every new open is decided again, so a revoked
grant refuses the next open while a stream opened earlier (immutable bytes) may still finish. A version
without a present location is ``FILE_VERSION_NOT_READY``.
"""

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.ids import FileVersionId
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.artifacts.application.guards import (
    file_scope_of_version,
    require_bound,
    require_version_read,
)
from skm.modules.artifacts.application.reads import require_present_location, version_blob
from skm.modules.artifacts.domain.upload_rules import media_type_consistent
from skm.modules.artifacts.generated.queries import OpenFileVersionContent
from skm.modules.artifacts.generated.views import OpenFileVersionContentView
from skm.modules.artifacts.ports import FileRepository, FileVersionRepository

__all__ = ["SPEC", "handle"]

_OPAQUE = "application/octet-stream"


def handle(query: OpenFileVersionContent, ctx: QueryContext, uow: UnitOfWork) -> OpenFileVersionContentView:
    version = uow.repo(FileVersionRepository).get(FileVersionId(query.file_version_id))
    file = uow.repo(FileRepository).get(version.file_id)
    require_bound(ctx, file)
    require_version_read(uow, ctx, file, version)
    blob = version_blob(uow, version)
    location = require_present_location(uow, blob, version)
    declared = version.declared_media_type
    # The declared type is trusted only when the signature agrees; otherwise the bytes are opaque (G21).
    served = (
        declared
        if declared is not None and media_type_consistent(declared, blob.detected_media_type)
        else _OPAQUE
    )
    return OpenFileVersionContentView(
        location={
            "backend_id": location.backend_id,
            "storage_key": location.storage_key,
            "storage_version": location.storage_version,
        },
        size_bytes=blob.size_bytes,
        digest=blob.digest.value,
        media_type=served,
        filename=version.original_filename,
    )


SPEC = QuerySpec(
    name="artifacts.open_file_version_content",
    dto=OpenFileVersionContent,
    result=OpenFileVersionContentView,
    permission="file.read",
    scope_of=None,
    handler=handle,
    scope_resolver=file_scope_of_version,
)
