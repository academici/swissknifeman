"""Execution consumers use the event identity as their trusted continuation source."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid5

from skm.application_bus.registry import SubscriberSpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.ids import RunId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeId, ScopeKind, ScopeRef, ScopeRegistry
from skm.modules.access.public import SYSTEM_ACTOR
from skm.modules.execution.application._control import current_binding_digest, lock_run
from skm.modules.execution.application._events import cause, emit, save_task
from skm.modules.execution.application.apply_action import commit_trigger, prepare_trigger
from skm.modules.execution.application.commands.pause_run import handle
from skm.modules.execution.domain.blocking_reason import BlockingCode, blocking_reason
from skm.modules.execution.domain.decision_request import (
    Audience,
    DecisionKind,
    DecisionRequest,
    DecisionState,
)
from skm.modules.execution.domain.external_effect import EffectState
from skm.modules.execution.domain.ids import DecisionRequestId
from skm.modules.execution.domain.run import TERMINAL_RUN_STATUSES
from skm.modules.execution.domain.task import TERMINAL_TASK_STATUSES, TaskStatus
from skm.modules.execution.generated.commands import PauseRun
from skm.modules.execution.ports import (
    AttemptRepository,
    DecisionRepository,
    EffectRepository,
    RunRepository,
    TaskRepository,
)


def control_context(ctx: Any, uow: UnitOfWork, run: Any) -> Any:
    scope = ScopeRef(ScopeKind.RUN, ScopeId(run.id))
    return SimpleNamespace(
        actor=SYSTEM_ACTOR,
        config=ctx.config_for(scope),
        clock=ctx.clock,
        ids=ctx.ids,
        gateways=ctx.gateways,
        scope=scope,
        scope_chain=uow.repo(ScopeRegistry).ancestors(scope.id),
        log=ctx.log,
        meta=SimpleNamespace(request_id=ctx.consumer_id, surface="background"),
    )


def _runs(event: Any, uow: UnitOfWork) -> list[Any]:
    return [
        run
        for rid in uow.repo(RunRepository).list_active_ids(limit=500)
        if (run := uow.repo(RunRepository).get(rid)).workspace_id == event.workspace_id
    ]


def plan_archived_guard(event: Any, ctx: Any, uow: UnitOfWork) -> None:
    plan_id = event.payload.get("plan_id")
    for run in _runs(event, uow):
        if str(run.plan_id) == plan_id:
            handle(PauseRun(run.id, "plan archived"), control_context(ctx, uow, run), uow)


def material_available(event: Any, ctx: Any, uow: UnitOfWork) -> None:
    version_id = event.payload.get("file_version_id")
    for observed in _runs(event, uow):
        run = lock_run(uow, observed.id)
        for task in uow.repo(TaskRepository).list_for_run(run.id):
            reason = task.blocking_reason
            if (
                reason is not None
                and reason.code is BlockingCode.BLOCKED_BY_MATERIAL
                and version_id in reason.refs.get("file_version_ids", [])
            ):
                updated = replace(
                    task,
                    blocking_reason=replace(reason, next_check_at=ctx.clock.now()),
                    row_version=task.row_version + 1,
                )
                save_task(uow, run, task, updated, cause("subscription", event_id=event.id), ctx.clock.now())


def intent_resolved_resume(event: Any, ctx: Any, uow: UnitOfWork) -> None:
    intent_id = event.payload.get("intent_id")
    approved = "intent-approved" in event.type
    for observed in _runs(event, uow):
        run = lock_run(uow, observed.id)
        cctx = control_context(ctx, uow, run)
        for task in uow.repo(TaskRepository).list_for_run(run.id):
            reason = task.blocking_reason
            if reason is None or reason.refs.get("intent_id") != intent_id or task.current_attempt_id is None:
                continue
            attempt = uow.repo(AttemptRepository).get(task.current_attempt_id, for_update=True)
            requests = [
                r
                for r in uow.repo(DecisionRepository).open_for_task(task.id)
                if r.kind is DecisionKind.APPROVAL
            ]
            if task.status is not TaskStatus.AWAITING_DECISION or not requests:
                continue
            if any(
                r.binding.get("input_part_digest") != current_binding_digest(uow, attempt)
                or r.binding.get("attempt_id") != str(attempt.id)
                or r.binding.get("output_id") not in (None, str(attempt.current_output_id))
                for r in requests
            ):
                continue
            why = cause(
                "policy_resolved",
                event_id=event.id,
                refs=[{"kind": "decision_request", "id": str(r.id)} for r in requests],
            )
            pending = prepare_trigger(uow, cctx, attempt, event.id, why)
            if pending is attempt:
                continue
            for request in uow.repo(DecisionRepository).open_for_task(task.id):
                if request.kind is DecisionKind.APPROVAL:
                    uow.repo(DecisionRepository).save(
                        replace(
                            request,
                            state=DecisionState.APPLIED if approved else DecisionState.DENIED,
                            payload={
                                **request.payload,
                                "policy_resolution": "approved" if approved else "denied",
                            },
                        )
                    )
            if not approved:
                for effect in uow.repo(EffectRepository).unresolved(limit=500):
                    if str(effect.intent_id) == intent_id and effect.state is EffectState.INTENDED:
                        uow.repo(EffectRepository).save(
                            replace(effect, state=EffectState.FAILED, updated_at=ctx.clock.now())
                        )
                _hook_request(uow, cctx, run, task, event, "APPROVAL_MISMATCH")
            commit_trigger(uow, cctx, run, pending)


def _hook_request(uow: UnitOfWork, ctx: Any, run: Any, task: Any, event: Any, code: str) -> Any:
    options = (
        ["retry", "ignore", "cancel_run"] if code == "HOOK_DELIVERY_FAILED" else ["resume_run", "cancel_run"]
    )
    payload_doc: dict[str, Any] = {
        "code": code,
        "source_event_id": str(event.id),
        "subscription_id": event.payload.get("subscription_id"),
        "options": options,
    }
    if event.payload.get("delivery_id") is not None:
        payload_doc["delivery_id"] = event.payload.get("delivery_id")
    if event.payload.get("event_id") is not None:
        payload_doc["hook_event_id"] = event.payload.get("event_id")
    request = DecisionRequest(
        _hook_request_id(run, event) if code == "HOOK_DELIVERY_FAILED" else ctx.ids.new_id(),
        run.workspace_id,
        run.id,
        None if task is None else task.id,
        DecisionKind.ESCALATION,
        Audience.OWNER,
        None,
        frozenset(),
        None,
        None,
        1,
        payload_doc,
        None,
        {}
        if task is None or task.current_attempt_id is None
        else {
            "attempt_id": str(task.current_attempt_id),
            "input_part_digest": current_binding_digest(
                uow, uow.repo(AttemptRepository).get(task.current_attempt_id)
            ),
        },
        DecisionState.OPEN,
        None,
        None,
        ctx.clock.now(),
    )
    uow.repo(DecisionRepository).add(request)
    if task is not None:
        blocked = blocking_reason(
            BlockingCode.WAITING_OWNER,
            task_id=task.id,
            refs={"decision_request_id": str(request.id), "stop_code": code},
            now=ctx.clock.now(),
            message=code,
        )
        updated = replace(
            task,
            status=TaskStatus.AWAITING_DECISION,
            blocking_reason=blocked,
            row_version=task.row_version + 1,
        )
        save_task(uow, run, task, updated, cause("subscription", event_id=event.id), ctx.clock.now())
    emit(
        uow,
        run,
        "decision-requested",
        {
            "request_id": str(request.id),
            "task_id": None if task is None else str(task.id),
            "kind": "escalation",
            "audience": "owner",
            "blocking_code": "WAITING_OWNER",
        },
        cause("subscription", event_id=event.id),
    )
    return request


def _audit_hook_failure_ignored(ctx: Any, event: Any, reason: str) -> None:
    ctx.log.info(
        "execution.hook_delivery_failure.ignored",
        reason=reason,
        source_event_id=str(event.id),
        delivery_id=event.payload.get("delivery_id"),
        subscription_id=event.payload.get("subscription_id"),
        hook_event_id=event.payload.get("event_id"),
        run_id=event.payload.get("run_id"),
        blocking=bool(event.payload.get("blocking")),
    )


def _hook_request_id(run: Any, event: Any) -> DecisionRequestId:
    """A durable identity survives answered requests, task transitions and relay redelivery."""
    source = event.payload.get("event_id") or str(event.id)
    subscription = event.payload.get("subscription_id")
    return DecisionRequestId(uuid5(run.id, f"hook-delivery-failed:{source}:{subscription}"))


def _validate_blocking_run(event: Any, ctx: Any, uow: UnitOfWork) -> Any | None:
    if not event.payload.get("blocking"):
        _audit_hook_failure_ignored(ctx, event, "non_blocking")
        return None
    rid = event.payload.get("run_id")
    if not isinstance(rid, str) or not rid:
        _audit_hook_failure_ignored(ctx, event, "missing_run_id")
        return None
    try:
        run_uuid = RunId(UUID(rid))
    except ValueError:
        _audit_hook_failure_ignored(ctx, event, "invalid_run_id")
        return None

    from skm.kernel.errors import NotFound

    try:
        observed = uow.repo(RunRepository).get(run_uuid)
    except NotFound:
        _audit_hook_failure_ignored(ctx, event, "run_not_found")
        return None
    if observed.workspace_id != event.workspace_id:
        _audit_hook_failure_ignored(ctx, event, "workspace_mismatch")
        return None
    if observed.status in TERMINAL_RUN_STATUSES:
        _audit_hook_failure_ignored(ctx, event, "terminal_run")
        return None
    locked = lock_run(uow, observed.id)
    if locked.status in TERMINAL_RUN_STATUSES:
        _audit_hook_failure_ignored(ctx, event, "terminal_run")
        return None
    return locked


def _already_escalated(uow: UnitOfWork, run: Any, event: Any) -> bool:
    from skm.kernel.errors import NotFound

    try:
        uow.repo(DecisionRepository).get(_hook_request_id(run, event))
    except NotFound:
        return False
    return True


def escalate_blocking_hook_failure(event: Any, ctx: Any, uow: UnitOfWork) -> None:
    run = _validate_blocking_run(event, ctx, uow)
    if run is None:
        return
    cctx = control_context(ctx, uow, run)
    active_tasks = [
        t for t in uow.repo(TaskRepository).list_for_run(run.id) if t.status not in TERMINAL_TASK_STATUSES
    ]
    raw_task_id = event.payload.get("task_id")
    task = next((t for t in active_tasks if str(t.id) == raw_task_id), None)
    if task is None and active_tasks:
        task = active_tasks[0]
    if _already_escalated(uow, run, event):
        return

    _hook_request(uow, cctx, run, task, event, "HOOK_DELIVERY_FAILED")
    if task is not None and task.current_attempt_id is not None:
        attempt = uow.repo(AttemptRepository).get(task.current_attempt_id, for_update=True)
        try:
            pending = prepare_trigger(uow, cctx, attempt, event.id, cause("subscription", event_id=event.id))
        except SkmError as exc:
            if exc.code is not ErrorCode.INVALID_TRANSITION:
                raise
            ctx.log.info(
                "execution.hook_delivery_failure.advance_deferred",
                source_event_id=str(event.id),
                run_id=str(run.id),
                attempt_id=str(attempt.id),
                reason_code=exc.code.value,
            )
            return
        if pending is not attempt:
            commit_trigger(uow, cctx, run, pending)


SUBSCRIBERS = (
    SubscriberSpec(
        "execution.intent_resolved_resume",
        frozenset({"urn:skm:policy:event:intent-approved:v1", "urn:skm:policy:event:intent-denied:v1"}),
        intent_resolved_resume,
    ),
    SubscriberSpec(
        "execution.plan_archived_guard",
        frozenset({"urn:skm:planning:event:plan-archived:v1"}),
        plan_archived_guard,
    ),
    SubscriberSpec(
        "execution.material_available",
        frozenset({"urn:skm:artifacts:event:file-version-added:v1"}),
        material_available,
    ),
    SubscriberSpec(
        "execution.escalate_blocking_hook_failure",
        frozenset({"urn:skm:integrations:event:hook-delivery-failed:v1"}),
        escalate_blocking_hook_failure,
    ),
)
