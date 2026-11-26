"""Resume every persisted continuation without replaying selected semantic actions."""

from typing import Any

from skm.application_bus.registry import CommandSpec
from skm.kernel.actor import SYSTEM_PRINCIPAL_ID, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.execution.application._admission import require_run_admission
from skm.modules.execution.application._control import live_guard, lock_run, run_scope
from skm.modules.execution.application._events import cause, emit
from skm.modules.execution.application._state import effective_values
from skm.modules.execution.application.apply_action import resume_advance_attempts
from skm.modules.execution.domain.run import resume
from skm.modules.execution.generated.commands import ResumeRun
from skm.modules.execution.generated.results import ResumeRunResult
from skm.modules.execution.ports import RunRepository


def handle(cmd: ResumeRun, ctx: Any, uow: UnitOfWork) -> ResumeRunResult:
    if ctx.actor.principal_id == SYSTEM_PRINCIPAL_ID and cmd.expected_row_version is None:
        raise error_for(ErrorCode.VERSION_CONFLICT, "system resume requires the observed version")
    run = lock_run(uow, cmd.run_id, cmd.expected_row_version)
    if run.autopilot and run.pause_source == "owner" and ctx.actor.kind is not PrincipalKind.HUMAN:
        raise error_for(ErrorCode.FORBIDDEN, "an owner must release the campaign run pause")
    live_guard(uow, ctx, run)

    _, values = effective_values(uow, run.id)
    require_run_admission(uow, ctx, run, values)
    updated = resume(run)
    if updated != run:
        uow.repo(RunRepository).save(updated, expected_version=run.row_version)
        emit(
            uow,
            run,
            "run-resumed",
            {
                "by": str(ctx.actor.principal_id),
                "previous_stop_code": run.stop_code,
                "previous_pause_source": run.pause_source,
            },
            cause("operator_resume"),
        )

    resume_advance_attempts(uow, ctx, updated)
    latest = uow.repo(RunRepository).get(run.id)
    return ResumeRunResult(run.id, latest.status.value, latest.row_version)


SPEC = CommandSpec(
    name="execution.resume_run",
    dto=ResumeRun,
    result=ResumeRunResult,
    permission="run.control",
    scope_of=run_scope,
    handler=handle,
)
