"""Read a task's current fence and provider-observed tool-call journal."""

from skm.application_bus.registry import QuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.ids import AttemptId, RunId, ScopeId, TaskId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.execution.application._incident_gate import REPAIR_ACTION_DIGEST
from skm.modules.execution.application._live_control import current_owner
from skm.modules.execution.domain.frozen_json import thaw_json
from skm.modules.execution.domain.ids import StepId
from skm.modules.execution.domain.step import AttemptStep
from skm.modules.execution.generated.queries import GetTaskLiveControl
from skm.modules.execution.generated.views import TaskLiveControlView
from skm.modules.execution.ports import (
    AttemptRepository,
    RunRepository,
    StageRepository,
    StepRepository,
    TaskRepository,
)


def _recent_steps(uow: UnitOfWork, attempt_ids: list[AttemptId]) -> list[AttemptStep]:
    stages = uow.repo(StageRepository)
    result: list[AttemptStep] = []
    for attempt_id in attempt_ids:
        result.extend(
            step for entry in reversed(stages.history(attempt_id).entries) for step in reversed(entry.steps)
        )
        if len(result) >= 100:
            break
    return result[:100]


def _coverage(step: AttemptStep) -> object:
    tools = thaw_json(step.runtime_observation.get("tools")) if step.runtime_observation else None
    return tools.get("coverage", "unavailable") if isinstance(tools, dict) else "unavailable"


def handle(query: GetTaskLiveControl, _ctx: object, uow: UnitOfWork) -> TaskLiveControlView:
    run = uow.repo(RunRepository).get(RunId(query.run_id))
    task = uow.repo(TaskRepository).get(TaskId(query.task_id))
    if task.run_id != run.id:
        raise error_for(ErrorCode.NOT_FOUND, "task does not belong to this run")
    repo, attempts = uow.repo(StepRepository), uow.repo(AttemptRepository)
    owner = current_owner(uow, task.current_attempt_id)
    active = owner.step if owner else None
    recent = _recent_steps(uow, [attempt.id for attempt in reversed(attempts.list_for_task(task.id))])
    selected = repo.get(StepId(query.step_id)) if query.step_id else active or next(iter(recent), None)
    if selected is not None and attempts.get(selected.attempt_id).task_id != task.id:
        raise error_for(ErrorCode.NOT_FOUND, "step does not belong to this task")
    calls = (
        () if selected is None else repo.tool_calls(selected.id, after=query.after_call_id or "", limit=101)
    )
    return TaskLiveControlView.from_json(
        {
            "row_version": run.row_version,
            "assignment_id": str(owner.assignment.id) if owner else None,
            "fencing_token": owner.lease.fencing_token if owner else None,
            "active_step_id": str(active.id) if active else None,
            "cancellation_requested": bool(
                owner and owner.stage and (owner.stage.outcome or {}).get("timeout_requested_at")
            ),
            "pending_controls": sorted(repo.live_controls(task.id)),
            "incidents": [
                {
                    "gate_id": str(g.id),
                    "branch": g.details.get("branch", "C" if g.details.get("authority") == "owner" else "A"),
                    "authority": g.details.get("authority", "owner"),
                    "action_digest": g.details.get(REPAIR_ACTION_DIGEST),
                    "stop_after": str(g.stop_after) if g.stop_after else None,
                }
                for g in [
                    g
                    for g in repo.incident_gates(task.id)
                    if g.details.get("action") == "stop_after" or "branch" in g.details
                ][-50:]
            ],
            "steps": [
                {
                    "step_id": str(step.id),
                    "role": step.role.value,
                    "state": step.state.value,
                    "coverage": _coverage(step),
                }
                for step in recent
            ],
            "selected_step_id": str(selected.id) if selected else None,
            "tool_calls": [
                {
                    "call_id": entry.call.call_id,
                    "tool": entry.call.tool,
                    "duration_ms": entry.call.duration_ms,
                    "coverage": entry.coverage,
                }
                for entry in calls[:100]
            ],
            "next_call_id": calls[99].call.call_id if len(calls) > 100 else None,
        }
    )


SPEC = QuerySpec(
    name="execution.get_task_live_control",
    dto=GetTaskLiveControl,
    result=TaskLiveControlView,
    permission="run.read",
    scope_of=lambda query: ScopeRef(ScopeKind.RUN, ScopeId(query.run_id)),
    handler=handle,
)
