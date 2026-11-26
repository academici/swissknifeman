"""One serialized campaign tick; child commands share its locks and transaction."""

from dataclasses import replace
from typing import Any
from uuid import UUID

from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeId, ScopeKind, ScopeRef
from skm.modules.execution.application._events import cause, emit
from skm.modules.execution.application._incident_gate import journal
from skm.modules.execution.application._primitives import server_context
from skm.modules.execution.application._worker_dtos import WireRecord, parse_datetime
from skm.modules.execution.application.commands import resume_run, start_run
from skm.modules.execution.application.commands.expire_leases import system_guard
from skm.modules.execution.application.commands.start_autopilot import (
    load_state,
    policy_for,
    project_scope,
    save_state,
    status_result,
)
from skm.modules.execution.application.commands.stop_autopilot import project_runs
from skm.modules.execution.application.queries.explain_autopilot import observe, requests_for
from skm.modules.execution.application.queries.get_autopilot_status import approved_queue, scoped_context
from skm.modules.execution.domain.autopilot import (
    OWNER_CODES,
    TRANSIENT_CODES,
    AutopilotStateKind,
    classify_outcome,
    effective_policy,
    evaluate_conditions,
)
from skm.modules.execution.domain.decision_request import (
    Audience,
    DecisionKind,
    DecisionRequest,
    DecisionState,
)
from skm.modules.execution.generated.commands import ResumeRun, StartRun
from skm.modules.execution.ports import DecisionRepository, RunRepository, TaskRepository


class AutopilotTick(WireRecord):
    SCHEMA_URN = "urn:skm:execution:command:autopilot-tick:v1"


class AutopilotTickResult(WireRecord):
    SCHEMA_URN = "urn:skm:execution:result:autopilot-tick:v1"


def fold_counters(state: Any, run: Any, events: Any, blocker: Any, facts: Any, uow: UnitOfWork) -> Any:
    counters = dict(state.counters)
    if run is None:
        return state
    same_run = counters.get("event_run_id") == str(run.id)
    after = int(counters.get("event_seq", 0)) if same_run else 0
    for event in events:
        if int(event["stream_seq"]) <= after:
            continue
        if (
            state.session_started_at is not None
            and parse_datetime(event["occurred_at"]) < state.session_started_at
        ):
            continue
        name, payload = event["event_type"], event["payload"]
        if ":task-accepted:" in name:
            counters.update(auto_decisions=0, no_progress_runs=0, infra_failures=0)
        elif ":decision-answered:" in name and payload.get("answered_by_kind") in {
            "advisor",
            "consilium",
            "policy",
        }:
            counters["auto_decisions"] = int(counters.get("auto_decisions", 0)) + 1
        elif ":stage-recovered:" in name:
            counters["recoveries"] = int(counters.get("recoveries", 0)) + 1
    counters.update(event_run_id=str(run.id), event_seq=int(events[-1]["stream_seq"]) if events else 0)
    if blocker:
        counters.update(last_blocker=blocker, last_blocker_run_id=str(run.id))
    if facts.repeated_blocker:
        counters["repeated_blocker"] = True
    if run.status.value in {"succeeded", "failed", "cancelled"} and counters.get("completed_run_id") != str(
        run.id
    ):
        accepted = any(t.status.value == "accepted" for t in uow.repo(TaskRepository).list_for_run(run.id))
        counters["no_progress_runs"] = 0 if accepted else int(counters.get("no_progress_runs", 0)) + 1
        counters["infra_failures"] = (
            int(counters.get("infra_failures", 0)) + 1
            if run.stop_code in TRANSIENT_CODES | {"LEASE_LOST", "WORKER_LOST", "ENVIRONMENT_ERROR"}
            else 0
        )
        if blocker is None:
            # A completed clean run breaks adjacency; pause/stop-start alone never does.
            counters.update(last_blocker=None, last_blocker_run_id=None, repeated_blocker=False)
        counters["completed_run_id"] = str(run.id)
    return replace(state, counters=counters)


