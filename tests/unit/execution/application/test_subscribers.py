"""Subscriber guards, event-source deduplication, archive pause, and material rechecks."""

from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from typing import Any

from skm.modules.execution.application import subscribers
from skm.modules.execution.domain.blocking_reason import BlockingCode, blocking_reason
from skm.modules.execution.domain.run import RunStatus
from skm.modules.execution.domain.task import TaskStatus
from skm.modules.execution.ports import AttemptRepository, DecisionRepository, RunRepository, TaskRepository

from ._support import _shared_side as _shared_side
from ._support import context, seeded
from ._support import side as side


def subctx(side: Any, uow: Any, run: Any) -> Any:
    ctx = context(side, uow, run)
    return SimpleNamespace(
        clock=ctx.clock,
        ids=ctx.ids,
        gateways=ctx.gateways,
        log=ctx.log,
        consumer_id="execution.test",
        config_for=lambda scope: ctx.config,
    )


def event(side: Any, run: Any, **payload: Any) -> Any:
    return SimpleNamespace(
        id=side.new_id(),
        workspace_id=side.ws,
        type="urn:skm:integrations:event:hook-delivery-failed:v1",
        payload={"run_id": str(run.id), **payload},
    )


def test_blocking_hook_uses_source_identity_and_duplicate_delivery_is_a_noop(side: Any) -> None:
    run, task, attempt = seeded(side, run_status=RunStatus.PAUSED)
    received = event(side, run, blocking=True, subscription_id=str(side.new_id()))
    with side.uow() as uow:
        ctx = subctx(side, uow, run)
        subscribers.escalate_blocking_hook_failure(received, ctx, uow)
        subscribers.escalate_blocking_hook_failure(received, ctx, uow)
        requests = uow.repo(DecisionRepository).open_for_task(task.id)
        assert len(requests) == 1
        assert requests[0].payload["code"] == "HOOK_DELIVERY_FAILED"
        cursor = uow.repo(AttemptRepository).get(attempt.id).continuation
        assert len(cursor.triggers) == 1
        assert cursor.triggers[0].source_event_id == received.id
        uow.commit()


def test_nonblocking_hook_has_no_mutation(side: Any) -> None:
    run, task, _ = seeded(side)
    with side.uow() as uow:
        subscribers.escalate_blocking_hook_failure(
            event(side, run, blocking=False), subctx(side, uow, run), uow
        )
        assert not uow.repo(DecisionRepository).open_for_task(task.id)


def test_plan_archive_pauses_and_does_not_replay_stage_selection(side: Any) -> None:
    from skm.kernel.error_codes import ErrorCode
    from skm.modules.execution.domain.attempt import AttemptState
    from skm.modules.execution.ports import ExecutionQueries

    from .test_cancel_pause_resume import assignment

    run, task, attempt = seeded(
        side, cursor=True, task_status=TaskStatus.ASSIGNED, attempt_state=AttemptState.PREPARING
    )
    with side.uow() as uow:
        assignment(side, uow, run, task, attempt)
        received = event(side, run, plan_id=str(run.plan_id))
        subscribers.plan_archived_guard(received, subctx(side, uow, run), uow)
        assert uow.repo(RunRepository).get(run.id).status is RunStatus.PAUSED
        assert uow.repo(AttemptRepository).get(attempt.id).continuation == attempt.continuation
        paused = uow.repo(RunRepository).get(run.id)
        assert paused.stop_code == ErrorCode.PLAN_ARCHIVED.value
        assert paused.pause_source == "system"
        assert uow.repo(TaskRepository).get(task.id).status is TaskStatus.READY
        uow.commit()
    with side.uow(readonly=True) as uow:
        query = uow.repo(ExecutionQueries)
        events = query.run_events(run.id, 0, query.head_run_seq(run.id), 100)
        ready = next(
            e["payload"] for e in events if e["event_type"] == "urn:skm:execution:event:task-ready:v1"
        )
        assert ready["cause"]["trigger_kind"] == "subscription"
        assert ErrorCode.PLAN_ARCHIVED.value in ready["cause"]["reason_codes"]


def test_material_availability_only_advances_the_matching_recheck_time(side: Any) -> None:
    run, task, _ = seeded(side)
    with side.uow() as uow:
        reason = blocking_reason(
            BlockingCode.BLOCKED_BY_MATERIAL,
            task_id=task.id,
            refs={"material_ids": [], "file_version_ids": [str(side.fv1)], "required_for": "execution"},
            now=side.clock.now(),
            message="material pending",
            next_check_at=side.clock.now() + timedelta(hours=1),
        )
        blocked = replace(
            task, status=TaskStatus.BLOCKED, blocking_reason=reason, row_version=task.row_version + 1
        )
        uow.repo(TaskRepository).save(blocked, expected_version=task.row_version)
        received = event(side, run, file_version_id=str(side.fv1))
        subscribers.material_available(received, subctx(side, uow, run), uow)
        result = uow.repo(TaskRepository).get(task.id)
        assert result.blocking_reason.next_check_at == side.clock.now()
        assert result.blocking_reason.since == reason.since
        uow.commit()


