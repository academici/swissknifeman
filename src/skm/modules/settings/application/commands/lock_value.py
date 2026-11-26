"""``settings.lock_value`` (settings §A.7.4); ``change_lock`` is shared with ``settings.unlock_value``.

Rules R1, R3, R9 (lock only), R10, R11, R12, R13, R16. A lock flag that already has the requested value is a
no-op (``changed=false``, nothing written). ``shadowed_below`` counts the entries of the key in descendant
scopes that the lock now hides (unlock: that take effect again); they are not removed.
"""

from typing import cast

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.settings.application.rights import BASE_PERMISSION, write_permissions
from skm.modules.settings.application.scopes import bus_scope_of
from skm.modules.settings.application.write_flow import WriteSession, entry_view
from skm.modules.settings.domain.entry import ConfigEntry
from skm.modules.settings.domain.write_rules import check_write
from skm.modules.settings.generated.commands import LockValue, UnlockValue
from skm.modules.settings.generated.results import LockValueResult
from skm.modules.settings.generated.views import EntryView

__all__ = ["SPEC", "change_lock", "handle"]


def permissions_of(cmd: LockValue | UnlockValue) -> tuple[str, ...]:
    return write_permissions(cmd.scope.level, (cmd.key,), lock_change=True)


def change_lock(
    cmd: LockValue | UnlockValue, ctx: CommandContext, uow: UnitOfWork, *, locked: bool
) -> tuple[EntryView, bool, int, int]:
    """``(entry, changed, generation, shadowed_below)`` of a lock or unlock."""
    session = WriteSession(ctx, uow, cmd.scope, reason=cmd.reason)
    key, target = cmd.key, session.target
    existing = session.entries.find(target.scope.id, key, for_update=True)
    request = session.request(
        key,
        action="lock" if locked else "unlock",
        expected_row_version=cmd.expected_row_version,
        confirmed=cmd.confirmed,
    )
    check_write(request, session.context(request, existing))
    entry = cast("ConfigEntry", existing)  # R12 refused a missing entry
    spec = session.registry.find(key)
    shadowed = session.entries.count_shadowed_below(target.scope.id, key)
    write = session.build(key, entry, op=entry.op, value=entry.value, locked=locked)
    if write is None:
        return entry_view(entry, target.label, spec), False, session.counter.current(), shadowed
    generation = session.persist((write,))
    session.record_locks((write,), generation)
    after = cast("ConfigEntry", write.after)
    return entry_view(after, target.label, spec), True, generation, shadowed


def handle(cmd: LockValue, ctx: CommandContext, uow: UnitOfWork) -> LockValueResult:
    entry, changed, generation, shadowed = change_lock(cmd, ctx, uow, locked=True)
    return LockValueResult(entry=entry, changed=changed, generation=generation, shadowed_below=shadowed)


SPEC = CommandSpec(
    name="settings.lock_value",
    dto=LockValue,
    result=LockValueResult,
    permission=BASE_PERMISSION,
    scope_of=bus_scope_of(lambda cmd: cmd.scope),
    handler=handle,
    permissions_of=permissions_of,
)
