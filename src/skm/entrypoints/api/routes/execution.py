"""HTTP routes for the execution module."""

from collections.abc import Mapping
from typing import Any, override

from skm.application_bus.registry import IdempotencyMode
from skm.entrypoints.api.routing import Route
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.modules.execution import public as execution

__all__ = ["ROUTES"]

_AUTOPILOT = "/api/v1/projects/{project_id}/autopilot"
_RUN = "/api/v1/runs/{run_id}"
_TASK = "/api/v1/tasks/{task_id}"
_RUN_TASK = _RUN + "/tasks/{task_id}"
_RUN_TASK_PARAMS = {"run_id": "run_id", "task_id": "task_id"}


class _QueryRoute(Route):
    """Decode structured GET parameters before the route validates the complete DTO."""

    __slots__ = ()

    @override
    def bind(
        self, body: Mapping[str, Any], path: Mapping[str, str], query: Mapping[str, str], **kwargs: Any
    ) -> Any:
        fields = dict(body)
        scalars = dict(query)
        for key, target in self.query_params.items():
            if key not in query:
                continue

            if target == "scope":
                kind, _, identifier = scalars.pop(key).partition(":")
                if kind not in {"project", "run"} or not identifier:
                    raise error_for(ErrorCode.SCHEMA_INVALID, "Expected project or run scope")
                value = {"kind": kind, "id": identifier}
            elif target in {"kinds", "states", "statuses"}:
                raw = scalars.pop(key)
                getlist = getattr(query, "getlist", None)
                values: list[str] = [raw] if getlist is None else getlist(key)
                value = [item for group in values for item in group.split(",")]
            else:
                continue
            if target in fields and fields[target] != value:
                raise error_for(ErrorCode.SCHEMA_INVALID, f"Conflicting values for {target}")
            fields[target] = value
        return super().bind(fields, path, scalars, **kwargs)


