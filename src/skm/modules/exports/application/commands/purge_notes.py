"""Expire pending generations and purge retained notes with their receipts."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.modules.exports.application.queries.list_pending_notes import load_note_settings
from skm.modules.exports.generated.commands import PurgeNotes
from skm.modules.exports.generated.results import PurgeNotesResult
from skm.modules.exports.ports import VaultNoteRepository

if TYPE_CHECKING:
    from skm.application_bus.context import CommandContext
    from skm.kernel.ports_uow import UnitOfWork


def handle(cmd: PurgeNotes, ctx: CommandContext, uow: UnitOfWork) -> PurgeNotesResult:
    now = ctx.clock.now()
    settings = load_note_settings(ctx.config)
    repo = uow.repo(VaultNoteRepository)
    expired = repo.expire_due(now, settings.pending_ttl_days, limit=cmd.batch)
    if expired:
        ctx.log.info("exports.notes.expired", count=expired)
    return PurgeNotesResult(
        repo.delete_older_than(now - timedelta(days=settings.retention_days), limit=cmd.batch)
    )


SPEC = CommandSpec(
    name="exports.purge_notes",
    dto=PurgeNotes,
    result=PurgeNotesResult,
    permission="system.internal",
    scope_of=None,
    internal=True,
    audit=False,
    idempotency=IdempotencyMode.FORBIDDEN,
    handler=handle,
)
