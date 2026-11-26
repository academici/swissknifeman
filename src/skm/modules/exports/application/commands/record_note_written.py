"""Append a receipt under the delivery generation's note lock."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, NotFound
from skm.kernel.ids import ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.exports.application.queries.list_pending_notes import (
    accessible_source,
    load_note_settings,
    validate_host,
)
from skm.modules.exports.domain.events import VaultNoteWritten
from skm.modules.exports.domain.note import VaultNote, VaultNoteId, VaultNoteWrite, validate_relative_path
from skm.modules.exports.generated.commands import RecordNoteWritten
from skm.modules.exports.generated.results import RecordNoteWrittenResult
from skm.modules.exports.ports import VaultNoteRepository

if TYPE_CHECKING:
    from skm.application_bus.context import CommandContext
    from skm.kernel.ports_uow import UnitOfWork


def scoped_note(uow: UnitOfWork, project_id: UUID, note_id: UUID, *, lock: bool = True) -> VaultNote:
    note = uow.repo(VaultNoteRepository).get(VaultNoteId(note_id), for_update=lock)
    if note.project_id != project_id:
        raise NotFound(ErrorCode.NOT_FOUND, "Vault note not found")
    return note


def _admit(ctx: CommandContext, uow: UnitOfWork, note: VaultNote):
    host = validate_host(ctx, uow, note.workspace_id, project_id=note.project_id)
    if accessible_source(ctx, uow, note, delivery=False) is None:
        raise Forbidden(ErrorCode.FORBIDDEN, "Vault note source access denied")
    return host


def replay_guard(cmd: RecordNoteWritten, ctx: CommandContext, uow: UnitOfWork) -> None:
    _admit(ctx, uow, scoped_note(uow, cmd.project_id, cmd.note_id, lock=False))


def handle(cmd: RecordNoteWritten, ctx: CommandContext, uow: UnitOfWork) -> RecordNoteWrittenResult:
    validate_relative_path(cmd.relative_path)
    note = scoped_note(uow, cmd.project_id, cmd.note_id)
    host = _admit(ctx, uow, note)
    now = ctx.clock.now()
    write = VaultNoteWrite(
        note.id,
        cmd.vault_id,
        cmd.generation,
        host,
        cmd.relative_path,
        cmd.outcome,
        cmd.expected_digest,
        cmd.observed_digest,
        now,
    )
    recorded = uow.repo(VaultNoteRepository).add_write(
        write,
        now=now,
        ttl_days=load_note_settings(ctx.config).pending_ttl_days,
    )
    if recorded:
        uow.record(VaultNoteWritten(note.workspace_id, write))
    return RecordNoteWrittenResult(recorded, note.id, cmd.vault_id, cmd.generation)


SPEC = CommandSpec(
    name="exports.record_note_written",
    dto=RecordNoteWritten,
    result=RecordNoteWrittenResult,
    permission="export.run",
    scope_of=lambda cmd: ScopeRef(ScopeKind.PROJECT, ScopeId(cmd.project_id)),
    idempotency=IdempotencyMode.REQUIRED,
    handler=handle,
    replay_guard=replay_guard,
)
