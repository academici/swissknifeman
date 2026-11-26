"""Background commands through real memory UoW and bus, with FrozenClock."""

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from contracts.execution._worker_protocol_support import claim, make_case
from contracts.execution.seed_helpers import seed_stage, seed_step
from skm.kernel.actor import SYSTEM_PRINCIPAL_ID, Actor, PrincipalKind
from skm.kernel.errors import SkmError
from skm.modules.execution.application.apply_action import process_pending
from skm.modules.execution.application.commands import enforce_timeouts, expire_leases, schedule_ready_tasks
from skm.modules.execution.domain.assignment import AssignmentState, transition_assignment
from skm.modules.execution.domain.attempt import (
    AttemptEndReason,
    AttemptState,
    consume_stage,
    transition_attempt,
)
from skm.modules.execution.domain.blocking_reason import BlockingCode
from skm.modules.execution.domain.budget import BudgetAccount, BudgetDimension, reserve
from skm.modules.execution.domain.run import RunStatus, pause
from skm.modules.execution.domain.stage_record import StageState
from skm.modules.execution.domain.step import RoleId
from skm.modules.execution.domain.task import TaskStatus
from skm.modules.execution.ports import (
    AssignmentRepository,
    AttemptRepository,
    BudgetRepository,
    BundleRepository,
    ExecutionQueries,
    RunRepository,
    StageRepository,
    StepRepository,
    TaskRepository,
)
from skm.modules.execution.public import ClaimAssignment
from skm.modules.settings.public import SetValue
from skm.modules.workspace.public import RecordWorkerHeartbeat
from unit.execution.application._support import (
    _shared_side,
    context,
    decision_case,
    seeded,
    set_setting,
    side,
)

__all__ = ["_shared_side", "side"]
SYSTEM = Actor(SYSTEM_PRINCIPAL_ID, PrincipalKind.SERVICE, "system")


def execute(side, module, payload=None):
    with side.uow() as uow:
        result = module.handle(module.SPEC.dto(payload or {}), context(side, uow, actor=SYSTEM), uow)
        uow.commit()
        return result


def cancel_available(side, assignment):
    with side.uow() as uow:
        repo = uow.repo(AssignmentRepository)
        current = repo.get(assignment.id)
        repo.save(
            transition_assignment(current, AssignmentState.CANCELLED), expected_version=current.row_version
        )
        uow.commit()


def expire_clock(side):
    side.clock.advance(timedelta(seconds=121))


def snapshot(side, run, task, attempt):
    with side.uow(readonly=True) as uow:
        return (
            uow.repo(RunRepository).get(run.id),
            uow.repo(TaskRepository).get(task.id),
            uow.repo(AttemptRepository).get(attempt.id),
            uow.repo(AssignmentRepository).for_attempt(attempt.id),
        )


def events(side, run, kind):
    with side.uow(readonly=True) as uow:
        repo = uow.repo(ExecutionQueries)
        return [
            e
            for e in repo.run_events(run.id, 0, repo.head_run_seq(run.id), 1000)
            if e.get("event_type", e.get("type")) == f"urn:skm:execution:event:{kind}:v1"
        ]


def test_scheduler_reissues_preparing_without_charge_or_reselecting_a1(side):
    run, task, attempt, assignment = make_case(side)
    cancel_available(side, assignment)
    first = execute(side, schedule_ready_tasks)
    second = execute(side, schedule_ready_tasks)
    assert len(first["scheduled"]) == 1
    assert second["scheduled"] == []
    _, current_task, current_attempt, rows = snapshot(side, run, task, attempt)
    assert current_task.attempt_count == 1
    assert current_attempt.state is AttemptState.PREPARING
    assert current_attempt.continuation == attempt.continuation
    assert sum(a.state is AssignmentState.AVAILABLE for a in rows) == 1