def record_blocker_action(uow: UnitOfWork, ctx: Any, run: Any, blocker: Any, code: str, branch: str) -> None:
    if run is None or not run.autopilot or not blocker:
        return
    task = next(
        (
            task
            for task in uow.repo(TaskRepository).list_for_run(run.id)
            if task.display_key == blocker["task_key"] and task.blocking_reason is not None
        ),
        None,
    )
    if task is not None:
        journal(
            uow,
            ctx,
            task.id,
            code,
            {
                "branch": branch,
                "authority": "owner" if branch == "C" else "coordinator",
                "code": code,
                "run_version": run.row_version,
                "blocker": blocker["code"],
            },
        )


def escalate(uow: UnitOfWork, ctx: Any, state: Any, code: str, runs: Any) -> None:
    if code not in OWNER_CODES:
        return
    run = next((r for r in runs if r.id == state.current_run_id), None)
    if run is None:
        run = max(runs, key=lambda r: (r.created_at, str(r.id)), default=None)
    # DecisionRequest requires a real run FK. Before the first run the project stop event and
    # stop_detail retain the owner requirement; never manufacture an execution to host a decision.
    if run is None:
        return
    if any(
        r["state"] == "open" and r["kind"] == "escalation" and r["payload"].get("code") == code
        for r in requests_for(uow, state.project_id)
    ):
        return
    if state.counters.get("last_blocker_run_id") == str(run.id):
        record_blocker_action(uow, ctx, run, state.counters.get("last_blocker"), code, "C")
    request = DecisionRequest(
        id=ctx.ids.new_id(),
        workspace_id=state.workspace_id,
        run_id=run.id,
        task_id=None,
        kind=DecisionKind.ESCALATION,
        audience=Audience.OWNER,
        category=None,
        gate_categories=frozenset(),
        question_key=None,
        question_digest=None,
        revision=1,
        payload={
            "code": code,
            "message": "Autopilot requires an owner decision",
            "options": [
                {"id": "resume_run", "label": "Resume after resolving the campaign blocker"},
                {"id": "cancel_run", "label": "Cancel this run"},
            ],
        },
        asked_by_step_id=None,
        binding={},
        state=DecisionState.OPEN,
        stale_answer=None,
        deadline_at=None,
        created_at=ctx.clock.now(),
    )
    uow.repo(DecisionRepository).add(request)
    emit(
        uow,
        run,
        "decision-requested",
        {
            "request_id": str(request.id),
            "task_id": None,
            "kind": "escalation",
            "audience": "owner",
            "category": None,
            "blocking_code": "WAITING_OWNER",
        },
        cause("wait_changed", codes=[code]),
    )


def stopped(uow: UnitOfWork, ctx: Any, old: Any, state: Any, code: str, runs: Any) -> Any:
    escalate(uow, ctx, state, code, runs)
    updated = save_state(
        uow,
        ctx,
        old,
        replace(
            state,
            state=AutopilotStateKind.STOPPED,
            stop_code=code,
            stop_detail=("Owner decision required: " if code in OWNER_CODES else "") + code,
        ),
        code=code,
    )
    return AutopilotTickResult(status_result(updated, policy_for(ctx)), action="stop")


