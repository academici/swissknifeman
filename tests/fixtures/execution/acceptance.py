"""An accept-ready attempt; mutations under test remain in the real AcceptanceGate."""

from contracts.execution.seed_helpers import seed_output, seed_stage, seed_step
from skm.modules.artifacts.public import BindingRole
from skm.modules.execution.application._primitives import save_attempt
from skm.modules.execution.domain.attempt import record_output
from skm.modules.execution.domain.check_execution import CheckExecution, CheckKind, CheckState
from skm.modules.execution.domain.manual_verdict import ManualVerdict
from skm.modules.execution.domain.output import OutputSource
from skm.modules.execution.domain.stage_record import StageState
from skm.modules.execution.domain.step import StepState
from skm.modules.execution.domain.task import TaskStatus
from skm.modules.execution.ports import CheckRepository, EvidenceBindingRepository
from skm.modules.planning import public as planning
from unit.execution.application._support import seeded


def seed_accept_ready(side, uow, run, task, attempt, manifest):
    """Seed a passed manual check with bound evidence on a fresh executor output; return the output.

    ``manifest`` comes from ``side.make_final_manifest()``, which needs its own unit of work.
    """
    stage = seed_stage(side, uow, attempt, state=StageState.COMPLETED)
    step = seed_step(
        side,
        uow,
        attempt,
        stage,
        manifest_id=manifest,
        state=StepState.SUCCEEDED,
        result={"self_check": {"performed": True}},
    )
    output = seed_output(side, uow, attempt, source=OutputSource.EXECUTOR, step_id=step.id)
    save_attempt(uow, record_output(attempt, output, previous=None))
    spec = planning.get_revision_specification(uow, run.revision_id)
    check = CheckExecution(
        side.new_id(),
        side.ws,
        run.id,
        task.id,
        attempt.id,
        output.id,
        spec.checks[0].id,
        "P1.1:V1",
        CheckKind.MANUAL,
        True,
        CheckState.PASSED,
        None,
        "verified",
        None,
        None,
        "sha256:" + "1" * 64,
        None,
        None,
        1,
    )
    uow.repo(CheckRepository).add_many((check,))
    uow.repo(CheckRepository).add_verdict(
        ManualVerdict(
            side.new_id(), check.id, side.owner.principal_id, "pass", "verified", side.clock.now(), None
        )
    )
    uow.repo(EvidenceBindingRepository).bind("output", output.id, (side.fv1,), BindingRole.EVIDENCE)
    return output


def acceptance_case(side):
    run, task, attempt = seeded(side, task_status=TaskStatus.CHECKING)
    manifest = side.make_final_manifest()
    with side.uow() as uow:
        seed_accept_ready(side, uow, run, task, attempt, manifest)
        uow.commit()
    return run, task, attempt
