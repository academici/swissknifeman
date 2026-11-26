"""Bounded scheduler: initial selection, durable continuation, and Rule L3 handoff."""

from dataclasses import replace
from decimal import Decimal
from typing import Any
from uuid import UUID

from skm.application_bus.registry import CommandSpec
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.ids import RepositoryId, RunId
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.execution.application._action_effects import finish_run
from skm.modules.execution.application._admission import require_future_admission
from skm.modules.execution.application._control import live_guard, revoke_assignment
from skm.modules.execution.application._events import cause, emit, save_task
from skm.modules.execution.application._primitives import attempts_for_run, move, save_attempt, server_context
from skm.modules.execution.application._scheduler_materials import refresh_material_waits
from skm.modules.execution.application._start_inputs import policy_from_values, value
from skm.modules.execution.application._state import effective_values, load_state
from skm.modules.execution.application._worker_dtos import WireRecord
from skm.modules.execution.application.apply_action import (
    apply_action,
    empty_gate,
    process_pending,
    requirements,
)
from skm.modules.execution.application.stages.gate_dispatch import select
from skm.modules.execution.domain.assignment import Assignment, AssignmentState
from skm.modules.execution.domain.attempt import (
    TERMINAL_ATTEMPT_STATES,
    Attempt,
    AttemptState,
    ContinuationCause,
    SelectedStage,
    select_stage,
)
from skm.modules.execution.domain.blocking_reason import BlockingCode, blocking_reason
from skm.modules.execution.domain.budget import BudgetDimension, BudgetExhausted, reserve
from skm.modules.execution.domain.decision_request import (
    Audience,
    DecisionKind,
    DecisionRequest,
    DecisionState,
)
from skm.modules.execution.domain.run import RunStatus, start, wait, wake
from skm.modules.execution.domain.scheduling import (
    UNSCHEDULABLE_STATUSES,
    SchedulingInput,
    required_host,
    select_assignable,
)
from skm.modules.execution.domain.stage_record import ACTIVE_STAGE_STATES
from skm.modules.execution.domain.task import TERMINAL_TASK_STATUSES, Task, TaskStatus
from skm.modules.execution.domain.task_graph import EdgeKind
from skm.modules.execution.domain.workflow.actions import Ctx, Fail, NewAttempt, RunStage
from skm.modules.execution.domain.workflow.engine import decide_advance, initial_selection
from skm.modules.execution.domain.workflow.stage_inputs import FeedbackRefs
from skm.modules.execution.generated.commands import schedule_ready_tasks_from_json
from skm.modules.execution.generated.results import schedule_ready_tasks_result_from_json
from skm.modules.execution.ports import (
    AssignmentRepository,
    AttemptRepository,
    BudgetRepository,
    DecisionRepository,
    EnvironmentRepository,
    IntegrationSlotRepository,
    RecoveryRepository,
    RunRepository,
    StageRepository,
    TaskRepository,
)
from skm.modules.workspace import public as workspace

from .expire_leases import capability_wait, control_now, monitor, reap_expired, system_guard


class ScheduleReadyTasks(WireRecord):
    SCHEMA_URN = "urn:skm:execution:command:schedule-ready-tasks:v1"


class ScheduleReadyTasksResult(WireRecord):
    SCHEMA_URN = "urn:skm:execution:result:schedule-ready-tasks:v1"


def escalate(uow: UnitOfWork, ctx: Any, run: Any, task: Any, code: str) -> None:
    for assignment in (
        uow.repo(AssignmentRepository).for_attempt(task.current_attempt_id) if task.current_attempt_id else ()
    ):
        if assignment.state is AssignmentState.AVAILABLE:
            revoke_assignment(uow, ctx, assignment)
    if uow.repo(DecisionRepository).open_for_task(task.id):
        return
    request = DecisionRequest(
        ctx.ids.new_id(),
        run.workspace_id,
        run.id,
        task.id,
        DecisionKind.ESCALATION,
        Audience.OWNER,
        None,
        frozenset(),
        None,
        None,
        1,
        {"code": code, "options": ["fail"]},
        None,
        {},
        DecisionState.OPEN,
        None,
        None,
        control_now(uow),
    )
    uow.repo(DecisionRepository).add(request)
    reason = blocking_reason(
        BlockingCode.WAITING_OWNER,
        task_id=task.id,
        refs={"decision_request_id": str(request.id), "stop_code": code},
        now=control_now(uow),
        message=code,
    )
    move(
        uow,
        ctx,
        run,
        task,
        TaskStatus.AWAITING_DECISION,
        cause("wait_changed", codes=[code]),
        blocking=reason,
    )
    emit(
        uow,
        run,
        "decision-requested",
        {
            "request_id": str(request.id),
            "task_id": str(task.id),
            "kind": "escalation",
            "audience": "owner",
            "blocking_code": "WAITING_OWNER",
        },
        cause("wait_changed", codes=[code]),
    )


