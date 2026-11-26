"""Public facade of the ``execution`` module (execution §13)."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING
from uuid import UUID

from skm.kernel.json_types import JsonObject
from skm.modules.execution.application import _worker_dtos as _worker_dtos
from skm.modules.execution.application import _worker_protocol as _worker_protocol
from skm.modules.execution.application import loaders as _loaders
from skm.modules.execution.application import research_access as _research_access
from skm.modules.execution.application._worker_dtos import (
    BeginStage as BeginStage,
)
from skm.modules.execution.application._worker_dtos import (
    BeginStageResult as BeginStageResult,
)
from skm.modules.execution.application._worker_dtos import (
    ClaimAssignment as ClaimAssignment,
)
from skm.modules.execution.application._worker_dtos import (
    ClaimAssignmentResult as ClaimAssignmentResult,
)
from skm.modules.execution.application._worker_dtos import (
    RecordStageResult as RecordStageResult,
)
from skm.modules.execution.application._worker_dtos import (
    RecordStageResultResult as RecordStageResultResult,
)
from skm.modules.execution.application._worker_dtos import (
    RecordStepNote as RecordStepNote,
)
from skm.modules.execution.application._worker_dtos import (
    RecordStepNoteResult as RecordStepNoteResult,
)
from skm.modules.execution.application._worker_dtos import (
    ReleaseAssignment as ReleaseAssignment,
)
from skm.modules.execution.application._worker_dtos import (
    ReleaseAssignmentResult as ReleaseAssignmentResult,
)
from skm.modules.execution.application._worker_dtos import (
    RenewLease as RenewLease,
)
from skm.modules.execution.application._worker_dtos import (
    RenewLeaseResult as RenewLeaseResult,
)
from skm.modules.execution.application._worker_dtos import (
    ReportAttemptFailure as ReportAttemptFailure,
)
from skm.modules.execution.application._worker_dtos import (
    ReportAttemptFailureResult as ReportAttemptFailureResult,
)
from skm.modules.execution.application._worker_dtos import (
    SealOutput as SealOutput,
)
from skm.modules.execution.application._worker_dtos import (
    SealOutputResult as SealOutputResult,
)
from skm.modules.execution.application.commands.acquire_integration_slot import (
    AcquireIntegrationSlot as AcquireIntegrationSlot,
)
from skm.modules.execution.application.commands.record_external_effect import (
    RecordExternalEffect as RecordExternalEffect,
)
from skm.modules.execution.application.commands.release_integration_slot import (
    ReleaseIntegrationSlot as ReleaseIntegrationSlot,
)
from skm.modules.execution.application.export_report import load_run_export_metrics
from skm.modules.execution.domain.blocking_reason import BlockingCode as BlockingCode
from skm.modules.execution.domain.run import RunKind as RunKind
from skm.modules.execution.domain.run import RunStatus as RunStatus
from skm.modules.execution.domain.task import TaskKind as TaskKind
from skm.modules.execution.domain.task import TaskStatus as TaskStatus
from skm.modules.execution.generated.detail import ExecutionDetailView as ExecutionDetailView
from skm.modules.execution.generated.detail import GetExecutionDetail as GetExecutionDetail
from skm.modules.execution.host.stages.base import StageOutcome as StageOutcome
from skm.modules.execution.host.stages.base import StageRequest as StageRequest
from skm.modules.execution.ports import CheckRunner as CheckRunner
from skm.modules.execution.ports import CheckRunnerRegistry as CheckRunnerRegistry
from skm.modules.execution.ports import ExecutionEnvironmentManager as ExecutionEnvironmentManager
from skm.modules.execution.ports import Isolation as Isolation
from skm.modules.execution.ports import IsolationRegistry as IsolationRegistry
from skm.modules.execution.ports import StageClient as StageClient
from skm.modules.execution.ports import StageDeps as StageDeps
from skm.modules.execution.ports import StageHandler as StageHandler
from skm.modules.execution.ports import Vcs as Vcs

if TYPE_CHECKING:
    from datetime import datetime

    from skm.kernel.actor import Actor
    from skm.kernel.ids import AttemptId, PlanId, ProjectId, RevisionId, RunId, TaskId
    from skm.kernel.ports_uow import UnitOfWork


def require_current_context_owner(
    uow: UnitOfWork,
    actor: Actor,
    owner_ref: str,
    *,
    assignment_id: UUID,
    attempt_id: UUID,
    worker_id: UUID,
    fencing_token: int,
    now: datetime,
) -> None:
    _worker_protocol.require_context_owner(
        uow,
        actor,
        owner_ref,
        {
            "assignment_id": str(assignment_id),
            "attempt_id": str(attempt_id),
            "worker_id": str(worker_id),
            "fencing_token": fencing_token,
        },
        now=now,
    )


def get_run_summary(uow: UnitOfWork, run_id: RunId) -> JsonObject:
    return _loaders.build_run_summary(uow, run_id)


def require_research_step_scope(uow: UnitOfWork, project_id: ProjectId, step_ref: str) -> None:
    """Check a human caller's provenance reference against the authorized project/workspace."""
    _research_access.require_step_scope(uow, project_id, step_ref)


