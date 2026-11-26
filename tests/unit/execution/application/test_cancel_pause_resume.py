"""Run control preserves cursors, revokes leases, and closes observations exactly once."""

from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest

from skm.kernel.errors import SkmError
from skm.modules.execution.application._events import cause
from skm.modules.execution.application._primitives import save_attempt
from skm.modules.execution.application.apply_action import prepare_trigger
from skm.modules.execution.domain.assignment import (
    Assignment,
    AssignmentState,
    WorkerOffer,
    WorkerRequirements,
)
from skm.modules.execution.domain.attempt import AttemptState
from skm.modules.execution.domain.environment import EnvironmentKind
from skm.modules.execution.domain.run import RunStatus
from skm.modules.execution.domain.task import TaskStatus
from skm.modules.execution.generated.commands import CancelRun, PauseRun, ResumeRun
from skm.modules.execution.ports import (
    AssignmentRepository,
    AttemptRepository,
    ExecutionQueries,
    RunRepository,
    TaskRepository,
)

from ._support import _shared_side as _shared_side
from ._support import context, seeded
from ._support import side as side


def assignment(side: Any, uow: Any, run: Any, task: Any, attempt: Any, *, leased: bool = False) -> Any:
    row = Assignment(
        side.new_id(),
        run.id,
        task.id,
        attempt.id,
        side.ws,
        AssignmentState.AVAILABLE,
        side.clock.now(),
        WorkerRequirements(
            frozenset(), side.host1, frozenset(), EnvironmentKind.GIT_WORKTREE, frozenset({"landlock"})
        ),
        0,
        0,
        None,
        None,
        None,
        side.clock.now(),
        1,
    )
    repo = uow.repo(AssignmentRepository)
    repo.add(row)
    if leased:
        offer = WorkerOffer(
            side.worker1,
            side.host1,
            frozenset(),
            frozenset(),
            frozenset({EnvironmentKind.GIT_WORKTREE}),
            frozenset({"landlock"}),
            (),
        )
        row, _ = repo.claim(
            worker=offer,
            workspace_ids=frozenset({side.ws}),
            blocked_project_ids=frozenset(),
            now=side.clock.now(),
            ttl=timedelta(seconds=60),
        )
    return row


def test_owner_pause_releases_available_pre_stage_but_preserves_attempt_and_cursor(side: Any) -> None:
    run, task, attempt = seeded(
        side, task_status=TaskStatus.ASSIGNED, attempt_state=AttemptState.PREPARING, cursor=True
    )
    with side.uow() as uow:
        row = assignment(side, uow, run, task, attempt)
        uow.commit()
    paused = side.client.dispatch(PauseRun(run.id, "operator", run.row_version))
    with side.uow(readonly=True) as uow:
        assert uow.repo(RunRepository).get(run.id).pause_source == "owner"
        assert uow.repo(TaskRepository).get(task.id).status is TaskStatus.READY
        assert uow.repo(AttemptRepository).get(attempt.id).continuation == attempt.continuation
        assert uow.repo(AssignmentRepository).get(row.id).state is AssignmentState.CANCELLED
    assert paused.status == "paused"
    with side.uow(readonly=True) as uow:
        query = uow.repo(ExecutionQueries)
        events = query.run_events(run.id, 0, query.head_run_seq(run.id), 100)
        ready = next(
            e["payload"] for e in events if e["event_type"] == "urn:skm:execution:event:task-ready:v1"
        )
        assert ready["cause"]["trigger_kind"] == "wait_changed"
        assert "RUN_PAUSED" in ready["cause"]["reason_codes"]


