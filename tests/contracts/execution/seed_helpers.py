"""Entity seeding helpers for dual-backend execution contract tests."""

from __future__ import annotations

import base64
from collections.abc import Mapping
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar, override
from uuid import UUID

from contracts.context.harness import UNIT_ID
from skm.kernel.events import DomainEvent
from skm.kernel.ids import (
    AttemptId,
    ContextManifestId,
    EntityId,
    FileVersionId,
    HostId,
    PlanId,
    ProjectId,
    RevisionId,
    RunId,
    ScopeId,
    TaskId,
    WorkerId,
    WorkspaceId,
)
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRegistry
from skm.modules.execution.domain.attempt import Attempt, AttemptState, PendingContinuation
from skm.modules.execution.domain.blocking_reason import BlockingReason
from skm.modules.execution.domain.execution_bundle import (
    DEFAULT_POLICY_KEY,
    ExecutionBundle,
    ResourcePin,
    ResourcePins,
    RunSelection,
)
from skm.modules.execution.domain.ids import (
    EnvironmentId,
    OutputId,
    ReadinessReportId,
    ReviewRequestId,
    StageRecordId,
    StepId,
)
from skm.modules.execution.domain.output import (
    OUTPUT_ALGORITHM,
    ChangedPath,
    DiffStats,
    Output,
    OutputManifest,
    OutputMount,
    OutputSource,
    manifest_digest,
)
from skm.modules.execution.domain.review_grouping import ReviewGrouping
from skm.modules.execution.domain.run import Run, RunKind, RunStatus
from skm.modules.execution.domain.session import RouteRef, SessionFingerprint
from skm.modules.execution.domain.stage_record import StageOutcomeKind, StageRecord, StageState
from skm.modules.execution.domain.step import AttemptStep, RoleId, StepPurpose, StepState
from skm.modules.execution.domain.task import PathPattern, ReviewMode, Task, TaskKind, TaskOrigin, TaskStatus
from skm.modules.execution.domain.work_policy import (
    EffectiveWorkPolicy,
    HardCeilings,
    Intensity,
    WorkPolicyOverride,
    WorkPolicySettings,
    resolve_work_policy,
)
from skm.modules.execution.domain.workflow.stage_inputs import StageMode
from skm.modules.execution.ports import (
    AttemptRepository,
    BundleRepository,
    OutputRepository,
    RunRepository,
    StageRepository,
    StepRepository,
    TaskRepository,
)

if TYPE_CHECKING:
    from .harness import ExecSide

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
COMMIT_1 = "1" * 40
COMMIT_2 = "2" * 40
TREE_1 = "3" * 40


def make_work_policies(
    *task_keys: str, executor_intensity: Intensity = Intensity.MEDIUM
) -> dict[str, EffectiveWorkPolicy]:
    settings = WorkPolicySettings.defaults()
    ceilings = HardCeilings(step_wall_seconds=3600)
    default_pol = resolve_work_policy(settings, ceilings=ceilings)
    out: dict[str, EffectiveWorkPolicy] = {DEFAULT_POLICY_KEY: default_pol}
    override = WorkPolicyOverride(role_intensity={"executor": executor_intensity})
    for key in task_keys or ("P1.1/U1",):
        out[key] = resolve_work_policy(settings, unit=override, ceilings=ceilings, unit_ref=key)
    return out


