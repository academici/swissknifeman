"""CAS checkpoint overlays retain ledger truth and reject semantic widening."""

from decimal import Decimal
from typing import Any

import pytest

from skm.kernel.errors import SkmError
from skm.modules.execution.application._state import effective_values
from skm.modules.execution.domain.budget import BudgetAccount, BudgetDimension
from skm.modules.execution.domain.run import RunStatus
from skm.modules.execution.generated.commands import ReconfigureRun
from skm.modules.execution.ports import BudgetRepository, BundleRepository

from ._support import _shared_side as _shared_side
from ._support import seeded
from ._support import side as side
from .test_cancel_pause_resume import assignment


def test_reconfigure_rejects_lease_even_without_stage_record(side: Any) -> None:
    run, task, attempt = seeded(side)
    with side.uow() as uow:
        assignment(side, uow, run, task, attempt, leased=True)
        uow.commit()
    with pytest.raises(SkmError) as caught:
        side.client.dispatch(
            ReconfigureRun(run.id, run.row_version, {"budgets.task.max_attempts": 1}, "checkpoint")
        )
    assert caught.value.details.get("reason") == "reconfiguration_checkpoint_required"
    with side.uow(readonly=True) as uow:
        assert uow.repo(BundleRepository).reconfigurations(run.id) == ()


@pytest.mark.parametrize(
    "key",
    [
        "execution.workflow.profile",
        "execution.review.max_rounds",
        "execution.work_policy.verification_intensity",
        "budgets.unknown_usage_policy",
    ],
)
def test_fixed_allowlist_does_not_allow_policy_workflow_or_review_semantics(side: Any, key: str) -> None:
    run, _, _ = seeded(side, run_status=RunStatus.PAUSED)
    with pytest.raises(SkmError):
        side.client.dispatch(ReconfigureRun(run.id, 1, {key: 1}, "forbidden"))


def test_lower_limit_retains_spend_and_frozen_bundle_and_overlay_order(side: Any) -> None:
    run, task, _ = seeded(side, run_status=RunStatus.PAUSED)
    with side.uow() as uow:
        before = uow.repo(BundleRepository).get(run.id)
        account = BudgetAccount(
            side.new_id(),
            run.id,
            "task",
            task.id,
            BudgetDimension.ATTEMPTS,
            Decimal(3),
            Decimal(2),
            Decimal(0),
            1,
        )
        uow.repo(BudgetRepository).add_accounts((account,))
        uow.commit()
    first = side.client.dispatch(ReconfigureRun(run.id, 1, {"budgets.task.max_attempts": 2}, "lower"))
    second = side.client.dispatch(
        ReconfigureRun(run.id, first.row_version, {"budgets.task.max_attempts": 1}, "lower again")
    )
    with side.uow(readonly=True) as uow:
        loaded, values = effective_values(uow, run.id)
        current = uow.repo(BudgetRepository).accounts_for(run.id, task.id, BudgetDimension.ATTEMPTS)[0]
        assert values["budgets.task.max_attempts"] == 1
        assert current.spent == Decimal(2)
        assert current.reserved == 0
        assert current.limit_value == 1
        assert uow.repo(BundleRepository).get(run.id) == before
        assert len(uow.repo(BundleRepository).reconfigurations(run.id)) == 2
        assert loaded.reconfiguration_ids == (second.reconfiguration_id,)


def test_raise_above_current_ceiling_and_stale_cas_are_rejected(side: Any) -> None:
    run, _, _ = seeded(side, run_status=RunStatus.PAUSED)
    for cmd in (
        ReconfigureRun(run.id, 100, {"budgets.task.max_attempts": 1}, "stale"),
        ReconfigureRun(run.id, 1, {"execution.parallel.max_units": 999}, "above"),
    ):
        with pytest.raises(SkmError):
            side.client.dispatch(cmd)


@pytest.mark.parametrize("active", [False, True])
def test_reconfigure_rejects_active_stage_and_unfinished_recovery(side: Any, active: bool) -> None:
    from skm.modules.execution.domain.recovery import RecoveryRecord
    from skm.modules.execution.domain.stage_record import StageState
    from skm.modules.execution.ports import RecoveryRepository

    from ._support import seed_stage

    run, task, attempt = seeded(side, run_status=RunStatus.PAUSED)
    with side.uow() as uow:
        stage = seed_stage(side, uow, attempt, state=StageState.RUNNING if active else StageState.INTERRUPTED)
        if not active:
            uow.repo(RecoveryRepository).add(
                RecoveryRecord(
                    side.new_id(),
                    run.id,
                    task.id,
                    attempt.id,
                    stage.id,
                    None,
                    "lease_expired",
                    (),
                    None,
                    None,
                    (),
                    side.clock.now(),
                )
            )
        uow.commit()
    with pytest.raises(SkmError) as caught:
        side.client.dispatch(ReconfigureRun(run.id, 1, {"budgets.task.max_attempts": 1}, "not a checkpoint"))
    assert caught.value.details.get("reason") == "reconfiguration_checkpoint_required"