@pytest.mark.parametrize("entry_point", ["scheduler", "continuation"])
def test_worker_selector_applies_to_assignment_requirements(side, entry_point):
    side.client.dispatch(
        SetValue.from_json(
            {
                "scope": {"level": "project", "scope_id": str(side.proj)},
                "key": "execution.workers.selector",
                "value": ["linux", "arch=x86_64", "runtime=managed", "runtime:codex_cli"],
            }
        )
    )
    run, task, attempt, original = make_case(side)
    cancel_available(side, original)
    if entry_point == "scheduler":
        assert len(execute(side, schedule_ready_tasks)["scheduled"]) == 1
    else:
        with side.uow() as uow:
            assert process_pending(uow, context(side, uow, run), attempt.id) == "run_stage"
            uow.commit()

    _, _, _, rows = snapshot(side, run, task, attempt)
    (pending,) = (a for a in rows if a.state is AssignmentState.AVAILABLE)
    assert pending.requirements.capabilities == frozenset({"runtime:codex_cli"})
    assert pending.requirements.required_labels == frozenset({"linux", "arch=x86_64", "runtime=managed"})


@pytest.mark.parametrize(
    ("runtime_id", "offered_capabilities", "can_claim"),
    [
        pytest.param("codex_cli", ["codex_cli"], True, id="legacy-offer"),
        pytest.param("codex_cli", ["codex_cli", "runtime:codex_cli"], True, id="prefixed-offer"),
        pytest.param("codex_cli", [], False, id="runtime-omitted-from-offer"),
        pytest.param("claude_code", ["codex_cli"], False, id="runtime-not-registered"),
    ],
)
def test_runtime_selector_for_claim_and_capability_wait(side, runtime_id, offered_capabilities, can_claim):
    set_setting(side, "execution.scheduler.capability_wait_seconds", 10)
    side.client.dispatch(
        SetValue.from_json(
            {
                "scope": {"level": "project", "scope_id": str(side.proj)},
                "key": "execution.workers.selector",
                "value": [f"runtime:{runtime_id}"],
            }
        )
    )
    run, task, attempt, original = make_case(side)
    cancel_available(side, original)
    (scheduled,) = execute(side, schedule_ready_tasks)["scheduled"]
    side.clock.advance(timedelta(seconds=11))
    side.worker1_client.dispatch(RecordWorkerHeartbeat(side.worker1, None))
    execute(side, schedule_ready_tasks)

    _, current_task, _, _ = snapshot(side, run, task, attempt)
    if runtime_id == "codex_cli":
        assert current_task.blocking_reason is None
    else:
        assert current_task.blocking_reason is not None
        assert current_task.blocking_reason.code is BlockingCode.BLOCKED_BY_CAPABILITY

    result = side.worker1_client.dispatch(
        ClaimAssignment(
            worker_id=str(side.worker1),
            host_id=str(side.host1),
            workspace_id=str(side.ws),
            offer={
                "capabilities": offered_capabilities,
                "labels": ["linux"],
                "environment_kinds": ["git_worktree"],
                "isolation_profiles": ["landlock"],
            },
        ),
        idempotency_key=f"claim:{side.new_id()}",
    )
    if can_claim:
        assert result["assignment_id"] == scheduled["assignment_id"]
    else:
        assert result["outcome"] == "nothing_to_claim"


def test_initial_scheduler_selects_a1_once_and_never_starts_the_attempt(side):
    _run, task, old = seeded(side, task_status=TaskStatus.READY, attempt_state=AttemptState.PREPARING)
    with side.uow() as uow:
        repo = uow.repo(AttemptRepository)
        repo.save(
            transition_attempt(
                old, AttemptState.ABANDONED, now=side.clock.now(), end_reason=AttemptEndReason.RESTARTED
            ),
            expected_version=repo.version(old.id),
        )
        current = replace(task, current_attempt_id=None, attempt_count=0, row_version=task.row_version + 1)
        uow.repo(TaskRepository).save(current, expected_version=task.row_version)
        uow.commit()
    result = execute(side, schedule_ready_tasks)
    assert len(result["scheduled"]) == 1
    with side.uow(readonly=True) as uow:
        current = uow.repo(TaskRepository).get(task.id)
        attempt = uow.repo(AttemptRepository).get(current.current_attempt_id)
        assert current.attempt_count == 1
        assert current.status is TaskStatus.ASSIGNED
        assert attempt.state is AttemptState.PREPARING
        assert attempt.continuation.cause.advance_rule == "A1"
        assert attempt.continuation.stage.stage_type == "prepare_environment"
        assert uow.repo(StageRepository).history(attempt.id).entries == ()
    assert execute(side, schedule_ready_tasks)["scheduled"] == []