def require_research_assignment(
    uow: UnitOfWork,
    actor: Actor,
    project_id: ProjectId,
    *,
    step_ref: str | None,
    for_update: bool,
    now: datetime,
    permission: str = "context.read",
) -> JsonObject:
    """Bind research to a current worker, lease, run and started step in the caller's UoW."""
    return _research_access.require_assignment(
        uow,
        actor,
        project_id,
        step_ref=step_ref,
        for_update=for_update,
        now=now,
        permission=permission,
    )


def require_live_attempt_claim(
    uow: UnitOfWork, actor: Actor, *, attempt_id: AttemptId, raw_claim: object, now: datetime
) -> None:
    """Verify worker ownership, active lease/fence, and non-terminal attempt for live stream publish."""
    _worker_protocol.require_live_attempt_claim(
        uow, actor, attempt_id=attempt_id, raw_claim=raw_claim, now=now
    )


def get_attempt_summary(uow: UnitOfWork, attempt_id: AttemptId) -> JsonObject:
    return _loaders.build_attempt_summary(uow, attempt_id)


def get_run_report_data(uow: UnitOfWork, run_id: RunId) -> JsonObject:
    return _loaders.build_run_report_data(uow, run_id)


def get_run_export_metrics(uow: UnitOfWork, run_id: RunId) -> JsonObject:
    return load_run_export_metrics(uow, run_id)


def latest_run_outcome(
    uow: UnitOfWork,
    project_id: ProjectId,
    plan_id: PlanId | None = None,
    *,
    revision_id: RevisionId | None = None,
) -> JsonObject | None:
    return _loaders.build_latest_run_outcome(uow, project_id, plan_id, revision_id=revision_id)


def get_attempt_activity(uow: UnitOfWork, attempt_id: AttemptId) -> JsonObject:
    return _worker_protocol.attempt_activity(uow, attempt_id)


def list_check_executions(uow: UnitOfWork, attempt_id: AttemptId) -> tuple[JsonObject, ...]:
    """Return check keys and states in execution order across the attempt's outputs."""
    return _loaders.load_check_executions(uow, attempt_id)


def list_task_attempts_for_learning(uow: UnitOfWork, task_id: TaskId) -> tuple[JsonObject, ...]:
    return _loaders.build_task_attempts_for_learning(uow, task_id)


