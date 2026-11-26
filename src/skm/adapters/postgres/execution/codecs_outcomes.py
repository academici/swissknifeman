"""PostgreSQL row <-> domain codecs for outcome ``skm_execution`` entities (DDL ``0014``-``0016``)."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any, Literal, cast
from uuid import UUID

from skm.adapters.postgres.execution.codecs_core import as_uuid
from skm.adapters.postgres.execution.mapping import DictRow
from skm.kernel.ids import (
    AttemptId,
    EntityId,
    FileVersionId,
    HostId,
    PlanId,
    PrincipalId,
    ProjectId,
    RepositoryId,
    ResourceVersionId,
    RevisionId,
    RunId,
    TaskId,
    WorkspaceId,
)
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.execution.domain.acceptance import AcceptanceBasis, AcceptanceDecision
from skm.modules.execution.domain.autonomy import AuthorityEnvelope
from skm.modules.execution.domain.autopilot import AutopilotState, AutopilotStateKind
from skm.modules.execution.domain.budget import BudgetAccount, BudgetDimension, BudgetReservation
from skm.modules.execution.domain.carry_forward import CarryForward
from skm.modules.execution.domain.check_execution import CheckExecution, CheckKind, CheckState
from skm.modules.execution.domain.decision_record import DecisionRecord, QuestionCategory
from skm.modules.execution.domain.decision_request import (
    Audience,
    DecisionAnswer,
    DecisionKind,
    DecisionRequest,
    DecisionState,
)
from skm.modules.execution.domain.deviation import DeviationAcceptance
from skm.modules.execution.domain.external_effect import EffectKind, EffectState, ExternalEffect
from skm.modules.execution.domain.finding import Finding, FindingState, Severity
from skm.modules.execution.domain.finding_resolution import FindingResolution, ResolutionKind
from skm.modules.execution.domain.fix_brief import FixBrief, FixBriefCheck, FixBriefItem
from skm.modules.execution.domain.frozen_json import thaw_json
from skm.modules.execution.domain.ids import (
    AcceptanceDecisionId,
    BudgetReservationId,
    CarryForwardId,
    CheckExecutionId,
    DecisionAnswerId,
    DecisionRecordId,
    DecisionRequestId,
    DeviationId,
    ExternalEffectId,
    FindingId,
    FindingResolutionId,
    FixBriefId,
    IntegrationSlotId,
    ManualVerdictId,
    OutputId,
    RecoveryRecordId,
    ReviewId,
    ReviewRequestId,
    StageRecordId,
    StepId,
)
from skm.modules.execution.domain.integration import IntegrationSlot
from skm.modules.execution.domain.manual_verdict import ManualVerdict
from skm.modules.execution.domain.recovery import RecoveryRecord, RecoveryStep
from skm.modules.execution.domain.review import (
    Freshness,
    Review,
    ReviewClearance,
    ReviewerKind,
    ReviewState,
    Verdict,
)
from skm.modules.execution.domain.review_request import (
    CommitReviewTarget,
    ReviewRequest,
    WorkingTreeReviewTarget,
)

__all__: list[str] = []


def check_from_row(r: DictRow) -> CheckExecution:
    return CheckExecution(
        id=CheckExecutionId(as_uuid(r["id"])),
        workspace_id=WorkspaceId(as_uuid(r["workspace_id"])),
        run_id=RunId(as_uuid(r["run_id"])),
        task_id=TaskId(as_uuid(r["task_id"])),
        attempt_id=AttemptId(as_uuid(r["attempt_id"])),
        output_id=OutputId(as_uuid(r["output_id"])),
        check_spec_id=EntityId(as_uuid(r["check_spec_id"])),
        check_key=str(r["check_key"]),
        kind=CheckKind(str(r["kind"])),
        required=bool(r["required"]),
        state=CheckState(str(r["state"])),
        exit_code=r["exit_code"],
        summary=str(r["summary"]),
        error_code=r["error_code"],
        reused_from_id=(
            None if r["reused_from_id"] is None else CheckExecutionId(as_uuid(r["reused_from_id"]))
        ),
        fingerprint=str(r["fingerprint"]),
        started_at=r["started_at"],
        finished_at=r["finished_at"],
        round_no=int(r["round_no"]),
    )


def verdict_from_row(r: DictRow) -> ManualVerdict:
    return ManualVerdict(
        id=ManualVerdictId(as_uuid(r["id"])),
        check_execution_id=CheckExecutionId(as_uuid(r["check_execution_id"])),
        principal_id=PrincipalId(as_uuid(r["principal_id"])),
        verdict=cast("Literal['pass', 'fail']", str(r["verdict"])),
        comment=str(r["comment"]),
        recorded_at=r["recorded_at"],
        supersedes_id=None if r["supersedes_id"] is None else ManualVerdictId(as_uuid(r["supersedes_id"])),
    )


def review_from_row(r: DictRow) -> Review:
    pv = r["profile_version_id"]
    pvid = ResourceVersionId(as_uuid(pv)) if pv is not None else ResourceVersionId(UUID(int=0))
    return Review(
        id=ReviewId(as_uuid(r["id"])),
        workspace_id=WorkspaceId(as_uuid(r["workspace_id"])),
        run_id=RunId(as_uuid(r["run_id"])),
        task_id=TaskId(as_uuid(r["task_id"])),
        attempt_id=AttemptId(as_uuid(r["attempt_id"])),
        output_id=OutputId(as_uuid(r["output_id"])),
        round_no=int(r["round_no"]),
        reviewer_kind=ReviewerKind(str(r["reviewer_kind"])),
        reviewer_ref=cast("JsonObject", thaw_json(r["reviewer_ref"])),
        profile_key=str(r["profile_key"]),
        profile_version_id=pvid,
        audit_scope=cast("Literal['corrected', 'full', 'range']", str(r["audit_scope"])),
        state=ReviewState(str(r["state"])),
        verdict=None if r["verdict"] is None else Verdict(str(r["verdict"])),
        freshness=Freshness(str(r["freshness"])),
        base_output_id=None if r["base_output_id"] is None else OutputId(as_uuid(r["base_output_id"])),
        residual_risk=str(r["residual_risk"]),
        completed_at=r["completed_at"],
    )


def finding_from_row(r: DictRow) -> Finding:
    return Finding(
        id=FindingId(as_uuid(r["id"])),
        review_id=ReviewId(as_uuid(r["review_id"])),
        local_id=str(r["local_id"]),
        finding_key=str(r["finding_key"]),
        severity=Severity(str(r["severity"])),
        confidence=cast("Literal['high', 'medium', 'low']", str(r["confidence"])),
        basis=str(r["basis"]),
        category=str(r["category"]),
        message=str(r["message"]),
        failure_scenario=str(r["failure_scenario"]),
        location=cast("JsonObject", thaw_json(r["location"])),
        reproduction=(
            None if r["reproduction"] is None else cast("JsonObject", thaw_json(r["reproduction"]))
        ),
        first_seen_review_id=ReviewId(as_uuid(r["first_seen_review_id"])),
        state=FindingState(str(r["state"])),
    )


def resolution_from_row(r: DictRow) -> FindingResolution:
    rb = cast("Mapping[str, Any]", r["resolved_by"])
    actor = as_uuid(rb.get("principal_id") or rb.get("step_id") or rb.get("id"))
    return FindingResolution(
        id=FindingResolutionId(as_uuid(r["id"])),
        finding_id=FindingId(as_uuid(r["finding_id"])),
        resolution_kind=ResolutionKind(str(r["resolution_kind"])),
        target_output_id=(
            None if r["target_output_id"] is None else OutputId(as_uuid(r["target_output_id"]))
        ),
        comment=str(r["comment"]),
        resolved_by=actor,
        at=r["at"],
    )


def fix_brief_from_row(r: DictRow) -> FixBrief:
    doc = cast("Mapping[str, Any]", r["document"])
    items = tuple(
        FixBriefItem(
            finding_key=str(it["finding_key"]),
            local_id=str(it["local_id"]),
            severity=Severity(str(it["severity"])),
            category=str(it["category"]),
            location=cast("JsonObject", thaw_json(it["location"])),
            problem=str(it["problem"]),
            fix=str(it["fix"]),
            observed=str(it.get("observed", "")),
            reproduction=str(it.get("reproduction", "")),
        )
        for it in doc.get("items", ())
    )
    checks = tuple(
        FixBriefCheck(
            check_key=str(ch["check_key"]),
            exit_code=ch.get("exit_code"),
            tail=str(ch["tail"]),
            tail_bytes=int(ch["tail_bytes"]),
            full_log_file_version_id=(
                None
                if ch.get("full_log_file_version_id") is None
                else FileVersionId(as_uuid(ch["full_log_file_version_id"]))
            ),
        )
        for ch in doc.get("checks", ())
    )
    return FixBrief(
        id=FixBriefId(as_uuid(r["id"])),
        task_id=TaskId(as_uuid(r["task_id"])),
        attempt_id=AttemptId(as_uuid(r["attempt_id"])),
        source_review_id=(
            None if r["source_review_id"] is None else ReviewId(as_uuid(r["source_review_id"]))
        ),
        source_check_round=r["source_check_round"],
        items=items,
        truncated=bool(r["truncated"]),
        full_report_file_version_id=FileVersionId(as_uuid(r["full_report_file_version_id"])),
        limits=cast("JsonObject", thaw_json(doc.get("limits", {}))),
        digest=str(r["digest"]),
        checks=checks,
        deferred_finding_keys=tuple(str(x) for x in doc.get("deferred_finding_keys", ())),
    )


def acceptance_from_row(r: DictRow) -> AcceptanceDecision:
    b = cast("Mapping[str, Any]", r["basis"])
    basis = AcceptanceBasis(
        clearance=ReviewClearance(str(b["clearance"])),
        check_execution_ids=tuple(CheckExecutionId(as_uuid(x)) for x in b.get("check_execution_ids", ())),
        review_id=None if b.get("review_id") is None else ReviewId(as_uuid(b["review_id"])),
        manual_verdict_ids=tuple(ManualVerdictId(as_uuid(x)) for x in b.get("manual_verdict_ids", ())),
        deviation_ids=tuple(DeviationId(as_uuid(x)) for x in b.get("deviation_ids", ())),
        review_debt=bool(b.get("review_debt", False)),
        coverage_report=(
            None if b.get("coverage_report") is None else cast("JsonObject", thaw_json(b["coverage_report"]))
        ),
        carry_forward_id=(
            None if b.get("carry_forward_id") is None else CarryForwardId(as_uuid(b["carry_forward_id"]))
        ),
        reasons=tuple(str(x) for x in b.get("reasons", ())),
    )
    att_id = AttemptId(as_uuid(r["attempt_id"])) if r["attempt_id"] is not None else AttemptId(UUID(int=0))
    return AcceptanceDecision(
        id=AcceptanceDecisionId(as_uuid(r["id"])),
        workspace_id=WorkspaceId(as_uuid(r["workspace_id"])),
        run_id=RunId(as_uuid(r["run_id"])),
        task_id=TaskId(as_uuid(r["task_id"])),
        attempt_id=att_id,
        output_id=None if r["output_id"] is None else OutputId(as_uuid(r["output_id"])),
        decision=cast("Literal['accepted', 'rejected']", str(r["decision"])),
        actor_id=PrincipalId(as_uuid(r["actor_id"])),
        basis=basis,
        decided_at=r["decided_at"],
    )


def deviation_from_row(r: DictRow) -> DeviationAcceptance:
    return DeviationAcceptance(
        id=DeviationId(as_uuid(r["id"])),
        run_id=RunId(as_uuid(r["run_id"])),
        task_id=TaskId(as_uuid(r["task_id"])),
        criterion_id=None if r["criterion_id"] is None else EntityId(as_uuid(r["criterion_id"])),
        finding_id=None if r["finding_id"] is None else FindingId(as_uuid(r["finding_id"])),
        reason=str(r["reason"]),
        approved_by=PrincipalId(as_uuid(r["approved_by"])),
        approved_at=r["approved_at"],
        scope=cast("Literal['criterion', 'finding', 'attention_verdict', 'coverage']", str(r["scope"])),
    )


def carry_forward_from_row(r: DictRow) -> CarryForward:
    return CarryForward(
        id=CarryForwardId(as_uuid(r["id"])),
        source_run_id=RunId(as_uuid(r["source_run_id"])),
        source_task_id=TaskId(as_uuid(r["source_task_id"])),
        source_attempt_id=AttemptId(as_uuid(r["source_attempt_id"])),
        source_output_id=OutputId(as_uuid(r["source_output_id"])),
        target_run_id=RunId(as_uuid(r["target_run_id"])),
        target_task_id=TaskId(as_uuid(r["target_task_id"])),
        compatibility_digest=str(r["compatibility_digest"]),
        compatibility_inputs=cast("JsonObject", thaw_json(r["compatibility_inputs"])),
        decision=cast("Literal['accepted', 'rejected']", str(r["decision"])),
        approved_by=PrincipalId(as_uuid(r["approved_by"])),
        reason=str(r["reason"]),
        created_at=r["created_at"],
    )


def budget_account_from_row(r: DictRow) -> BudgetAccount:
    return BudgetAccount(
        id=as_uuid(r["id"]),
        run_id=RunId(as_uuid(r["run_id"])),
        scope=cast("Literal['run', 'task']", str(r["scope"])),
        task_id=None if r["task_id"] is None else TaskId(as_uuid(r["task_id"])),
        dimension=BudgetDimension(str(r["dimension"])),
        limit_value=None if r["limit_value"] is None else Decimal(str(r["limit_value"])),
        spent=Decimal(str(r["spent"])),
        reserved=Decimal(str(r["reserved"])),
        row_version=int(r["row_version"]),
    )


def budget_reservation_from_row(r: DictRow) -> BudgetReservation:
    return BudgetReservation(
        id=BudgetReservationId(as_uuid(r["id"])),
        account_ids=tuple(as_uuid(x) for x in r["account_ids"]),
        dimension=BudgetDimension(str(r["dimension"])),
        step_id=None if r["step_id"] is None else StepId(as_uuid(r["step_id"])),
        amount=Decimal(str(r["amount"])),
        state=cast("Literal['reserved', 'settled', 'released']", str(r["state"])),
        settled_amount=None if r["settled_amount"] is None else Decimal(str(r["settled_amount"])),
        created_at=r["created_at"],
        settled_at=r["settled_at"],
    )


def decision_request_from_row(r: DictRow) -> DecisionRequest:
    pl = cast("dict[str, JsonValue]", thaw_json(r["payload"]))
    clean_pl = {k: v for k, v in pl.items() if k != "_binding_output_id"}
    binding: dict[str, JsonValue] = {}
    if r["input_part_digest"] is not None:
        binding["input_part_digest"] = str(r["input_part_digest"])
    if r["attempt_id"] is not None:
        binding["attempt_id"] = str(r["attempt_id"])
    if r["stage_record_id"] is not None:
        binding["stage_record_id"] = str(r["stage_record_id"])
    if isinstance(oid := pl.get("_binding_output_id"), str):
        binding["output_id"] = oid
    ans = r.get("answer_id")
    return DecisionRequest(
        id=DecisionRequestId(as_uuid(r["id"])),
        workspace_id=WorkspaceId(as_uuid(r["workspace_id"])),
        run_id=RunId(as_uuid(r["run_id"])),
        task_id=None if r["task_id"] is None else TaskId(as_uuid(r["task_id"])),
        kind=DecisionKind(str(r["kind"])),
        audience=Audience(str(r["audience"])),
        category=None if r["category"] is None else QuestionCategory(str(r["category"])),
        gate_categories=frozenset(str(x) for x in (r["gate_categories"] or ())),
        question_key=r["question_key"],
        question_digest=(
            None if r["question_digest"] is None else str(r["question_digest"]).removeprefix("sha256:")
        ),
        revision=int(r["revision"]),
        payload=clean_pl,
        asked_by_step_id=None if r["asked_by_step_id"] is None else StepId(as_uuid(r["asked_by_step_id"])),
        binding=binding,
        state=DecisionState(str(r["state"])),
        stale_answer=thaw_json(r["stale_answer"]),
        deadline_at=r["deadline_at"],
        created_at=r["created_at"],
        answer_id=None if ans is None else DecisionAnswerId(as_uuid(ans)),
    )


def decision_answer_from_row(r: DictRow) -> DecisionAnswer:
    by: dict[str, JsonValue] = {"kind": str(r["answered_by_kind"])}
    if r["answered_by_principal_id"] is not None:
        by["principal_id"] = str(r["answered_by_principal_id"])
    if r["answered_by_step_id"] is not None:
        by["step_id"] = str(r["answered_by_step_id"])
    auth = cast("Mapping[str, Any]", r["authority"])
    return DecisionAnswer(
        id=DecisionAnswerId(as_uuid(r["id"])),
        request_id=DecisionRequestId(as_uuid(r["request_id"])),
        answered_by=by,
        value=thaw_json(r["value"]),
        authority=AuthorityEnvelope(
            mode=str(auth["mode"]),
            gate_categories=tuple(str(x) for x in auth.get("gate_categories", ())),
            confidence=auth.get("confidence"),
        ),
        answered_at=r["answered_at"],
    )


def decision_record_from_row(r: DictRow) -> DecisionRecord:
    return DecisionRecord(
        id=DecisionRecordId(as_uuid(r["id"])),
        workspace_id=WorkspaceId(as_uuid(r["workspace_id"])),
        project_id=ProjectId(as_uuid(r["project_id"])),
        run_id=RunId(as_uuid(r["run_id"])),
        task_id=TaskId(as_uuid(r["task_id"])),
        request_id=DecisionRequestId(as_uuid(r["request_id"])),
        category=QuestionCategory(str(r["category"])),
        gate_categories=tuple(str(x) for x in (r["gate_categories"] or ())),
        authority=cast("Literal['owner', 'advisor', 'consilium']", str(r["authority"])),
        status=cast("Literal['applied', 'superseded']", str(r["status"])),
        selected_option=r["selected_option"],
        value=thaw_json(r["value"]),
        rationale=str(r["rationale"]),
        evidence_refs=tuple(str(x) for x in (r["evidence_refs"] or ())),
        assumptions=tuple(str(x) for x in (r["assumptions"] or ())),
        requires_owner=bool(r["requires_owner"]),
        question_key=str(r["question_key"]),
        question_input_digest=str(r["question_input_digest"]),
        created_at=r["created_at"],
    )


def effect_from_row(r: DictRow) -> ExternalEffect:
    return ExternalEffect(
        id=ExternalEffectId(as_uuid(r["id"])),
        workspace_id=WorkspaceId(as_uuid(r["workspace_id"])),
        run_id=RunId(as_uuid(r["run_id"])),
        attempt_id=AttemptId(as_uuid(r["attempt_id"])),
        task_id=TaskId(as_uuid(r["task_id"])),
        kind=EffectKind(str(r["kind"])),
        intent_id=None if r["intent_id"] is None else as_uuid(r["intent_id"]),
        request_digest=str(r["request_digest"]),
        request=cast("JsonObject", thaw_json(r["request"])),
        state=EffectState(str(r["state"])),
        receipt=None if r["receipt"] is None else cast("JsonObject", thaw_json(r["receipt"])),
        created_at=r["created_at"],
        updated_at=r["updated_at"],
    )


def slot_from_row(r: DictRow) -> IntegrationSlot:
    return IntegrationSlot(
        id=IntegrationSlotId(as_uuid(r["id"])),
        workspace_id=WorkspaceId(as_uuid(r["workspace_id"])),
        repository_id=RepositoryId(as_uuid(r["repository_id"])),
        target_branch=str(r["target_branch"]),
        holder_attempt_id=(
            None if r["holder_attempt_id"] is None else AttemptId(as_uuid(r["holder_attempt_id"]))
        ),
        fencing_token=int(r["fencing_token"]),
        expires_at=r["expires_at"],
        writer_host_id=HostId(as_uuid(r["writer_host_id"])),
        row_version=int(r["row_version"]),
    )


def review_request_from_row(r: DictRow) -> ReviewRequest:
    tgt = (
        CommitReviewTarget("commits", str(r["base_commit"]), str(r["head_commit"]))
        if r["target_kind"] == "commits"
        else WorkingTreeReviewTarget(
            "working_tree", str(r["base_commit"]), FileVersionId(as_uuid(r["patch_file_version_id"]))
        )
    )
    return ReviewRequest(
        id=ReviewRequestId(as_uuid(r["id"])),
        workspace_id=WorkspaceId(as_uuid(r["workspace_id"])),
        project_id=ProjectId(as_uuid(r["project_id"])),
        mount=str(r["mount"]),
        repository_id=RepositoryId(as_uuid(r["repository_id"])),
        target=tgt,
        profile_key=str(r["profile_key"]),
        reason=str(r["reason"]),
        requested_by=PrincipalId(as_uuid(r["requested_by"])),
        plan_id=PlanId(as_uuid(r["plan_id"])),
        revision_id=RevisionId(as_uuid(r["revision_id"])),
        created_at=r["created_at"],
    )


def autopilot_from_row(r: DictRow) -> AutopilotState:
    return AutopilotState(
        project_id=ProjectId(as_uuid(r["project_id"])),
        workspace_id=WorkspaceId(as_uuid(r["workspace_id"])),
        state=AutopilotStateKind(str(r["state"])),
        emergency=bool(r["emergency"]),
        current_run_id=None if r["current_run_id"] is None else RunId(as_uuid(r["current_run_id"])),
        session_started_at=r["session_started_at"],
        counters=cast("JsonObject", thaw_json(r["counters"])),
        session_limits=cast("JsonObject", thaw_json(r["session_limits"])),
        stop_code=r["stop_code"],
        stop_detail=r["stop_detail"],
        updated_by=PrincipalId(as_uuid(r["updated_by"])),
        updated_at=r["updated_at"],
        row_version=int(r["row_version"]),
    )


def recovery_from_row(r: DictRow) -> RecoveryRecord:
    raw_steps = cast("list[Any] | tuple[Any, ...]", r["steps_done"] or ())
    steps = tuple(
        RecoveryStep(str(cast("Mapping[str, Any]", x)["step"] if isinstance(x, Mapping) else x))
        for x in raw_steps
    )
    return RecoveryRecord(
        id=RecoveryRecordId(as_uuid(r["id"])),
        run_id=RunId(as_uuid(r["run_id"])),
        task_id=TaskId(as_uuid(r["task_id"])),
        attempt_id=AttemptId(as_uuid(r["attempt_id"])),
        stage_record_id=StageRecordId(as_uuid(r["stage_record_id"])),
        step_id=None if r["step_id"] is None else StepId(as_uuid(r["step_id"])),
        trigger=cast("Literal['hung', 'suspected_stall', 'orphaned', 'lease_expired']", str(r["trigger"])),
        steps_done=steps,
        snapshot_file_version_id=(
            None
            if r["snapshot_file_version_id"] is None
            else FileVersionId(as_uuid(r["snapshot_file_version_id"]))
        ),
        outcome=cast(
            "Literal['retried', 'new_attempt', 'escalated', 'not_needed'] | None",
            r["outcome"],
        ),
        reason_codes=tuple(str(x) for x in (r["reason_codes"] or ())),
        at=r["at"],
    )