def scheduling_input(
    uow: UnitOfWork, ctx: Any, run: Any, values: Any, *, tasks: tuple[Task, ...] | None = None
) -> SchedulingInput:
    if tasks is None:
        tasks = uow.repo(TaskRepository).list_for_run(run.id)
    attempts = {a.id: a for a in attempts_for_run(uow, run.id)}
    assignment_repo = uow.repo(AssignmentRepository)
    assignments = [a for attempt_id in attempts for a in assignment_repo.for_attempt(attempt_id)]
    active = {a.attempt_id for a in assignments if a.state is AssignmentState.LEASED}
    active.update(
        t.current_attempt_id
        for t in tasks
        if t.current_attempt_id is not None
        and t.blocking_reason
        and t.blocking_reason.code is BlockingCode.RECOVERING
    )
    pending = {a.task_id for a in assignments if a.state is AssignmentState.AVAILABLE}
    for attempt in attempts.values():
        if any(
            e.record.state in ACTIVE_STAGE_STATES or uow.repo(RecoveryRepository).open_for_stage(e.record.id)
            for e in uow.repo(StageRepository).history(attempt.id).entries
        ):
            active.add(attempt.id)
    project = workspace.get_project(uow, run.project_id)
    branch = str(values.get("execution.integration.branch", "skm/integration/{run}")).replace(
        "{run}", str(run.id)
    )
    targets = {RepositoryId(m.repository_id): branch for m in project.mounts}
    edges = uow.repo(TaskRepository).edges_for_run(run.id)
    # Batch edges form connected components, not independent pairwise groups.
    groups: dict[Any, str] = {}
    for edge in edges:
        if edge.kind is not EdgeKind.BATCH:
            continue
        left, right = groups.get(edge.dependent_task_id), groups.get(edge.prerequisite_task_id)
        label = min(str(edge.dependent_task_id), str(edge.prerequisite_task_id), left or "~", right or "~")
        groups = {tid: label if g in {left, right} else g for tid, g in groups.items()}
        groups.update({edge.dependent_task_id: label, edge.prerequisite_task_id: label})
    limit = min(
        int(value(ctx.config, "execution.parallel.max_units", 2)),
        int(values.get("execution.parallel.max_units", 2)),
    )
    return SchedulingInput(
        run,
        tasks,
        edges,
        tuple(t for t in tasks if t.current_attempt_id in active),
        tuple(t for t in tasks if t.id in pending),
        limit,
        groups,
        uow.repo(EnvironmentRepository).busy_existing_checkout_repos(run.project_id)
        if values.get("execution.environment.kind") == "existing_checkout"
        else frozenset(),
        uow.repo(IntegrationSlotRepository).hosts_for_run(run.id),
        targets,
        uow.repo(IntegrationSlotRepository).target_hosts(tuple(targets.items())),
        {m.mount_name: RepositoryId(m.repository_id) for m in project.mounts},
        existing_checkout_repos_busy_by_attempt={
            aid: uow.repo(EnvironmentRepository).busy_existing_checkout_repos(
                run.project_id, exclude_attempt_id=aid
            )
            for aid, attempt in attempts.items()
            if attempt.state not in TERMINAL_ATTEMPT_STATES
            and attempt.continuation is not None
            and any(t.current_attempt_id == aid for t in tasks)
        }
        if values.get("execution.environment.kind") == "existing_checkout"
        else {},
    )


def admitted(uow: UnitOfWork, ctx: Any, run: Any, task: Any, values: Any) -> bool:
    try:
        return require_future_admission(uow, ctx, run, task, values)
    except SkmError as exc:
        if exc.code is not ErrorCode.BUDGET_EXHAUSTED:
            raise
        return False


