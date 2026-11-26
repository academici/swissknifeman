"""Stable import facade for the PostgreSQL artifacts repository adapters.

Concrete adapters and SQL live in blobs.py, files.py and grants.py; row codecs and
write guards live in mapping.py. Composition still imports these classes here.
"""

from skm.adapters.postgres.artifacts.blobs import (
    PostgresBlobContentReader,
    PostgresBlobRepository,
    PostgresStagedBlobRepository,
)
from skm.adapters.postgres.artifacts.files import PostgresFileRepository, PostgresFileVersionRepository
from skm.adapters.postgres.artifacts.grants import PostgresAccessGrantRepository

__all__ = [
    "PostgresAccessGrantRepository",
    "PostgresBlobContentReader",
    "PostgresBlobRepository",
    "PostgresFileRepository",
    "PostgresFileVersionRepository",
    "PostgresStagedBlobRepository",
]
