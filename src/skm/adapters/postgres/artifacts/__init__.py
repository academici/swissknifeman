"""PostgreSQL adapters of the artifacts repository ports (artifacts §3, §6, §11).

``REPOSITORIES`` maps each port to its factory over the transaction connection. ``BlobContentReader`` defaults
to an unbound ``PostgresBlobContentReader`` until host composition supplies a ``BlobStore``.
"""

from collections.abc import Callable, Mapping
from types import MappingProxyType

import psycopg

from skm.adapters.postgres.artifacts.blob_coordination import PostgresBlobDigestLock
from skm.adapters.postgres.artifacts.repositories import (
    PostgresAccessGrantRepository,
    PostgresBlobContentReader,
    PostgresBlobRepository,
    PostgresFileRepository,
    PostgresFileVersionRepository,
    PostgresStagedBlobRepository,
)
from skm.modules.artifacts.ports import (
    AccessGrantRepository,
    BlobContentReader,
    BlobDigestLock,
    BlobRepository,
    FileRepository,
    FileVersionRepository,
    StagedBlobRepository,
)

__all__ = ["REPOSITORIES"]

REPOSITORIES: Mapping[type, Callable[[psycopg.Connection], object]] = MappingProxyType(
    {
        StagedBlobRepository: PostgresStagedBlobRepository,
        BlobRepository: PostgresBlobRepository,
        FileRepository: PostgresFileRepository,
        FileVersionRepository: PostgresFileVersionRepository,
        AccessGrantRepository: PostgresAccessGrantRepository,
        BlobContentReader: PostgresBlobContentReader,
        BlobDigestLock: PostgresBlobDigestLock,
    }
)
