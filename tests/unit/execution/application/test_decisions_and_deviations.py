"""Owner authority cannot transfer to another output, task or request revision."""

from dataclasses import replace
from typing import Any

import pytest

from skm.kernel.errors import SkmError
from skm.modules.execution.generated.commands import (
    AcceptDeviation,
    AnswerDecisionRequest,
    AnswerDecisionRequestAnswer,
    CarryForwardResult,
)
from skm.modules.execution.ports import AcceptanceRepository, DecisionRepository

from ._support import _shared_side as _shared_side
from ._support import decision_case, seeded
from ._support import side as side


def test_unoffered_option_and_stale_binding_are_rejected(side: Any) -> None:
    _run, _task, _attempt, request = decision_case(side)
    with pytest.raises(SkmError):
        side.client.dispatch(
            AnswerDecisionRequest(request.id, AnswerDecisionRequestAnswer(option_id="unknown"), 1)
        )
    with side.uow() as uow:
        uow.repo(DecisionRepository).save(
            replace(request, binding={**request.binding, "attempt_id": str(side.new_id())})
        )
        uow.commit()
    with pytest.raises(SkmError):
        side.client.dispatch(
            AnswerDecisionRequest(request.id, AnswerDecisionRequestAnswer(option_id="continue"), 1)
        )


def test_deviation_requires_matching_committed_owner_wait(side: Any) -> None:
    _run, task, _attempt = seeded(side)
    with pytest.raises(SkmError):
        side.client.dispatch(AcceptDeviation(task.id, "attention_verdict", "accept"))
    with side.uow(readonly=True) as uow:
        assert not uow.repo(AcceptanceRepository).deviations_for_task(task.id)


def test_owner_deviation_is_recorded_once_and_paused_advance_is_retained(side: Any) -> None:
    _, task, _attempt, _request = decision_case(side, code="NOT_ACCEPTABLE")
    result = side.client.dispatch(AcceptDeviation(task.id, "attention_verdict", "accept current result"))
    with side.uow(readonly=True) as uow:
        deviations = uow.repo(AcceptanceRepository).deviations_for_task(task.id)
        assert len(deviations) == 1
        assert deviations[0].id == result.deviation_id


def test_incompatible_and_unprepared_carry_forward_are_rejected(side: Any) -> None:
    _, source, _ = seeded(side)
    _, target, _ = seeded(side)
    with pytest.raises(SkmError):
        side.client.dispatch(CarryForwardResult(source.id, target.id, "reuse"))


def test_carry_forward_after_prepare_preserves_exact_inputs_and_prep_history(side: Any) -> None:
    from skm.modules.execution.ports import AttemptRepository, StageRepository, TaskRepository

    from ._support import carry_case

    _source_run, source, target_run, target, attempt = carry_case(side)
    from decimal import Decimal

    from skm.modules.execution.domain.budget import BudgetAccount, BudgetDimension
    from skm.modules.execution.ports import AssignmentRepository, BudgetRepository

    from .test_cancel_pause_resume import assignment

    with side.uow() as uow:
        row = assignment(side, uow, target_run, target, attempt)
        uow.repo(BudgetRepository).add_accounts(
            (
                BudgetAccount(
                    side.new_id(),
                    target_run.id,
                    "run",
                    None,
                    BudgetDimension.TOKENS,
                    Decimal(100),
                    Decimal(7),
                    Decimal(0),
                    1,
                ),
            )
        )
        uow.commit()
    result = side.client.dispatch(CarryForwardResult(source.id, target.id, "exact compatible reuse"))
    with side.uow(readonly=True) as uow:
        accepted = uow.repo(TaskRepository).get(target.id)
        assert accepted.status.value == "accepted"
        assert accepted.accepted_attempt_id is None
        assert accepted.attempt_count == target.attempt_count
        assert uow.repo(AssignmentRepository).get(row.id).state.value == "cancelled"
        assert (
            uow.repo(BudgetRepository).accounts_for(target_run.id, None, BudgetDimension.TOKENS)[0].spent == 7
        )
        assert uow.repo(AttemptRepository).get(attempt.id).state.value == "abandoned"
        assert len(uow.repo(StageRepository).history(attempt.id).entries) == 1
        row = uow.repo(AcceptanceRepository).carry_forwards_for_run(target_run.id)[0]
        assert row.id == result.carry_forward_id
        assert row.compatibility_inputs["source"] == row.compatibility_inputs["target"]


@pytest.mark.parametrize(("baseline", "extra_work"), [(None, False), ("2" * 40, False), ("1" * 40, True)])
def test_carry_forward_refuses_missing_or_different_baseline_and_next_stage(
    side: Any, baseline: Any, extra_work: bool
) -> None:
    from ._support import carry_case

    _, source, target_run, target, _ = carry_case(side, baseline=baseline, extra_work=extra_work)
    with pytest.raises(SkmError):
        side.client.dispatch(CarryForwardResult(source.id, target.id, "must refuse"))
    with side.uow(readonly=True) as uow:
        assert not uow.repo(AcceptanceRepository).carry_forwards_for_run(target_run.id)