def approval_case(side: Any):
    from skm.modules.execution.domain.decision_request import DecisionKind, DecisionState
    from skm.modules.execution.domain.stage_record import StageOutcomeKind, StageState
    from skm.modules.execution.ports import StageRepository

    from ._support import decision_case, seed_stage

    run, task, attempt, request = decision_case(side, code="APPROVAL_REQUIRED")
    intent_id, effect_id = side.new_id(), side.new_id()
    with side.uow() as uow:
        stage = seed_stage(
            side,
            uow,
            attempt,
            stage_id="integrate",
            stage_type="integrate",
            state=StageState.COMPLETED,
            outcome_kind=StageOutcomeKind.APPROVAL_REQUIRED,
        )
        uow.repo(StageRepository).save(
            replace(stage, outcome={"intent_id": str(intent_id), "effect_id": str(effect_id)})
        )
        uow.repo(DecisionRepository).save(replace(request, state=DecisionState.CANCELLED))
        request = replace(
            request,
            id=side.new_id(),
            kind=DecisionKind.APPROVAL,
            payload={
                "code": "APPROVAL_REQUIRED",
                "refs": {"intent_id": str(intent_id), "effect_id": str(effect_id)},
            },
            binding={"attempt_id": str(attempt.id), "input_part_digest": stage.input_digest},
        )
        uow.repo(DecisionRepository).add(request)
        task = replace(
            task,
            blocking_reason=blocking_reason(
                BlockingCode.WAITING_APPROVAL,
                task_id=task.id,
                refs={"intent_id": str(intent_id), "decision_request_id": str(request.id)},
                now=side.clock.now(),
                message="approval",
            ),
            row_version=task.row_version + 1,
        )
        uow.repo(TaskRepository).save(task, expected_version=task.row_version - 1)
        uow.commit()
    return run, task, attempt, request, intent_id, effect_id


def test_policy_approval_defers_while_paused_then_selects_exact_effect_once(side: Any) -> None:
    from skm.modules.execution.generated.commands import ResumeRun
    from skm.modules.execution.ports import AssignmentRepository

    run, _task, attempt, request, intent_id, effect_id = approval_case(side)
    received = event(side, run, intent_id=str(intent_id))
    received.type = "urn:skm:policy:event:intent-approved:v1"
    with side.uow() as uow:
        subscribers.intent_resolved_resume(received, subctx(side, uow, run), uow)
        assert uow.repo(DecisionRepository).get(request.id).state.value == "applied"
        cursor = uow.repo(AttemptRepository).get(attempt.id).continuation
        assert cursor.kind == "advance"
        assert cursor.triggers[0].source_event_id == received.id
        uow.commit()
    side.client.dispatch(ResumeRun(run.id))
    side.client.dispatch(ResumeRun(run.id))
    with side.uow(readonly=True) as uow:
        cursor = uow.repo(AttemptRepository).get(attempt.id).continuation
        assert cursor.kind == "stage"
        assert cursor.stage.stage_type == "integrate"
        assert cursor.stage.params["effect_id"] == str(effect_id)
        assert len(uow.repo(AssignmentRepository).for_attempt(attempt.id)) == 1


def test_policy_denial_creates_explicit_owner_mismatch_wait(side: Any) -> None:
    run, task, _attempt, request, intent_id, _effect_id = approval_case(side)
    received = event(side, run, intent_id=str(intent_id))
    received.type = "urn:skm:policy:event:intent-denied:v1"
    with side.uow() as uow:
        subscribers.intent_resolved_resume(received, subctx(side, uow, run), uow)
        assert uow.repo(DecisionRepository).get(request.id).state.value == "denied"
        assert any(
            r.payload.get("code") == "APPROVAL_MISMATCH"
            for r in uow.repo(DecisionRepository).open_for_task(task.id)
        )
        uow.commit()


def test_stale_policy_approval_never_transfers_to_a_changed_stage_digest(side: Any) -> None:

    run, _task, attempt, request, intent_id, _effect_id = approval_case(side)
    received = event(side, run, intent_id=str(intent_id))
    received.type = "urn:skm:policy:event:intent-approved:v1"
    with side.uow() as uow:
        from skm.modules.execution.ports import StageRepository

        latest = uow.repo(StageRepository).history(attempt.id).last().record
        uow.repo(StageRepository).add(
            replace(
                latest,
                id=side.new_id(),
                seq=2,
                stage_id="execute",
                stage_type="agent_step",
                input_digest="sha256:" + "f" * 64,
            )
        )
        subscribers.intent_resolved_resume(received, subctx(side, uow, run), uow)
        assert uow.repo(DecisionRepository).get(request.id).state.value == "open"
        assert uow.repo(AttemptRepository).get(attempt.id).continuation is None
        uow.commit()
