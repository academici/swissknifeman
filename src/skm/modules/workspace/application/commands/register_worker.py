"""``workspace.register_worker`` (workspace §7): the identity of an execution process on one host.

The principal, its ``worker`` membership and its token are created here, through the access facade, in the
same transaction as the ``Worker`` row. The secret is in the result and nowhere else, so a key is refused:
a replay could not return it.
"""

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.actor import Actor
from skm.kernel.ids import HostId, ScopeId, WorkerId, WorkspaceId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.access.public import AccessSettings, TokenId, TokenPepperSource, create_worker_principal
from skm.modules.workspace.application.events import WorkerRegistered
from skm.modules.workspace.application.guards import allow_unconfined, require_active_workspace
from skm.modules.workspace.application.views import capabilities_from_document
from skm.modules.workspace.domain import host as host_rules
from skm.modules.workspace.domain import worker as worker_rules
from skm.modules.workspace.generated.commands import RegisterWorker
from skm.modules.workspace.generated.results import RegisterWorkerResult
from skm.modules.workspace.ports import HostRepository, WorkerRepository

__all__ = ["SPEC", "handle"]


def handle(cmd: RegisterWorker, ctx: CommandContext, uow: UnitOfWork) -> RegisterWorkerResult:
    result, _ = register(cmd, ctx, uow, ctx.actor)
    return result


def register(
    cmd: RegisterWorker, ctx: CommandContext, uow: UnitOfWork, issuer: Actor
) -> tuple[RegisterWorkerResult, TokenId]:
    """Register the worker and issue its credential in the caller's transaction."""
    workspace = require_active_workspace(uow, WorkspaceId(cmd.workspace_id))
    host = uow.repo(HostRepository).get(HostId(cmd.host_id))
    host_rules.require_active(host)
    capabilities = capabilities_from_document(cmd.capabilities)
    worker_rules.ensure_unconfined_allowed(capabilities, allow_unconfined=allow_unconfined(ctx))
    now = ctx.clock.now()
    worker_id = WorkerId(ctx.ids.new_id())
    principal_id, token_id, secret = create_worker_principal(
        uow,
        display_name=cmd.display_name,
        workspace_scope_id=ScopeId(workspace.id),
        issuer=issuer,
        worker_id=worker_id,
        host_scope_id=ScopeId(host.id),
        token_name=f"worker-{worker_id}",
        pepper=ctx.gateways.get(TokenPepperSource).pepper(),
        entropy=ctx.entropy.bytes,
        now=now,
        settings=ctx.config.section(AccessSettings),
    )
    worker = worker_rules.new_worker(
        worker_id=worker_id,
        workspace_id=workspace.id,
        host_id=host.id,
        principal_id=principal_id,
        display_name=cmd.display_name,
        capabilities=capabilities,
        now=now,
    )
    uow.repo(WorkerRepository).add(worker)
    uow.record(WorkerRegistered(worker.id, workspace.id, host.id, principal_id, capabilities))
    return RegisterWorkerResult(worker_id=worker.id, principal_id=principal_id, token_secret=secret), token_id


SPEC = CommandSpec(
    name="workspace.register_worker",
    dto=RegisterWorker,
    result=RegisterWorkerResult,
    permission="worker.register",
    scope_of=lambda cmd: ScopeRef(ScopeKind.WORKSPACE, ScopeId(cmd.workspace_id)),
    idempotency=IdempotencyMode.FORBIDDEN,
    handler=handle,
)