def test_run_wall_budget_retains_active_stage_time_after_pause_and_reconfiguration(side: Any) -> None:
    from dataclasses import replace
    from datetime import timedelta

    from skm.modules.execution.domain.stage_record import StageOutcomeKind, StageState
    from skm.modules.execution.generated.commands import PauseRun, ResumeRun
    from skm.modules.execution.ports import RunRepository, StageRepository

    from ._support import seed_stage

    run, _, attempt = seeded(side)
    with side.uow() as uow:
        stage = seed_stage(side, uow, attempt)
        side.clock.advance(timedelta(seconds=11))
        uow.repo(StageRepository).save(
            replace(
                stage,
                state=StageState.COMPLETED,
                outcome_kind=StageOutcomeKind.SUCCESS,
                outcome={},
                finished_at=side.clock.now(),
            )
        )
        uow.repo(BudgetRepository).add_accounts(
            (
                BudgetAccount(
                    side.new_id(),
                    run.id,
                    "run",
                    None,
                    BudgetDimension.WALL_SECONDS,
                    Decimal(100),
                    Decimal(0),
                    Decimal(0),
                    1,
                ),
            )
        )
        uow.commit()
    paused = side.client.dispatch(PauseRun(run.id, "checkpoint after active work"))
    side.client.dispatch(
        ReconfigureRun(run.id, paused.row_version, {"budgets.run.max_wall_seconds": 10}, "shorter")
    )
    side.clock.advance(timedelta(seconds=11))
    with side.uow(readonly=True) as uow:
        assert uow.repo(RunRepository).active_seconds(run.id, side.clock.now()) == 11
    with pytest.raises(SkmError) as caught:
        side.client.dispatch(ResumeRun(run.id))
    assert caught.value.code.value == "BUDGET_EXHAUSTED"


def test_attempt_overlay_changes_the_workflow_evaluator_decision(side: Any) -> None:
    from skm.modules.execution.application._state import load_state
    from skm.modules.execution.domain.attempt import AttemptState
    from skm.modules.execution.domain.workflow.actions import Fail, NewAttempt
    from skm.modules.execution.domain.workflow.engine import decide_advance

    run, task, _ = seeded(side, attempt_state=AttemptState.OWNERSHIP_LOST)
    with side.uow() as uow:
        uow.repo(BudgetRepository).add_accounts(
            (
                BudgetAccount(
                    side.new_id(),
                    run.id,
                    "task",
                    task.id,
                    BudgetDimension.ATTEMPTS,
                    Decimal(3),
                    Decimal(1),
                    Decimal(0),
                    1,
                ),
            )
        )
        before, workflow = load_state(uow, task.id)
        assert isinstance(
            decide_advance(before, workflow, before.effective_policy, side.clock.now()).action, NewAttempt
        )
        uow.commit()
    side.client.dispatch(ReconfigureRun(run.id, 1, {"budgets.task.max_attempts": 1}, "last attempt"))
    with side.uow(readonly=True) as uow:
        state, workflow = load_state(uow, task.id)
        decision = decide_advance(state, workflow, state.effective_policy, side.clock.now())
        assert isinstance(decision.action, Fail)
        assert decision.action.code == "LEASE_LOST"
        assert state.task.attempt_count == 1


def test_frozen_and_prospective_policy_use_the_same_evaluator_keys(side: Any) -> None:
    from skm.modules.execution.application._start_inputs import POLICY_ALIASES, execution_policy
    from skm.modules.execution.application._state import load_state

    from ._support import context

    run, task, _ = seeded(side)
    with side.uow(readonly=True) as uow:
        cfg = context(side, uow, run).config
        state, _ = load_state(uow, task.id)
        _, saved_values = effective_values(uow, run.id)
        prospective = execution_policy(cfg)
        expected = {alias: prospective[alias] for key, alias in POLICY_ALIASES.items() if key in saved_values}
        expected["retry"] = prospective["retry"]
        assert state.effective_policy == expected
        assert all(key in cfg.resolved_keys() for key in POLICY_ALIASES)
        for key, alias in POLICY_ALIASES.items():
            if key in saved_values:
                assert state.effective_policy[alias] == cfg.get(key)
        assert set(state.effective_policy) >= {
            "attempts_max",
            "rework_max_rounds",
            "review_final_correction",
            "review_accept_findings_only",
            "review_attention_policy",
            "risk_threshold",
            "followups_max",
            "step_max_result_retries",
            "step_max_infra_retries",
            "checks_error_retries",
            "retry_budget_total_max",
            "retry_provider_wait_max_seconds",
            "advisor_enabled",
            "advisor_max_rounds",
            "question_policy",
            "max_questions_per_task",
            "human_gate",
            "scope_outside_policy",
        }
        assert state.effective_policy["retry"] == {
            "on_error": cfg.get("execution.retry.on_error"),
            "fallback_routes": cfg.get("execution.retry.fallback_routes"),
        }


