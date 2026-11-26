"""PostgreSQL row <-> domain codecs for core ``skm_execution`` aggregates (DDL ``0013``-``0014``)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Literal, cast
from uuid import UUID

from skm.adapters.postgres.execution.mapping import DictRow, process_identity_from_json, usage_from_json
from skm.kernel.ids import (
    AttemptId,
    ContextManifestId,
    EntityId,
    FileVersionId,
    HostId,
    PlanId,
    PrincipalId,
    ProjectId,
    ResourceVersionId,
    RevisionId,
    RunId,
    TaskId,
    WorkerId,
    WorkspaceId,
)
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.execution.domain.attempt import (
    AdvanceContinuation,
    Attempt,
    AttemptState,
    ContinuationCause,
    DeferredTrigger,
    EntityRef,
    PendingContinuation,
    SelectedStage,
    StageContinuation,
)
from skm.modules.execution.domain.blocking_reason import blocking_reason_from_json
from skm.modules.execution.domain.execution_bundle import (
    ExecutionBundle,
    ResourcePin,
    ResourcePins,
    RunSelection,
    SatisfiedTask,
)
from skm.modules.execution.domain.frozen_json import thaw_json
from skm.modules.execution.domain.ids import (
    DecisionRequestId,
    EnvironmentId,
    FindingId,
    FixBriefId,
    OutputId,
    ReadinessReportId,
    ReviewRequestId,
    StageRecordId,
    StepId,
)
from skm.modules.execution.domain.readiness import (
    ReadinessCheckResult,
    ReadinessFinding,
    ReadinessInputs,
    ReadinessReport,
    ReadinessScope,
    ReadinessStatus,
)
from skm.modules.execution.domain.review_grouping import ReviewGrouping
from skm.modules.execution.domain.run import PauseSource, Run, RunKind, RunStatus
from skm.modules.execution.domain.session import RouteRef, SessionFingerprint
from skm.modules.execution.domain.stage_record import StageOutcomeKind, StageRecord, StageState
from skm.modules.execution.domain.step import AttemptStep, RoleId, StepPurpose, StepState
from skm.modules.execution.domain.task import PathPattern, ReviewMode, Task, TaskKind, TaskOrigin, TaskStatus
from skm.modules.execution.domain.task_graph import EdgeKind, TaskEdge
from skm.modules.execution.domain.work_policy import work_policy_from_json
from skm.modules.execution.domain.workflow.stage_inputs import FeedbackRefs, StageMode
from skm.modules.execution.ports import ReconfigurationRecord

__all__: list[str] = []


def as_uuid(val: Any) -> UUID:
    return val if isinstance(val, UUID) else UUID(str(val))


def review_grouping_to_json(rg: ReviewGrouping) -> JsonObject:
    return {
        "mode": rg.mode,
        "groups": [[str(tid) for tid in g] for g in rg.groups],
        "reviewer_effort": rg.reviewer_effort,
        "reason": rg.reason,
    }


def review_grouping_from_json(raw: object) -> ReviewGrouping:
    d = cast("Mapping[str, Any]", raw)
    groups = tuple(tuple(TaskId(as_uuid(tid)) for tid in g) for g in d.get("groups", ()))
    return ReviewGrouping(
        mode=cast("Literal['none', 'groups']", str(d["mode"])),
        groups=groups,
        reviewer_effort=cast("Literal['medium', 'high']", str(d.get("reviewer_effort", "medium"))),
        reason=str(d.get("reason", "")),
    )


def run_from_row(r: DictRow) -> Run:
    return Run(
        id=RunId(as_uuid(r["id"])),
        workspace_id=WorkspaceId(as_uuid(r["workspace_id"])),
        project_id=ProjectId(as_uuid(r["project_id"])),
        kind=RunKind(str(r["kind"])),
        plan_id=None if r["plan_id"] is None else PlanId(as_uuid(r["plan_id"])),
        revision_id=None if r["revision_id"] is None else RevisionId(as_uuid(r["revision_id"])),
        revision_no=None if r["revision_no"] is None else int(r["revision_no"]),
        inline_spec_file_version_id=(
            None
            if r["inline_spec_file_version_id"] is None
            else FileVersionId(as_uuid(r["inline_spec_file_version_id"]))
        ),
        status=RunStatus(str(r["status"])),
        requested_by=PrincipalId(as_uuid(r["requested_by"])),
        readiness_report_id=(
            None if r["readiness_report_id"] is None else ReadinessReportId(as_uuid(r["readiness_report_id"]))
        ),
        audited_report_id=(
            None if r["audited_report_id"] is None else ReadinessReportId(as_uuid(r["audited_report_id"]))
        ),
        review_request_id=(
            None if r["review_request_id"] is None else ReviewRequestId(as_uuid(r["review_request_id"]))
        ),
        compiler_version=int(r["compiler_version"]),
        workflow_resource_version_id=ResourceVersionId(as_uuid(r["workflow_resource_version_id"])),
        review_grouping=review_grouping_from_json(r["review_grouping"]),
        autopilot=bool(r["autopilot"]),
        queued=bool(r["queued"]),
        pause_reason=r["pause_reason"],
        pause_source=cast("PauseSource | None", r["pause_source"]),
        stop_code=r["stop_code"],
        unmetered_at=r["unmetered_at"],
        row_version=int(r["row_version"]),
        created_at=r["created_at"],
        started_at=r["started_at"],
        finished_at=r["finished_at"],
    )


def bundle_from_row(r: DictRow) -> ExecutionBundle:
    pins_raw = cast("Mapping[str, Any]", r["resource_pins"])
    resources = tuple(
        ResourcePin(
            kind=str(p["kind"]),
            key=str(p["key"]),
            resource_version_id=ResourceVersionId(as_uuid(p["resource_version_id"])),
            digest=str(p["digest"]),
        )
        for p in pins_raw.get("resources", ())
    )
    packs = {str(k): as_uuid(v) for k, v in cast("Mapping[str, Any]", pins_raw.get("packs", {})).items()}
    sel_raw = r["selection"]
    sel: RunSelection | None = None
    if sel_raw is not None:
        sd = cast("Mapping[str, Any]", sel_raw)
        sel = RunSelection(
            task_keys=tuple(str(x) for x in sd.get("task_keys", ())),
            phases=tuple(str(x) for x in sd.get("phases", ())),
            stop_after=sd.get("stop_after"),
            compiled_keys=tuple(str(x) for x in sd.get("compiled_keys", ())),
            satisfied=tuple(
                SatisfiedTask(str(s["display_key"]), TaskId(as_uuid(s["source_task_id"])))
                for s in sd.get("satisfied", ())
            ),
        )
    wp_raw = r["work_policies"]
    wp = (
        None
        if wp_raw is None
        else {
            str(k): work_policy_from_json(cast("JsonObject", thaw_json(v)))
            for k, v in cast("Mapping[str, Any]", wp_raw).items()
        }
    )
    return ExecutionBundle(
        run_id=RunId(as_uuid(r["run_id"])),
        config_snapshot=cast("JsonObject", thaw_json(r["config_snapshot"])),
        config_digest=str(r["config_digest"]),
        policy_digest=str(r["policy_digest"]),
        resource_pins=ResourcePins(resources=resources, packs=packs),
        selection=sel,
        work_policies=wp,
        context_policy=cast("Mapping[str, JsonValue]", thaw_json(r["context_policy"])),
        review_grouping=review_grouping_from_json(r["review_grouping"]),
        created_at=r["created_at"],
    )


def reconfiguration_from_row(r: DictRow) -> ReconfigurationRecord:
    return ReconfigurationRecord(
        id=as_uuid(r["id"]),
        run_id=RunId(as_uuid(r["run_id"])),
        changes=cast("JsonObject", thaw_json(r["changes"])),
        reason=str(r["reason"]),
        changed_by=PrincipalId(as_uuid(r["changed_by"])),
        changed_at=r["changed_at"],
    )


def readiness_from_row(r: DictRow) -> ReadinessReport:
    sc = cast("Mapping[str, Any]", r["scope"])
    inp = cast("Mapping[str, Any]", r["inputs"])
    wp_raw = r["work_policies"]
    wp = (
        None
        if wp_raw is None
        else {
            str(k): work_policy_from_json(cast("JsonObject", thaw_json(v)))
            for k, v in cast("Mapping[str, Any]", wp_raw).items()
        }
    )
    return ReadinessReport(
        id=ReadinessReportId(as_uuid(r["id"])),
        workspace_id=WorkspaceId(as_uuid(r["workspace_id"])),
        project_id=ProjectId(as_uuid(r["project_id"])),
        plan_id=PlanId(as_uuid(r["plan_id"])),
        revision_id=RevisionId(as_uuid(r["revision_id"])),
        revision_digest=str(r["revision_digest"]),
        status=ReadinessStatus(str(r["status"])),
        scope=ReadinessScope(
            kind=cast("Literal['plan', 'phases', 'selection']", str(sc["kind"])),
            phase_keys=tuple(str(x) for x in sc.get("phase_keys", ())),
        ),
        inputs=ReadinessInputs(
            requirements=str(inp["requirements"]),
            dependencies=str(inp["dependencies"]),
            write_scopes=str(inp["write_scopes"]),
            criteria=str(inp["criteria"]),
            capability_requirements=str(inp["capability_requirements"]),
            policy=str(inp["policy"]),
            config=str(inp["config"]),
            resources=str(inp["resources"]),
            materials=str(inp["materials"]),
        ),
        inputs_digest=str(r["inputs_digest"]),
        policy_digest=str(r["policy_digest"]),
        results=tuple(
            ReadinessCheckResult(
                rule_id=str(it["rule_id"]),
                outcome=cast("Literal['passed', 'failed', 'advisory', 'skipped']", str(it["outcome"])),
                findings_count=int(it["findings_count"]),
            )
            for it in r["results"]
        ),
        findings=tuple(
            ReadinessFinding(
                code=str(f["code"]),
                severity=cast("Literal['error', 'advisory']", str(f["severity"])),
                entity_id=None if f.get("entity_id") is None else EntityId(as_uuid(f["entity_id"])),
                message=str(f["message"]),
                rule_id=str(f["rule_id"]),
            )
            for f in r["findings"]
        ),
        assumptions=tuple(str(x) for x in r["assumptions"]),
        structural_counts={
            str(k): int(v) for k, v in cast("Mapping[str, Any]", r["structural_counts"]).items()
        },
        start_request=(
            None if r["start_request"] is None else cast("JsonObject", thaw_json(r["start_request"]))
        ),
        work_policies=wp,
        estimate=cast("JsonObject", thaw_json(r["estimate"])),
        audit=None if r["audit"] is None else cast("JsonObject", thaw_json(r["audit"])),
        supersedes_report_id=(
            None
            if r["supersedes_report_id"] is None
            else ReadinessReportId(as_uuid(r["supersedes_report_id"]))
        ),
        validator_version=int(r["validator_version"]),
        created_by=PrincipalId(as_uuid(r["created_by"])),
        created_at=r["created_at"],
    )


def task_from_row(r: DictRow) -> Task:
    tid = TaskId(as_uuid(r["id"]))
    orig_raw = r["origin"]
    orig = (
        None
        if orig_raw is None
        else TaskOrigin(
            source_task_id=(
                None
                if orig_raw.get("source_task_id") is None
                else TaskId(as_uuid(orig_raw["source_task_id"]))
            ),
            finding_ids=tuple(FindingId(as_uuid(fid)) for fid in orig_raw.get("finding_ids", ())),
            reason=str(orig_raw.get("reason", "")),
        )
    )
    ws_raw = r["declared_write_scope"]
    ws = None if ws_raw is None else tuple(PathPattern(str(p["mount"]), str(p["pattern"])) for p in ws_raw)
    br = (
        None
        if r["blocking_reason"] is None
        else blocking_reason_from_json(cast("JsonObject", thaw_json(r["blocking_reason"])))
    )
    return Task(
        id=tid,
        run_id=RunId(as_uuid(r["run_id"])),
        workspace_id=WorkspaceId(as_uuid(r["workspace_id"])),
        kind=TaskKind(str(r["kind"])),
        spec_entity_id=None if r["spec_entity_id"] is None else EntityId(as_uuid(r["spec_entity_id"])),
        display_key=str(r["display_key"]),
        origin=orig,
        position=int(r["position"]),
        status=TaskStatus(str(r["status"])),
        work_kind=str(r["work_kind"]),
        review_mode=ReviewMode(str(r["review_mode"])),
        review_profile=r["review_profile"],
        declared_write_scope=ws,
        required_host_id=None if r["required_host_id"] is None else HostId(as_uuid(r["required_host_id"])),
        current_attempt_id=(
            None if r["current_attempt_id"] is None else AttemptId(as_uuid(r["current_attempt_id"]))
        ),
        accepted_attempt_id=(
            None if r["accepted_attempt_id"] is None else AttemptId(as_uuid(r["accepted_attempt_id"]))
        ),
        accepted_output_id=(
            None if r["accepted_output_id"] is None else OutputId(as_uuid(r["accepted_output_id"]))
        ),
        check_fix_rounds=int(r["check_fix_rounds"]),
        review_rounds=int(r["review_rounds"]),
        attempt_count=int(r["attempt_count"]),
        blocking_reason=br,
        row_version=int(r["row_version"]),
    )


def edge_from_row(r: DictRow) -> TaskEdge:
    return TaskEdge(
        run_id=RunId(as_uuid(r["run_id"])),
        dependent_task_id=TaskId(as_uuid(r["dependent_task_id"])),
        prerequisite_task_id=TaskId(as_uuid(r["prerequisite_task_id"])),
        kind=EdgeKind(str(r["kind"])),
        reasons=frozenset(str(x) for x in (r["reasons"] or ())),
    )


def _cause_from_json(raw: Mapping[str, Any]) -> ContinuationCause:
    return ContinuationCause(
        trigger_kind=str(raw["trigger_kind"]),
        advance_rule=raw.get("advance_rule"),
        reason_codes=tuple(str(c) for c in raw.get("reason_codes", ())),
        refs=tuple(EntityRef(str(rf["kind"]), as_uuid(rf["id"])) for rf in raw.get("refs", ())),
        command_id=raw.get("command_id"),
        source_event_id=None if raw.get("source_event_id") is None else as_uuid(raw["source_event_id"]),
    )


def continuation_from_json(raw: object) -> PendingContinuation | None:
    if raw is None:
        return None
    d = cast("Mapping[str, Any]", raw)
    if str(d["kind"]) == "advance":
        trigs = tuple(
            DeferredTrigger(as_uuid(t["source_event_id"]), _cause_from_json(t["cause"]))
            for t in d.get("triggers", ())
        )
        return AdvanceContinuation(1, as_uuid(d["continuation_id"]), "advance", trigs)
    st = cast("Mapping[str, Any]", d["stage"])
    ro_raw = st.get("route_override")
    ro = (
        None
        if ro_raw is None
        else RouteRef(str(ro_raw["runtime_id"]), str(ro_raw["model"]), ro_raw.get("effort"))
    )
    fb = cast("Mapping[str, Any]", st["feedback_refs"])
    frefs = FeedbackRefs(
        fix_brief_id=None if fb.get("fix_brief_id") is None else FixBriefId(as_uuid(fb["fix_brief_id"])),
        schema_errors_step_id=(
            None if fb.get("schema_errors_step_id") is None else StepId(as_uuid(fb["schema_errors_step_id"]))
        ),
        answer_request_ids=tuple(DecisionRequestId(as_uuid(x)) for x in fb.get("answer_request_ids", ())),
        advice_step_id=None if fb.get("advice_step_id") is None else StepId(as_uuid(fb["advice_step_id"])),
        interrupted_stage_record_id=(
            None
            if fb.get("interrupted_stage_record_id") is None
            else StageRecordId(as_uuid(fb["interrupted_stage_record_id"]))
        ),
    )
    sel = SelectedStage(
        stage_id=str(st["stage_id"]),
        stage_type=str(st["stage_type"]),
        mode=StageMode(str(st["mode"])),
        round_no=int(st["round_no"]),
        params=cast("Mapping[str, JsonValue]", thaw_json(st["params"])),
        not_before=None if st.get("not_before") is None else datetime.fromisoformat(str(st["not_before"])),
        route_override=ro,
        feedback_refs=frefs,
        input_output_id=(
            None if st.get("input_output_id") is None else OutputId(as_uuid(st["input_output_id"]))
        ),
        retry_of_id=None if st.get("retry_of_id") is None else StageRecordId(as_uuid(st["retry_of_id"])),
    )
    return StageContinuation(1, as_uuid(d["continuation_id"]), "stage", _cause_from_json(d["cause"]), sel)


def attempt_from_row(r: DictRow) -> Attempt:
    er = r["executor_route"]
    route = None if er is None else RouteRef(str(er["runtime_id"]), str(er["model"]), er.get("effort"))
    return Attempt(
        id=AttemptId(as_uuid(r["id"])),
        run_id=RunId(as_uuid(r["run_id"])),
        task_id=TaskId(as_uuid(r["task_id"])),
        workspace_id=WorkspaceId(as_uuid(r["workspace_id"])),
        attempt_no=int(r["attempt_no"]),
        state=AttemptState(str(r["state"])),
        worker_id=None if r["worker_id"] is None else WorkerId(as_uuid(r["worker_id"])),
        host_id=None if r["host_id"] is None else HostId(as_uuid(r["host_id"])),
        environment_id=None if r["environment_id"] is None else EnvironmentId(as_uuid(r["environment_id"])),
        current_output_id=None
        if r["current_output_id"] is None
        else OutputId(as_uuid(r["current_output_id"])),
        executor_route=route,
        continuation=continuation_from_json(r["continuation"]),
        started_at=r["started_at"] or r["created_at"],
        finished_at=r["finished_at"],
        end_reason=r["end_reason"],
    )


def stage_from_row(r: DictRow) -> StageRecord:
    pids = tuple(
        pi
        for raw_pi in (r["process_identities"] or ())
        if (pi := process_identity_from_json(raw_pi)) is not None
    )
    return StageRecord(
        id=StageRecordId(as_uuid(r["id"])),
        attempt_id=AttemptId(as_uuid(r["attempt_id"])),
        run_id=RunId(as_uuid(r["run_id"])),
        task_id=TaskId(as_uuid(r["task_id"])),
        seq=int(r["seq"]),
        stage_id=str(r["stage_id"]),
        stage_type=str(r["stage_type"]),
        round_no=int(r["round_no"]),
        mode=StageMode(str(r["mode"])),
        retry_of_id=None if r["retry_of_id"] is None else StageRecordId(as_uuid(r["retry_of_id"])),
        state=StageState(str(r["state"])),
        input_digest=str(r["input_digest"]),
        outcome_kind=None if r["outcome_kind"] is None else StageOutcomeKind(str(r["outcome_kind"])),
        outcome=None if r["outcome"] is None else cast("Mapping[str, JsonValue]", thaw_json(r["outcome"])),
        error_code=r["error_code"],
        started_at=r["started_at"],
        finished_at=r["finished_at"],
        fencing_token=int(r["fencing_token"]),
        runtime_started_at=r["runtime_started_at"],
        process_identities=pids,
        reused_from_step_id=(
            None if r["reused_from_step_id"] is None else StepId(as_uuid(r["reused_from_step_id"]))
        ),
    )


def step_from_row(r: DictRow) -> AttemptStep:
    sf = cast("Mapping[str, Any]", r["session_fingerprint"])
    rt = cast("Mapping[str, Any]", sf["route"])
    fp = SessionFingerprint(
        runtime_id=str(sf["runtime_id"]),
        project_id=ProjectId(as_uuid(sf["project_id"])),
        environment_id=EnvironmentId(as_uuid(sf["environment_id"])),
        role=RoleId(str(sf["role"])),
        attempt_id=AttemptId(as_uuid(sf["attempt_id"])),
        instruction_digest=str(sf["instruction_digest"]),
        authority_digest=str(sf["authority_digest"]),
        route=RouteRef(str(rt["runtime_id"]), str(rt["model"]), rt.get("effort")),
        last_validated_output_id=(
            None
            if sf.get("last_validated_output_id") is None
            else OutputId(as_uuid(sf["last_validated_output_id"]))
        ),
    )
    return AttemptStep(
        id=StepId(as_uuid(r["id"])),
        attempt_id=AttemptId(as_uuid(r["attempt_id"])),
        stage_record_id=StageRecordId(as_uuid(r["stage_record_id"])),
        parent_step_id=None if r["parent_step_id"] is None else StepId(as_uuid(r["parent_step_id"])),
        seq=int(r["seq"]),
        role=RoleId(str(r["role"])),
        purpose=StepPurpose(str(r["purpose"])),
        runtime_id=str(r["runtime_id"]),
        model=str(r["model"]),
        effort=r["effort"],
        operation=str(r["operation"]),
        admission=cast("Mapping[str, JsonValue]", thaw_json(r["admission"])),
        route_source=str(r["route_source"]),
        route_reason=str(r["route_reason"]),
        context_manifest_id=ContextManifestId(as_uuid(r["context_manifest_id"])),
        session_mode=cast("Literal['new', 'resume']", str(r["session_mode"])),
        session_ref=r["session_ref"],
        session_fingerprint=fp,
        session_fingerprint_digest=str(r["session_fingerprint_digest"]),
        fresh_reason=r["fresh_reason"],
        state=StepState(str(r["state"])),
        result=None if r["result"] is None else cast("Mapping[str, JsonValue]", thaw_json(r["result"])),
        raw_result_file_version_id=(
            None
            if r["raw_result_file_version_id"] is None
            else FileVersionId(as_uuid(r["raw_result_file_version_id"]))
        ),
        repairs=tuple(str(x) for x in (r["repairs"] or ())),
        schema_errors=tuple(cast("JsonObject", thaw_json(e)) for e in (r["schema_errors"] or ())),
        usage=usage_from_json(r["usage"]),
        usage_so_far=usage_from_json(r["usage_so_far"]),
        process_identity=process_identity_from_json(r["process_identity"]),
        activity=None if r["activity"] is None else cast("Mapping[str, JsonValue]", thaw_json(r["activity"])),
        route_snapshot=(
            None
            if r["route_snapshot"] is None
            else cast("Mapping[str, JsonValue]", thaw_json(r["route_snapshot"]))
        ),
        runtime_observation=(
            None
            if r["runtime_observation"] is None
            else cast("Mapping[str, JsonValue]", thaw_json(r["runtime_observation"]))
        ),
        reuse_key=r["reuse_key"],
        transcript_file_version_id=(
            None
            if r["transcript_file_version_id"] is None
            else FileVersionId(as_uuid(r["transcript_file_version_id"]))
        ),
        last_progress_at=r["last_progress_at"],
        error_code=r["error_code"],
        started_at=r["started_at"],
        finished_at=r["finished_at"],
    )
