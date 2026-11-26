"""Companion metadata for existing closed v1 execution views."""

from __future__ import annotations

from typing import TYPE_CHECKING

from skm.application_bus.registry import QuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, NotFound, ValidationFailed
from skm.kernel.ids import AttemptId, RunId, ScopeId, TaskId
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.access.public import effective_permissions
from skm.modules.execution.application._control import checkpoint_state
from skm.modules.execution.application._start_inputs import value
from skm.modules.execution.application._state import effective_values
from skm.modules.execution.application.commands.reconfigure_run import allowed_keys
from skm.modules.execution.application.commands.restart_task import restart_allowed
from skm.modules.execution.domain.run import RunStatus
from skm.modules.execution.generated.detail import ExecutionDetailView, GetExecutionDetail
from skm.modules.execution.ports import AttemptRepository, RunRepository, TaskRepository
from skm.modules.extensions import public as extensions

if TYPE_CHECKING:
    from skm.application_bus.context import QueryContext
    from skm.kernel.json_types import JsonObject
    from skm.kernel.ports_uow import UnitOfWork
    from skm.modules.execution.domain.run import Run
    from skm.modules.execution.domain.task import Task

__all__ = ["SPEC", "handle"]


def _run_id(query: GetExecutionDetail, uow: UnitOfWork) -> RunId:
    if query.task_id is not None:
        return uow.repo(TaskRepository).get(TaskId(query.task_id)).run_id
    if query.attempt_id is not None:
        return uow.repo(AttemptRepository).get(AttemptId(query.attempt_id)).run_id
    if query.run_id is None:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "an execution selector is required")
    return uow.repo(RunRepository).get(RunId(query.run_id)).id


def _scope(query: GetExecutionDetail, uow: UnitOfWork) -> ScopeRef | None:
    try:
        return ScopeRef(ScopeKind.RUN, ScopeId(_run_id(query, uow)))
    except NotFound:
        return None


def _restart(task: Task, run: Run, ctx: QueryContext, uow: UnitOfWork) -> JsonObject:
    eligible = restart_allowed(run.status, task.status)
    if not eligible:
        return {"eligible": False, "requires_attempts_override": False}
    _, frozen = effective_values(uow, run.id)
    key = "budgets.task.max_attempts"
    limit = frozen.get(key, 3)
    requires_override = bool(limit and task.attempt_count >= limit)
    if requires_override:
        ceiling = value(ctx.config, key, 0)
        eligible = (
            key in allowed_keys(ctx.config)
            and ctx.config.provenance(key).locked_by is None
            and (not ceiling or task.attempt_count + 1 <= ceiling)
            and not any(checkpoint_state(uow, run.id, closing_attempt_id=task.current_attempt_id).values())
        )
    return {"eligible": eligible, "requires_attempts_override": requires_override}


def handle(query: GetExecutionDetail, ctx: QueryContext, uow: UnitOfWork) -> ExecutionDetailView:
    run = uow.repo(RunRepository).get(_run_id(query, uow))
    detail: JsonObject = {
        "run_id": str(run.id),
        "workspace_id": str(run.workspace_id),
        "project_id": str(run.project_id),
        "plan_id": str(run.plan_id) if run.plan_id is not None else None,
        "revision_id": str(run.revision_id) if run.revision_id is not None else None,
        "row_version": run.row_version,
    }
    permissions = effective_permissions(uow, ctx.actor, ScopeId(run.id))
    if "run.read" not in permissions:
        if query.task_id is not None or query.attempt_id is not None:
            raise Forbidden(
                ErrorCode.FORBIDDEN, "required permission is missing", details={"permission": "run.read"}
            )
        return ExecutionDetailView.from_json(detail)
    can_control = "run.control" in permissions
    if query.task_id is not None and can_control:
        task = uow.repo(TaskRepository).get(TaskId(query.task_id))
        detail["restart"] = _restart(task, run, ctx, uow)
    if query.run_id is not None:
        workflow = extensions.get_resource_version(uow, run.workflow_resource_version_id)
        detail["workflow"] = {
            "key": workflow.key,
            "version": workflow.version,
            "resource_version_id": str(run.workflow_resource_version_id),
            "digest": workflow.digest,
        }
        if run.status is RunStatus.PAUSED and can_control:
            detail["checkpoint"] = {
                **checkpoint_state(uow, run.id),
                "changes": [
                    {
                        "key": key,
                        "locked": ctx.config.provenance(key).locked_by is not None,
                        "ceiling": value(ctx.config, key, 0),
                    }
                    for key in sorted(allowed_keys(ctx.config))
                ],
            }
    return ExecutionDetailView.from_json(detail)


SPEC = QuerySpec(
    name="execution.get_execution_detail",
    dto=GetExecutionDetail,
    result=ExecutionDetailView,
    permission="run.read",
    permission_alternatives=("inbox.read",),
    scope_of=None,
    scope_resolver=_scope,
    handler=handle,
)