@pytest.mark.parametrize(
    ("key", "new"),
    [
        ("budgets.task.max_attempts", 0),
        ("budgets.task.max_attempts", -1),
        ("budgets.task.max_attempts", 1.0),
        ("budgets.task.max_attempts", True),
        ("budgets.task.max_attempts", 51),
        ("execution.parallel.max_units", 0),
        ("execution.parallel.max_units", 65),
        ("budgets.run.max_attempts", 10001),
        ("budgets.run.max_review_rounds", 1001),
        ("budgets.task.max_tokens", 0.5),
        ("budgets.task.max_tokens", 10000000001),
        ("budgets.task.max_wall_seconds", 2592001),
        ("budgets.run.max_usd", 100000.01),
    ],
)
def test_reconfigure_validates_registry_type_and_bounds_before_mutation(
    side: Any, key: str, new: Any
) -> None:
    from skm.kernel.error_codes import ErrorCode
    from skm.modules.execution.ports import RunRepository

    run, _, _ = seeded(side, run_status=RunStatus.PAUSED)
    with pytest.raises(SkmError) as caught:
        side.client.dispatch(ReconfigureRun(run.id, 1, {key: new}, "invalid schema value"))
    assert caught.value.code is ErrorCode.SCHEMA_INVALID
    with side.uow(readonly=True) as uow:
        assert not uow.repo(BundleRepository).reconfigurations(run.id)
        assert uow.repo(RunRepository).get(run.id).row_version == 1


@pytest.mark.parametrize("key", ["budgets.task.max_review_rounds", "budgets.task.max_tool_calls"])
def test_reconfigure_refuses_nonexistent_budget_keys(side: Any, key: str) -> None:
    from skm.kernel.error_codes import ErrorCode

    run, _, _ = seeded(side)
    with pytest.raises(SkmError) as caught:
        side.client.dispatch(ReconfigureRun(run.id, 1, {key: 1}, "undefined budget"))
    assert caught.value.code is ErrorCode.FORBIDDEN


def test_new_budget_dimensions_and_synthetic_accounts_support_reconfiguration(side: Any) -> None:
    from dataclasses import replace

    from contracts.execution.seed_helpers import seed_attempt
    from skm.modules.execution.application.apply_action import apply_action
    from skm.modules.execution.domain.task import TaskKind, TaskStatus
    from skm.modules.execution.domain.workflow.actions import ActionDecision, CreateFollowups
    from skm.modules.execution.generated.commands import StartRun, ValidateForExecution
    from skm.modules.execution.ports import RunRepository, TaskRepository

    from ._support import context

    report = side.client.dispatch(ValidateForExecution(side.plan1, side.rev2))
    result = side.client.dispatch(StartRun(side.plan1, side.rev2, report.report_id, {}, "budgets"))
    with side.uow() as uow:
        run = uow.repo(RunRepository).get(result.run_id)
        task = next(t for t in uow.repo(TaskRepository).list_for_run(run.id) if t.kind is TaskKind.UNIT)
        attempt = seed_attempt(side, uow, run.id, task.id)
        uow.repo(TaskRepository).save(
            replace(
                task,
                status=TaskStatus.CHECKING,
                current_attempt_id=attempt.id,
                attempt_count=1,
                blocking_reason=None,
                row_version=task.row_version + 1,
            ),
            expected_version=task.row_version,
        )
        why = {"trigger_kind": "followup", "advance_rule": "E4", "reason_codes": [], "refs": []}
        apply_action(
            ActionDecision(CreateFollowups("checks_failed", (), ()), why),
            context(side, uow, run),
            uow,
            task_id=task.id,
        )
        child = next(t for t in uow.repo(TaskRepository).list_for_run(run.id) if t.kind is TaskKind.FOLLOWUP)
        uow.commit()
    changes = {
        "budgets.run.max_attempts": 5,
        "budgets.run.max_review_rounds": 4,
        "budgets.task.max_wall_seconds": 120,
    }
    side.client.dispatch(ReconfigureRun(run.id, run.row_version, changes, "canonical dimensions"))
    with side.uow(readonly=True) as uow:
        repo = uow.repo(BudgetRepository)
        assert repo.accounts_for(run.id, None, BudgetDimension.ATTEMPTS)[0].limit_value == 5
        assert repo.accounts_for(run.id, None, BudgetDimension.REVIEW_ROUNDS)[0].limit_value == 4
        child_accounts = [
            a
            for dim in BudgetDimension
            for a in repo.accounts_for(run.id, child.id, dim)
            if a.task_id == child.id
        ]
        assert {a.dimension for a in child_accounts} == {
            BudgetDimension.USD,
            BudgetDimension.TOKENS,
            BudgetDimension.ATTEMPTS,
            BudgetDimension.WALL_SECONDS,
        }
        assert (
            next(a for a in child_accounts if a.dimension is BudgetDimension.WALL_SECONDS).limit_value == 120
        )
        assert all(a.spent == a.reserved == 0 for a in child_accounts)