def test_pause_keeps_live_claim_cancel_revokes_it_and_clears_cursor(side: Any) -> None:
    run, task, attempt = seeded(
        side, task_status=TaskStatus.ASSIGNED, attempt_state=AttemptState.PREPARING, cursor=True
    )
    with side.uow() as uow:
        row = assignment(side, uow, run, task, attempt, leased=True)
        uow.commit()
    side.client.dispatch(PauseRun(run.id, "pause"))
    with side.uow(readonly=True) as uow:
        assert uow.repo(AssignmentRepository).lease(row.id) is not None
    side.client.dispatch(CancelRun(run.id, "cancel"))
    with side.uow(readonly=True) as uow:
        assert uow.repo(AssignmentRepository).lease(row.id) is None
        assert uow.repo(AttemptRepository).get(attempt.id).continuation is None
        assert uow.repo(TaskRepository).get(task.id).status is TaskStatus.CANCELLED
        assert uow.repo(RunRepository).get(run.id).stop_code is None


def test_resume_stage_enqueues_same_attempt_once_without_evaluation(side: Any) -> None:
    run, task, attempt = seeded(side, run_status=RunStatus.PAUSED, cursor=True)
    side.client.dispatch(ResumeRun(run.id))
    side.client.dispatch(ResumeRun(run.id))
    with side.uow(readonly=True) as uow:
        rows = uow.repo(AssignmentRepository).for_attempt(attempt.id)
        assert len(rows) == 1
        assert uow.repo(AttemptRepository).get(attempt.id).continuation == attempt.continuation
        assert uow.repo(TaskRepository).get(task.id).attempt_count == 1
        assert uow.repo(RunRepository).get(run.id).pause_source is None


def test_paused_triggers_are_bounded_deduplicated_and_overflow_precedes_mutation(side: Any) -> None:
    run, _task, attempt = seeded(side, run_status=RunStatus.PAUSED)
    with side.uow() as uow:
        ctx = context(side, uow, run)
        ids = [side.new_id() for _ in range(128)]
        current = attempt
        for eid in ids:
            current = prepare_trigger(uow, ctx, current, eid, cause("manual_verdict"))
        duplicate = prepare_trigger(uow, ctx, current, ids[-1], cause("manual_verdict"))
        assert duplicate is current
        with pytest.raises(SkmError):
            prepare_trigger(uow, ctx, current, side.new_id(), cause("manual_verdict"))
        assert len(current.continuation.triggers) == 128
        save_attempt(uow, current)
        uow.commit()
    with side.uow(readonly=True) as uow:
        assert len(uow.repo(AttemptRepository).get(attempt.id).continuation.triggers) == 128


def test_resume_never_guesses_a_null_legacy_cursor_and_cas_is_checked(side: Any) -> None:
    run, _task, attempt = seeded(side, run_status=RunStatus.PAUSED)
    with pytest.raises(SkmError):
        side.client.dispatch(ResumeRun(run.id, 100))
    side.client.dispatch(ResumeRun(run.id))
    with side.uow(readonly=True) as uow:
        assert uow.repo(AssignmentRepository).for_attempt(attempt.id) == ()
        assert uow.repo(AttemptRepository).get(attempt.id).continuation is None