def test_crash_before_begin_keeps_attempt_cursor_and_fences_old_claim(side):
    run, task, attempt, assignment = make_case(side)
    old = claim(side)
    expire_clock(side)
    assert execute(side, expire_leases)["expired"] == 1
    assert execute(side, expire_leases)["expired"] == 0
    _, current_task, current_attempt, rows = snapshot(side, run, task, attempt)
    assert current_task.attempt_count == 1
    assert current_attempt.continuation == attempt.continuation
    assert next(a for a in rows if a.id == assignment.id).state is AssignmentState.EXPIRED
    fresh = claim(side)
    assert fresh["assignment_id"] != old["assignment_id"]
    assert fresh["attempt_id"] == old["attempt_id"]


def test_expiry_between_stages_ignores_old_completed_runtime(side):
    run, task, attempt, _ = make_case(side, env=True)
    claim(side)
    with side.uow() as uow:
        completed = seed_stage(side, uow, attempt, stage_id="past", state=StageState.COMPLETED)
        uow.repo(StageRepository).save(replace(completed, runtime_started_at=completed.started_at))
        uow.commit()
    expire_clock(side)
    assert execute(side, expire_leases)["expired"] == 1
    _, current_task, current_attempt, rows = snapshot(side, run, task, attempt)
    assert current_attempt.continuation == attempt.continuation
    assert current_task.blocking_reason is None
    assert all(row.reap_stage_record_id is None for row in rows)


def running_case(side, *, state=StageState.RUNNING, role=RoleId.REVIEWER):
    run, task, attempt, assignment = make_case(side, stage_id="review", stage_type="agent_review", env=True)
    from contracts.execution.seed_helpers import seed_output
    from skm.modules.execution.domain.attempt import record_output

    with side.uow() as uow:
        attempts = uow.repo(AttemptRepository)
        current = attempts.get(attempt.id)
        output = seed_output(side, uow, current)
        attempts.save(
            record_output(current, output, previous=None), expected_version=attempts.version(current.id)
        )
        uow.commit()
    claimed = claim(side)
    assert claimed.get("outcome") is None, claimed
    manifest = side.make_final_manifest()
    with side.uow() as uow:
        task = uow.repo(TaskRepository).get(task.id)
        updated = replace(task, status=TaskStatus.REVIEWING, row_version=task.row_version + 1)
        uow.repo(TaskRepository).save(updated, expected_version=task.row_version)
        current_attempt = uow.repo(AttemptRepository).get(attempt.id)
        consumed, _ = consume_stage(
            current_attempt, continuation_id=current_attempt.continuation.continuation_id
        )
        uow.repo(AttemptRepository).save(
            consumed, expected_version=uow.repo(AttemptRepository).version(attempt.id)
        )
        stage = seed_stage(side, uow, attempt, stage_id="review", stage_type="agent_review", state=state)
        step = seed_step(
            side,
            uow,
            attempt,
            stage,
            manifest_id=manifest,
            role=role,
            admission={"min_class": "implementation"},
        )
        uow.commit()
    return run, updated, attempt, assignment, stage, step