def seed_run(
    side: ExecSide,
    uow: UnitOfWork,
    *,
    run_id: RunId | None = None,
    plan_id: PlanId | None = None,
    rev_id: RevisionId | None = None,
    revision_no: int = 1,
    kind: RunKind = RunKind.PLAN,
    inline_spec_file_version_id: FileVersionId | None = None,
    status: RunStatus = RunStatus.RUNNING,
    ws: WorkspaceId | None = None,
    proj: ProjectId | None = None,
    created_at: datetime | None = None,
    readiness_report_id: ReadinessReportId | None = None,
    audited_report_id: ReadinessReportId | None = None,
    review_request_id: ReviewRequestId | None = None,
    unmetered_at: datetime | None = None,
) -> Run:
    rid, pid, rvid = run_id or RunId(side.new_id()), plan_id or side.plan1, rev_id or side.rev1
    ws_id, pr_id, ts = ws or side.ws, proj or side.proj, created_at or side.clock.now()
    started = None if status in {RunStatus.CREATED, RunStatus.READY} else ts
    finished = ts if status in {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED} else None
    p_src = "owner" if status is RunStatus.PAUSED else None
    p_rsn = "operator paused" if status is RunStatus.PAUSED else None
    adhoc = kind is RunKind.ADHOC
    uow.repo(ScopeRegistry).create(
        ScopeId(rid), ScopeKind.RUN, parent=ScopeId(pr_id if adhoc else pid), workspace_id=ws_id
    )
    run = Run(
        id=rid,
        workspace_id=ws_id,
        project_id=pr_id,
        kind=kind,
        plan_id=None if adhoc else pid,
        revision_id=None if adhoc else rvid,
        revision_no=None if adhoc else revision_no,
        inline_spec_file_version_id=inline_spec_file_version_id,
        status=status,
        requested_by=side.owner.principal_id,
        readiness_report_id=readiness_report_id,
        audited_report_id=audited_report_id,
        review_request_id=review_request_id,
        compiler_version=1,
        workflow_resource_version_id=side.workflow_rv_id,
        review_grouping=ReviewGrouping("none", (), "medium", "off"),
        autopilot=False,
        queued=False,
        pause_reason=p_rsn,
        pause_source=p_src,
        stop_code=None,
        unmetered_at=unmetered_at,
        row_version=1,
        created_at=ts,
        started_at=started,
        finished_at=finished,
    )
    uow.repo(RunRepository).add(run)
    return run


def seed_bundle(
    side: ExecSide,
    uow: UnitOfWork,
    run_id: RunId,
    *,
    work_policies: Mapping[str, EffectiveWorkPolicy] | None = None,
    omit_work_policies: bool = False,
    config_snapshot: JsonObject | None = None,
    selection: RunSelection | None = None,
) -> ExecutionBundle:
    wp = (
        None
        if omit_work_policies
        else (dict(work_policies) if work_policies is not None else make_work_policies())
    )
    pins = ResourcePins((ResourcePin("agent_profile", "executor", side.workflow_rv_id, DIGEST_A),), {})
    bundle = ExecutionBundle(
        run_id=run_id,
        config_snapshot=config_snapshot or {"budgets": {"task": {"max_attempts": 3}}, "mode": "strict"},
        config_digest=DIGEST_A,
        policy_digest=DIGEST_B,
        resource_pins=pins,
        selection=selection,
        work_policies=wp,
        context_policy={"max_tokens": 32000},
        review_grouping=ReviewGrouping("none", (), "medium", "off"),
        created_at=side.clock.now(),
    )
    uow.repo(BundleRepository).add(bundle)
    return bundle


def seed_task(
    side: ExecSide,
    uow: UnitOfWork,
    run_id: RunId,
    *,
    task_id: TaskId | None = None,
    kind: TaskKind = TaskKind.UNIT,
    spec_entity_id: EntityId | None = UNIT_ID,
    display_key: str = "P1.1/U1",
    origin: TaskOrigin | None = None,
    status: TaskStatus = TaskStatus.READY,
    position: int = 0,
    ws: WorkspaceId | None = None,
    blocking_reason: BlockingReason | None = None,
) -> Task:
    tid = task_id or TaskId(side.new_id())
    spec_k = {TaskKind.UNIT, TaskKind.ITEM, TaskKind.ITEM_GATE, TaskKind.PHASE_GATE}
    gate_k = {TaskKind.ITEM_GATE, TaskKind.PHASE_GATE, TaskKind.PLAN_ACCEPTANCE}
    ent = spec_entity_id if kind in spec_k else None
    wscope = () if kind in gate_k else (PathPattern("repo", "src/**"),)
    task = Task(
        id=tid,
        run_id=run_id,
        workspace_id=ws or side.ws,
        kind=kind,
        spec_entity_id=ent,
        display_key=display_key,
        origin=origin
        or (
            TaskOrigin(None, (), "SYNTHETIC")
            if kind in {TaskKind.INTEGRATION, TaskKind.FOLLOWUP, TaskKind.GROUP_REVIEW}
            else None
        ),
        position=position,
        status=status,
        work_kind="code",
        review_mode=ReviewMode.SELF,
        review_profile=None,
        declared_write_scope=wscope,
        required_host_id=None,
        current_attempt_id=None,
        accepted_attempt_id=None,
        accepted_output_id=None,
        check_fix_rounds=0,
        review_rounds=0,
        attempt_count=0,
        blocking_reason=blocking_reason,
        row_version=1,
    )
    uow.repo(TaskRepository).add_many((task,), ())
    return task