@pytest.mark.parametrize("runtime_started", [False, True])
@pytest.mark.parametrize("terminal", [False, True])
def test_cancel_closes_every_reservation_and_emits_one_terminal_observation(
    side: Any, runtime_started: bool, terminal: bool
) -> None:
    from skm.modules.execution.domain.budget import BudgetAccount, BudgetDimension, BudgetReservation
    from skm.modules.execution.domain.stage_record import begin_stage_record, mark_runtime_started
    from skm.modules.execution.domain.step import StepState
    from skm.modules.execution.domain.workflow.stage_inputs import StageMode
    from skm.modules.execution.ports import BudgetRepository, StageRepository, StepRepository

    from ._support import seed_step

    run, task, attempt = seeded(side)
    manifest = side.make_final_manifest()
    with side.uow() as uow:
        stage = begin_stage_record(
            (),
            record_id=side.new_id(),
            attempt_id=attempt.id,
            run_id=run.id,
            task_id=task.id,
            stage_id="execute",
            stage_type="agent_step",
            round_no=1,
            mode=StageMode.NORMAL,
            input_digest="sha256:" + "1" * 64,
            fencing_token=1,
            now=side.clock.now(),
        )
        if runtime_started:
            stage = mark_runtime_started(stage, now=side.clock.now())
        uow.repo(StageRepository).add(stage)
        step = seed_step(
            side,
            uow,
            attempt,
            stage,
            manifest_id=manifest,
            state=StepState.SUCCEEDED if terminal else StepState.STARTED,
        )
        budget = uow.repo(BudgetRepository)
        account = BudgetAccount(
            side.new_id(),
            run.id,
            "run",
            None,
            BudgetDimension.TOKENS,
            Decimal(100),
            Decimal(0),
            Decimal(0),
            1,
        )
        budget.add_accounts((account,))
        assert budget.reserve((account.id,), Decimal(10))
        reservation = BudgetReservation(
            side.new_id(),
            (account.id,),
            BudgetDimension.TOKENS,
            step.id,
            Decimal(10),
            "reserved",
            None,
            side.clock.now(),
            None,
        )
        budget.add_reservation(reservation)
        uow.commit()
    side.client.dispatch(CancelRun(run.id, "cancel stage"))
    side.client.dispatch(CancelRun(run.id, "replay"))
    with side.uow(readonly=True) as uow:
        closed = uow.repo(BudgetRepository).get_reservation(reservation.id)
        assert closed.state == ("settled" if runtime_started else "released")
        assert uow.repo(BudgetRepository).accounts_for(run.id, None, BudgetDimension.TOKENS)[0].reserved == 0
        assert uow.repo(StepRepository).get(step.id).state.value == ("succeeded" if terminal else "cancelled")
        assert uow.repo(StageRepository).get(stage.id).state.value == "interrupted"
        query = uow.repo(ExecutionQueries)
        events = query.run_events(run.id, 0, query.head_run_seq(run.id), 200)
        observations = [
            e for e in events if "step-observation-recorded" in str(e.get("type", e.get("event_type")))
        ]
        assert len(observations) == (0 if terminal else 1)


def test_cancellation_preserves_uncertain_effect_request_and_receipt(side: Any) -> None:
    from skm.modules.execution.domain.external_effect import EffectKind, EffectState, ExternalEffect
    from skm.modules.execution.ports import EffectRepository

    run, task, attempt = seeded(side)
    effect = ExternalEffect(
        side.new_id(),
        side.ws,
        run.id,
        attempt.id,
        task.id,
        EffectKind.GIT_COMMIT,
        None,
        "sha256:" + "1" * 64,
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
        EffectState.EXECUTING,
        {"process_ref": "retained"},
        side.clock.now(),
        side.clock.now(),
    )
    with side.uow() as uow:
        uow.repo(EffectRepository).add(effect)
        uow.commit()
    side.client.dispatch(CancelRun(run.id, "uncertain process"))
    with side.uow(readonly=True) as uow:
        saved = uow.repo(EffectRepository).get(effect.id)
        assert saved.state is EffectState.OUTCOME_UNKNOWN
        assert saved.request == effect.request
        assert saved.receipt["process_ref"] == "retained"
        assert uow.repo(AttemptRepository).get(attempt.id).continuation is None


def test_live_kill_switch_refuses_resume_without_rewriting_bundle(side: Any) -> None:
    from skm.modules.execution.ports import BundleRepository

    from ._support import set_setting

    run, _task, _attempt = seeded(side, run_status=RunStatus.PAUSED, cursor=True)
    with side.uow(readonly=True) as uow:
        frozen = uow.repo(BundleRepository).get(run.id)
    set_setting(side, "execution.kill_switch", True)
    with pytest.raises(SkmError):
        side.client.dispatch(ResumeRun(run.id))
    with side.uow(readonly=True) as uow:
        assert uow.repo(RunRepository).get(run.id).status is RunStatus.PAUSED
        assert uow.repo(BundleRepository).get(run.id) == frozen


def test_submitted_attempt_cancel_clears_cursor_in_terminal_update(side: Any) -> None:
    run, _task, attempt = seeded(side, attempt_state=AttemptState.SUBMITTED, cursor=True)
    side.client.dispatch(CancelRun(run.id, "integration uncertain"))
    with side.uow(readonly=True) as uow:
        saved = uow.repo(AttemptRepository).get(attempt.id)
        assert saved.state is AttemptState.OWNERSHIP_LOST
        assert saved.continuation is None
        assert saved.end_reason == "CANCELLED"