ROUTES: tuple[Route, ...] = (
    Route(
        "GET",
        _RUN_TASK + "/live-control",
        execution.TaskLiveControlView,
        query=execution.GetTaskLiveControl,
        path_params=_RUN_TASK_PARAMS,
        query_params={"step_id": "step_id", "after_call_id": "after_call_id"},
        body="none",
        tags=("execution",),
    ),
    *(
        Route(
            "POST",
            _RUN_TASK + "/" + action,
            execution.LiveControlResult,
            command=command,
            path_params=_RUN_TASK_PARAMS,
            idempotency=IdempotencyMode.OPTIONAL,
            etag_from="row_version",
            if_match_to="expected_row_version",
            tags=("execution",),
        )
        for action, command in (
            ("abort-step", execution.AbortStep),
            ("override-actor", execution.OverrideActor),
            ("reroute", execution.RerouteTask),
            ("steer", execution.SteerTask),
        )
    ),
    Route(
        "POST",
        "/api/v1/plans/{plan_id}/revisions/{revision_id}/readiness",
        execution.ValidateForExecutionResult,
        command=execution.ValidateForExecution,
        path_params={"plan_id": "plan_id", "revision_id": "revision_id"},
        success_status=201,
        idempotency=IdempotencyMode.OPTIONAL,
        tags=("execution",),
    ),
    Route(
        "POST",
        "/api/v1/plans/{plan_id}/revision-visas",
        execution.ApproveRevisionResult,
        command=execution.ApproveRevision,
        path_params={"plan_id": "plan_id"},
        success_status=201,
        idempotency=IdempotencyMode.OPTIONAL,
        tags=("execution",),
    ),
    Route(
        "GET",
        "/api/v1/plans/{plan_id}/revisions/{revision_id}/visa",
        execution.RevisionVisaStatus,
        query=execution.GetRevisionVisa,
        path_params={"plan_id": "plan_id", "revision_id": "revision_id"},
        body="none",
        tags=("execution",),
    ),
    Route(
        "GET",
        "/api/v1/readiness-reports/{report_id}",
        execution.ReadinessReportView,
        query=execution.GetReadinessReport,
        path_params={"report_id": "report_id"},
        body="none",
        tags=("execution",),
    ),
    Route(
        "POST",
        "/api/v1/projects/{project_id}/runs/adhoc",
        execution.StartRunResult,
        command=execution.RunAdhoc,
        path_params={"project_id": "project_id"},
        success_status=201,
        idempotency=IdempotencyMode.OPTIONAL,
        tags=("execution",),
    ),
    Route(
        "POST",
        "/api/v1/plans/{plan_id}/runs",
        execution.StartRunResult,
        command=execution.StartRun,
        path_params={"plan_id": "plan_id"},
        success_status=201,
        idempotency=IdempotencyMode.OPTIONAL,
        tags=("execution",),
    ),
    _QueryRoute(
        "GET",
        "/api/v1/projects/{project_id}/runs",
        execution.RunsView,
        query=execution.ListRuns,
        path_params={"project_id": "project_id"},
        query_params={
            "statuses": "statuses",
            "kinds": "kinds",
            "plan_id": "plan_id",
            "after": "after",
            "limit": "limit",
            "status": "statuses",
        },
        body="none",
        tags=("execution",),
    ),
    Route(
        "GET",
        _RUN,
        execution.RunView,
        query=execution.GetRun,
        path_params={"run_id": "run_id"},
        body="none",
        etag_from="row_version",
        tags=("execution",),
    ),
    Route(
        "GET",
        "/api/v1/execution/detail",
        execution.ExecutionDetailView,
        query=execution.GetExecutionDetail,
        query_params={"run_id": "run_id", "task_id": "task_id", "attempt_id": "attempt_id"},
        body="none",
        tags=("execution",),
    ),
    Route(
        "POST",
        _RUN + "/pause",
        execution.PauseRunResult,
        command=execution.PauseRun,
        path_params={"run_id": "run_id"},
        idempotency=IdempotencyMode.OPTIONAL,
        etag_from="row_version",
        if_match_to="expected_row_version",
        tags=("execution",),
    ),
    Route(
        "POST",
        _RUN + "/resume",
        execution.ResumeRunResult,
        command=execution.ResumeRun,
        path_params={"run_id": "run_id"},
        idempotency=IdempotencyMode.OPTIONAL,
        etag_from="row_version",
        if_match_to="expected_row_version",
        tags=("execution",),
    ),
    Route(
        "POST",
        _RUN + "/cancel",
        execution.CancelRunResult,
        command=execution.CancelRun,
        path_params={"run_id": "run_id"},
        idempotency=IdempotencyMode.OPTIONAL,
        etag_from="row_version",
        tags=("execution",),
    ),
    Route(
        "POST",
        _RUN + "/reconfigure",
        execution.ReconfigureRunResult,
        command=execution.ReconfigureRun,
        path_params={"run_id": "run_id"},
        idempotency=IdempotencyMode.OPTIONAL,
        etag_from="row_version",
        if_match_to="expected_row_version",
        tags=("execution",),
    ),
    _QueryRoute(
        "GET",
        _RUN + "/tasks",
        execution.TasksView,
        query=execution.ListTasks,
        path_params={"run_id": "run_id"},
        query_params={"statuses": "statuses", "kinds": "kinds", "status": "statuses"},
        body="none",
        tags=("execution",),
    ),
    Route(
        "GET",
        _RUN + "/analytics/review-roi",
        execution.ReviewRoiView,
        query=execution.GetReviewRoi,
        path_params={"run_id": "run_id"},
        body="none",
        tags=("execution",),
    ),
    Route(
        "GET",
        _RUN + "/budget",
        execution.RunBudgetView,
        query=execution.GetRunBudget,
        path_params={"run_id": "run_id"},
        body="none",
        tags=("execution",),
    ),
    Route(
        "GET",
        _RUN + "/timeline",
        execution.RunTimelineView,
        query=execution.GetRunTimeline,
        path_params={"run_id": "run_id"},
        query_params={"after_seq": "after_seq", "limit": "limit"},
        body="none",
        tags=("execution",),
    ),
    Route(
        "GET",
        _RUN + "/history",
        execution.RunHistoryResult,
        query=execution.GetRunHistory,
        path_params={"run_id": "run_id"},
        query_params={"after": "after", "through_seq": "through_seq", "limit": "limit"},
        body="none",
        tags=("execution",),
    ),
    Route(
        "GET",
        _RUN + "/health",
        execution.RunHealth,
        query=execution.GetRunHealth,
        path_params={"run_id": "run_id"},
        body="none",
        tags=("execution",),
    ),
    Route(
        "GET",
        _TASK,
        execution.TaskView,
        query=execution.GetTask,
        path_params={"task_id": "task_id"},
        body="none",
        etag_from="row_version",
        tags=("execution",),
    ),
    Route(
        "POST",
        _TASK + "/restart",
        execution.RestartTaskResult,
        command=execution.RestartTask,
        path_params={"task_id": "task_id"},
        idempotency=IdempotencyMode.OPTIONAL,
        tags=("execution",),
    ),
    Route(
        "POST",
        _TASK + "/skip",
        execution.SkipTaskResult,
        command=execution.SkipTask,
        path_params={"task_id": "task_id"},
        idempotency=IdempotencyMode.OPTIONAL,
        tags=("execution",),
    ),
    Route(
        "POST",
        _TASK + "/carry-forward",
        execution.CarryForwardResultResult,
        command=execution.CarryForwardResult,
        path_params={"task_id": "target_task_id"},
        success_status=201,
        idempotency=IdempotencyMode.OPTIONAL,
        tags=("execution",),
    ),
    Route(
        "GET",
        _TASK + "/attempts",
        execution.TaskAttemptsView,
        query=execution.ListTaskAttempts,
        path_params={"task_id": "task_id"},
        body="none",
        tags=("execution",),
    ),
    Route(
        "GET",
        "/api/v1/fix-briefs/{fix_brief_id}",
        execution.FixBriefView,
        query=execution.GetFixBrief,
        path_params={"fix_brief_id": "fix_brief_id"},
        body="none",
        tags=("execution",),
    ),
    Route(
        "GET",
        "/api/v1/attempts/{attempt_id}",
        execution.AttemptView,
        query=execution.GetAttempt,
        path_params={"attempt_id": "attempt_id"},
        body="none",
        tags=("execution",),
    ),
    Route(
        "GET",
        "/api/v1/steps/{step_id}",
        execution.StepView,
        query=execution.GetStep,
        path_params={"step_id": "step_id"},
        body="none",
        tags=("execution",),
    ),
    Route(
        "GET",
        "/api/v1/worker/stages/{stage_record_id}/access",
        execution.StageAccessView,
        query=execution.VerifyStageAccess,
        path_params={"stage_record_id": "stage_record_id"},
        query_params={
            "assignment_id": "assignment_id",
            "attempt_id": "attempt_id",
            "worker_id": "worker_id",
            "fencing_token": "fencing_token",
            "step_id": "step_id",
        },
        body="none",
        tags=("execution",),
    ),
    _QueryRoute(
        "GET",
        "/api/v1/inbox",
        execution.DecisionRequestsView,
        query=execution.ListDecisionRequests,
        query_params={
            "scope": "scope",
            "kinds": "kinds",
            "states": "states",
            "after": "after",
            "limit": "limit",
            "kind": "kinds",
            "state": "states",
        },
        body="none",
        tags=("execution",),
    ),
    Route(
        "POST",
        "/api/v1/decision-requests/{request_id}/answer",
        execution.AnswerDecisionRequestResult,
        command=execution.AnswerDecisionRequest,
        path_params={"request_id": "request_id"},
        idempotency=IdempotencyMode.OPTIONAL,
        tags=("execution",),
    ),
    Route(
        "POST",
        "/api/v1/check-executions/{check_execution_id}/verdict",
        execution.RecordManualVerdictResult,
        command=execution.RecordManualVerdict,
        path_params={"check_execution_id": "check_execution_id"},
        success_status=201,
        idempotency=IdempotencyMode.OPTIONAL,
        tags=("execution",),
    ),
    Route(
        "POST",
        "/api/v1/deviations",
        execution.AcceptDeviationResult,
        command=execution.AcceptDeviation,
        success_status=201,
        idempotency=IdempotencyMode.OPTIONAL,
        tags=("execution",),
    ),
    Route(
        "POST",
        "/api/v1/admin/external-effects/{effect_id}/reconcile",
        execution.ReconcileExternalEffectResult,
        command=execution.ReconcileExternalEffect,
        path_params={"effect_id": "effect_id"},
        idempotency=IdempotencyMode.OPTIONAL,
        tags=("execution",),
    ),
    Route(
        "POST",
        "/api/v1/projects/{project_id}/review-requests",
        execution.RequestReviewResult,
        command=execution.RequestReview,
        path_params={"project_id": "project_id"},
        success_status=201,
        idempotency=IdempotencyMode.REQUIRED,
        tags=("execution",),
    ),
    Route(
        "GET",
        _RUN + "/review-receipt",
        execution.ReviewReceipt,
        query=execution.GetReviewReceipt,
        path_params={"run_id": "run_id"},
        body="none",
        tags=("execution",),
    ),
    Route(
        "GET",
        _AUTOPILOT,
        execution.AutopilotStatusView,
        query=execution.GetAutopilotStatus,
        path_params={"project_id": "project_id"},
        body="none",
        tags=("execution",),
    ),
    Route(
        "GET",
        _AUTOPILOT + "/explain",
        execution.AutopilotExplainView,
        query=execution.ExplainAutopilot,
        path_params={"project_id": "project_id"},
        body="none",
        tags=("execution",),
    ),
    Route(
        "POST",
        _AUTOPILOT + "/start",
        execution.StartAutopilotResult,
        command=execution.StartAutopilot,
        path_params={"project_id": "project_id"},
        idempotency=IdempotencyMode.OPTIONAL,
        tags=("execution",),
    ),
    Route(
        "POST",
        _AUTOPILOT + "/pause",
        execution.PauseAutopilotResult,
        command=execution.PauseAutopilot,
        path_params={"project_id": "project_id"},
        idempotency=IdempotencyMode.OPTIONAL,
        tags=("execution",),
    ),
    Route(
        "POST",
        _AUTOPILOT + "/drain",
        execution.DrainAutopilotResult,
        command=execution.DrainAutopilot,
        path_params={"project_id": "project_id"},
        idempotency=IdempotencyMode.OPTIONAL,
        tags=("execution",),
    ),
    Route(
        "POST",
        _AUTOPILOT + "/stop",
        execution.StopAutopilotResult,
        command=execution.StopAutopilot,
        path_params={"project_id": "project_id"},
        idempotency=IdempotencyMode.OPTIONAL,
        tags=("execution",),
    ),
    Route(
        "GET",
        "/api/v1/hosts/{host_id}/execution-environments",
        execution.ExecutionEnvironmentsView,
        query=execution.ListExecutionEnvironments,
        path_params={"host_id": "host_id"},
        query_params={"after": "after", "limit": "limit", "removable": "removable_only"},
        body="none",
        tags=("execution",),
    ),
    Route(
        "POST",
        "/api/v1/hosts/{host_id}/execution-environments/removed",
        execution.MarkEnvironmentsRemovedReceipt,
        command=execution.MarkEnvironmentsRemovedCommand,
        path_params={"host_id": "host_id"},
        idempotency=IdempotencyMode.REQUIRED,
        tags=("execution",),
    ),
)
