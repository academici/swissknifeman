"""Both stores name the PostgreSQL constraint a refused write violates.

``details["constraint"]`` is what callers and logs see for ``ALREADY_EXISTS`` / ``INVALID_REFERENCE``; the
memory store has to report the name the migrations give, or a test that passes on memory says nothing about
the real database.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.ids import RunId, TaskId
from skm.modules.execution.domain.autopilot import AutopilotState, AutopilotStateKind
from skm.modules.execution.domain.budget import BudgetAccount, BudgetDimension
from skm.modules.execution.domain.reaping import reap_receipt
from skm.modules.execution.domain.task_graph import EdgeKind, TaskEdge
from skm.modules.execution.ports import (
    AutopilotRepository,
    BudgetRepository,
    RecoveryRepository,
    TaskRepository,
)

from .seed_helpers import seed_attempt, seed_run, seed_stage, seed_task

if TYPE_CHECKING:
    from collections.abc import Callable

    from skm.kernel.ports_uow import UnitOfWork

    from .harness import ExecSide


def _refused(side: ExecSide, write: Callable[[UnitOfWork], None]) -> SkmError:
    with side.uow() as uow:
        with pytest.raises(SkmError) as exc:
            write(uow)
        uow.rollback()
    return exc.value


def _account(side: ExecSide, run_id: RunId, task_id: TaskId | None) -> BudgetAccount:
    scope = "run" if task_id is None else "task"
    return BudgetAccount(
        side.new_id(), run_id, scope, task_id, BudgetDimension.TOKENS, Decimal(5), Decimal(0), Decimal(0), 1
    )


@pytest.mark.parametrize(
    ("scoped_to_task", "constraint"),
    [
        (False, "uq_budget_accounts__run_id_dimension_run"),
        (True, "uq_budget_accounts__task_id_dimension_task"),
    ],
)
def test_second_budget_account_of_a_dimension(
    exec_side: ExecSide, scoped_to_task: bool, constraint: str
) -> None:
    with exec_side.uow() as uow:
        run = seed_run(exec_side, uow)
        task_id = seed_task(exec_side, uow, run.id).id if scoped_to_task else None
        uow.repo(BudgetRepository).add_accounts((_account(exec_side, run.id, task_id),))
        uow.commit()
    error = _refused(
        exec_side,
        lambda uow: uow.repo(BudgetRepository).add_accounts((_account(exec_side, run.id, task_id),)),
    )
    assert (error.code, error.details["constraint"]) == (ErrorCode.ALREADY_EXISTS, constraint)


def test_edge_to_a_missing_prerequisite(exec_side: ExecSide) -> None:
    with exec_side.uow() as uow:
        run = seed_run(exec_side, uow)
        task = seed_task(exec_side, uow, run.id)
        uow.commit()
    edge = TaskEdge(run.id, task.id, TaskId(exec_side.new_id()), EdgeKind.BLOCKS, frozenset())
    error = _refused(exec_side, lambda uow: uow.repo(TaskRepository).add_many((), (edge,)))
    assert (error.code, error.details["constraint"]) == (
        ErrorCode.INVALID_REFERENCE,
        "fk_run_task_edges__prerequisite",
    )


def test_recovery_of_a_stage_of_another_attempt(exec_side: ExecSide) -> None:
    with exec_side.uow() as uow:
        run = seed_run(exec_side, uow)
        own = seed_attempt(exec_side, uow, run.id, seed_task(exec_side, uow, run.id).id)
        other_task = seed_task(exec_side, uow, run.id, display_key="P1.1/U2", position=1)
        foreign_stage = seed_stage(exec_side, uow, seed_attempt(exec_side, uow, run.id, other_task.id))
        uow.commit()
    record = replace(
        reap_receipt(UUID(int=exec_side.new_id().int), foreign_stage, exec_side.clock.now()),
        task_id=own.task_id,
        attempt_id=own.id,
    )
    error = _refused(exec_side, lambda uow: uow.repo(RecoveryRepository).add(record))
    assert (error.code, error.details["constraint"]) == (
        ErrorCode.INVALID_REFERENCE,
        "fk_run_recoveries__attempt_stages",
    )


def test_autopilot_pointing_at_a_missing_run(exec_side: ExecSide) -> None:
    state = AutopilotState(
        exec_side.proj,
        exec_side.ws,
        AutopilotStateKind.IDLE,
        False,
        RunId(exec_side.new_id()),
        None,
        {},
        {},
        None,
        None,
        exec_side.owner.principal_id,
        exec_side.clock.now(),
        1,
    )
    error = _refused(exec_side, lambda uow: uow.repo(AutopilotRepository).save(state, expected_version=None))
    assert (error.code, error.details["constraint"]) == (
        ErrorCode.INVALID_REFERENCE,
        "fk_autopilot_states__runs",
    )