def enqueue_selected(
    uow: UnitOfWork, ctx: Any, run: Any, task: Any, attempt: Any, inputs: Any, values: Any
) -> Any:
    cursor = attempt.continuation
    if (
        cursor is None
        or cursor.kind != "stage"
        or (cursor.stage.not_before and cursor.stage.not_before > control_now(uow))
    ):
        return None
    if uow.repo(DecisionRepository).open_for_task(task.id):
        return None
    if any(
        a.state in {AssignmentState.AVAILABLE, AssignmentState.LEASED}
        for a in uow.repo(AssignmentRepository).for_attempt(attempt.id)
    ):
        return None
    if any(
        e.record.state in ACTIVE_STAGE_STATES or uow.repo(RecoveryRepository).open_for_stage(e.record.id)
        for e in uow.repo(StageRepository).history(attempt.id).entries
    ):
        return None
    if task.blocking_reason and task.blocking_reason.code not in {
        BlockingCode.WAITING_PROVIDER,
        BlockingCode.BLOCKED_BY_CAPABILITY,
    }:
        return None
    if not admitted(uow, ctx, run, task, values):
        return None
    host, _ = required_host(task, inputs)
    assignment = Assignment(
        ctx.ids.new_id(),
        run.id,
        task.id,
        attempt.id,
        run.workspace_id,
        AssignmentState.AVAILABLE,
        control_now(uow),
        requirements(values, host or attempt.host_id),
        task.position,
        0,
        None,
        None,
        None,
        control_now(uow),
        1,
    )
    uow.repo(AssignmentRepository).add(assignment)
    return assignment


def create_attempt(uow: UnitOfWork, ctx: Any, run: Any, task: Any, values: Any) -> Any:
    if empty_gate(uow, ctx, run, task, cause("run_start")):
        return None
    repo, now = uow.repo(AttemptRepository), control_now(uow)
    limits = [
        int(v)
        for v in (
            value(ctx.config, "budgets.task.max_attempts", 3),
            values.get("budgets.task.max_attempts", 3),
        )
        if int(v) > 0
    ]
    if limits and task.attempt_count >= min(limits):
        if values.get("execution.attempts.on_exhausted", "escalate") == "fail":
            move(uow, ctx, run, task, TaskStatus.FAILED, cause("wait_changed", codes=["ATTEMPTS_EXHAUSTED"]))
            emit(
                uow,
                run,
                "task-failed",
                {"task_id": str(task.id), "code": "ATTEMPTS_EXHAUSTED"},
                cause("wait_changed"),
            )
        else:
            escalate(uow, ctx, run, task, "ATTEMPTS_EXHAUSTED")
        return None
    budget = uow.repo(BudgetRepository)
    accounts = budget.accounts_for(run.id, task.id, BudgetDimension.ATTEMPTS)
    if accounts:
        try:
            _, reservation = reserve(accounts, Decimal(1), reservation_id=ctx.ids.new_id(), now=now)
            if not budget.reserve(reservation.account_ids, reservation.amount):
                raise BudgetExhausted(BudgetDimension.ATTEMPTS, Decimal(0), Decimal(0), Decimal(1))
            budget.add_reservation(reservation)
            budget.settle(reservation, Decimal(1))
        except BudgetExhausted:
            escalate(uow, ctx, run, task, "ATTEMPTS_EXHAUSTED")
            return None
    attempt = Attempt(
        ctx.ids.new_id(),
        run.id,
        task.id,
        run.workspace_id,
        repo.next_attempt_no(task.id),
        AttemptState.PREPARING,
        None,
        None,
        None,
        None,
        None,
        None,
        now,
        None,
        None,
    )
    assigned = replace(
        task,
        status=TaskStatus.ASSIGNED,
        blocking_reason=None,
        current_attempt_id=attempt.id,
        attempt_count=task.attempt_count + 1,
        row_version=task.row_version + 1,
    )
    repo.add(attempt)
    save_task(uow, run, task, assigned, cause("run_start"), now)
    state, workflow = load_state(uow, task.id)
    decision = initial_selection(Ctx(state, workflow, state.effective_policy, now))
    action = decision.action
    if not isinstance(action, RunStage):
        escalate(uow, ctx, run, assigned, "WORKFLOW_INCOMPLETE")
        return None

    action = select(uow, state, workflow, action)
    attempt = select_stage(
        attempt,
        cause=ContinuationCause("run_start", "A1"),
        stage=SelectedStage(
            action.stage_id,
            action.stage_type.value,
            action.mode,
            action.round_no,
            action.params,
            action.not_before,
            action.route_override,
            action.feedback or FeedbackRefs(),
            None,
            None,
        ),
        continuation_id=ctx.ids.new_id(),
    )
    save_attempt(uow, attempt)
    return attempt


