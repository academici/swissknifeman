"""``workspace.set_worker_state`` (workspace §7).

``retired`` also revokes the tokens of the worker and disables its principal through the access facade, in
the same transaction. The DTO names a worker, which is not a scope: the bus checks the self right and this
handler decides ``worker.register`` on the worker's workspace.
"""

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.ids import WorkerId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.versions import ExpectedVersion, check_expected
from skm.modules.access.public import revoke_principal_tokens
from skm.modules.workspace.application.events import WorkerStateChanged
from skm.modules.workspace.application.guards import SELF_PERMISSION, require
from skm.modules.workspace.domain import worker as worker_rules
from skm.modules.workspace.domain.worker import WorkerState
from skm.modules.workspace.generated.commands import SetWorkerState
from skm.modules.workspace.generated.results import SetWorkerStateResult
from skm.modules.workspace.ports import WorkerRepository

__all__ = ["PERMISSION", "SPEC", "handle"]

PERMISSION = "worker.register"


def handle(cmd: SetWorkerState, ctx: CommandContext, uow: UnitOfWork) -> SetWorkerStateResult:
    workers = uow.repo(WorkerRepository)
    worker = workers.get(WorkerId(cmd.worker_id))
    require(uow, ctx.clock, ctx.actor, PERMISSION, worker.workspace_id)
    check_expected(worker.row_version, ExpectedVersion(cmd.expected_row_version))
    target = WorkerState(cmd.state)
    changed = worker_rules.set_state(worker, target)
    if changed is not worker:  # the same state again changes nothing and records nothing
        workers.save(changed, expected_version=worker.row_version)
        if target is WorkerState.RETIRED:
            revoke_principal_tokens(
                uow, worker.principal_id, by=ctx.actor.principal_id, now=ctx.clock.now(), disable=True
            )
        uow.record(WorkerStateChanged(worker.id, worker.workspace_id, worker.state, changed.state))
    return SetWorkerStateResult(
        worker_id=changed.id, state=changed.state.value, row_version=changed.row_version
    )


SPEC = CommandSpec(
    name="workspace.set_worker_state",
    dto=SetWorkerState,
    result=SetWorkerStateResult,
    permission=SELF_PERMISSION,
    scope_of=None,
    idempotency=IdempotencyMode.OPTIONAL,
    handler=handle,
)
