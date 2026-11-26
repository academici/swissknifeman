"""Transactional storage for the memory vault queue and append-only ledger."""

from dataclasses import dataclass, field
from uuid import UUID

from skm.adapters.memory.core.state import MemoryBackendState
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError
from skm.kernel.ids import EventId
from skm.modules.exports.domain.note import NoteKind, VaultNote, VaultNoteId, VaultNoteWrite

__all__ = ["NoteState", "exports_state"]


@dataclass
class NoteState:
    notes: dict[VaultNoteId, VaultNote] = field(default_factory=dict[VaultNoteId, VaultNote])
    events: dict[tuple[EventId, NoteKind], VaultNoteId] = field(
        default_factory=dict[tuple[EventId, NoteKind], VaultNoteId]
    )
    writes: dict[tuple[VaultNoteId, UUID, int], VaultNoteWrite] = field(
        default_factory=dict[tuple[VaultNoteId, UUID, int], VaultNoteWrite]
    )


def exports_state(state: MemoryBackendState) -> NoteState:
    found = state.modules.get("exports")
    if found is None:
        found = NoteState()
        state.modules["exports"] = found
    if not isinstance(found, NoteState):
        raise InternalError(ErrorCode.INTERNAL_ERROR, "Invalid exports backend state")
    return found