@pytest.mark.parametrize("attempt_limit", [1, 3])
def test_runtime_expiry_requires_reap_then_l3_while_paused(side, attempt_limit):
    run, task, attempt, _, stage, _ = running_case(side)
    expire_clock(side)
    assert execute(side, expire_leases)["expired"] == 1
    _, current_task, current_attempt, rows = snapshot(side, run, task, attempt)
    assert current_task.blocking_reason.code.value == "RECOVERING"
    assert current_attempt.state is AttemptState.WAITING
    assert current_attempt.continuation.kind == "advance"
    reap = next(a for a in rows if a.state is AssignmentState.AVAILABLE)
    assert reap.reap_stage_record_id == stage.id
    assert claim(side)["outcome"] == "nothing_to_claim"
    with side.uow() as uow:
        repo = uow.repo(RunRepository)
        latest = repo.get(run.id)
        repo.save(pause(latest, reason="owner", source="owner"), expected_version=latest.row_version)
        uow.commit()
    side.clock.advance(timedelta(seconds=1000))
    execute(side, schedule_ready_tasks)
    latest_run, current_task, current_attempt, rows = snapshot(side, run, task, attempt)
    assert latest_run.status is RunStatus.PAUSED
    assert current_task.status is TaskStatus.READY
    assert current_task.blocking_reason is None
    assert current_task.attempt_count == 1
    assert current_attempt.state is AttemptState.OWNERSHIP_LOST
    assert current_attempt.continuation is None
    assert not any(a.state in {AssignmentState.AVAILABLE, AssignmentState.LEASED} for a in rows)
    set_setting(side, "budgets.task.max_attempts", attempt_limit)
    from skm.modules.execution.domain.run import resume

    with side.uow() as uow:
        latest = uow.repo(RunRepository).get(run.id)
        uow.repo(RunRepository).save(resume(latest), expected_version=latest.row_version)
        uow.commit()
    execute(side, schedule_ready_tasks)
    with side.uow(readonly=True) as uow:
        task_after = uow.repo(TaskRepository).get(task.id)
        if attempt_limit == 1:
            assert task_after.status is TaskStatus.FAILED
            assert task_after.attempt_count == 1
        else:
            assert task_after.attempt_count == 2
            assert task_after.current_attempt_id != attempt.id
            assert (
                uow.repo(AttemptRepository).get(task_after.current_attempt_id).state is AttemptState.PREPARING
            )


@pytest.mark.parametrize(
    ("state", "expected"), [(StageState.CONTEXT_DRAFT, "released"), (StageState.RUNNING, "settled")]
)
def test_expiry_closes_every_reservation_in_the_stage_transaction(side, state, expected):
    run, _task, _attempt, _, stage, step = running_case(side, state=state)
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
        uow.commit()
    expire_clock(side)
    execute(side, expire_leases)
    with side.uow(readonly=True) as uow:
        assert not uow.repo(BudgetRepository).open_for_steps((step.id,))
        assert uow.repo(BudgetRepository).get_reservation(reservation.id).state == expected
        closed = uow.repo(StepRepository).get(step.id)
        assert closed.runtime_observation is None
        assert closed.error_code == "LEASE_LOST"
        assert uow.repo(StageRepository).get(stage.id).state is StageState.INTERRUPTED
    terminal = events(side, run, "stage-completed")
    assert len(terminal) == 1
    assert terminal[0]["payload"]["coverage"] == "unavailable"
    assert terminal[0]["payload"]["step_states"] == [{"step_id": str(step.id), "state": "failed"}]


def test_human_wait_is_not_an_attempt_or_timeout(side):
    run, task, attempt, _ = decision_case(side)
    side.clock.advance(timedelta(days=2))
    execute(side, schedule_ready_tasks)
    execute(side, enforce_timeouts)
    _, current_task, current_attempt, rows = snapshot(side, run, task, attempt)
    assert current_task.attempt_count == 1
    assert current_attempt.id == attempt.id
    assert rows == ()


@pytest.mark.parametrize(("tier", "expected"), [("light", 180), ("medium", 300), ("heavy", 600)])
def test_reviewer_soft_warning_never_pauses_or_recovers(side, monkeypatch, tier, expected):
    from skm.modules.execution.domain.work_policy import (
        HardCeilings,
        Intensity,
        WorkPolicyOverride,
        WorkPolicySettings,
        resolve_work_policy,
    )

    policy = resolve_work_policy(
        WorkPolicySettings.defaults(),
        unit=WorkPolicyOverride(role_intensity={"reviewer": Intensity(tier)}),
        ceilings=HardCeilings(profile_timeout_seconds={"reviewer": 1800}),
    )
    monkeypatch.setattr(enforce_timeouts, "find_task_work_policy", lambda _uow, _task: policy)
    run, task, attempt, _, stage, _ = running_case(side)
    side.clock.advance(timedelta(seconds=expected + 1))
    result = execute(side, enforce_timeouts, {"run_id": str(run.id)})
    latest_run, current_task, _, _ = snapshot(side, run, task, attempt)
    assert latest_run.status is RunStatus.RUNNING
    assert current_task.blocking_reason is None
    assert result["failed"] == result["cancel_requested"] == 0
    assert result["diagnostics"][0]["actual_seconds"] == expected + 1
    assert result["diagnostics"][0]["expected_seconds"] == expected
    with side.uow(readonly=True) as uow:
        assert uow.repo(StageRepository).get(stage.id).state is StageState.RUNNING


