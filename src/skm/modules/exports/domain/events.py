"""Metadata-only queue and write events."""

from dataclasses import dataclass
from typing import ClassVar, override
from uuid import UUID

from skm.kernel.events import DomainEvent
from skm.kernel.ids import WorkspaceId
from skm.kernel.json_types import JsonObject

from .note import VaultNote, VaultNoteWrite

EVENT_TYPES = (
    "urn:skm:exports:event:vault-note-queued:v1",
    "urn:skm:exports:event:vault-note-written:v1",
)


@dataclass(frozen=True, slots=True)
class VaultNoteQueued(DomainEvent):
    event_type: ClassVar[str] = EVENT_TYPES[0]
    stream_kind: ClassVar[str] = "vault_note"

    note: VaultNote

    @override
    def stream_id(self) -> UUID:
        return self.note.id

    @override
    def scope_workspace_id(self) -> WorkspaceId:
        return self.note.workspace_id

    @override
    def payload(self) -> JsonObject:
        return {
            "note_id": str(self.note.id),
            "project_id": str(self.note.project_id),
            "kind": self.note.kind.value,
            "event_id": str(self.note.event_id),
            "name": self.note.name,
        }


@dataclass(frozen=True, slots=True)
class VaultNoteWritten(DomainEvent):
    event_type: ClassVar[str] = EVENT_TYPES[1]
    stream_kind: ClassVar[str] = "vault_note"

    workspace_id: WorkspaceId
    write: VaultNoteWrite

    @override
    def stream_id(self) -> UUID:
        return self.write.note_id

    @override
    def scope_workspace_id(self) -> WorkspaceId:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return {
            "note_id": str(self.write.note_id),
            "vault_id": str(self.write.vault_id),
            "generation": self.write.generation,
            "host_id": str(self.write.host_id),
            "relative_path": self.write.relative_path,
            "outcome": self.write.outcome,
        }
