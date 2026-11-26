"""Convert explicit SQL queue and ledger rows to exports domain values."""

from typing import Any

from skm.kernel.ids import EventId, HostId, ProjectId, WorkspaceId
from skm.modules.exports.domain.note import NoteKind, VaultNote, VaultNoteId, VaultNoteState, VaultNoteWrite

__all__ = ["note_from_row", "write_from_row"]


def note_from_row(row: dict[str, Any]) -> VaultNote:
    return VaultNote(
        id=VaultNoteId(row["id"]),
        workspace_id=WorkspaceId(row["workspace_id"]),
        project_id=ProjectId(row["project_id"]),
        kind=NoteKind(row["kind"]),
        event_id=EventId(row["event_id"]),
        source_id=row["source_id"],
        name=row["name"],
        subfolder=row["subfolder"],
        body=row["body"],
        body_digest=row["body_digest"],
        state=VaultNoteState(row["state"]),
        generation=row["generation"],
        created_at=row["created_at"],
        requeued_at=row["requeued_at"],
    )


def write_from_row(row: dict[str, Any]) -> VaultNoteWrite:
    return VaultNoteWrite(
        note_id=VaultNoteId(row["note_id"]),
        vault_id=row["vault_id"],
        generation=row["generation"],
        host_id=HostId(row["host_id"]),
        relative_path=row["relative_path"],
        outcome=row["outcome"],
        expected_digest=row["expected_digest"],
        observed_digest=row["observed_digest"],
        written_at=row["written_at"],
    )