def test_emergency_timeout_waits_grace_then_closes_once_with_reap_barrier(side):
    run, task, attempt, _, stage, step = running_case(side)
    side.clock.advance(timedelta(seconds=1801))
    first = execute(side, enforce_timeouts, {"run_id": str(run.id)})
    assert first["cancel_requested"] == 1
    assert snapshot(side, run, task, attempt)[0].status is RunStatus.RUNNING
    with side.uow(readonly=True) as uow:
        assert uow.repo(StageRepository).cancel_requested(attempt.id, 1)
    side.clock.advance(timedelta(seconds=61))
    result = execute(side, enforce_timeouts, {"run_id": str(run.id)})
    assert result["failed"] == 1
    assert execute(side, enforce_timeouts, {"run_id": str(run.id)})["failed"] == 0
    with side.uow(readonly=True) as uow:
        record = uow.repo(StageRepository).get(stage.id)
        assert record.state is StageState.FAILED
        assert record.error_code == "RUNTIME_TIMEOUT"
        assert uow.repo(StepRepository).get(step.id).runtime_observation is None


def test_terminal_pause_and_human_wait_do_not_add_active_seconds(side):
    run, _, attempt, _ = make_case(side)
    with side.uow() as uow:
        seed_stage(side, uow, attempt, state=StageState.COMPLETED)
        uow.commit()
    side.clock.advance(timedelta(days=2))
    execute(side, enforce_timeouts)
    with side.uow(readonly=True) as uow:
        assert uow.repo(RunRepository).get(run.id).status is RunStatus.RUNNING


def test_commands_reject_non_system_service_before_mutation(side):
    with side.uow() as uow:
        with pytest.raises(SkmError) as caught:
            schedule_ready_tasks.handle(schedule_ready_tasks.ScheduleReadyTasks(), context(side, uow), uow)
        assert caught.value.code.value == "FORBIDDEN"


def test_live_monitor_snapshot_does_not_change_frozen_bundle(side):
    run, _, _, assignment = make_case(side)
    cancel_available(side, assignment)
    with side.uow(readonly=True) as uow:
        before = uow.repo(BundleRepository).get(run.id)
    execute(side, schedule_ready_tasks, {"run_ids": [str(run.id)], "limit": 1})
    with side.uow(readonly=True) as uow:
        assert uow.repo(BundleRepository).get(run.id) == before
        repo = uow.repo(ExecutionQueries)
        history = repo.run_events(run.id, 0, repo.head_run_seq(run.id), 100)
        assert history


def test_background_services_use_system_actor_surface_and_registered_dto(side):
    from skm.background.lease_sweeper import LeaseSweeper
    from skm.background.scheduler import Scheduler
    from skm.background.timeout_enforcer import TimeoutEnforcer
    from skm.kernel.ports_uow import Surface

    for service_type, module, result in (
        (Scheduler, schedule_ready_tasks, {"scheduled": [{}], "runs_started": [], "runs_checked": 1}),
        (LeaseSweeper, expire_leases, {"expired": 1}),
        (TimeoutEnforcer, enforce_timeouts, {"failed": 1}),
    ):
        calls = []

        class Bus:
            def dispatch(self, cmd, *, actor, meta, calls=calls, module=module, result=result):
                calls.append((cmd, actor, meta))
                return module.SPEC.result(result)

        class Registry:
            def command_by_name(self, name, module=module):
                return module.SPEC

        service = service_type(Bus(), registry=Registry(), clock=side.clock, ids=side.ids, limit=1)
        tick = service.tick()
        assert tick.processed == 1
        assert tick.next_delay_seconds == 0.0
        cmd, actor, meta = calls[0]
        assert type(cmd) is module.SPEC.dto
        assert cmd["limit"] == 1
        assert actor == SYSTEM
        assert meta.surface is Surface.BACKGROUND
        assert meta.idempotency_key is None


