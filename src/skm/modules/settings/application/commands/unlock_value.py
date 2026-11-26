"""``settings.unlock_value`` (settings §A.7.5): the mirror of ``lock_value`` (history ``unlocked``,
``ConfigUnlocked``; ``shadowed_below`` counts the descendant entries that take effect again)."""

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.settings.application.rights import BASE_PERMISSION
from skm.modules.settings.application.scopes import bus_scope_of
from skm.modules.settings.generated.commands import UnlockValue
from skm.modules.settings.generated.results import UnlockValueResult

from .lock_value import change_lock, permissions_of

__all__ = ["SPEC", "handle"]


def handle(cmd: UnlockValue, ctx: CommandContext, uow: UnitOfWork) -> UnlockValueResult:
    entry, changed, generation, shadowed = change_lock(cmd, ctx, uow, locked=False)
    return UnlockValueResult(entry=entry, changed=changed, generation=generation, shadowed_below=shadowed)


SPEC = CommandSpec(
    name="settings.unlock_value",
    dto=UnlockValue,
    result=UnlockValueResult,
    permission=BASE_PERMISSION,
    scope_of=bus_scope_of(lambda cmd: cmd.scope),
    handler=handle,
    permissions_of=permissions_of,
)