def handle(cmd: AutopilotTick, ctx: Any, uow: UnitOfWork) -> AutopilotTickResult:
    system_guard(ctx)
    state = load_state(cmd, ctx, uow, lock=True)
    ctx = server_context(ctx, uow)
    policy = policy_for(ctx)
    if state.state not in {
        AutopilotStateKind.RUNNING,
        AutopilotStateKind.PAUSED,
        AutopilotStateKind.DRAINING,
    } or not (policy.allowed and policy.enabled):
        return AutopilotTickResult(status_result(state, policy), action="noop")
    # All run locks follow the campaign lock, in deterministic order, before any task mutation.
    runs = [
        uow.repo(RunRepository).get(r.id, for_update=True)
        for r in sorted(
            project_runs(uow, state.project_id),
            key=lambda r: str(r.id),
        )
    ]
    current = next((r for r in runs if r.id == state.current_run_id), None)
    active = [r for r in runs if r.autopilot and r.status.value not in {"succeeded", "failed", "cancelled"}]
    working = state
    if active and (current is None or current.status.value in {"succeeded", "failed", "cancelled"}):
        current = active[0]
        working = replace(state, current_run_id=current.id)
    queue = approved_queue(uow, ctx, state.project_id, lock=True)
    facts, blocker, events = observe(uow, ctx, working, queue, runs)
    working = fold_counters(working, current, events, blocker, facts, uow)
    facts = replace(facts, repeated_blocker=working.counters.get("repeated_blocker") is True)
    conditions = evaluate_conditions(working, policy, ctx.clock.now(), facts)
    condition = next((c for c in conditions if c.met), None)
    if condition is not None:
        if condition.id == "AP2":
            updated = save_state(
                uow,
                ctx,
                state,
                replace(
                    working,
                    state=AutopilotStateKind.IDLE,
                    current_run_id=None,
                    stop_code=None,
                    stop_detail=None,
                ),
                code=condition.code,
            )
            return AutopilotTickResult(status_result(updated, policy), action="drained")
        return stopped(uow, ctx, state, working, condition.code, runs)
    if state.state is AutopilotStateKind.PAUSED:
        updated = save_state(uow, ctx, state, working)
        return AutopilotTickResult(status_result(updated, policy), action="waiting")
    action = classify_outcome(
        current,
        effective_policy(policy, working.session_limits),
        now=ctx.clock.now(),
        quota_reset_at=facts.quota_reset_at,
    )
    if action == "resume" and current is not None:
        try:
            resume_run.handle(ResumeRun(current.id, expected_row_version=current.row_version), ctx, uow)
        except SkmError as error:
            if error.code is ErrorCode.VERSION_CONFLICT:
                return AutopilotTickResult(
                    status_result(state, policy), action="noop", code="VERSION_CONFLICT"
                )
            raise
        record_blocker_action(uow, ctx, current, blocker, current.stop_code or "resume", "A")
    elif action == "wait_quota" and current is not None:
        record_blocker_action(uow, ctx, current, blocker, "wait_quota", "A")
    elif action.startswith("stop("):
        return stopped(uow, ctx, state, working, action[5:-1], runs)
    elif action == "continue" and state.state is AutopilotStateKind.RUNNING and not active:
        row = next(row for row in queue if row["status"] != "complete")
        plan_ctx = scoped_context(uow, ctx, ScopeRef(ScopeKind.PLAN, ScopeId(UUID(row["plan_id"]))))
        started = start_run.handle(
            StartRun(
                UUID(row["plan_id"]),
                UUID(row["revision_id"]),
                UUID(row["report_id"]),
                {},
                "Approved autopilot queue",
                autopilot=True,
            ),
            plan_ctx,
            uow,
        )
        counters = dict(working.counters)
        counters["runs_started"] = int(counters.get("runs_started", 0)) + 1
        working = replace(working, current_run_id=started.run_id, counters=counters)
        action = "started"
    updated = save_state(uow, ctx, state, working)
    result = AutopilotTickResult(status_result(updated, policy), action=action)
    if action == "wait_quota" and facts.quota_reset_at is not None:
        result["next_check_at"] = facts.quota_reset_at.isoformat()
    return result


SPEC = CommandSpec(
    name="execution.autopilot_tick",
    dto=AutopilotTick,
    result=AutopilotTickResult,
    permission="system.internal",
    scope_of=project_scope,
    handler=handle,
    internal=True,
    idempotency=IdempotencyMode.FORBIDDEN,
)