def test_same_wait_does_not_repeat_boundary_but_changed_target_does(side: Any) -> None:
    from dataclasses import replace

    from skm.modules.execution.application._events import save_task
    from skm.modules.execution.domain.blocking_reason import BlockingCode, blocking_reason

    run, task, _ = seeded(side)
    with side.uow() as uow:
        first = blocking_reason(
            BlockingCode.BLOCKED_BY_DEPENDENCY,
            task_id=task.id,
            refs={"prerequisite_task_ids": [str(side.new_id())]},
            now=side.clock.now(),
            message="waiting",
        )
        old = task
        for reason in (
            first,
            replace(first, since=first.since + timedelta(seconds=1)),
            replace(first, refs={"prerequisite_task_ids": [str(side.new_id())]}),
        ):
            updated = replace(
                old, status=TaskStatus.BLOCKED, blocking_reason=reason, row_version=old.row_version + 1
            )
            save_task(uow, run, old, updated, cause("wait_changed"), side.clock.now())
            old = uow.repo(TaskRepository).get(task.id)
        uow.commit()
    with side.uow(readonly=True) as uow:
        query = uow.repo(ExecutionQueries)
        events = query.run_events(run.id, 0, query.head_run_seq(run.id), 100)
        boundaries = [e for e in events if "task-wait-changed" in str(e.get("type", e.get("event_type")))]
        assert len(boundaries) == 2


def test_restart_preserves_spend_counters_and_old_attempt_history(side: Any) -> None:
    from dataclasses import replace

    from skm.modules.execution.domain.stage_record import StageState
    from skm.modules.execution.generated.commands import RestartTask
    from skm.modules.execution.ports import StageRepository

    from ._support import seed_stage

    _run, task, attempt = seeded(side)
    with side.uow() as uow:
        previous = replace(task, check_fix_rounds=2, review_rounds=2, row_version=task.row_version + 1)
        uow.repo(TaskRepository).save(previous, expected_version=task.row_version)
        stage = seed_stage(side, uow, attempt, state=StageState.COMPLETED)
        uow.commit()
    side.client.dispatch(RestartTask.from_json({"task_id": str(task.id), "reason": "owner restart"}))
    with side.uow(readonly=True) as uow:
        ready = uow.repo(TaskRepository).get(task.id)
        assert ready.status is TaskStatus.READY
        assert ready.current_attempt_id is None
        assert (ready.attempt_count, ready.review_rounds, ready.check_fix_rounds) == (1, 2, 2)
        assert uow.repo(StageRepository).get(stage.id).state is StageState.COMPLETED
        assert uow.repo(AttemptRepository).get(attempt.id).state is AttemptState.ABANDONED


def test_resume_keeps_live_leases_and_defers_cursor_when_parallel_capacity_is_full(side: Any) -> None:
    from dataclasses import replace

    from contracts.execution.seed_helpers import seed_attempt
    from skm.modules.execution.domain.attempt import select_stage
    from skm.modules.execution.domain.task import TaskKind, TaskOrigin

    from ._support import seed_task

    run, first, attempt = seeded(side, cursor=True)
    with side.uow() as uow:
        first_assignment = assignment(side, uow, run, first, attempt, leased=True)
        extra = []
        for index in range(2):
            tid = side.new_id()
            task = seed_task(
                side,
                uow,
                run.id,
                task_id=tid,
                kind=TaskKind.FOLLOWUP,
                origin=TaskOrigin(first.id, (), "FOLLOWUP"),
                display_key=f"@followup/{tid}",
                status=TaskStatus.EXECUTING,
            )
            current = seed_attempt(side, uow, run.id, tid)
            current = select_stage(
                current,
                cause=attempt.continuation.cause,
                stage=attempt.continuation.stage,
                continuation_id=side.new_id(),
            )
            save_attempt(uow, current)
            task = replace(
                task, current_attempt_id=current.id, attempt_count=1, row_version=task.row_version + 1
            )
            uow.repo(TaskRepository).save(task, expected_version=task.row_version - 1)
            extra.append(current)
            if index == 0:
                second_assignment = assignment(side, uow, run, task, current, leased=True)
        uow.commit()
    side.client.dispatch(PauseRun(run.id, "keep live claims"))
    result = side.client.dispatch(ResumeRun(run.id))
    assert result.status == "running"
    with side.uow(readonly=True) as uow:
        repo = uow.repo(AssignmentRepository)
        assert repo.lease(first_assignment.id) is not None
        assert repo.lease(second_assignment.id) is not None
        assert not repo.for_attempt(extra[1].id)
        assert uow.repo(AttemptRepository).get(extra[1].id).continuation == extra[1].continuation