if TYPE_CHECKING:
    from .application.commands.acquire_integration_slot import (
        AcquireIntegrationSlotResult as AcquireIntegrationSlotResult,
    )
    from .application.commands.drain_autopilot import (
        DrainAutopilot as DrainAutopilot,
    )
    from .application.commands.drain_autopilot import (
        DrainAutopilotResult as DrainAutopilotResult,
    )
    from .application.commands.mark_environments_removed import (
        MarkEnvironmentsRemovedCommand as MarkEnvironmentsRemovedCommand,
    )
    from .application.commands.mark_environments_removed import (
        MarkEnvironmentsRemovedReceipt as MarkEnvironmentsRemovedReceipt,
    )
    from .application.commands.pause_autopilot import (
        PauseAutopilot as PauseAutopilot,
    )
    from .application.commands.pause_autopilot import (
        PauseAutopilotResult as PauseAutopilotResult,
    )
    from .application.commands.reconcile_external_effect import (
        ReconcileExternalEffect as ReconcileExternalEffect,
    )
    from .application.commands.reconcile_external_effect import (
        ReconcileExternalEffectResult as ReconcileExternalEffectResult,
    )
    from .application.commands.record_external_effect import (
        RecordExternalEffectResult as RecordExternalEffectResult,
    )
    from .application.commands.release_integration_slot import (
        ReleaseIntegrationSlotResult as ReleaseIntegrationSlotResult,
    )
    from .application.commands.request_review import RequestReviewResult as RequestReviewResult
    from .application.commands.start_autopilot import (
        StartAutopilot as StartAutopilot,
    )
    from .application.commands.start_autopilot import (
        StartAutopilotResult as StartAutopilotResult,
    )
    from .application.commands.stop_autopilot import (
        StopAutopilot as StopAutopilot,
    )
    from .application.commands.stop_autopilot import (
        StopAutopilotResult as StopAutopilotResult,
    )
    from .application.queries import RunHistoryResult as RunHistoryResult
    from .application.queries.explain_autopilot import (
        AutopilotExplainView as AutopilotExplainView,
    )
    from .application.queries.explain_autopilot import (
        ExplainAutopilot as ExplainAutopilot,
    )
    from .application.queries.get_autopilot_status import (
        AutopilotStatusView as AutopilotStatusView,
    )
    from .application.queries.get_autopilot_status import (
        GetAutopilotStatus as GetAutopilotStatus,
    )
    from .application.queries.get_fix_brief import FixBriefView as FixBriefView
    from .application.queries.get_fix_brief import GetFixBrief as GetFixBrief
    from .application.queries.get_review_receipt import GetReviewReceipt as GetReviewReceipt
    from .domain.review_request import RequestReview as RequestReview
    from .domain.review_request import ReviewReceipt as ReviewReceipt
    from .generated._commands_abort_step import AbortStep as AbortStep
    from .generated._commands_accept_deviation import AcceptDeviation as AcceptDeviation
    from .generated._commands_answer_decision_request import AnswerDecisionRequest as AnswerDecisionRequest
    from .generated._commands_approve_revision import ApproveRevision as ApproveRevision
    from .generated._commands_cancel_run import CancelRun as CancelRun
    from .generated._commands_carry_forward_result import CarryForwardResult as CarryForwardResult
    from .generated._commands_override_actor import OverrideActor as OverrideActor
    from .generated._commands_pause_run import PauseRun as PauseRun
    from .generated._commands_reconfigure_run import ReconfigureRun as ReconfigureRun
    from .generated._commands_record_manual_verdict import RecordManualVerdict as RecordManualVerdict
    from .generated._commands_reroute_task import RerouteTask as RerouteTask
    from .generated._commands_restart_task import RestartTask as RestartTask
    from .generated._commands_resume_run import ResumeRun as ResumeRun
    from .generated._commands_run_adhoc import RunAdhoc as RunAdhoc
    from .generated._commands_skip_task import SkipTask as SkipTask
    from .generated._commands_start_run import StartRun as StartRun
    from .generated._commands_steer_task import SteerTask as SteerTask
    from .generated._commands_validate_for_execution import ValidateForExecution as ValidateForExecution
    from .generated._results_accept_deviation_result import AcceptDeviationResult as AcceptDeviationResult
    from .generated._results_answer_decision_request_result import (
        AnswerDecisionRequestResult as AnswerDecisionRequestResult,
    )
    from .generated._results_approve_revision_result import ApproveRevisionResult as ApproveRevisionResult
    from .generated._results_cancel_run_result import CancelRunResult as CancelRunResult
    from .generated._results_carry_forward_result_result import (
        CarryForwardResultResult as CarryForwardResultResult,
    )
    from .generated._results_live_control_result import LiveControlResult as LiveControlResult
    from .generated._results_pause_run_result import PauseRunResult as PauseRunResult
    from .generated._results_reconfigure_run_result import ReconfigureRunResult as ReconfigureRunResult
    from .generated._results_record_manual_verdict_result import (
        RecordManualVerdictResult as RecordManualVerdictResult,
    )
    from .generated._results_restart_task_result import RestartTaskResult as RestartTaskResult
    from .generated._results_resume_run_result import ResumeRunResult as ResumeRunResult
    from .generated._results_skip_task_result import SkipTaskResult as SkipTaskResult
    from .generated._results_start_run_result import StartRunResult as StartRunResult
    from .generated._results_validate_for_execution_result import (
        ValidateForExecutionResult as ValidateForExecutionResult,
    )
    from .generated._views_attempt_view import AttemptView as AttemptView
    from .generated._views_decision_requests_view import DecisionRequestsView as DecisionRequestsView
    from .generated._views_execution_environments_view import (
        ExecutionEnvironmentsView as ExecutionEnvironmentsView,
    )
    from .generated._views_readiness_report_view import ReadinessReportView as ReadinessReportView
    from .generated._views_review_roi_view import ReviewRoiView as ReviewRoiView
    from .generated._views_revision_visa_status import RevisionVisaStatus as RevisionVisaStatus
    from .generated._views_run_budget_view import RunBudgetView as RunBudgetView
    from .generated._views_run_health import RunHealth as RunHealth
    from .generated._views_run_timeline_view import RunTimelineView as RunTimelineView
    from .generated._views_run_view import RunView as RunView
    from .generated._views_runs_view import RunsView as RunsView
    from .generated._views_step_view import StepView as StepView
    from .generated._views_task_attempts_view import TaskAttemptsView as TaskAttemptsView
    from .generated._views_task_live_control_view import TaskLiveControlView as TaskLiveControlView
    from .generated._views_task_view import TaskView as TaskView
    from .generated._views_tasks_view import TasksView as TasksView
    from .generated.queries import (
        GetAttempt as GetAttempt,
    )
    from .generated.queries import (
        GetReadinessReport as GetReadinessReport,
    )
    from .generated.queries import GetReviewRoi as GetReviewRoi
    from .generated.queries import GetRevisionVisa as GetRevisionVisa
    from .generated.queries import (
        GetRun as GetRun,
    )
    from .generated.queries import (
        GetRunBudget as GetRunBudget,
    )
    from .generated.queries import (
        GetRunHealth as GetRunHealth,
    )
    from .generated.queries import (
        GetRunHistory as GetRunHistory,
    )
    from .generated.queries import (
        GetRunTimeline as GetRunTimeline,
    )
    from .generated.queries import (
        GetStep as GetStep,
    )
    from .generated.queries import (
        GetTask as GetTask,
    )
    from .generated.queries import GetTaskLiveControl as GetTaskLiveControl
    from .generated.queries import (
        ListDecisionRequests as ListDecisionRequests,
    )
    from .generated.queries import (
        ListExecutionEnvironments as ListExecutionEnvironments,
    )
    from .generated.queries import (
        ListRuns as ListRuns,
    )
    from .generated.queries import (
        ListTaskAttempts as ListTaskAttempts,
    )
    from .generated.queries import (
        ListTasks as ListTasks,
    )
    from .generated.queries import VerifyStageAccess as VerifyStageAccess
    from .generated.views import StageAccessView as StageAccessView

