"""Readiness and run-history event fixtures for execution contract tests."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from contracts.context.harness import UNIT_ID
from skm.kernel.ids import PlanId, RevisionId, RunId, TaskId
from skm.kernel.json_types import JsonObject
from skm.modules.execution.domain.ids import ReadinessReportId, ReviewRequestId, StepId
from skm.modules.execution.domain.readiness import (
    ReadinessCheckResult,
    ReadinessInputs,
    ReadinessReport,
    ReadinessScope,
    ReadinessStatus,
)
from skm.modules.execution.domain.review_request import CommitReviewTarget, ReviewRequest
from skm.modules.execution.domain.run import RunKind
from skm.modules.execution.domain.task import ReviewMode, Task, TaskKind, TaskOrigin, TaskStatus
from skm.modules.execution.domain.task_graph import EdgeKind, TaskEdge
from skm.modules.execution.domain.work_policy import Intensity
from skm.modules.execution.ports import ReviewRequestRepository, TaskRepository
from skm.modules.planning import public as planning

from .seed_helpers import (
    COMMIT_1,
    COMMIT_2,
    DIGEST_A,
    DIGEST_B,
    make_work_policies,
    record_run_event,
    seed_run,
)

if TYPE_CHECKING:
    from skm.kernel.ports_uow import UnitOfWork

    from .harness import ExecSide


def make_readiness(
    side: ExecSide,
    *,
    plan_id: PlanId | None = None,
    rev_id: RevisionId | None = None,
    work_policies_present: bool = True,
    start_request: JsonObject | None = None,
) -> ReadinessReport:
    inputs = ReadinessInputs(
        requirements=DIGEST_A,
        dependencies=DIGEST_A,
        write_scopes=DIGEST_A,
        criteria=DIGEST_A,
        capability_requirements=DIGEST_A,
        policy=DIGEST_B,
        config=DIGEST_A,
        resources=DIGEST_A,
        materials=DIGEST_A,
    )
    wp = make_work_policies("P1.1/U1", executor_intensity=Intensity.HEAVY) if work_policies_present else None
    return ReadinessReport(
        id=ReadinessReportId(side.new_id()),
        workspace_id=side.ws,
        project_id=side.proj,
        plan_id=plan_id or side.plan1,
        revision_id=rev_id or side.rev2,
        revision_digest=DIGEST_A,
        status=ReadinessStatus.READY,
        scope=ReadinessScope(kind="plan", phase_keys=()),
        inputs=inputs,
        inputs_digest=DIGEST_A,
        policy_digest=DIGEST_B,
        results=(ReadinessCheckResult(rule_id="R1", outcome="passed", findings_count=0),),
        findings=(),
        assumptions=("clean tree",),
        structural_counts={"units": 1, "items": 1},
        start_request=start_request,
        work_policies=wp,
        estimate={"max_usd": "10.00"},
        audit=None,
        supersedes_report_id=None,
        validator_version=1,
        created_by=side.owner.principal_id,
        created_at=side.clock.now(),
    )


def seed_service_review_runs(side: ExecSide, uow: UnitOfWork, created_at_offset_s: int) -> PlanId:
    req_id = side.new_id()
    svc_spec = planning.ReviewRequestSpec(
        request_id=req_id,
        mount="repo",
        target=planning.CommitReviewTarget(kind="commits", base_commit=COMMIT_1, head_commit=COMMIT_2),
        profile="reviewer",
        reason="Verify service plan exclusion in latest_run_outcome",
    )
    svc_meta = planning.publish_review_request_revision(
        uow, side.owner, side.proj, svc_spec, ids=side.ids, now=side.clock.now()
    )
    assert svc_meta.plan_purpose is planning.PlanPurpose.REVIEW_REQUESTS
    rr_id = ReviewRequestId(req_id)
    uow.repo(ReviewRequestRepository).add(
        ReviewRequest(
            id=rr_id,
            workspace_id=side.ws,
            project_id=side.proj,
            mount="repo",
            repository_id=side.repo_id,
            target=CommitReviewTarget(kind="commits", base_commit=COMMIT_1, head_commit=COMMIT_2),
            profile_key="reviewer",
            reason="Verify service plan exclusion",
            requested_by=side.owner.principal_id,
            plan_id=svc_meta.plan_id,
            revision_id=svc_meta.revision_id,
            created_at=side.clock.now(),
        )
    )
    ts = side.clock.now() + timedelta(seconds=created_at_offset_s)
    seed_run(
        side,
        uow,
        plan_id=svc_meta.plan_id,
        rev_id=svc_meta.revision_id,
        kind=RunKind.REVIEW_REQUEST,
        review_request_id=rr_id,
        created_at=ts,
    )
    seed_run(
        side,
        uow,
        plan_id=svc_meta.plan_id,
        rev_id=svc_meta.revision_id,
        kind=RunKind.PLAN,
        created_at=ts + timedelta(seconds=1),
    )
    return svc_meta.plan_id


def seed_group_review_task(side: ExecSide, uow: UnitOfWork, run_id: RunId, member_task_id: TaskId) -> Task:
    gr_id = TaskId(side.new_id())
    gr_task = Task(
        id=gr_id,
        run_id=run_id,
        workspace_id=side.ws,
        kind=TaskKind.GROUP_REVIEW,
        spec_entity_id=None,
        display_key="GR-1",
        origin=TaskOrigin(member_task_id, (), "GROUP_REVIEW"),
        position=3,
        status=TaskStatus.READY,
        work_kind="review",
        review_mode=ReviewMode.REQUIRED,
        review_profile="reviewer",
        declared_write_scope=(),
        required_host_id=None,
        current_attempt_id=None,
        accepted_attempt_id=None,
        accepted_output_id=None,
        check_fix_rounds=0,
        review_rounds=0,
        attempt_count=0,
        blocking_reason=None,
        row_version=1,
    )
    edge = TaskEdge(
        run_id=run_id,
        prerequisite_task_id=member_task_id,
        dependent_task_id=gr_id,
        kind=EdgeKind.GATE_MEMBER,
        reasons=frozenset(),
    )
    uow.repo(TaskRepository).add_many((gr_task,), (edge,))
    return gr_task


def history_cause(trigger_kind: str = "run_start", advance_rule: str | None = "K1") -> JsonObject:
    return {"trigger_kind": trigger_kind, "advance_rule": advance_rule, "reason_codes": [], "refs": []}


def make_route_snapshot(side: ExecSide) -> JsonObject:
    return {
        "requested": {
            "runtime_id": "codex_cli",
            "model": "gpt-5",
            "model_class": "implementation",
            "effort": "high",
        },
        "resolved": {"runtime_id": "codex_cli", "model": "gpt-5", "effort": "high"},
        "route_source": "plan_route",
        "host_id": str(side.host1),
        "executable_sha256": DIGEST_A,
        "verification_key": DIGEST_B,
        "effective_config_digest": DIGEST_A,
        "reconfiguration_ids": [],
        "route_reason": "ROUTE_DEFAULT",
        "runtime_version": "1.2.0",
        "adapter_version": "1.0.0",
        "catalog_digest": DIGEST_A,
        "profile_version_id": str(side.workflow_rv_id),
    }


def make_runtime_obs(side: ExecSide, step_id: StepId, *, observed_calls: int = 3) -> JsonObject:
    return {
        "schema": "urn:skm:runtimes:runtime-observation:v1",
        "request_id": str(step_id),
        "binding": {
            "runtime_id": "codex_cli",
            "runtime_version": "1.2.0",
            "adapter_version": "1.0.0",
            "executable_sha256": DIGEST_A,
            "verification_key": DIGEST_B,
            "provider_reported_model": "gpt-5",
            "model_source": "provider_stream",
        },
        "timing": {
            "clock_domain_id": str(side.new_id()),
            "duration_ms": 850,
            "first_observed_at": "2026-04-08T12:00:00Z",
            "last_observed_at": "2026-04-08T12:00:01Z",
        },
        "capture": {
            "coverage": "complete",
            "bytes_seen": 512,
            "bytes_retained": 512,
            "bytes_dropped": 0,
            "truncated": False,
            "gaps": [],
            "parser_flags": [],
            "live_events_dropped": 0,
        },
        "tools": {"coverage": "complete", "observed_calls": observed_calls},
    }


def emit_core_history(
    side: ExecSide,
    uow: UnitOfWork,
    run_id: RunId,
    task_id: TaskId,
    attempt_id: UUID,
    stage_record_id: UUID,
    step_id: StepId,
    manifest_id: UUID,
) -> None:
    ws_s, pr_s, r_s, t_s = str(side.ws), str(side.proj), str(run_id), str(task_id)
    for short, payload in (
        (
            "run-created",
            {
                "workspace_id": ws_s,
                "project_id": pr_s,
                "run_id": r_s,
                "plan_id": str(side.plan1),
                "revision_id": str(side.rev1),
                "revision_no": 1,
                "kind": "plan",
                "requested_by": str(side.owner.principal_id),
                "bundle_digest": DIGEST_A,
                "cause": history_cause("manual_start", "START"),
            },
        ),
        (
            "run-started",
            {
                "workspace_id": ws_s,
                "project_id": pr_s,
                "run_id": r_s,
                "task_count": 1,
                "ready_count": 1,
                "bundle_digest": DIGEST_A,
                "review_grouping": {"mode": "none"},
            },
        ),
        (
            "task-created",
            {
                "workspace_id": ws_s,
                "project_id": pr_s,
                "run_id": r_s,
                "task_id": t_s,
                "kind": "unit",
                "revision_id": str(side.rev1),
                "entity_id": str(UNIT_ID),
                "origin": None,
                "cause": history_cause(),
                "initial_state": "ready",
                "position": 0,
                "parent_task_id": None,
            },
        ),
        (
            "attempt-started",
            {
                "workspace_id": ws_s,
                "project_id": pr_s,
                "run_id": r_s,
                "attempt_id": str(attempt_id),
                "task_id": t_s,
                "attempt_no": 1,
                "worker_id": str(side.worker1),
                "host_id": str(side.host1),
            },
        ),
        (
            "stage-started",
            {
                "workspace_id": ws_s,
                "project_id": pr_s,
                "run_id": r_s,
                "attempt_id": str(attempt_id),
                "task_id": t_s,
                "stage_record_id": str(stage_record_id),
                "stage_id": "execute",
                "stage_type": "agent_step",
                "round_no": 1,
                "mode": "normal",
                "skipped_stage_ids": [],
                "input_digest": DIGEST_A,
                "feedback_refs": {},
                "step_refs": [str(step_id)],
                "effective_config_digest": DIGEST_A,
                "reconfiguration_ids": [],
                "cause": history_cause("stage_outcome", "K2"),
            },
        ),
        (
            "step-observation-recorded",
            {
                "workspace_id": ws_s,
                "project_id": pr_s,
                "run_id": r_s,
                "task_id": t_s,
                "attempt_id": str(attempt_id),
                "stage_record_id": str(stage_record_id),
                "step_id": str(step_id),
                "observation": make_runtime_obs(side, step_id),
                "observation_digest": DIGEST_B,
                "cause": history_cause("observation", None),
                "route_snapshot": make_route_snapshot(side),
                "role": "executor",
                "purpose": "primary",
                "seq": 1,
                "parent_step_id": None,
                "context_manifest_id": str(manifest_id),
                "binding_consistency": "matched",
            },
        ),
        (
            "task-accepted",
            {
                "workspace_id": ws_s,
                "project_id": pr_s,
                "run_id": r_s,
                "task_id": t_s,
                "attempt_id": str(attempt_id),
                "output_id": None,
                "clearance": "green",
                "carried_forward": False,
            },
        ),
    ):
        record_run_event(side, uow, run_id, short, payload)