def test_run_filter_and_limit_are_consumed_by_scheduler(side):
    first = make_case(side)
    second = make_case(side)
    cancel_available(side, first[3])
    cancel_available(side, second[3])
    result = execute(side, schedule_ready_tasks, {"run_ids": [str(second[0].id)], "limit": 1})
    assert result["runs_checked"] == 1
    assert result["scheduled"][0]["task_id"] == str(second[1].id)
    assert execute(side, schedule_ready_tasks, {"run_ids": [str(first[0].id)], "limit": 1})["scheduled"]


def test_expired_decision_keeps_waiting_without_new_attempt(side):
    from skm.modules.execution.ports import DecisionRepository

    run, task, attempt, request = decision_case(side)
    with side.uow() as uow:
        uow.repo(DecisionRepository).save(
            replace(request, deadline_at=side.clock.now() - timedelta(seconds=1))
        )
        uow.commit()
    result = execute(side, enforce_timeouts, {"run_id": str(run.id), "limit": 1})
    assert result["decisions_expired"] == 1
    assert execute(side, enforce_timeouts, {"run_id": str(run.id)})["decisions_expired"] == 0
    assert snapshot(side, run, task, attempt)[1].attempt_count == 1


def test_confirmed_reap_claim_clears_old_l3_deadline_without_losing_attempt(side):
    from skm.modules.execution import public as execution
    from skm.modules.execution.domain.lease import ProcessIdentity
    from skm.modules.execution.domain.stage_record import record_process_identity

    run, task, attempt, _, stage, step = running_case(side)
    owner = {
        "host_id": str(side.host1),
        "worker_id": str(side.worker1),
        "attempt_id": str(attempt.id),
        "stage_record_id": str(stage.id),
        "unit_kind": "step",
        "unit_id": str(step.id),
        "owner_nonce": "reap-proof-owner-123456",
        "identity_dir": "/owned/background-step",
    }
    ownership = {"kind": "cgroup", "ref": "/skm/background-step", "owner": owner}
    raw_identity = {
        "pid": 123,
        "pgid": 123,
        "started_at": side.clock.now().isoformat(),
        "ownership": ownership,
        "boot_id": "background-test-boot",
        "start_ticks": 100,
    }
    identity = ProcessIdentity(
        123, 123, side.clock.now(), ownership, boot_id="background-test-boot", start_ticks=100
    )
    with side.uow() as uow:
        uow.repo(StageRepository).save(record_process_identity(stage, identity))
        uow.commit()
    expire_clock(side)
    execute(side, expire_leases)
    assert claim(side)["outcome"] == "nothing_to_claim"
    from copy import deepcopy

    from skm.modules.execution.domain.assignment import WorkerOffer
    from skm.modules.execution.domain.environment import EnvironmentKind

    proof = {
        "identity": raw_identity,
        "dead": True,
        "stage_record_id": str(stage.id),
        "unit_kind": "step",
        "unit_id": str(step.id),
    }
    offer = WorkerOffer(
        side.worker1,
        side.host1,
        frozenset(),
        frozenset(),
        frozenset({EnvironmentKind.GIT_WORKTREE}),
        frozenset(),
        (proof,),
    )
    forged = deepcopy(proof)
    forged["identity"]["ownership"]["owner"]["owner_nonce"] = "foreign-owner-nonce"
    with side.uow() as uow:
        repo = uow.repo(StageRepository)
        now = uow.repo(RunRepository).now()
        assert not repo.confirm_reap(
            stage.id, replace(offer, reaped_steps=(forged,)), now, receipt_id=side.new_id()
        )
        assert not repo.confirm_reap(
            stage.id, replace(offer, host_id=side.host2), now, receipt_id=side.new_id()
        )
        assert repo.confirm_reap(stage.id, offer, now, receipt_id=side.new_id())
        assert repo.reap_confirmed(stage.id)
        uow.commit()
    fresh = side.worker1_client.dispatch(
        execution.ClaimAssignment(
            worker_id=str(side.worker1),
            host_id=str(side.host1),
            workspace_id=str(side.ws),
            offer={
                "capabilities": ["codex_cli"],
                "labels": ["linux"],
                "environment_kinds": ["git_worktree"],
                "isolation_profiles": ["landlock"],
            },
            reaped_steps=[
                {
                    "identity": raw_identity,
                    "dead": True,
                    "stage_record_id": str(stage.id),
                    "unit_kind": "step",
                    "unit_id": str(step.id),
                }
            ],
        ),
        idempotency_key=f"reap-claim:{side.new_id()}",
    )
    assert fresh["attempt_id"] == str(attempt.id)
    new_claim = {
        "assignment_id": fresh["assignment_id"],
        "attempt_id": str(attempt.id),
        "worker_id": str(side.worker1),
        "fencing_token": fresh["fencing_token"],
    }
    for _ in range(4):
        side.clock.advance(timedelta(seconds=100))
        side.worker1_client.dispatch(
            execution.RenewLease(claim=new_claim), idempotency_key=f"reap-renew:{side.new_id()}"
        )
    execute(side, schedule_ready_tasks)
    _, current_task, current_attempt, _ = snapshot(side, run, task, attempt)
    assert current_task.blocking_reason is None
    assert current_task.attempt_count == 1
    assert current_attempt.state is AttemptState.RUNNING
    assert current_attempt.continuation.stage.mode.value == "retry"