_LAZY_EXPORTS: dict[str, str] = {
    "AcquireIntegrationSlotResult": ".application.commands.acquire_integration_slot",
    **dict.fromkeys(("DrainAutopilot", "DrainAutopilotResult"), ".application.commands.drain_autopilot"),
    **dict.fromkeys(
        ("MarkEnvironmentsRemovedCommand", "MarkEnvironmentsRemovedReceipt"),
        ".application.commands.mark_environments_removed",
    ),
    **dict.fromkeys(("PauseAutopilot", "PauseAutopilotResult"), ".application.commands.pause_autopilot"),
    **dict.fromkeys(
        ("ReconcileExternalEffect", "ReconcileExternalEffectResult"),
        ".application.commands.reconcile_external_effect",
    ),
    "RecordExternalEffectResult": ".application.commands.record_external_effect",
    "ReleaseIntegrationSlotResult": ".application.commands.release_integration_slot",
    "RequestReviewResult": ".application.commands.request_review",
    **dict.fromkeys(("StartAutopilot", "StartAutopilotResult"), ".application.commands.start_autopilot"),
    **dict.fromkeys(("StopAutopilot", "StopAutopilotResult"), ".application.commands.stop_autopilot"),
    "RunHistoryResult": ".application.queries",
    **dict.fromkeys(("AutopilotExplainView", "ExplainAutopilot"), ".application.queries.explain_autopilot"),
    **dict.fromkeys(
        ("AutopilotStatusView", "GetAutopilotStatus"), ".application.queries.get_autopilot_status"
    ),
    **dict.fromkeys(("FixBriefView", "GetFixBrief"), ".application.queries.get_fix_brief"),
    "GetReviewReceipt": ".application.queries.get_review_receipt",
    "GetReviewRoi": ".generated.queries",
    "ReviewRoiView": ".generated._views_review_roi_view",
    **dict.fromkeys(("RequestReview", "ReviewReceipt"), ".domain.review_request"),
    "AcceptDeviation": ".generated._commands_accept_deviation",
    "ApproveRevision": ".generated._commands_approve_revision",
    "AnswerDecisionRequest": ".generated._commands_answer_decision_request",
    "AbortStep": ".generated._commands_abort_step",
    "OverrideActor": ".generated._commands_override_actor",
    "RerouteTask": ".generated._commands_reroute_task",
    "SteerTask": ".generated._commands_steer_task",
    "GetTaskLiveControl": ".generated.queries",
    "LiveControlResult": ".generated._results_live_control_result",
    "TaskLiveControlView": ".generated._views_task_live_control_view",
    "CancelRun": ".generated._commands_cancel_run",
    "CarryForwardResult": ".generated._commands_carry_forward_result",
    "PauseRun": ".generated._commands_pause_run",
    "ReconfigureRun": ".generated._commands_reconfigure_run",
    "RecordManualVerdict": ".generated._commands_record_manual_verdict",
    "RestartTask": ".generated._commands_restart_task",
    "ResumeRun": ".generated._commands_resume_run",
    "SkipTask": ".generated._commands_skip_task",
    "RunAdhoc": ".generated._commands_run_adhoc",
    "StartRun": ".generated._commands_start_run",
    "ValidateForExecution": ".generated._commands_validate_for_execution",
    "AcceptDeviationResult": ".generated._results_accept_deviation_result",
    "ApproveRevisionResult": ".generated._results_approve_revision_result",
    "AnswerDecisionRequestResult": ".generated._results_answer_decision_request_result",
    "CancelRunResult": ".generated._results_cancel_run_result",
    "CarryForwardResultResult": ".generated._results_carry_forward_result_result",
    "PauseRunResult": ".generated._results_pause_run_result",
    "ReconfigureRunResult": ".generated._results_reconfigure_run_result",
    "RecordManualVerdictResult": ".generated._results_record_manual_verdict_result",
    "RestartTaskResult": ".generated._results_restart_task_result",
    "ResumeRunResult": ".generated._results_resume_run_result",
    "SkipTaskResult": ".generated._results_skip_task_result",
    "StartRunResult": ".generated._results_start_run_result",
    "ValidateForExecutionResult": ".generated._results_validate_for_execution_result",
    "AttemptView": ".generated._views_attempt_view",
    "DecisionRequestsView": ".generated._views_decision_requests_view",
    "ExecutionEnvironmentsView": ".generated._views_execution_environments_view",
    "ReadinessReportView": ".generated._views_readiness_report_view",
    "GetRevisionVisa": ".generated.queries",
    "RevisionVisaStatus": ".generated._views_revision_visa_status",
    "RunBudgetView": ".generated._views_run_budget_view",
    "RunHealth": ".generated._views_run_health",
    "RunTimelineView": ".generated._views_run_timeline_view",
    "RunView": ".generated._views_run_view",
    "RunsView": ".generated._views_runs_view",
    "StepView": ".generated._views_step_view",
    "StageAccessView": ".generated.views",
    "VerifyStageAccess": ".generated.queries",
    "TaskAttemptsView": ".generated._views_task_attempts_view",
    "TaskView": ".generated._views_task_view",
    "TasksView": ".generated._views_tasks_view",
    **dict.fromkeys(
        (
            "GetAttempt",
            "GetReadinessReport",
            "GetRun",
            "GetRunBudget",
            "GetRunHealth",
            "GetRunHistory",
            "GetRunTimeline",
            "GetStep",
            "GetTask",
            "ListDecisionRequests",
            "ListExecutionEnvironments",
            "ListRuns",
            "ListTaskAttempts",
            "ListTasks",
        ),
        ".generated.queries",
    ),
}


