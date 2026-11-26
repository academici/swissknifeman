"""Persisted snapshot grace, safe notify and emergency closure with real memory UoW."""

from datetime import timedelta

import pytest

from skm.modules.execution.application.commands import detect_stalls
from skm.modules.execution.domain.stage_record import StageState
from skm.modules.execution.ports import RecoveryRepository, StageRepository
from unit.execution.application._support import _shared_side, set_setting, side
from unit.execution.application.test_background_commands import execute, running_case

__all__ = ["_shared_side", "side"]


def test_notify_persists_snapshot_then_closes_without_cancelling(side):
    _run, _, _, _, stage, _ = running_case(side)
    side.clock.advance(timedelta(seconds=301))
    assert execute(side, detect_stalls)["detected"] == 1
    with side.uow(readonly=True) as uow:
        recovery = uow.repo(RecoveryRepository).open_for_stage(stage.id)
        assert recovery is not None
        assert recovery.outcome is None
    assert execute(side, detect_stalls)["detected"] == 0
    side.clock.advance(timedelta(seconds=61))
    assert execute(side, detect_stalls)["detected"] == 1
    with side.uow(readonly=True) as uow:
        assert uow.repo(RecoveryRepository).open_for_stage(stage.id) is None
        assert uow.repo(StageRepository).get(stage.id).state == stage.state


def test_quiet_check_within_hard_deadline_is_not_killed(side):
    from contracts.execution._worker_protocol_support import claim, make_case
    from contracts.execution.seed_helpers import seed_stage

    _run, _, attempt, _ = make_case(side, stage_id="checks", stage_type="run_checks", env=True)
    claim(side)
    with side.uow() as uow:
        stage = seed_stage(side, uow, attempt, stage_id="checks", stage_type="run_checks")
        uow.commit()
    side.clock.advance(timedelta(seconds=301))
    set_setting(side, "execution.supervisor.recover", "resume")
    assert execute(side, detect_stalls)["detected"] == 0
    with side.uow(readonly=True) as uow:
        assert uow.repo(StageRepository).get(stage.id).state == stage.state
        assert not uow.repo(StageRepository).cancel_requested(attempt.id, stage.fencing_token)


def test_deadline_recovery_closes_terminal_stage_and_revokes_old_claim(side):
    from skm.modules.execution.domain.stage_record import StageState
    from skm.modules.execution.ports import BudgetRepository, StepRepository

    _run, _, _, _, stage, step = running_case(side)
    set_setting(side, "execution.supervisor.recover", "resume")
    side.clock.advance(timedelta(seconds=1801))
    assert execute(side, detect_stalls)["detected"] == 1
    side.clock.advance(timedelta(seconds=61))
    assert execute(side, detect_stalls)["detected"] == 1
    with side.uow(readonly=True) as uow:
        assert uow.repo(StageRepository).get(stage.id).state is StageState.FAILED
        assert not uow.repo(BudgetRepository).open_for_steps((step.id,))
        assert uow.repo(StepRepository).get(step.id).state.value in {"failed", "cancelled"}
    assert execute(side, detect_stalls)["detected"] == 0


def test_circuit_opens_after_reconcile_and_keeps_owner_options(side):
    from skm.modules.execution.ports import DecisionRepository, RunRepository

    run, task, _, _, stage, _ = running_case(side)
    set_setting(side, "execution.supervisor.recover", "resume")
    set_setting(side, "execution.supervisor.max_recoveries", 0)
    side.clock.advance(timedelta(seconds=1801))
    execute(side, detect_stalls)
    side.clock.advance(timedelta(seconds=61))
    execute(side, detect_stalls)
    with side.uow(readonly=True) as uow:
        latest = uow.repo(RunRepository).get(run.id)
        assert latest.status.value == "paused"
        assert latest.stop_code == "RECOVERY_CIRCUIT_OPEN"
        request = next(
            r
            for r in uow.repo(DecisionRepository).open_for_task(task.id)
            if r.payload.get("code") == "RECOVERY_CIRCUIT_OPEN"
        )
        assert request.audience.value == "owner"
        assert request.payload["options"] == ["resume_run", "cancel_run"]
        assert uow.repo(RecoveryRepository).open_for_stage(stage.id) is None


