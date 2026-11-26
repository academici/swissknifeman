"""Server-owned check/review preparation and result facts for worker stages."""

from dataclasses import replace
from typing import Any
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.ids import ResourceVersionId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.execution.application._events import cause, emit
from skm.modules.execution.application._worker_dtos import digest, document
from skm.modules.execution.application._worker_result import resolve_review_findings
from skm.modules.execution.application.stages.gate_facts import check_definitions
from skm.modules.execution.domain.check_execution import (
    CheckExecution,
    CheckKind,
    CheckState,
    check_summary,
)
from skm.modules.execution.domain.finding import (
    Finding,
    FindingState,
    Severity,
    finding_key,
    logical_findings,
)
from skm.modules.execution.domain.ids import CheckExecutionId
from skm.modules.execution.domain.review import Freshness, Review, ReviewerKind, ReviewState, Verdict
from skm.modules.execution.ports import (
    CheckRepository,
    EvidenceBindingRepository,
    OutputRepository,
    ReviewRepository,
    RunRepository,
    StageRepository,
    TaskRepository,
)
from skm.platform.logging.redaction import Redactor


def check_round(uow: UnitOfWork, stage: Any) -> int:
    """Check rounds belong to the attempt, including a distinct integration recheck stage."""
    return 1 + sum(
        entry.record.stage_type == "run_checks" and entry.record.seq < stage.seq
        for entry in uow.repo(StageRepository).history(stage.attempt_id).entries
    )


def prepare_checks(uow: UnitOfWork, ctx: Any, fenced: Any, stage: Any, selected: Any) -> list[Any]:
    output = uow.repo(OutputRepository).latest(fenced.attempt.id)
    if output is None:
        raise error_for(ErrorCode.INVALID_TRANSITION, "checks require a sealed output")

    definitions = check_definitions(uow, fenced.run, fenced.task)
    if selected.params.get("scope") == "rerun_after_integration":
        definitions = tuple(check for check in definitions if check.rerun_after_integration)
    round_no = check_round(uow, stage)
    records: list[Any] = []
    payloads: list[Any] = []
    for definition in definitions:
        kind = CheckKind(definition.kind.value)
        fingerprint = digest(
            {
                "output_tree": output.manifest.tree_digest,
                "unproven_environment_stage": str(stage.id),
                "spec": document(definition),
                "scope": selected.params.get("scope"),
            }
        )
        record = CheckExecution(
            ctx.ids.new_id(),
            fenced.run.workspace_id,
            fenced.run.id,
            fenced.task.id,
            fenced.attempt.id,
            output.id,
            definition.id,
            f"{definition.owner}:{definition.key}",
            kind,
            definition.required,
            CheckState.PENDING,
            None,
            "",
            None,
            None,
            fingerprint,
            None,
            None,
            round_no,
        )
        records.append(record)
        payloads.append(
            {
                "check_execution_id": str(record.id),
                "check_spec_id": str(definition.id),
                "kind": definition.kind.value,
                "definition": document(definition.definition),
                "output_limits": {"capture_max_bytes": ctx.config.get("checks.capture.max_bytes")},
                "reused": False,
            }
        )
    uow.repo(CheckRepository).add_many(records)
    return payloads