def seed_attempt(
    side: ExecSide,
    uow: UnitOfWork,
    run_id: RunId,
    task_id: TaskId,
    *,
    attempt_id: AttemptId | None = None,
    attempt_no: int = 1,
    state: AttemptState = AttemptState.RUNNING,
    worker_id: WorkerId | None = None,
    host_id: HostId | None = None,
    environment_id: EnvironmentId | None = None,
    continuation: PendingContinuation | None = None,
    ws: WorkspaceId | None = None,
) -> Attempt:
    aid = attempt_id or AttemptId(side.new_id())
    term = state in {AttemptState.COMPLETED, AttemptState.OWNERSHIP_LOST, AttemptState.ABANDONED}
    att = Attempt(
        id=aid,
        run_id=run_id,
        task_id=task_id,
        workspace_id=ws or side.ws,
        attempt_no=attempt_no,
        state=state,
        worker_id=worker_id or side.worker1,
        host_id=host_id or side.host1,
        environment_id=environment_id,
        current_output_id=None,
        executor_route=RouteRef("codex_cli", "gpt-5", "high"),
        continuation=continuation,
        started_at=side.clock.now(),
        finished_at=side.clock.now() if term else None,
        end_reason="ACCEPTED" if term else None,
    )
    uow.repo(AttemptRepository).add(att)
    return att


def seed_stage(
    side: ExecSide,
    uow: UnitOfWork,
    attempt: Attempt,
    *,
    stage_record_id: StageRecordId | None = None,
    seq: int = 1,
    stage_id: str = "execute",
    stage_type: str = "agent_step",
    round_no: int = 1,
    state: StageState = StageState.RUNNING,
    outcome_kind: StageOutcomeKind | None = None,
    fencing_token: int = 1,
) -> StageRecord:
    srid = stage_record_id or StageRecordId(side.new_id())
    term = state in {StageState.COMPLETED, StageState.FAILED, StageState.INTERRUPTED, StageState.SKIPPED}
    okind = outcome_kind or (StageOutcomeKind.SUCCESS if state is StageState.COMPLETED else None)
    rec = StageRecord(
        id=srid,
        attempt_id=attempt.id,
        run_id=attempt.run_id,
        task_id=attempt.task_id,
        seq=seq,
        stage_id=stage_id,
        stage_type=stage_type,
        round_no=round_no,
        mode=StageMode.NORMAL,
        retry_of_id=None,
        state=state,
        input_digest=DIGEST_A,
        outcome_kind=okind,
        outcome={"ok": True} if state is StageState.COMPLETED else None,
        error_code=None,
        started_at=side.clock.now(),
        finished_at=side.clock.now() if term else None,
        fencing_token=fencing_token,
        runtime_started_at=side.clock.now() if state is StageState.RUNNING else None,
        process_identities=(),
        reused_from_step_id=None,
    )
    uow.repo(StageRepository).add(rec)
    return rec


