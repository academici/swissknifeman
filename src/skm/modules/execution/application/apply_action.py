"""Atomic trusted-trigger -> advance -> action -> durable continuation (execution §7.3)."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError, error_for
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.execution.application._admission import require_future_admission
from skm.modules.execution.application._incident_gate import gate_action
from skm.modules.execution.application._primitives import attempts_for_run, clear_advance, move, save_attempt
from skm.modules.execution.application._resolutions import resolved_action
from skm.modules.execution.application._scheduler_materials import refresh_material_waits
from skm.modules.execution.application.stages import human_gate, phase_gate, plan_acceptance
from skm.modules.execution.application.stages.gate_dispatch import require_done, select
from skm.modules.execution.application.stages.gate_lifecycle import followups, open_empty_gate, rereview
from skm.modules.execution.domain import run as run_rules
from skm.modules.execution.domain import task as task_rules
from skm.modules.execution.domain.assignment import Assignment, AssignmentState, WorkerRequirements
from skm.modules.execution.domain.attempt import (
    TERMINAL_ATTEMPT_STATES,
    AttemptEndReason,
    AttemptState,
    ContinuationCause,
    DeferredTrigger,
    EntityRef,
    SelectedStage,
    defer_trigger,
    select_stage,
    transition_attempt,
)
from skm.modules.execution.domain.blocking_reason import BlockingCode, blocking_reason
from skm.modules.execution.domain.decision_record import QuestionCategory
from skm.modules.execution.domain.decision_request import (
    Audience,
    DecisionKind,
    DecisionRequest,
    DecisionState,
)
from skm.modules.execution.domain.environment import EnvironmentKind
from skm.modules.execution.domain.ids import StageRecordId
from skm.modules.execution.domain.readiness import canonical_digest
from skm.modules.execution.domain.role_contracts import ROLE_CONTRACTS, WriteAuthority
from skm.modules.execution.domain.run import RunStatus
from skm.modules.execution.domain.stage_record import (
    ACTIVE_STAGE_STATES,
    control_plane_record,
)
from skm.modules.execution.domain.task import TERMINAL_TASK_STATUSES, TaskStatus
from skm.modules.execution.domain.task_graph import ready_task_ids
from skm.modules.execution.domain.workflow import actions as act
from skm.modules.execution.domain.workflow.engine import decide_advance
from skm.modules.execution.domain.workflow.stage_inputs import FeedbackRefs, StageMode
from skm.modules.execution.ports import (
    AssignmentRepository,
    AttemptRepository,
    DecisionRepository,
    IntegrationSlotRepository,
    RecoveryRepository,
    RunRepository,
    StageRepository,
    TaskRepository,
)

from ._action_effects import (
    accept_action,
    control_stage,
    create_followups,
    done_clearance,
    finish_run,
    question_request,
    reuse_scout,
    rework_action,
)
from ._control import close_attempt, current_binding_digest, live_guard, stage_completed
from ._events import cause, emit, save_task
from ._state import effective_values, load_state


def prepare_trigger(uow: UnitOfWork, ctx: Any, attempt: Any, source_event_id: UUID, why: Any) -> Any:
    """Validate eligibility and the 128-trigger cap before the source mutation."""
    if attempt.state in TERMINAL_ATTEMPT_STATES:
        raise error_for(ErrorCode.INVALID_TRANSITION, "terminal attempts accept no semantic trigger")
    for entry in uow.repo(StageRepository).history(attempt.id).entries:
        if entry.record.state in ACTIVE_STAGE_STATES:
            raise error_for(ErrorCode.INVALID_TRANSITION, "active stage prevents a semantic amendment")
    trusted = ContinuationCause(
        why["trigger_kind"],
        None,
        tuple(why.get("reason_codes", [])),
        tuple(EntityRef(ref["kind"], UUID(ref["id"])) for ref in why.get("refs", [])),
        why.get("command_id"),
        source_event_id,
    )
    return defer_trigger(attempt, DeferredTrigger(source_event_id, trusted), continuation_id=ctx.ids.new_id())


def commit_trigger(uow: UnitOfWork, ctx: Any, run: Any, pending: Any) -> str:
    save_attempt(uow, pending)
    if run.status is RunStatus.WAITING:
        resumed = run_rules.wake(run)
        uow.repo(RunRepository).save(resumed, expected_version=run.row_version)
        emit(
            uow,
            resumed,
            "run-resumed",
            {
                "by": str(ctx.actor.principal_id),
                "previous_stop_code": run.stop_code,
                "previous_pause_source": run.pause_source,
            },
            cause("wait_changed"),
        )
        run = resumed
    if run.status is RunStatus.RUNNING:
        return process_pending(uow, ctx, pending.id)
    return "deferred"


def _why(cursor: Any, decision: Any) -> Any:
    result = dict(decision.cause)
    if cursor is not None and cursor.kind == "advance":
        source = cursor.triggers[-1]
        result.update(
            source_event_id=str(source.source_event_id),
            command_id=source.cause.command_id,
            trigger_kind=source.cause.trigger_kind,
        )
        result["refs"] = [
            {"kind": r.kind, "id": str(r.id)} for trigger in cursor.triggers for r in trigger.cause.refs
        ]
    if result.get("command_id") is None:
        result.pop("command_id", None)
    return result


def empty_gate(uow: UnitOfWork, ctx: Any, run: Any, task: Any, why: Any) -> bool:
    """Accept a gate with no applicable stages; False when the gate still has work to schedule."""
    if not open_empty_gate(uow, ctx, run, task, why):
        return False
    apply_action(
        act.ActionDecision(act.Done(), {**why, "reason_codes": ["GATE_EMPTY"]}), ctx, uow, task_id=task.id
    )
    return True


def release_dependents(uow: UnitOfWork, ctx: Any, run: Any, why: Any) -> None:
    repo = uow.repo(TaskRepository)
    tasks, edges = repo.list_for_run(run.id), repo.edges_for_run(run.id)
    ready = ready_task_ids(tasks, edges)
    if ready:
        _, values = effective_values(uow, run.id)
        refresh_material_waits(uow, ctx, run, values, ctx.clock.now(), initial_ready=ready)
    for tid in ready:
        task = repo.get(tid, for_update=True)
        if task.blocking_reason and task.blocking_reason.code is BlockingCode.BLOCKED_BY_MATERIAL:
            continue

        if task.kind in task_rules.GATE_KINDS and task.current_attempt_id is not None:
            rereview(uow, ctx, run, task, why)
            continue
        updated = task_rules.transition(task, TaskStatus.READY, rule="T1")
        save_task(uow, run, task, updated, why, ctx.clock.now())
        emit(uow, run, "task-ready", {"task_id": str(tid), "reason": "dependency_satisfied"}, why)
        empty_gate(uow, ctx, run, updated, why)


def requirements(values: Any, host: Any) -> WorkerRequirements:
    selector = frozenset(values.get("execution.workers.selector", ()))
    capabilities = frozenset(
        entry for entry in selector if re.fullmatch(r"runtime:[a-z][a-z0-9_]{1,31}", entry)
    )
    return WorkerRequirements(
        capabilities,
        host,
        selector - capabilities,
        EnvironmentKind(values.get("execution.environment.kind", "git_worktree")),
        frozenset({values.get("execution.isolation.profile", "landlock")}),
    )


def enqueue(uow: UnitOfWork, ctx: Any, state: Any) -> None:
    attempt = state.attempt
    cursor = None if attempt is None else attempt.continuation
    if (
        attempt is None
        or cursor is None
        or cursor.kind != "stage"
        or state.run.status is not RunStatus.RUNNING
    ):
        return
    if uow.repo(DecisionRepository).open_for_task(state.task.id):
        return
    assignments = uow.repo(AssignmentRepository).for_attempt(attempt.id)
    if any(a.state in {AssignmentState.AVAILABLE, AssignmentState.LEASED} for a in assignments):
        return
    if any(e.record.state in ACTIVE_STAGE_STATES for e in state.history.entries):
        return
    if any(
        uow.repo(RecoveryRepository).open_for_stage(e.record.id) is not None for e in state.history.entries
    ):
        return
    live_guard(uow, ctx, state.run)
    _loaded, values = effective_values(uow, state.run.id)

    try:
        if not require_future_admission(uow, ctx, state.run, state.task, values):
            return
    except SkmError as exc:
        if exc.code is not ErrorCode.BUDGET_EXHAUSTED:
            raise
        return
    req = requirements(values, state.task.required_host_id or attempt.host_id)
    uow.repo(AssignmentRepository).add(
        Assignment(
            ctx.ids.new_id(),
            state.run.id,
            state.task.id,
            attempt.id,
            state.run.workspace_id,
            AssignmentState.AVAILABLE,
            cursor.stage.not_before or ctx.clock.now(),
            req,
            state.task.position,
            0,
            None,
            None,
            None,
            ctx.clock.now(),
            1,
        )
    )


def process_pending(uow: UnitOfWork, ctx: Any, attempt_id: Any) -> str:
    attempt = uow.repo(AttemptRepository).get(attempt_id, for_update=True)
    state, workflow = load_state(uow, attempt.task_id)
    if state.run.status is not RunStatus.RUNNING or attempt.state in TERMINAL_ATTEMPT_STATES:
        return "deferred"
    if any(a.state is AssignmentState.LEASED for a in uow.repo(AssignmentRepository).for_attempt(attempt.id)):
        return "deferred"
    if any(e.record.state in ACTIVE_STAGE_STATES for e in state.history.entries):
        return "deferred"
    cursor = attempt.continuation
    if cursor is None:
        return "none"
    reason = state.task.blocking_reason
    if reason and reason.code is BlockingCode.RECOVERING and reason.refs.get("reap_stage_record_id"):
        if not uow.repo(StageRepository).reap_confirmed(
            StageRecordId(UUID(str(reason.refs["reap_stage_record_id"])))
        ):
            return "deferred"
        state = replace(state, reap_confirmed=True)
    if cursor.kind == "stage":
        enqueue(uow, ctx, state)
        return "run_stage"
    # One evaluation consumes this committed set of source transitions. A selected stage
    # is never evaluated again on resume/claim; effects and cursor commit together.

    decision = resolved_action(uow, state, workflow, cursor, ctx.clock.now())
    if decision is None:
        decision = decide_advance(state, workflow, state.effective_policy, ctx.clock.now())
    return apply_action(decision, ctx, uow, task_id=state.task.id, why=_why(cursor, decision))


def resume_advance_attempts(uow: UnitOfWork, ctx: Any, run: Any, *, limit: int = 128) -> int:
    pending = [
        a
        for a in attempts_for_run(uow, run.id)
        if a.state not in TERMINAL_ATTEMPT_STATES and a.continuation is not None
    ]
    for attempt in pending[:limit]:
        process_pending(uow, ctx, attempt.id)
    return min(limit, len(pending))


def apply_action(  # noqa: PLR0911, PLR0912, PLR0915 -- closed action table §7.3
    decision: Any, ctx: Any, uow: UnitOfWork, *, task_id: Any, why: Any = None, depth: int = 0
) -> str:
    if depth >= 128:
        raise error_for(ErrorCode.INVALID_TRANSITION, "control-plane action chain is bounded")
    state, workflow = load_state(uow, task_id)
    run, task, attempt, action = state.run, state.task, state.attempt, decision.action
    why = dict(decision.cause) if why is None else why
    if attempt is None:
        raise error_for(ErrorCode.INVALID_TRANSITION, "advance requires a current attempt")
    if (attempt.continuation is not None and attempt.continuation.kind == "stage") or any(
        e.record.state in ACTIVE_STAGE_STATES for e in state.history.entries
    ):
        raise error_for(ErrorCode.INVALID_TRANSITION, "semantic action requires no active or selected stage")
    action = gate_action(uow, ctx, state, action)
    if isinstance(action, act.Noop):
        clear_advance(uow, attempt)
        return "noop"
    if isinstance(action, act.RunStage):
        if action.stage_type.value in {"human_gate", "acceptance_gate", "phase_gate", "plan_acceptance"}:
            if action.stage_type.value in {"phase_gate", "plan_acceptance"}:
                outcome = (
                    plan_acceptance.decide(
                        state, ctx, uow, why, coverage_mode=action.params.get("coverage", "required")
                    )
                    if action.stage_type.value == "plan_acceptance"
                    else phase_gate.decide(state, ctx, uow, why)
                )
            else:
                outcome = control_stage(uow, ctx, state, action, why)
            records = tuple(e.record for e in state.history.entries)

            record = control_plane_record(
                records,
                record_id=ctx.ids.new_id(),
                attempt_id=attempt.id,
                run_id=run.id,
                task_id=task.id,
                stage_id=action.stage_id,
                stage_type=action.stage_type.value,
                round_no=action.round_no,
                input_digest=canonical_digest({"cause": why, "params": dict(action.params)}),
                outcome_kind=outcome.kind,
                outcome=outcome.payload,
                now=ctx.clock.now(),
            )
            uow.repo(StageRepository).add(record)
            stage_completed(uow, run, record, [], why)
            fresh, workflow = load_state(uow, task.id)
            return apply_action(
                decide_advance(fresh, workflow, fresh.effective_policy, ctx.clock.now()),
                ctx,
                uow,
                task_id=task.id,
                why=why,
                depth=depth + 1,
            )
        if task.kind in task_rules.GATE_KINDS and action.stage_type.value == "agent_step":
            definition = next(s for s in workflow.stages if s.id == action.stage_id)
            if (
                definition.role
                and ROLE_CONTRACTS[definition.role].write_authority is WriteAuthority.CODE_SCOPE
            ):
                raise error_for(ErrorCode.INVALID_TRANSITION, "gate cannot launch a writable role")

        action = select(uow, state, workflow, action)
        if action.mode is StageMode.NORMAL and reuse_scout(uow, ctx, state, workflow, action, why):
            fresh, workflow = load_state(uow, task.id)
            return apply_action(
                decide_advance(fresh, workflow, fresh.effective_policy, ctx.clock.now()),
                ctx,
                uow,
                task_id=task.id,
                depth=depth + 1,
            )
        target = {
            "run_checks": TaskStatus.CHECKING,
            "agent_review": TaskStatus.REVIEWING,
            "integrate": TaskStatus.INTEGRATING,
        }.get(action.stage_type.value)
        if action.stage_type.value == "run_checks" and task.status is TaskStatus.INTEGRATING:
            target = None
        if target is None and task.status is TaskStatus.AWAITING_DECISION:
            target = TaskStatus.EXECUTING
        if action.mode is StageMode.REWORK:
            # T15 belongs to begin_stage; selection alone starts no execution.
            target = None if task.status is TaskStatus.REWORK_REQUIRED else TaskStatus.EXECUTING
        if target is not None and target is not task.status:
            task = move(uow, ctx, run, task, target, why)
        if (
            action.stage_type.value == "agent_review"
            and action.round_no > task.review_rounds
            and task.kind not in task_rules.GATE_KINDS
        ):
            updated = replace(task, review_rounds=action.round_no, row_version=task.row_version + 1)
            save_task(uow, run, task, updated, why, ctx.clock.now())
        selected = SelectedStage(
            action.stage_id,
            action.stage_type.value,
            action.mode,
            action.round_no,
            action.params,
            action.not_before,
            action.route_override,
            action.feedback or FeedbackRefs(),
            attempt.current_output_id,
            None,
        )
        selected_cause = ContinuationCause(
            why["trigger_kind"],
            why.get("advance_rule"),
            tuple(why.get("reason_codes", [])),
            tuple(EntityRef(r["kind"], UUID(r["id"])) for r in why.get("refs", [])),
            why.get("command_id"),
            None if why.get("source_event_id") is None else UUID(why["source_event_id"]),
        )
        save_attempt(
            uow, select_stage(attempt, cause=selected_cause, stage=selected, continuation_id=ctx.ids.new_id())
        )
        fresh, _ = load_state(uow, task.id)
        enqueue(uow, ctx, fresh)
        return "run_stage"
    if isinstance(action, act.WaitFor):
        status = task.status
        if action.blocking.code is BlockingCode.WAITING_MANUAL_CHECK:
            human_gate.open_manual_requests(state, ctx, uow, why)
            status = TaskStatus.MANUAL_PENDING
        move(uow, ctx, run, task, status, why, blocking=action.blocking)
        clear_advance(uow, attempt)
        return "wait"
    if isinstance(action, act.Accept):
        follow = accept_action(uow, ctx, state, workflow, action, why)
        return apply_action(follow, ctx, uow, task_id=task.id, depth=depth + 1)
    if isinstance(action, act.Integrate):
        stage = next(s for s in workflow.stages if s.type.value == "integrate")
        return apply_action(
            act.ActionDecision(
                act.RunStage(stage.id, stage.type, StageMode.NORMAL, 1, stage.params.as_json()), why
            ),
            ctx,
            uow,
            task_id=task.id,
            depth=depth + 1,
        )
    if isinstance(action, act.Escalate):
        request = DecisionRequest(
            ctx.ids.new_id(),
            run.workspace_id,
            run.id,
            task.id,
            action.kind,
            Audience.OWNER,
            QuestionCategory(action.payload.get("category", "architectural"))
            if action.kind is DecisionKind.QUESTION
            else None,
            frozenset(),
            None,
            None,
            1,
            dict(action.payload),
            None,
            {
                "attempt_id": str(attempt.id),
                "output_id": None if state.output is None else str(state.output.id),
                "input_part_digest": current_binding_digest(uow, attempt),
            },
            DecisionState.OPEN,
            None,
            None,
            ctx.clock.now(),
        )
        if action.kind is DecisionKind.QUESTION:
            request = question_request(request, state)
        uow.repo(DecisionRepository).add(request)
        refs = {"decision_request_id": str(request.id), "stop_code": action.code}
        if action.blocking_code is BlockingCode.WAITING_APPROVAL:
            refs = {
                "decision_request_id": str(request.id),
                "intent_id": str(action.payload.get("intent_id", request.id)),
            }
        if action.blocking_code is BlockingCode.WAITING_ANSWER:
            refs = {
                "decision_request_id": str(request.id),
                "question_id": str(action.payload.get("question_id", request.id)),
            }
        if action.blocking_code is BlockingCode.BLOCKED_BY_BUDGET:
            refs = {
                "decision_request_id": str(request.id),
                "scope": action.payload.get("scope", "run"),
                "dimension": action.payload.get("dimension", "usd"),
                "limit": action.payload.get("limit", 0),
                "spent": action.payload.get("spent", 0),
            }
        blocked = blocking_reason(
            action.blocking_code, task_id=task.id, refs=refs, now=ctx.clock.now(), message=action.code
        )
        move(uow, ctx, run, task, TaskStatus.AWAITING_DECISION, why, blocking=blocked)
        clear_advance(uow, attempt)
        emit(
            uow,
            run,
            "decision-requested",
            {
                "request_id": str(request.id),
                "task_id": str(task.id),
                "kind": request.kind.value,
                "audience": "owner",
                "blocking_code": action.blocking_code.value,
            },
            why,
        )
        return "escalate"
    if isinstance(action, act.NewAttempt):
        close_attempt(
            uow, ctx, run, attempt, code=action.reason_code, reason=AttemptEndReason.RETRY_NEW_ATTEMPT
        )
        hosts = uow.repo(IntegrationSlotRepository).hosts_for_run(run.id)
        host = next(iter(hosts.values()), None)
        updated = replace(
            task,
            status=TaskStatus.READY,
            blocking_reason=None,
            current_attempt_id=None,
            required_host_id=host,
            row_version=task.row_version + 1,
        )
        save_task(uow, run, task, updated, why, ctx.clock.now())
        emit(uow, run, "task-ready", {"task_id": str(task.id), "reason": action.reason_code}, why)
        return "new_attempt"
    if isinstance(action, act.CreateFollowups) and task.kind in task_rules.GATE_KINDS:
        return followups(uow, ctx, state, action, why)
    if isinstance(action, act.CreateFollowups):
        return create_followups(uow, ctx, state, action, why)
    if isinstance(action, act.Rework):
        follow = rework_action(uow, ctx, state, workflow, action, why)
        return apply_action(follow, ctx, uow, task_id=task.id, depth=depth + 1)
    if isinstance(action, act.Fail):
        close_attempt(uow, ctx, run, attempt, code=action.code, reason=AttemptEndReason.FAILED)
        move(uow, ctx, run, task, TaskStatus.FAILED, why)
        emit(uow, run, "task-failed", {"task_id": str(task.id), "code": action.code}, why)
        finish_run(uow, ctx, uow.repo(RunRepository).get(run.id), why)
        return "failed"
    if isinstance(action, act.Done):
        require_done(uow, ctx, state, workflow, why)
        clearance = done_clearance(uow, state)
        if task.status in TERMINAL_TASK_STATUSES:
            return "done"
        if task.status is not TaskStatus.INTEGRATING:
            task = move(uow, ctx, run, task, TaskStatus.INTEGRATING, why)
        accepted = task_rules.accept(
            task,
            rule="T19" if task.kind in task_rules.GATE_KINDS else "T21",
            attempt=attempt,
            output=state.output,
        )
        save_task(uow, run, task, accepted, why, ctx.clock.now())
        completed = transition_attempt(
            attempt, AttemptState.COMPLETED, now=ctx.clock.now(), end_reason=AttemptEndReason.ACCEPTED
        )
        save_attempt(uow, completed)
        emit(
            uow,
            run,
            "task-accepted",
            {
                "task_id": str(task.id),
                "attempt_id": str(attempt.id),
                "output_id": None if state.output is None else str(state.output.id),
                "carried_forward": False,
                "clearance": clearance,
            },
            why,
        )
        release_dependents(uow, ctx, run, why)
        latest = uow.repo(RunRepository).get(run.id)
        if latest.status in {RunStatus.RUNNING, RunStatus.WAITING}:
            finish_run(uow, ctx, latest, why)
        return "done"
    raise error_for(ErrorCode.INVALID_TRANSITION, "unsupported action")