def schedule_run(  # noqa: PLR0912 -- closed admission cases
    uow: UnitOfWork, ctx: Any, run: Any, limit: int
) -> list[Any]:
    _, values = effective_values(uow, run.id)
    try:
        live_guard(uow, ctx, run)
    except SkmError as exc:
        if exc.code not in {
            ErrorCode.FORBIDDEN,
            ErrorCode.PLAN_ARCHIVED,
            ErrorCode.PROJECT_ARCHIVED,
        }:
            raise
        return []

    tasks = refresh_material_waits(uow, ctx, run, values, control_now(uow))
    inputs = scheduling_input(uow, ctx, run, values, tasks=tasks)
    # Guards filter candidates, never the scan LIMIT; pending scopes remain protected.
    candidates: list[Any] = []
    for candidate in inputs.tasks:
        task = candidate
        if task.status in TERMINAL_TASK_STATUSES:
            continue
        if required_host(task, inputs)[1] == "INTEGRATION_HOST_MISMATCH":
            escalate(uow, ctx, run, task, "INTEGRATION_HOST_MISMATCH")
            continue
        attempt = (
            None
            if task.current_attempt_id is None
            else uow.repo(AttemptRepository).get(task.current_attempt_id)
        )
        if attempt and attempt.state is AttemptState.OWNERSHIP_LOST and task.status is TaskStatus.READY:
            state, workflow = load_state(uow, task.id)
            current = dict(values)
            for key in ("budgets.task.max_attempts", "budgets.run.max_attempts"):
                live = int(value(ctx.config, key, current.get(key, 0)))
                frozen = int(current.get(key, 0))
                current[key] = min(v for v in (live, frozen) if v > 0) if live > 0 or frozen > 0 else 0
            state = replace(state, effective_policy=policy_from_values(current))
            decision = decide_advance(state, workflow, state.effective_policy, control_now(uow))
            if isinstance(decision.action, (NewAttempt, Fail)):
                apply_action(decision, ctx, uow, task_id=task.id)
                task = uow.repo(TaskRepository).get(task.id)
                attempt = (
                    None
                    if task.current_attempt_id is None
                    else uow.repo(AttemptRepository).get(task.current_attempt_id)
                )
                inputs = scheduling_input(uow, ctx, run, values)
        if task.status in UNSCHEDULABLE_STATUSES or uow.repo(DecisionRepository).open_for_task(task.id):
            continue
        if attempt and attempt.state not in TERMINAL_ATTEMPT_STATES:
            if attempt.continuation is None:
                continue
            if attempt.continuation.kind == "advance":
                if task.blocking_reason and task.blocking_reason.code is BlockingCode.RECOVERING:
                    continue
            elif (
                attempt.continuation.stage.not_before
                and attempt.continuation.stage.not_before > control_now(uow)
            ):
                continue
        if attempt and any(
            a.state in {AssignmentState.AVAILABLE, AssignmentState.LEASED}
            for a in uow.repo(AssignmentRepository).for_attempt(attempt.id)
        ):
            continue
        if admitted(uow, ctx, run, task, values):
            candidates.append(task)
    inputs = replace(inputs, eligible_ids=frozenset(t.id for t in candidates))
    scheduled: list[Any] = []
    for tid in select_assignable(inputs, limit=limit):
        task = uow.repo(TaskRepository).get(tid, for_update=True)
        attempt = (
            None
            if task.current_attempt_id is None
            else uow.repo(AttemptRepository).get(task.current_attempt_id, for_update=True)
        )
        if attempt and attempt.continuation and attempt.continuation.kind == "advance":
            previous = {a.id for a in uow.repo(AssignmentRepository).for_attempt(attempt.id)}
            process_pending(uow, ctx, attempt.id)
            scheduled.extend(
                {"task_id": str(task.id), "assignment_id": str(a.id)}
                for a in uow.repo(AssignmentRepository).for_attempt(attempt.id)
                if a.id not in previous
            )
            continue
        if attempt is None or attempt.state in TERMINAL_ATTEMPT_STATES:
            attempt = create_attempt(uow, ctx, run, task, values)
            task = uow.repo(TaskRepository).get(task.id)
        if attempt is not None and (
            assignment := enqueue_selected(uow, ctx, run, task, attempt, inputs, values)
        ):
            scheduled.append({"task_id": str(task.id), "assignment_id": str(assignment.id)})
            emit(
                uow,
                run,
                "task-assigned",
                {
                    "task_id": str(task.id),
                    "attempt_id": str(attempt.id),
                    "assignment_id": str(assignment.id),
                    "attempt_no": attempt.attempt_no,
                    "attempt_state": attempt.state.value,
                },
                cause("run_start"),
            )
    # Queued templates stay durable while workers refresh their offers. Only a matching
    # worker can claim one, and the scheduler reconciles the resulting waits each tick.
    capability_wait(uow, ctx, run)
    monitor(uow, ctx, run, name="scheduler", rule="dispatch", thresholds={"max_units": inputs.max_units})
    return scheduled