@pytest.mark.parametrize(
    ("stage_state", "expected"), [(StageState.CONTEXT_DRAFT, "released"), (StageState.RUNNING, "settled")]
)
def test_emergency_closure_releases_real_budget_and_reconciles_effects(side, stage_state, expected):
    from decimal import Decimal

    from skm.modules.execution.domain.budget import BudgetAccount, BudgetDimension, reserve
    from skm.modules.execution.domain.external_effect import EffectKind, EffectState, ExternalEffect
    from skm.modules.execution.ports import BudgetRepository, EffectRepository

    run, task, attempt, _, _stage, step = running_case(side, state=stage_state)
    with side.uow() as uow:
        budget = uow.repo(BudgetRepository)
        account = BudgetAccount(
            side.new_id(),
            run.id,
            "run",
            None,
            BudgetDimension.TOKENS,
            Decimal(1000),
            Decimal(0),
            Decimal(0),
            1,
        )
        budget.add_accounts((account,))
        _, reservation = reserve(
            (account,), Decimal(20), reservation_id=side.new_id(), now=side.clock.now(), step_id=step.id
        )
        assert budget.reserve(reservation.account_ids, reservation.amount)
        budget.add_reservation(reservation)
        effects = []
        for state in (EffectState.INTENDED, EffectState.EXECUTING):
            effect = ExternalEffect(
                side.new_id(),
                run.workspace_id,
                run.id,
                attempt.id,
                task.id,
                EffectKind.GIT_COMMIT,
                None,
                "sha256:" + ("1" if state is EffectState.INTENDED else "2") * 64,
                {
                    "repository_id": str(side.repo_id),
                    "target_branch": "main",
                    "before_sha": "1" * 40,
                    "after_sha": "2" * 40,
                    "tree_sha": "3" * 40,
                    "baseline_sha": "1" * 40,
                    "output_ids": [],
                    "output_digests": [],
                    "commit_shas": ["2" * 40],
                    "assignment_fencing_token": 1,
                    "slot_fencing_token": 1,
                    "writer_epoch_sha": "1" * 40,
                },
                state,
                None,
                side.clock.now(),
                side.clock.now(),
            )
            uow.repo(EffectRepository).add(effect)
            effects.append(effect)
        uow.commit()
    set_setting(side, "execution.supervisor.recover", "resume")
    side.clock.advance(timedelta(seconds=1801))
    execute(side, detect_stalls)
    side.clock.advance(timedelta(seconds=61))
    execute(side, detect_stalls)
    with side.uow(readonly=True) as uow:
        budget = uow.repo(BudgetRepository)
        assert budget.get_reservation(reservation.id).state == expected
        assert not budget.open_for_steps((step.id,))
        assert uow.repo(EffectRepository).get(effects[0].id).state is EffectState.FAILED
        assert uow.repo(EffectRepository).get(effects[1].id).state is EffectState.OUTCOME_UNKNOWN


def test_worker_terminal_closes_inflight_recovery_without_retry(side):
    from skm.modules.execution.application.commands.expire_leases import lock_ownership, terminal_stage
    from unit.execution.application._support import context

    _run, _, _, assignment, stage, _ = running_case(side)
    side.clock.advance(timedelta(seconds=301))
    execute(side, detect_stalls)
    with side.uow() as uow:
        fenced = lock_ownership(uow, assignment)
        terminal_stage(uow, context(side, uow), fenced, stage, code="RUNTIME_TIMEOUT")
        uow.commit()
    assert execute(side, detect_stalls)["detected"] == 0
    with side.uow(readonly=True) as uow:
        assert uow.repo(RecoveryRepository).open_for_stage(stage.id) is None


def test_project_supervisor_override_and_unconfirmed_recovery(side):
    from skm.modules.execution.ports import ExecutionQueries
    from skm.modules.settings.public import SetValue

    run, _, _, _, stage, _ = running_case(side)
    side.client.dispatch(
        SetValue.from_json(
            {
                "scope": {"level": "project", "scope_id": str(run.project_id)},
                "key": "execution.supervisor.recover",
                "value": "resume",
                "reason": "project policy",
                "confirmed": True,
            }
        )
    )
    side.clock.advance(timedelta(seconds=1801))
    execute(side, detect_stalls)
    side.clock.advance(timedelta(seconds=61))
    execute(side, detect_stalls)
    with side.uow(readonly=True) as uow:
        assert uow.repo(StageRepository).get(stage.id).state is StageState.FAILED
        queries = uow.repo(ExecutionQueries)
        events = queries.run_events(run.id, 0, queries.head_run_seq(run.id), 1000)
        evaluations = [
            e["payload"] for e in events if "monitor-evaluated" in str(e.get("event_type", e.get("type")))
        ]
        assert evaluations[-1]["recovery_mode"] == "resume"
        assert evaluations[-1]["scheduled_at"] <= evaluations[-1]["started_at"]
        assert evaluations[-1]["started_at"] <= evaluations[-1]["finished_at"]
        assert (
            uow.repo(RecoveryRepository).count_since(
                run.id, side.clock.now() - timedelta(hours=1), frozenset({"retried", "new_attempt"})
            )
            == 0
        )
        assert "execution.stall.idle_seconds" in {t["key"] for t in evaluations[-1]["thresholds"]}