def test_cooperative_cancel_port_binds_request_to_stage_fence(side):
    run, _, attempt, assignment, stage, _ = running_case(side)
    with side.uow() as uow:
        stages = uow.repo(StageRepository)
        now = uow.repo(RunRepository).now()
        grace = {"grace_deadline_at": now}
        assert not stages.request_cancel(stage.id, assignment.id, 999, now, now, **grace)
        assert not stages.cancel_requested(attempt.id, 1)
        assert stages.request_cancel(stage.id, assignment.id, 1, now, now, **grace)
        assert not stages.request_cancel(stage.id, assignment.id, 1, now, now, **grace)
        assert stages.cancel_requested(attempt.id, 1)
        assert not stages.cancel_requested(attempt.id, 2)
        assert uow.repo(RunRepository).get(run.id).status is RunStatus.RUNNING
        uow.commit()


def test_live_limit_raise_cannot_reset_an_issued_timeout(side):
    run, _, _, _, stage, _ = running_case(side)
    set_setting(side, "execution.timeouts.role_wall_seconds", {"reviewer": 600})
    side.clock.advance(timedelta(seconds=601))
    assert execute(side, enforce_timeouts, {"run_id": str(run.id)})["cancel_requested"] == 1
    with side.uow(readonly=True) as uow:
        requested = uow.repo(StageRepository).get(stage.id).outcome["timeout_requested_at"]
    set_setting(side, "execution.timeouts.role_wall_seconds", {"reviewer": 1800})
    side.clock.advance(timedelta(seconds=61))
    assert execute(side, enforce_timeouts, {"run_id": str(run.id)})["failed"] == 1
    with side.uow(readonly=True) as uow:
        closed = uow.repo(StageRepository).get(stage.id)
        assert closed.error_code == "RUNTIME_TIMEOUT"
        assert closed.finished_at is not None
    assert requested


def test_live_grace_raise_cannot_postpone_an_issued_cancellation(side):
    run, _, _, _, stage, _ = running_case(side)
    set_setting(side, "execution.supervisor.grace_seconds", 60)
    side.clock.advance(timedelta(seconds=1801))
    assert execute(side, enforce_timeouts, {"run_id": str(run.id)})["cancel_requested"] == 1
    with side.uow(readonly=True) as uow:
        saved = uow.repo(StageRepository).get(stage.id).outcome["timeout_grace_deadline_at"]
    set_setting(side, "execution.supervisor.grace_seconds", 600)
    side.clock.advance(timedelta(seconds=59))
    assert execute(side, enforce_timeouts, {"run_id": str(run.id)})["failed"] == 0
    with side.uow(readonly=True) as uow:
        assert uow.repo(StageRepository).get(stage.id).outcome["timeout_grace_deadline_at"] == saved
    side.clock.advance(timedelta(seconds=2))
    assert execute(side, enforce_timeouts, {"run_id": str(run.id)})["failed"] == 1
    assert execute(side, enforce_timeouts, {"run_id": str(run.id)})["failed"] == 0
