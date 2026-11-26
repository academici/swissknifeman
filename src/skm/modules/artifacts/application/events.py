"""Domain events of the artifacts module (artifacts §9).

Grants produce no event (technical and frequent); the owning command of execution audits them. A payload
never carries a storage key, a location or a blob id: those are not part of the public contract.
"""

from dataclasses import dataclass
from typing import ClassVar, override
from uuid import UUID

from skm.kernel.events import DomainEvent
from skm.kernel.ids import FileVersionId, ProjectId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.modules.artifacts.domain.blob import ContentDigest
from skm.modules.artifacts.domain.classification import Classification
from skm.modules.artifacts.domain.content_safety import SafetyVerdict
from skm.modules.artifacts.domain.file import FileId, FileOrigin
from skm.modules.artifacts.generated import events as generated

__all__ = ["FileAdded", "FileRestored", "FileTrashed", "FileVersionAdded"]

_PREFIX = "urn:skm:artifacts:event:"


def _urn(name: str) -> str:
    return f"{_PREFIX}{name}:v1"


@dataclass(frozen=True, slots=True)
class FileAdded(DomainEvent):
    event_type: ClassVar[str] = _urn("file-added")
    stream_kind: ClassVar[str] = "file"

    file_id: FileId
    workspace_id: WorkspaceId
    project_id: ProjectId | None
    title: str
    origin: FileOrigin
    classification: Classification

    @override
    def stream_id(self) -> UUID:
        return self.file_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return generated.FileAdded(
            file_id=self.file_id,
            workspace_id=self.workspace_id,
            project_id=self.project_id,
            title=self.title,
            origin=generated.FileOrigin(self.origin.value),
            classification=generated.Classification(self.classification.value),
        ).to_json()


@dataclass(frozen=True, slots=True)
class FileVersionAdded(DomainEvent):
    event_type: ClassVar[str] = _urn("file-version-added")
    stream_kind: ClassVar[str] = "file"

    file_id: FileId
    workspace_id: WorkspaceId
    file_version_id: FileVersionId
    version_no: int
    size_bytes: int
    digest: ContentDigest
    safety_verdict: SafetyVerdict

    @override
    def stream_id(self) -> UUID:
        return self.file_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return generated.FileVersionAdded(
            file_id=self.file_id,
            file_version_id=self.file_version_id,
            version_no=self.version_no,
            size_bytes=self.size_bytes,
            digest=self.digest.value,
            safety_verdict=self.safety_verdict,
        ).to_json()


@dataclass(frozen=True, slots=True)
class FileTrashed(DomainEvent):
    event_type: ClassVar[str] = _urn("file-trashed")
    stream_kind: ClassVar[str] = "file"

    file_id: FileId
    workspace_id: WorkspaceId
    reason: str

    @override
    def stream_id(self) -> UUID:
        return self.file_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return generated.FileTrashed(file_id=self.file_id, reason=self.reason).to_json()


@dataclass(frozen=True, slots=True)
class FileRestored(DomainEvent):
    event_type: ClassVar[str] = _urn("file-restored")
    stream_kind: ClassVar[str] = "file"

    file_id: FileId
    workspace_id: WorkspaceId

    @override
    def stream_id(self) -> UUID:
        return self.file_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return generated.FileRestored(file_id=self.file_id).to_json()