def record_checks(uow: UnitOfWork, fenced: Any, stage: Any, outcome: Any) -> None:
    output = uow.repo(OutputRepository).latest(fenced.attempt.id)
    if output is None:
        raise error_for(ErrorCode.INVALID_TRANSITION, "check result requires an output")
    repo = uow.repo(CheckRepository)
    round_no = check_round(uow, stage)
    expected = {
        c.id: c
        for c in repo.for_output(output.id)
        if c.attempt_id == fenced.attempt.id and c.round_no == round_no
    }
    run = uow.repo(RunRepository).get(stage.run_id)
    task = uow.repo(TaskRepository).get(stage.task_id)
    expected_exits = {
        check.id: getattr(check.definition, "expected_exit", 0) for check in check_definitions(uow, run, task)
    }
    seen: set[Any] = set()
    for raw in outcome.get("results", ()):
        check_id = CheckExecutionId(UUID(raw["check_execution_id"]))
        if check_id not in expected or check_id in seen:
            raise error_for(ErrorCode.INVALID_REFERENCE, "check result target is foreign or duplicate")
        seen.add(check_id)
        check = expected[check_id]
        if str(check.check_spec_id) != raw["check_spec_id"]:
            raise error_for(
                ErrorCode.INVALID_REFERENCE, "check specification does not match the prepared check"
            )
        requested = CheckState(raw["state"])
        exit_code = raw.get("exit_code")
        code = None
        if outcome.get("tree_changed"):
            state, code = CheckState.UNKNOWN, "CHECK_TREE_CHANGED"
        elif requested in {CheckState.UNKNOWN, CheckState.CANCELLED}:
            state = requested
        elif check.kind is CheckKind.MANUAL:
            if requested is not CheckState.MANUAL_PENDING or exit_code is not None:
                raise error_for(ErrorCode.RESULT_INVALID, "manual check requires a human verdict")
            state, code = CheckState.MANUAL_PENDING, ErrorCode.MANUAL_PENDING
        elif exit_code is not None and exit_code < 0:
            state, code = CheckState.ERROR, ErrorCode.CHECK_KILLED
        elif requested is CheckState.ERROR:
            state = CheckState.ERROR
            supported = {
                "CHECK_TIMEOUT",
                "CHECK_COMMAND_NOT_FOUND",
                "CHECK_KILLED",
                "CHECK_MISCONFIGURED",
                "SANDBOX_UNAVAILABLE",
                "CAPABILITY_UNAVAILABLE",
                "RUNTIME_CRASHED",
            }
            prefix = str(raw.get("summary", "")).partition(":")[0]
            reported = prefix if prefix in supported else outcome.get("error_code")
            code = reported if reported in supported else ErrorCode.RUNTIME_CRASHED
        elif requested is CheckState.PASSED and exit_code == expected_exits.get(check.check_spec_id, 0):
            state = CheckState.PASSED
        elif (
            requested is CheckState.FAILED
            and exit_code is not None
            and exit_code != expected_exits.get(check.check_spec_id, 0)
        ):
            state = CheckState.FAILED
        else:
            raise error_for(ErrorCode.RESULT_INVALID, "check state contradicts its execution facts")
        repo.save(
            replace(
                check,
                state=state,
                error_code=code,
                exit_code=raw.get("exit_code"),
                summary=check_summary(Redactor().text(str(raw.get("summary", "")))),
                started_at=stage.started_at,
                finished_at=fenced.now,
            )
        )
    if any(c.required and c.state is CheckState.PENDING and c.id not in seen for c in expected.values()):
        raise error_for(ErrorCode.RESULT_INVALID, "required check result is missing")


def prepare_review(uow: UnitOfWork, ctx: Any, fenced: Any, _stage: Any, step: Any, selected: Any) -> Any:
    output = uow.repo(OutputRepository).latest(fenced.attempt.id)
    if output is None:
        raise error_for(ErrorCode.INVALID_TRANSITION, "review requires a sealed output")
    previous = uow.repo(ReviewRepository).for_task(fenced.task.id)
    base = previous[-1].output_id if previous else None
    snapshot = step.route_snapshot
    review = Review(
        ctx.ids.new_id(),
        fenced.run.workspace_id,
        fenced.run.id,
        fenced.task.id,
        fenced.attempt.id,
        output.id,
        len(previous) + 1,
        ReviewerKind.AGENT,
        {"step_id": str(step.id), "runtime_id": step.runtime_id, "model": step.model},
        str(step.admission.get("profile_key") or selected.params.get("profile") or "reviewer"),
        ResourceVersionId(UUID(snapshot["profile_version_id"])),
        selected.params.get("audit_scope", "full"),
        ReviewState.STARTED,
        None,
        Freshness.FRESH,
        base,
        "",
        None,
    )
    uow.repo(ReviewRepository).add(review)
    return review_payload(review, step)


def review_payload(review: Review, step: Any) -> JsonObject:
    return {
        "review_id": str(review.id),
        "round_no": review.round_no,
        "profile_key": review.profile_key,
        "audit_scope": review.audit_scope,
        "base_output_id": None if review.base_output_id is None else str(review.base_output_id),
        "reviewer_with_fix": step.admission.get("reviewer_with_fix") is True,
    }


