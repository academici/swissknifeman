"""``settings.remove_value`` (settings §A.7.3): delete the entry of this level, the key falls back to the
farther levels. Removing a ``narrow`` entry of a nearer level is allowed: the farther ceiling returns.

Rules R1, R3, R10, R11, R12, R13 (a locked entry needs ``config.lock``) and R16; R14 on the candidate without
the entry; then the conditional delete, one generation, history ``removed`` and ``ConfigChanged``.
"""

from typing import cast

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.settings.application.preview import chain_kind
from skm.modules.settings.application.rights import BASE_PERMISSION, write_permissions
from skm.modules.settings.application.scopes import bus_scope_of
from skm.modules.settings.application.write_flow import (
    WriteSession,
    candidate_problems,
    effective_view,
    raise_problems,
)
from skm.modules.settings.domain.entry import ConfigEntry
from skm.modules.settings.domain.write_rules import check_write
from skm.modules.settings.generated.commands import RemoveValue
from skm.modules.settings.generated.results import RemoveValueResult

__all__ = ["SPEC", "handle"]


def permissions_of(cmd: RemoveValue) -> tuple[str, ...]:
    return write_permissions(cmd.scope.level, (cmd.key,), lock_change=False)


def handle(cmd: RemoveValue, ctx: CommandContext, uow: UnitOfWork) -> RemoveValueResult:
    session = WriteSession(ctx, uow, cmd.scope, reason=cmd.reason)
    key, target = cmd.key, session.target
    existing = session.entries.find(target.scope.id, key, for_update=True)
    request = session.request(
        key, action="remove", expected_row_version=cmd.expected_row_version, confirmed=cmd.confirmed
    )
    check_write(request, session.context(request, existing))  # R1, R3, R10-R13, R16
    entry = cast("ConfigEntry", existing)  # R12 refused a missing entry
    spec = session.registry.spec(key)
    candidate = session.candidate({key: None})[chain_kind(target.ref.level, spec)]
    raise_problems(candidate_problems(candidate, (key,)))  # R14
    write = session.removal(entry)
    generation = session.persist((write,))
    session.record_changed((write,), generation)
    return RemoveValueResult(
        removed_entry_id=entry.id,
        generation=generation,
        effective=effective_view(candidate.resolution(key), spec),
    )


SPEC = CommandSpec(
    name="settings.remove_value",
    dto=RemoveValue,
    result=RemoveValueResult,
    permission=BASE_PERMISSION,
    scope_of=bus_scope_of(lambda cmd: cmd.scope),
    handler=handle,
    permissions_of=permissions_of,
)
