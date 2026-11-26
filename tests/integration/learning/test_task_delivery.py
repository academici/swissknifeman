"""Deliver real execution outcomes to learning across the PostgreSQL outbox."""

from typing import Any, cast
from uuid import UUID

import pytest

from fixtures.execution.harness import clean_test_database, pg_session, recovery, test_database
from fixtures.execution.single_run import run_worker, single_run, successful_script
from skm.kernel.ids import ScopeId
from skm.modules.execution.generated.commands import AnswerDecisionRequest, AnswerDecisionRequestAnswer
from skm.modules.execution.ports import AttemptRepository, DecisionRepository
from skm.modules.learning import public as learning
from skm.modules.learning.application.commands.extract_candidates import ActivityStorage
from skm.modules.learning.domain.detectors import Detector
from skm.modules.learning.ports import ActivityRecordRepository, CandidateRepository, SignalRepository
from support.service_runner import Instance, ServiceRunner
from unit.execution.application._support import set_setting

__all__ = ["clean_test_database", "pg_session", "recovery", "test_database"]
pytestmark = pytest.mark.pg


def _delivered(side: Any, attempt_id: UUID) -> Any:
    with side.uow(readonly=True) as uow:
        records = cast("ActivityStorage", uow.repo(ActivityRecordRepository))
        record = records.by_source(side.ws, str(attempt_id))
        return records.get(record) if record is not None else None


@pytest.mark.parametrize("fail_task", [False, True], ids=["reworked", "failed"])
def test_fake_runtime_terminal_event_reaches_learning(recovery: Any, fail_task: bool) -> None:
    side = recovery
    if fail_task:
        set_setting(side, "execution.rework.max_rounds", 0)

    case = single_run(side)
    script = successful_script(side, case.task.display_key, bad_check=True)
    with ServiceRunner(side) as services:
        Instance.wait_until(services.healthy, description="execution and delivery services")
        run_worker(side, case, script)
        if fail_task:
            with side.uow(readonly=True) as uow:
                (decision,) = uow.repo(DecisionRepository).open_for_task(case.task.id)
            side.client.dispatch(
                AnswerDecisionRequest(
                    decision.id, AnswerDecisionRequestAnswer(option_id="fail"), decision.revision
                )
            )
        activity = Instance.wait_until(
            lambda: _delivered(side, case.attempt.id), description="terminal execution event delivered"
        )

    if fail_task:
        with side.uow(readonly=True) as uow:
            attempt = uow.repo(AttemptRepository).get(case.attempt.id)
            assert attempt.state.value == "abandoned"
            assert attempt.end_reason == "FAILED"
        (event,) = side.client.events(
            workspace_id=side.ws,
            after=0,
            types=frozenset({"urn:skm:execution:event:task-failed:v1"}),
        )
        assert event.payload["task_id"] == str(case.task.id)
        assert "attempt_id" not in event.payload
        assert activity.outcome.value == activity.task_outcome.value == "failure"
        return

    assert activity.outcome.value == "success"
    with side.uow(readonly=True) as uow:
        (candidate,) = (
            uow.repo(CandidateRepository)
            .list((ScopeId(activity.project_id),), states=frozenset(), after=None, limit=10)
            .items
        )
        assert candidate.detector is Detector.RESOLVED_FAILURE
        (signal,) = uow.repo(SignalRepository).for_candidate(candidate.id)
        assert signal.tests_total >= 2
        assert signal.tests_total == signal.tests_passed + 1
    review = learning.ReviewCandidate.from_json(
        {
            "workspace_id": str(side.ws),
            "candidate_id": str(candidate.id),
            "verdict": "approve",
            "expected_row_version": candidate.row_version,
        }
    )
    reviewed = side.client.dispatch(review, idempotency_key=side.client.new_idempotency_key())
    assert reviewed["review_id"]