def seed_step(
    side: ExecSide,
    uow: UnitOfWork,
    attempt: Attempt,
    stage: StageRecord,
    *,
    manifest_id: ContextManifestId,
    step_id: StepId | None = None,
    seq: int = 1,
    role: RoleId = RoleId.EXECUTOR,
    state: StepState = StepState.STARTED,
    result: JsonObject | None = None,
    raw_fv_id: FileVersionId | None = None,
    transcript_fv_id: FileVersionId | None = None,
    reuse_key: str | None = None,
    route_snapshot: JsonObject | None = None,
    runtime_observation: JsonObject | None = None,
    admission: JsonObject | None = None,
) -> AttemptStep:
    sid = step_id or StepId(side.new_id())
    env_id = attempt.environment_id or EnvironmentId(side.new_id())
    fp = SessionFingerprint(
        "codex_cli",
        side.proj,
        env_id,
        role,
        attempt.id,
        DIGEST_A,
        DIGEST_B,
        RouteRef("codex_cli", "gpt-5", "high"),
        None,
    )
    step = AttemptStep(
        id=sid,
        attempt_id=attempt.id,
        stage_record_id=stage.id,
        parent_step_id=None,
        seq=seq,
        role=role,
        purpose=StepPurpose.PRIMARY,
        runtime_id="codex_cli",
        model="gpt-5",
        effort="high",
        operation="new_implementation",
        admission={"allowed": True, **(admission or {})},
        route_source="plan_route",
        route_reason="ROUTE_DEFAULT",
        context_manifest_id=manifest_id,
        session_mode="new",
        session_ref="sess-1",
        session_fingerprint=fp,
        session_fingerprint_digest=DIGEST_A,
        fresh_reason="NO_PREVIOUS_SESSION",
        state=state,
        result=result,
        raw_result_file_version_id=raw_fv_id,
        repairs=(),
        schema_errors=(),
        usage=None,
        usage_so_far=None,
        process_identity=None,
        activity={"phase": "running"},
        route_snapshot=route_snapshot,
        runtime_observation=runtime_observation,
        reuse_key=reuse_key,
        transcript_file_version_id=transcript_fv_id,
        last_progress_at=side.clock.now(),
        error_code=None,
        started_at=side.clock.now(),
        finished_at=None if state is StepState.STARTED else side.clock.now(),
    )
    uow.repo(StepRepository).add(step)
    return step


def seed_output(
    side: ExecSide,
    uow: UnitOfWork,
    attempt: Attempt,
    *,
    output_id: OutputId | None = None,
    seq: int = 1,
    source: OutputSource = OutputSource.RANGE,
    step_id: StepId | None = None,
    path: str = "src/target.py",
) -> Output:
    oid = output_id or OutputId(side.new_id())
    pbytes = base64.urlsafe_b64encode(path.encode("utf-8")).decode("ascii").rstrip("=")
    cpath = ChangedPath("repo", path, pbytes, "modified", None, None, f"100644 {COMMIT_2}")
    manifest = OutputManifest(
        algorithm=OUTPUT_ALGORITHM,
        mounts=(OutputMount("repo", side.repo_id, "sha1", COMMIT_1, COMMIT_2, TREE_1),),
        changed_paths=(cpath,),
        tree_digest=DIGEST_A,
        outside_write_scope=(),
        excluded_paths=(),
        patch_file_version_id=side.fv1,
        diff_stats=DiffStats(1, 5, 1),
        empty=False,
    )
    out = Output(
        id=oid,
        attempt_id=attempt.id,
        task_id=attempt.task_id,
        run_id=attempt.run_id,
        seq=seq,
        source=source,
        manifest=manifest,
        manifest_digest=manifest_digest(manifest),
        sealed_at=side.clock.now(),
        produced_by_step_id=step_id,
    )
    uow.repo(OutputRepository).add(out)
    return out


def record_run_event(
    side: ExecSide,
    uow: UnitOfWork,
    run_id: RunId,
    short: str,
    payload: JsonObject,
    *,
    ws: WorkspaceId | None = None,
) -> None:
    ws_id = ws or side.ws
    ev_urn = f"urn:skm:execution:event:{short}:v1"

    class _DynRunEvent(DomainEvent):
        event_type: ClassVar[str] = ev_urn
        stream_kind: ClassVar[str] = "run"

        @override
        def stream_id(self) -> UUID:
            return UUID(str(run_id))

        @override
        def scope_workspace_id(self) -> WorkspaceId | None:
            return ws_id

        @override
        def payload(self) -> JsonObject:
            return payload

    uow.record(_DynRunEvent())