def resume_review(uow: UnitOfWork, fenced: Any, step: Any) -> JsonObject:
    review = next(
        (
            r
            for r in uow.repo(ReviewRepository).for_task(fenced.task.id)
            if r.attempt_id == fenced.attempt.id and r.reviewer_ref.get("step_id") == str(step.id)
        ),
        None,
    )
    if review is None:
        raise error_for(ErrorCode.INVALID_REFERENCE, "review stage has no bound review")
    return review_payload(review, step)


def record_review(uow: UnitOfWork, ctx: Any, fenced: Any, outcome: Any, role_result: Any) -> None:
    repo = uow.repo(ReviewRepository)
    review = next((r for r in repo.for_task(fenced.task.id) if str(r.id) == outcome.get("review_id")), None)
    if (
        review is None
        or review.attempt_id != fenced.attempt.id
        or review.state is not ReviewState.STARTED
        or review.reviewer_ref.get("step_id") != outcome.get("step_id")
    ):
        raise error_for(ErrorCode.INVALID_REFERENCE, "review result does not name this active review")
    current = fenced.attempt.current_output_id
    if outcome.get("output_id") is None:
        if review.output_id != current:
            raise error_for(ErrorCode.INVALID_REFERENCE, "review output changed without a reported fix")
    else:
        if current is None:
            raise error_for(ErrorCode.INVALID_REFERENCE, "review fix requires a current output")
        fixed = uow.repo(OutputRepository).get(current)
        if (
            str(fixed.id) != outcome["output_id"]
            or str(fixed.produced_by_step_id) != outcome.get("step_id")
            or fixed.seq != uow.repo(OutputRepository).get(review.output_id).seq + 1
        ):
            raise error_for(ErrorCode.INVALID_REFERENCE, "review fix must name its newly sealed output")
    verdict = Verdict(role_result["verdict"])
    review = replace(
        review,
        state=ReviewState.COMPLETED,
        verdict=verdict,
        completed_at=fenced.now,
        residual_risk=str(role_result.get("residual_risk", "")),
    )
    repo.save(review)
    old = {
        f.finding_key: f
        for f in logical_findings(
            repo.findings_for_task(fenced.task.id), {r.id: r.round_no for r in repo.for_task(fenced.task.id)}
        )
    }
    findings: list[Any] = []
    for raw in role_result.get("findings", ()):
        location = raw["location"]
        key = finding_key(location, raw["category"], raw["failure_scenario"], raw["message"])
        previous = old.get(key)
        findings.append(
            Finding(
                ctx.ids.new_id(),
                review.id,
                raw["id"],
                key,
                Severity(raw["severity"]),
                raw.get("confidence", "medium"),
                raw.get("basis", ""),
                raw["category"],
                raw["message"],
                raw["failure_scenario"],
                location,
                raw.get("reproduction"),
                review.id if previous is None else previous.first_seen_review_id,
                previous.state
                if previous is not None
                and previous.state in {FindingState.OPEN, FindingState.CONFIRMED, FindingState.DEFERRED}
                else FindingState.OPEN,
            )
        )
    repo.add_findings(findings)

    resolve_review_findings(uow, ctx, fenced, review, old, {finding.finding_key for finding in findings})
    task = uow.repo(TaskRepository).get(fenced.task.id)
    uow.repo(TaskRepository).save(
        replace(
            task, review_rounds=max(task.review_rounds, review.round_no), row_version=task.row_version + 1
        ),
        expected_version=task.row_version,
    )
    emit(
        uow,
        fenced.run,
        "review-completed",
        {
            "review_id": str(review.id),
            "task_id": str(fenced.task.id),
            "reviewer_step_id": outcome.get("step_id"),
            "base_output_id": None if review.base_output_id is None else str(review.base_output_id),
            "profile_key": review.profile_key,
            "output_id": str(review.output_id),
            "verdict": verdict.value,
            "round_no": review.round_no,
            "finding_counts": {s.value: sum(f.severity is s for f in findings) for s in Severity},
            "new_finding_keys": [f.finding_key for f in findings if f.finding_key not in old],
            "evidence_refs": [
                {"file_version_id": str(v), "role": role.value}
                for v, role in uow.repo(EvidenceBindingRepository).for_owner("review", review.id)
            ],
        },
        cause("review_findings"),
    )
