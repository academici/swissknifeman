"""Storage backend descriptor; the root lives in configuration, not here."""

import re
from dataclasses import dataclass
from enum import StrEnum

__all__ = ["BackendKind", "BackendState", "StorageBackend"]


_BACKEND_ID = re.compile(r"[a-z][a-z0-9-]{1,31}")


class BackendKind(StrEnum):
    LOCAL = "local"
    S3 = "s3"


class BackendState(StrEnum):
    ACTIVE = "active"
    READONLY = "readonly"
    RETIRED = "retired"


@dataclass(frozen=True, slots=True)
class StorageBackend:
    id: str
    kind: BackendKind
    config_ref: str
    state: BackendState

    def __post_init__(self) -> None:
        if not _BACKEND_ID.fullmatch(self.id):
            raise ValueError("backend id must match ^[a-z][a-z0-9-]{1,31}$")
