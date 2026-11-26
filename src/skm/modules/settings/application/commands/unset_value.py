"""``settings.unset_value`` (settings §A.7.2): an ``op=unset`` entry, the reset to the default on this level.

Unlike ``remove_value`` the entry stays and hides every farther contribution except the default (§B.5.2);
R4 refuses it for monotonic keys (``narrow``, ``union``). The algorithm is ``set_value``'s.
"""

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.settings.application.rights import BASE_PERMISSION, write_permissions
from skm.modules.settings.application.scopes import bus_scope_of
from skm.modules.settings.domain.entry import EntryOp
from skm.modules.settings.generated.commands import UnsetValue
from skm.modules.settings.generated.results import UnsetValueResult

from .set_value import write_value

__all__ = ["SPEC", "handle"]


def permissions_of(cmd: UnsetValue) -> tuple[str, ...]:
    return write_permissions(cmd.scope.level, (cmd.key,), lock_change=False)


def handle(cmd: UnsetValue, ctx: CommandContext, uow: UnitOfWork) -> UnsetValueResult:
    entry, changed, generation, effective = write_value(
        cmd, ctx, uow, op=EntryOp.UNSET, value=None, locked=None
    )
    return UnsetValueResult(entry=entry, changed=changed, generation=generation, effective=effective)


SPEC = CommandSpec(
    name="settings.unset_value",
    dto=UnsetValue,
    result=UnsetValueResult,
    permission=BASE_PERMISSION,
    scope_of=bus_scope_of(lambda cmd: cmd.scope),
    handler=handle,
    permissions_of=permissions_of,
)
