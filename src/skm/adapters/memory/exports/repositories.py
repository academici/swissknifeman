"""In-memory queue and receipt ledger, serialized by the memory unit of work."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from uuid import UUID

from skm.adapters.memory.core.state import MemoryBackendState
from skm.adapters.memory.workspace.state import workspace_state
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, NotFound
from skm.kernel.ids import EventId, HostId, ProjectId, WorkspaceId
from skm.modules.exports.domain.note import (
    NoteKind,
    VaultNote,
    VaultNoteId,
    VaultNoteState,
    VaultNoteWrite,
    check_existing_write,
    check_generation,
    check_write,
    delivery_deadline,
    validate_relative_path,
)
from skm.modules.exports.ports import PENDING_SCAN_LIMIT, CandidatePage, NoteKey, candidate_page, note_key

from .state import exports_state

__all__ = ["MemoryVaultNoteRepository"]


class MemoryVaultNoteRepository:
    def __init__(self, state: MemoryBackendState) -> None:
        self._state = state
        self._rows = exports_state(state)

    def by_event(self, event_id: EventId, kind: NoteKind) -> VaultNote | None:
        identifier = self._rows.events.get((event_id, kind))
        return self._rows.notes[identifier] if identifier is not None else None

    def add(self, note: VaultNote) -> bool:
        self._state.core.require_writable()
        key = (note.event_id, note.kind)
        if key in self._rows.events:
            return False
        if note.id in self._rows.notes:
            raise Conflict(ErrorCode.ALREADY_EXISTS, "Vault note already exists")
        project = workspace_state(self._state).projects.get(note.project_id)
        if project is None or project.workspace_id != note.workspace_id:
            raise NotFound(ErrorCode.NOT_FOUND, "Vault note project missing")
        self._rows.notes[note.id] = note
        self._rows.events[key] = note.id
        return True

    def get(self, note_id: VaultNoteId, *, for_update: bool = False) -> VaultNote:
        if for_update:
            self._state.core.require_writable()
        note = self._rows.notes.get(note_id)
        if note is None:
            raise NotFound(ErrorCode.NOT_FOUND, "Vault note not found")
        return note

    def _checkout_projects(self, workspace_id: WorkspaceId, host_id: HostId) -> set[ProjectId]:
        ws = workspace_state(self._state)
        workspace, host = ws.workspaces.get(workspace_id), ws.hosts.get(host_id)
        if workspace is None or workspace.state != "active" or host is None or host.state != "active":
            return set()
        bound = {
            binding.repository_id
            for binding in ws.bindings.values()
            if binding.workspace_id == workspace_id
            and binding.host_id == host_id
            and binding.state == "active"
        }
        return {
            project_id
            for (project_id, _), mount in ws.mounts.items()
            if mount.repository_id in bound and ws.projects[project_id].state == "active"
        }

    def active_checkout(
        self, workspace_id: WorkspaceId, host_id: HostId, project_id: ProjectId | None = None
    ) -> bool:
        projects = self._checkout_projects(workspace_id, host_id)
        return bool(projects) if project_id is None else project_id in projects

    def pending_for_host(
        self,
        workspace_id: WorkspaceId,
        host_id: HostId,
        vault_id: UUID,
        *,
        now: datetime,
        ttl_days: int,
        after: NoteKey | None,
        scan_limit: int,
    ) -> CandidatePage:
        projects = self._checkout_projects(workspace_id, host_id)
        rows = sorted(
            (
                note
                for note in self._rows.notes.values()
                if note.workspace_id == workspace_id
                and note.project_id in projects
                and note.state == VaultNoteState.PENDING
                and now < delivery_deadline(note, ttl_days)
                and (note.id, vault_id, note.generation) not in self._rows.writes
                and (after is None or note_key(note) > after)
            ),
            key=note_key,
        )
        return candidate_page(rows, min(scan_limit, PENDING_SCAN_LIMIT))

    def list(self, project_id: ProjectId, *, after: NoteKey | None, limit: int) -> CandidatePage:
        rows = sorted(
            (
                note
                for note in self._rows.notes.values()
                if note.project_id == project_id and (after is None or note_key(note) > after)
            ),
            key=note_key,
        )
        return candidate_page(rows, limit)

    def add_write(self, w: VaultNoteWrite, *, now: datetime, ttl_days: int) -> bool:
        note = self.get(w.note_id, for_update=True)
        validate_relative_path(w.relative_path)
        check_write(note, w, now=now, ttl_days=ttl_days)
        key = (w.note_id, w.vault_id, w.generation)
        existing = self._rows.writes.get(key)
        if existing is not None:
            check_existing_write(existing, w)
            return False
        if w.host_id not in workspace_state(self._state).hosts:
            raise NotFound(ErrorCode.NOT_FOUND, "Vault note writer host missing")
        self._rows.writes[key] = w
        return True

    def writes(self, note_id: VaultNoteId) -> tuple[VaultNoteWrite, ...]:
        return tuple(
            sorted(
                (write for write in self._rows.writes.values() if write.note_id == note_id),
                key=lambda write: (write.generation, write.vault_id),
            )
        )

    def requeue(self, note_id: VaultNoteId, expected_generation: int, at: datetime) -> int:
        note = self.get(note_id, for_update=True)
        check_generation(note, expected_generation)
        generation = note.generation + 1
        self._rows.notes[note.id] = replace(
            note, generation=generation, requeued_at=at, state=VaultNoteState.PENDING
        )
        return generation

    def expire_due(self, now: datetime, ttl_days: int, *, limit: int) -> int:
        self._state.core.require_writable()
        rows = self._older(
            now - timedelta(days=ttl_days),
            limit,
            pending=True,
        )
        for note in rows:
            self._rows.notes[note.id] = replace(note, state=VaultNoteState.EXPIRED)
        return len(rows)

    def delete_older_than(self, cutoff: datetime, *, limit: int) -> int:
        self._state.core.require_writable()
        rows = self._older(cutoff, limit)
        removed = {note.id for note in rows}
        for note in rows:
            del self._rows.notes[note.id]
            del self._rows.events[(note.event_id, note.kind)]
        for key in tuple(self._rows.writes):
            if key[0] in removed:
                del self._rows.writes[key]
        return len(rows)

    def _older(self, cutoff: datetime, limit: int, *, pending: bool = False) -> tuple[VaultNote, ...]:
        return tuple(
            sorted(
                (
                    note
                    for note in self._rows.notes.values()
                    if (not pending or note.state == VaultNoteState.PENDING)
                    and (note.requeued_at or note.created_at) <= cutoff
                ),
                key=lambda note: (note.requeued_at or note.created_at, note.id),
            )[:limit]
        )