def __getattr__(name: str) -> object:
    module_name = _LAZY_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name, __package__), name)
    globals()[name] = value
    return value


__all__ = [
    "AbortStep",
    "AcceptDeviation",
    "AcceptDeviationResult",
    "AcquireIntegrationSlot",
    "AcquireIntegrationSlotResult",
    "AnswerDecisionRequest",
    "AnswerDecisionRequestResult",
    "ApproveRevision",
    "ApproveRevisionResult",
    "AttemptView",
    "AutopilotExplainView",
    "AutopilotStatusView",
    "BeginStage",
    "BeginStageResult",
    "BlockingCode",
    "CancelRun",
    "CancelRunResult",
    "CarryForwardResult",
    "CarryForwardResultResult",
    "CheckRunner",
    "CheckRunnerRegistry",
    "ClaimAssignment",
    "ClaimAssignmentResult",
    "DecisionRequestsView",
    "DrainAutopilot",
    "DrainAutopilotResult",
    "ExecutionDetailView",
    "ExecutionEnvironmentManager",
    "ExecutionEnvironmentsView",
    "ExplainAutopilot",
    "FixBriefView",
    "GetAttempt",
    "GetAutopilotStatus",
    "GetExecutionDetail",
    "GetFixBrief",
    "GetReadinessReport",
    "GetReviewReceipt",
    "GetReviewRoi",
    "GetRevisionVisa",
    "GetRun",
    "GetRunBudget",
    "GetRunHealth",
    "GetRunHistory",
    "GetRunTimeline",
    "GetStep",
    "GetTask",
    "GetTaskLiveControl",
    "Isolation",
    "IsolationRegistry",
    "ListDecisionRequests",
    "ListExecutionEnvironments",
    "ListRuns",
    "ListTaskAttempts",
    "ListTasks",
    "LiveControlResult",
    "MarkEnvironmentsRemovedCommand",
    "MarkEnvironmentsRemovedReceipt",
    "OverrideActor",
    "PauseAutopilot",
    "PauseAutopilotResult",
    "PauseRun",
    "PauseRunResult",
    "ReadinessReportView",
    "ReconcileExternalEffect",
    "ReconcileExternalEffectResult",
    "ReconfigureRun",
    "ReconfigureRunResult",
    "RecordExternalEffect",
    "RecordExternalEffectResult",
    "RecordManualVerdict",
    "RecordManualVerdictResult",
    "RecordStageResult",
    "RecordStageResultResult",
    "RecordStepNote",
    "RecordStepNoteResult",
    "ReleaseAssignment",
    "ReleaseAssignmentResult",
    "ReleaseIntegrationSlot",
    "ReleaseIntegrationSlotResult",
    "RenewLease",
    "RenewLeaseResult",
    "ReportAttemptFailure",
    "ReportAttemptFailureResult",
    "RequestReview",
    "RequestReviewResult",
    "RerouteTask",
    "RestartTask",
    "RestartTaskResult",
    "ResumeRun",
    "ResumeRunResult",
    "ReviewReceipt",
    "ReviewRoiView",
    "RevisionVisaStatus",
    "RunAdhoc",
    "RunBudgetView",
    "RunHealth",
    "RunHistoryResult",
    "RunKind",
    "RunStatus",
    "RunTimelineView",
    "RunView",
    "RunsView",
    "SealOutput",
    "SealOutputResult",
    "SkipTask",
    "SkipTaskResult",
    "StageAccessView",
    "StageClient",
    "StageDeps",
    "StageHandler",
    "StageOutcome",
    "StageRequest",
    "StartAutopilot",
    "StartAutopilotResult",
    "StartRun",
    "StartRunResult",
    "SteerTask",
    "StepView",
    "StopAutopilot",
    "StopAutopilotResult",
    "TaskAttemptsView",
    "TaskKind",
    "TaskLiveControlView",
    "TaskStatus",
    "TaskView",
    "TasksView",
    "ValidateForExecution",
    "ValidateForExecutionResult",
    "Vcs",
    "VerifyStageAccess",
    "get_attempt_activity",
    "get_attempt_summary",
    "get_run_export_metrics",
    "get_run_report_data",
    "get_run_summary",
    "latest_run_outcome",
    "list_check_executions",
    "list_task_attempts_for_learning",
    "require_current_context_owner",
    "require_live_attempt_claim",
    "require_research_assignment",
    "require_research_step_scope",
]
