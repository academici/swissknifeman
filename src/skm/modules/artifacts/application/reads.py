"""Read side shared by the artifacts queries and the facade (artifacts §8, §13).

A version is *ready* when its blob is available and one of its locations is present. Nothing here checks a
permission: the query handlers (``guards``) and the facade callers (already authorised handlers) do.
"""

from typing import BinaryIO

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.artifacts.application import views
from skm.modules.artifacts.domain.blob import Blob, BlobAvailability, BlobLocation, LocationState
from skm.modules.artifacts.domain.file import File, FileState
from skm.modules.artifacts.domain.file_version import FileVersion
from skm.modules.artifacts.generated.views import FileVersionView
from skm.modules.artifacts.ports import BlobContentReader, BlobRepository

__all__ = [
    "open_text",
    "present_location",
    "read_up_to",
    "ready",
    "require_present_location",
    "version_blob",
    "version_view_of",
]


def version_blob(uow: UnitOfWork, version: FileVersion) -> Blob:
    return uow.repo(BlobRepository).get(version.blob_id)


def version_view_of(uow: UnitOfWork, version: FileVersion) -> FileVersionView:
    return views.version_view(version, version_blob(uow, version))


def present_location(uow: UnitOfWork, blob: Blob) -> BlobLocation | None:
    if blob.availability is not BlobAvailability.AVAILABLE:
        return None
    return next(
        (item for item in uow.repo(BlobRepository).locations(blob.id) if item.state is LocationState.PRESENT),
        None,
    )


def ready(uow: UnitOfWork, file: File, version: FileVersion) -> bool:
    """An active file whose version has bytes in a present location."""
    return file.state is FileState.ACTIVE and present_location(uow, version_blob(uow, version)) is not None


def require_present_location(uow: UnitOfWork, blob: Blob, version: FileVersion) -> BlobLocation:
    location = present_location(uow, blob)
    if location is None:
        raise PreconditionFailed(
            ErrorCode.FILE_VERSION_NOT_READY,
            "the bytes of this file version are not available",
            details={"ids": [str(version.id)]},
        )
    return location


def read_up_to(stream: BinaryIO, limit: int) -> bytes:
    """Up to ``limit`` bytes, fewer only at the end of the stream.

    ``read(n)`` of a stream may return less than ``n`` before the end (sockets, pipes, a store that hands out
    its chunks); one call is therefore never taken for "all there is". An empty read is the end.
    """
    chunks: list[bytes] = []
    remaining = limit
    while remaining > 0:
        chunk = stream.read(remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def open_text(reader: BlobContentReader, location: BlobLocation, *, max_bytes: int) -> bytes | None:
    """At most ``max_bytes`` of the object; ``None`` when it is longer (read one byte past the limit)."""
    with reader.open(
        {
            "backend_id": location.backend_id,
            "storage_key": location.storage_key,
            "storage_version": location.storage_version,
        }
    ) as stream:
        data = read_up_to(stream, max_bytes + 1)
    return None if len(data) > max_bytes else data
