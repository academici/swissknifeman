"""Restart the real services around a paused, committed terminal advance cursor."""

import pytest

from fixtures.execution.harness import clean_test_database, pg_session, recovery, test_database
from fixtures.execution.single_run import run_worker, single_run, successful_script
from skm.modules.execution.generated.commands import ResumeRun
from skm.modules.execution.ports import (
    AcceptanceRepository,
    AttemptRepository,
    RunRepository,
    StageRepository,
    TaskRepository,
)
from support.service_runner import Instance, ServiceRunner

__all__ = ["clean_test_database", "pg_session", "recovery", "test_database"]
pytestmark = pytest.mark.pg


def counts(side, case):
    with side.uow(readonly=True) as uow:
        task = uow.repo(TaskRepository).get(case.task.id)
        briefs = uow.connection.execute(
            "SELECT count(*) FROM skm_execution.fix_briefs WHERE attempt_id=%s", (case.attempt.id,)
        ).fetchone()[0]
        return (
            task.check_fix_rounds,
            task.review_rounds,
            briefs,
            len(uow.repo(AcceptanceRepository).decisions_for_task(task.id)),
        )


def test_background_service_restart_preserves_paused_terminal_advance_once(recovery):
    side = recovery
    case = single_run(side)
    plan = successful_script(side, case.task.display_key, bad_check=True)
    side.pause_before_result, side.pause_run_id = "checks_failed", case.run.id
    with ServiceRunner(side) as services:
        Instance.wait_until(services.healthy, description="initial services")
        run_worker(side, case, plan)
    with side.uow(readonly=True) as uow:
        assert uow.repo(RunRepository).get(case.run.id).status.value == "paused"
        pending = uow.repo(AttemptRepository).get(case.attempt.id).continuation
        assert pending is not None
        assert pending.kind == "advance"
        terminal = uow.repo(StageRepository).history(case.attempt.id).entries[-1].record
        assert terminal.finished_at is not None
        assert terminal.outcome_kind.value == "checks_failed"
        assert pending.triggers[-1].cause.refs[0].id == terminal.id
    assert counts(side, case) == (0, 0, 0, 0)
    for _ in range(2):
        with ServiceRunner(side) as services:
            Instance.wait_until(services.healthy, description="restarted services while paused")
        with side.uow(readonly=True) as uow:
            assert uow.repo(AttemptRepository).get(case.attempt.id).continuation == pending
        assert counts(side, case) == (0, 0, 0, 0)
    side.client.dispatch(ResumeRun(case.run.id))
    assert counts(side, case) == (1, 0, 1, 0)
    with ServiceRunner(side) as services:
        Instance.wait_until(services.healthy, description="resumed services")
        run_worker(side, case, plan)
    for _ in range(2):
        with ServiceRunner(side) as services:
            Instance.wait_until(services.healthy, description="restarted services after completion")
        with side.uow(readonly=True) as uow:
            assert uow.repo(RunRepository).get(case.run.id).status.value == "succeeded"
            assert uow.repo(TaskRepository).get(case.task.id).attempt_count == 1
        assert counts(side, case) == (1, 1, 1, 1)
