"""``workspace.record_worker_heartbeat`` (workspace §7).

Only the principal of the worker may send its heartbeat. A heartbeat is not an event unless it changes the
state (``offline -> online``); it touches the host. The DTO names a worker, which is not a scope: the bus
checks the self right and this handler decides ``worker.claim`` on the worker's workspace.
"""

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden
from skm.kernel.ids import WorkerId
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.workspace.application.events import WorkerStateChanged
from skm.modules.workspace.application.guards import SELF_PERMISSION, allow_unconfined, require
from skm.modules.workspace.application.views import capabilities_from_document
from skm.modules.workspace.domain import worker as worker_rules
from skm.modules.workspace.generated.commands import RecordWorkerHeartbeat
from skm.modules.workspace.generated.results import RecordWorkerHeartbeatResult
from skm.modules.workspace.ports import HostRepository, WorkerRepository

__all__ = ["PERMISSION", "SPEC", "handle"]

PERMISSION = "worker.claim"


def handle(cmd: RecordWorkerHeartbeat, ctx: CommandContext, uow: UnitOfWork) -> RecordWorkerHeartbeatResult:
    workers = uow.repo(WorkerRepository)
    worker = workers.get(WorkerId(cmd.worker_id))
    grant = ctx.actor.grant
    if worker.principal_id != ctx.actor.principal_id or (
        grant is not None and grant.worker_id not in (None, worker.id)
    ):
        raise Forbidden(
            ErrorCode.FORBIDDEN,
            "only the principal of the worker sends its heartbeat",
            details={"permission": PERMISSION, "reason": "not_worker_principal"},
        )
    require(uow, ctx.clock, ctx.actor, PERMISSION, worker.workspace_id)
    capabilities = None if cmd.capabilities is None else capabilities_from_document(cmd.capabilities)
    if capabilities is not None:
        worker_rules.ensure_unconfined_allowed(capabilities, allow_unconfined=allow_unconfined(ctx))
    now = ctx.clock.now()
    beaten = workers.heartbeat(worker.id, now, capabilities)
    if beaten.state is not worker.state:
        uow.record(WorkerStateChanged(worker.id, worker.workspace_id, worker.state, beaten.state))
    uow.repo(HostRepository).touch(worker.host_id, now)
    return RecordWorkerHeartbeatResult(worker_id=beaten.id, state=beaten.state.value, last_heartbeat_at=now)


SPEC = CommandSpec(
    name="workspace.record_worker_heartbeat",
    dto=RecordWorkerHeartbeat,
    result=RecordWorkerHeartbeatResult,
    permission=SELF_PERMISSION,
    scope_of=None,
    idempotency=IdempotencyMode.OPTIONAL,
    handler=handle,
)
