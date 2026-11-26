"""Open one new vault delivery generation and preserve receipt history."""

from __future__ import annotations

from typing import TYPE_CHECKING

from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.actor import PrincipalKind
from skm.kernel.ids import ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.exports.generated.commands import RequeueNote
from skm.modules.exports.generated.results import RequeueNoteResult
from skm.modules.exports.ports import VaultNoteRepository

from .record_note_written import scoped_note

if TYPE_CHECKING:
    from skm.application_bus.context import CommandContext
    from skm.kernel.ports_uow import UnitOfWork


def handle(cmd: RequeueNote, ctx: CommandContext, uow: UnitOfWork) -> RequeueNoteResult:
    note = scoped_note(uow, cmd.project_id, cmd.note_id)
    generation = uow.repo(VaultNoteRepository).requeue(note.id, cmd.expected_generation, ctx.clock.now())
    return RequeueNoteResult(generation)


SPEC = CommandSpec(
    name="exports.requeue_note",
    dto=RequeueNote,
    result=RequeueNoteResult,
    permission="export.run",
    scope_of=lambda cmd: ScopeRef(ScopeKind.PROJECT, ScopeId(cmd.project_id)),
    allowed_kinds=frozenset({PrincipalKind.HUMAN, PrincipalKind.SERVICE}),
    idempotency=IdempotencyMode.REQUIRED,
    handler=handle,
)
