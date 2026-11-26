"""Blob (content-addressed bytes, per workspace) and its locations; a digest is not an access right."""

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import NewType
from uuid import UUID

from skm.kernel.ids import WorkspaceId

__all__ = ["Blob", "BlobAvailability", "BlobId", "BlobLocation", "ContentDigest", "LocationState"]


class BlobAvailability(StrEnum):
    AVAILABLE = "available"
    MISSING = "missing"


class LocationState(StrEnum):
    PRESENT = "present"
    MISSING = "missing"


BlobId = NewType("BlobId", UUID)


_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


@dataclass(frozen=True, slots=True)
class ContentDigest:
    value: str

    def __post_init__(self) -> None:
        if not _DIGEST.fullmatch(self.value):
            raise ValueError("digest must be 'sha256:' followed by 64 lowercase hex characters")


@dataclass(frozen=True, slots=True)
class Blob:
    id: BlobId
    workspace_id: WorkspaceId
    digest: ContentDigest
    size_bytes: int
    detected_media_type: str
    availability: BlobAvailability
    created_at: datetime
    verified_at: datetime | None

    def __post_init__(self) -> None:
        if self.size_bytes < 0:
            raise ValueError("size_bytes must be >= 0")


@dataclass(frozen=True, slots=True)
class BlobLocation:
    blob_id: BlobId
    backend_id: str
    storage_key: str
    storage_version: str | None
    state: LocationState
    verified_at: datetime | None