def test_resume_continues_last_allowed_attempt_without_charging_another_attempt(side: Any) -> None:
    from skm.modules.execution.domain.budget import BudgetAccount, BudgetDimension
    from skm.modules.execution.ports import BudgetRepository

    run, task, attempt = seeded(side, run_status=RunStatus.PAUSED, attempt_no=3, cursor=True)
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
                    Decimal(3),
                    Decimal(0),
                    1,
                ),
            )
        )
        uow.commit()
    side.client.dispatch(ResumeRun(run.id))
    with side.uow(readonly=True) as uow:
        assert uow.repo(TaskRepository).get(task.id).attempt_count == 3
        assert uow.repo(AttemptRepository).get(attempt.id).attempt_no == 3
        assert len(uow.repo(AssignmentRepository).for_attempt(attempt.id)) == 1
        assert (
            uow.repo(BudgetRepository).accounts_for(run.id, task.id, BudgetDimension.ATTEMPTS)[0].spent == 3
        )


def test_resume_ignores_accepted_task_with_exhausted_task_budget(side: Any) -> None:
    from skm.modules.execution.domain.budget import BudgetAccount, BudgetDimension
    from skm.modules.execution.ports import BudgetRepository

    from ._support import carry_case

    run, task, _, _, _ = carry_case(side)
    with side.uow() as uow:
        uow.repo(BudgetRepository).add_accounts(
            (
                BudgetAccount(
                    side.new_id(),
                    run.id,
                    "task",
                    task.id,
                    BudgetDimension.TOKENS,
                    Decimal(10),
                    Decimal(10),
                    Decimal(0),
                    1,
                ),
            )
        )
        uow.commit()
    side.client.dispatch(PauseRun(run.id, "accepted task retained"))
    assert side.client.dispatch(ResumeRun(run.id)).status == "running"
    with side.uow(readonly=True) as uow:
        assert uow.repo(TaskRepository).get(task.id).status is TaskStatus.ACCEPTED
        assert uow.repo(BudgetRepository).accounts_for(run.id, task.id, BudgetDimension.TOKENS)[0].spent == 10


def test_resume_still_refuses_exhausted_run_budget(side: Any) -> None:
    from skm.kernel.error_codes import ErrorCode
    from skm.modules.execution.domain.budget import BudgetAccount, BudgetDimension
    from skm.modules.execution.ports import BudgetRepository

    run, _, _ = seeded(side, run_status=RunStatus.PAUSED)
    with side.uow() as uow:
        uow.repo(BudgetRepository).add_accounts(
            (
                BudgetAccount(
                    side.new_id(),
                    run.id,
                    "run",
                    None,
                    BudgetDimension.TOKENS,
                    Decimal(10),
                    Decimal(10),
                    Decimal(0),
                    1,
                ),
            )
        )
        uow.commit()
    with pytest.raises(SkmError) as caught:
        side.client.dispatch(ResumeRun(run.id))
    assert caught.value.code is ErrorCode.BUDGET_EXHAUSTED
    with side.uow(readonly=True) as uow:
        assert uow.repo(RunRepository).get(run.id).status is RunStatus.PAUSED
