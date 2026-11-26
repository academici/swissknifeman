"""``workspace.register_host`` (workspace §7, §18 K17): a machine, instance level, registered by a person."""

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict
from skm.kernel.ids import HostId, ScopeId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRegistry
from skm.modules.workspace.application.events import HostRegistered
from skm.modules.workspace.application.views import platform_from_document
from skm.modules.workspace.domain import host as host_rules
from skm.modules.workspace.domain.host import HostName
from skm.modules.workspace.generated.commands import RegisterHost
from skm.modules.workspace.generated.results import RegisterHostResult
from skm.modules.workspace.ports import HostRepository

__all__ = ["SPEC", "handle"]


def handle(cmd: RegisterHost, ctx: CommandContext, uow: UnitOfWork) -> RegisterHostResult:
    hosts = uow.repo(HostRepository)
    name = HostName(cmd.name)
    if hosts.find_by_name(name.value) is not None:
        raise Conflict(ErrorCode.ALREADY_EXISTS, "host name already used", details={"name": name.value})
    host = host_rules.new_host(
        host_id=HostId(ctx.ids.new_id()),
        name=name,
        platform=platform_from_document(cmd.platform.os.value, cmd.platform.arch.value),
        now=ctx.clock.now(),
    )
    uow.repo(ScopeRegistry).create(ScopeId(host.id), ScopeKind.HOST, parent=ctx.scope.id, workspace_id=None)
    hosts.add(host)
    uow.record(HostRegistered(host.id, host.name, host.platform))
    return RegisterHostResult(host_id=host.id, name=host.name)


SPEC = CommandSpec(
    name="workspace.register_host",
    dto=RegisterHost,
    result=RegisterHostResult,
    permission="host.manage",
    scope_of=None,
    idempotency=IdempotencyMode.OPTIONAL,
    handler=handle,
    allowed_kinds=frozenset({PrincipalKind.HUMAN, PrincipalKind.SERVICE}),  # a worker never registers a host
)
