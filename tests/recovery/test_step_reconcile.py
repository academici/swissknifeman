"""A real worker death during runtime closes its unfinished stage exactly once."""

import pytest

from fixtures.execution.harness import clean_test_database, expire, pg_session, recovery, test_database
from fixtures.execution.processes import scenario, script, worker
from fixtures.execution.recovery_process import (
    kill_runtime,
    process_case,
    restore_subreaper,
    running_identity,
)
from skm.modules.execution.ports import (
    AcceptanceRepository,
    BudgetRepository,
    StageRepository,
    StepRepository,
)
from support.service_runner import Instance

__all__ = ["clean_test_database", "pg_session", "recovery", "test_database"]
pytestmark = pytest.mark.pg


def test_runtime_during_step_fault_interrupts_and_settles_once(recovery):
    side = recovery
    case = process_case(side)
    fixture = scenario(side.root / "runtime-during-step.toml", "executor", hang=True)
    plan = script(side.root / "runtime-script.toml", [("executor", case.task.display_key, 1, fixture)])
    identity = None
    try:
        with worker(side, side.root / f"repository-{case.attempt.id}", plan) as process:
            stage, identity = running_identity(side, case, process)
            Instance.kill(process)
        kill_runtime(identity)
        identity = None
        assert expire(side)["expired"] == 1
        with side.uow(readonly=True) as uow:
            stage = uow.repo(StageRepository).get(stage.id)
            steps = uow.repo(StepRepository).for_stage(stage.id)
            assert stage.state.value == "interrupted"
            assert stage.outcome_kind.value == "runtime_error"
            assert all(step.state.value == "failed" and step.error_code == "LEASE_LOST" for step in steps)
            assert not uow.repo(BudgetRepository).open_for_steps(tuple(step.id for step in steps))
            assert not uow.repo(AcceptanceRepository).decisions_for_task(case.task.id)
    finally:
        if identity is not None:
            kill_runtime(identity)
        restore_subreaper(case)