def handle(cmd: ScheduleReadyTasks, ctx: Any, uow: UnitOfWork) -> ScheduleReadyTasksResult:
    system_guard(ctx)
    ctx = server_context(ctx, uow)
    wire: Any = schedule_ready_tasks_from_json(cmd)
    limit = wire.get("limit", 100)
    repo = uow.repo(RunRepository)
    all_ids = repo.list_active_ids(limit=2**31 - 1)
    selected = {RunId(UUID(rid)) for rid in wire.get("run_ids", ())} or set(all_ids)
    runs = repo.lock_active(tuple(selected))
    started: list[str] = []
    scheduled: list[Any] = []
    checked = 0
    for candidate_run in sorted(runs, key=lambda r: (r.created_at, str(r.id))):
        run = candidate_run
        if run.id not in selected:
            continue
        reap_expired(uow, ctx, run)
        if run.status is RunStatus.READY and run.queued:
            _, queued_values = effective_values(uow, run.id)
            maximum = min(
                int(value(ctx.config, "execution.parallel.max_runs_per_project", 1)),
                int(queued_values.get("execution.parallel.max_runs_per_project", 1)),
            )
            if repo.project_has_slot(run.project_id, maximum):
                updated = start(run, now=control_now(uow))
                repo.save(updated, expected_version=run.row_version)
                emit(
                    uow,
                    run,
                    "run-started",
                    {
                        "revision_id": str(run.revision_id) if run.revision_id is not None else None,
                        "workflow_resource_version_id": str(run.workflow_resource_version_id),
                    },
                    cause("run_start"),
                )
                started.append(str(run.id))
                run = updated
        if run.status is RunStatus.WAITING:
            tasks = uow.repo(TaskRepository).list_for_run(run.id)
            if any(
                t.status is TaskStatus.READY
                or (
                    t.blocking_reason
                    and t.blocking_reason.next_check_at
                    and t.blocking_reason.next_check_at <= control_now(uow)
                )
                for t in tasks
            ):
                updated = wake(run)
                repo.save(updated, expected_version=run.row_version)
                run = updated
        checked += 1
        if run.status is RunStatus.RUNNING and len(scheduled) < limit:
            scheduled.extend(schedule_run(uow, ctx, run, limit - len(scheduled)))
            statuses = uow.repo(TaskRepository).statuses_for_run(run.id)
            latest = repo.get(run.id)
            if latest.status in {RunStatus.RUNNING, RunStatus.WAITING} and statuses <= TERMINAL_TASK_STATUSES:
                finish_run(uow, ctx, latest, cause("wait_changed"))
            elif (
                latest.status is RunStatus.RUNNING
                and statuses
                and statuses <= {TaskStatus.AWAITING_DECISION, TaskStatus.MANUAL_PENDING}
            ):
                repo.save(wait(latest), expected_version=latest.row_version)
                emit(
                    uow, run, "run-waiting", {"waiting": {"code": "WAITING_DECISION"}}, cause("wait_changed")
                )
    return ScheduleReadyTasksResult(
        schedule_ready_tasks_result_from_json(
            {"scheduled": scheduled, "runs_started": started, "runs_checked": checked}
        )
    )


SPEC = CommandSpec(
    name="execution.schedule_ready_tasks",
    dto=ScheduleReadyTasks,
    result=ScheduleReadyTasksResult,
    permission="system.internal",
    permissions_of=lambda _cmd: ("run.control",),
    scope_of=None,
    handler=handle,
    allowed_kinds=frozenset({PrincipalKind.SERVICE}),
    internal=True,
)
