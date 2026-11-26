"""Pure range gate invariants GA1-GA6 and revision coverage PA1-PA2 (§5.18)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Literal

from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.execution.domain.acceptance import (
    AcceptanceBasis,
    AcceptanceDecision,
    AcceptanceReason,
    Accepted,
    NotAcceptable,
)
from skm.modules.execution.domain.check_execution import CheckKind, CheckState
from skm.modules.execution.domain.finding import FindingState, Severity, logical_findings
from skm.modules.execution.domain.output import OutputSource
from skm.modules.execution.domain.review import ReviewClearance, ReviewState, Verdict
from skm.modules.execution.domain.task import TaskKind, TaskStatus

if TYPE_CHECKING:
    from skm.kernel.ids import EntityId, TaskId
    from skm.modules.execution.domain.check_execution import CheckExecution
    from skm.modules.execution.domain.deviation import DeviationAcceptance
    from skm.modules.execution.domain.finding import Finding
    from skm.modules.execution.domain.ids import CheckExecutionId, ManualVerdictId
    from skm.modules.execution.domain.manual_verdict import ManualVerdict
    from skm.modules.execution.domain.output import Output
    from skm.modules.execution.domain.review import Review
    from skm.modules.execution.domain.task import Task


@dataclass(frozen=True, slots=True)
class GateInputs:
    task: Task
    members: Sequence[Task]
    output: Output | None
    checks: Sequence[CheckExecution]
    manual: Mapping[CheckExecutionId, ManualVerdict]
    reviews: Sequence[Review]
    findings: Sequence[Finding]
    deviations: Sequence[DeviationAcceptance]
    policy_live_ok: bool
    required_checks: frozenset[EntityId] = frozenset()
    skipped_with_decision: frozenset[TaskId] = frozenset()
    followups: Sequence[Task] = ()
    clearance: ReviewClearance | None = None
    empty_allowed: bool = False


def member_done(task: Task, skipped_with_decision: frozenset[TaskId]) -> bool:
    return task.status is TaskStatus.ACCEPTED or (
        task.status is TaskStatus.SKIPPED and task.id in skipped_with_decision
    )


def decide_gate(  # noqa: PLR0913 -- GA1-GA6 owner signature, execution §5.18
    task: Task | GateInputs,
    members: Sequence[Task] = (),
    output: Output | None = None,
    checks: Sequence[CheckExecution] = (),
    manual: Mapping[CheckExecutionId, ManualVerdict] | None = None,
    reviews: Sequence[Review] = (),
    findings: Sequence[Finding] = (),
    deviations: Sequence[DeviationAcceptance] = (),
    policy_live_ok: bool = False,
    *,
    required_checks: frozenset[EntityId] = frozenset(),
    skipped_with_decision: frozenset[TaskId] = frozenset(),
    followups: Sequence[Task] = (),
    clearance: ReviewClearance | None = None,
) -> Accepted | NotAcceptable:
    """The owner signature, also accepting the explicit GateInputs value used by control-plane loaders."""
    inputs = (
        task
        if isinstance(task, GateInputs)
        else GateInputs(
            task,
            members,
            output,
            checks,
            manual or {},
            reviews,
            findings,
            deviations,
            policy_live_ok,
            required_checks,
            skipped_with_decision,
            followups,
            clearance,
        )
    )
    return _decide_gate(inputs)


def _decide_gate(inputs: GateInputs) -> Accepted | NotAcceptable:
    """Only facts about this gate's current range count; all unmet invariants are returned."""
    task, output = inputs.task, inputs.output
    reasons: list[AcceptanceReason] = []
    undone: list[JsonValue] = [
        str(t.id)
        for t in inputs.members
        if t.run_id != task.run_id
        or t.workspace_id != task.workspace_id
        or not member_done(t, inputs.skipped_with_decision)
    ]
    if undone:
        reasons.append(AcceptanceReason("MEMBER_NOT_DONE", {"task_ids": undone}))
    bound = (
        []
        if output is None
        else [
            c
            for c in inputs.checks
            if (c.run_id, c.task_id, c.attempt_id, c.output_id)
            == (task.run_id, task.id, task.current_attempt_id, output.id)
        ]
    )
    if not inputs.empty_allowed and (
        output is None
        or output.source is not OutputSource.RANGE
        or (output.task_id, output.run_id, output.attempt_id)
        != (task.id, task.run_id, task.current_attempt_id)
    ):
        reasons.append(AcceptanceReason("OUTPUT_NOT_CURRENT", {}))
    passed, verdicts = _checks(reasons, bound, inputs.manual, inputs.required_checks)
    reviews = [
        r
        for r in inputs.reviews
        if output is not None
        and (r.task_id, r.run_id, r.attempt_id, r.output_id)
        == (task.id, task.run_id, task.current_attempt_id, output.id)
        and r.state is ReviewState.COMPLETED
        and r.audit_scope == "range"
        and (task.review_profile is None or r.profile_key == task.review_profile)
    ]
    latest = max(reviews, key=lambda r: r.round_no, default=None)
    deviations = [d for d in inputs.deviations if d.run_id == task.run_id and d.task_id == task.id]
    clearance = inputs.clearance or (
        ReviewClearance.GREEN if latest and latest.verdict is Verdict.GREEN else ReviewClearance.WAIVED
    )
    if task.review_mode == "required":
        if latest is None:
            reasons.append(AcceptanceReason("REVIEW_MISSING", {}))
        elif (
            clearance
            not in {ReviewClearance.GREEN, ReviewClearance.CLEARED_BY_TRIAGE, ReviewClearance.DEVIATION}
            or (clearance is ReviewClearance.GREEN and latest.verdict is not Verdict.GREEN)
            or (clearance is ReviewClearance.DEVIATION and not deviations)
        ):
            reasons.append(AcceptanceReason("REVIEW_NOT_GREEN", {"review_id": str(latest.id)}))
    waived = {d.finding_id for d in deviations if d.scope == "finding"}
    findings = logical_findings(inputs.findings, {r.id: r.round_no for r in inputs.reviews})
    blockers: list[JsonValue] = []
    for finding in findings:
        if (
            finding.severity not in {Severity.BLOCKER, Severity.MAJOR}
            or finding.state is not FindingState.CONFIRMED
        ):
            continue
        fixes = [
            t
            for t in inputs.followups
            if t.origin
            and finding.id in t.origin.finding_ids
            and t.origin.source_task_id == task.id
            and t.run_id == task.run_id
        ]
        if finding.id not in waived and not (
            fixes and all(member_done(t, inputs.skipped_with_decision) for t in fixes)
        ):
            blockers.append(str(finding.id))
    if blockers:
        reasons.append(AcceptanceReason("BLOCKER_OPEN", {"finding_ids": blockers}))
    if not inputs.policy_live_ok:
        reasons.append(AcceptanceReason("POLICY_DENIES", {}))
    if reasons:
        return NotAcceptable(tuple(reasons))
    return Accepted(
        clearance,
        AcceptanceBasis(
            clearance,
            tuple(passed),
            None if latest is None else latest.id,
            tuple(verdicts),
            tuple(d.id for d in deviations),
            False,
            None,
            None,
            (),
        ),
    )


@dataclass(frozen=True, slots=True)
class RequirementCoverage:
    key: str
    items: tuple[str, ...]
    status: Literal["covered", "uncovered"]


@dataclass(frozen=True, slots=True)
class CriterionCoverage:
    key: str
    owner_task: str
    evidence: Literal["check", "review", "deviation", "none"]


@dataclass(frozen=True, slots=True)
class CoverageReport:
    requirements: tuple[RequirementCoverage, ...]
    criteria: tuple[CriterionCoverage, ...]
    counts: Mapping[str, int]
    diagnostics: tuple[str, ...] = field(default=())

    def to_json(self) -> JsonObject:
        return {
            "requirements": [
                {"key": r.key, "items": list(r.items), "status": r.status} for r in self.requirements
            ],
            "criteria": [
                {"key": c.key, "owner_task": c.owner_task, "evidence": c.evidence} for c in self.criteria
            ],
            "counts": dict(self.counts),
        }


def decide_plan_acceptance(
    gate_inputs: GateInputs,
    spec: Mapping[str, Any],
    tasks: Sequence[Task],
    acceptances: Sequence[AcceptanceDecision],
    coverage_mode: Literal["required", "advisory"],
    *,
    checks: Sequence[CheckExecution] = (),
    deviations: Sequence[DeviationAcceptance] = (),
) -> tuple[Accepted | NotAcceptable, CoverageReport]:
    """The application supplies the frozen revision document through the planning facade."""
    gate = replace(gate_inputs, members=tuple(t for t in tasks if t.id != gate_inputs.task.id))
    result = decide_gate(gate)
    by_key = {t.display_key: t for t in tasks if t.run_id == gate.task.run_id}
    criteria = tuple(
        _criterion(c, by_key, acceptances, checks, deviations, gate) for c in spec.get("criteria", ())
    )
    requirements: list[RequirementCoverage] = []
    for requirement in spec.get("requirements", ()):
        key = requirement["key"]
        items = tuple(
            item["key"]
            for item in spec.get("items", ())
            if key in item.get("implements", ()) and _item_accepted(item["key"], by_key)
        )
        requirements.append(RequirementCoverage(key, items, "covered" if items else "uncovered"))
    counts = {
        "requirements": len(requirements),
        "covered": sum(r.status == "covered" for r in requirements),
        "criteria": len(criteria),
        "verified": sum(c.evidence != "none" for c in criteria),
    }
    gaps = tuple(
        [
            AcceptanceReason("CRITERION_UNVERIFIED", {"criterion_key": c.key})
            for c in criteria
            if c.evidence == "none"
        ]
        + [
            AcceptanceReason("REQUIREMENT_UNCOVERED", {"requirement_key": r.key})
            for r in requirements
            if r.status == "uncovered"
        ]
    )
    report = CoverageReport(
        tuple(requirements),
        criteria,
        counts,
        ("COVERAGE_GAP",) if gaps and coverage_mode == "advisory" else (),
    )
    reasons = (() if isinstance(result, Accepted) else result.reasons) + (
        gaps if coverage_mode == "required" else ()
    )
    if reasons:
        return NotAcceptable(reasons), report
    if not isinstance(result, Accepted):
        return result, report
    return replace(result, basis=replace(result.basis, coverage_report=report.to_json())), report


def _owner(key: str, by_key: Mapping[str, Task]) -> Task | None:
    return by_key.get(key) or by_key.get(key + "#gate")


def _item_accepted(key: str, by_key: Mapping[str, Task]) -> bool:
    owner = _owner(key, by_key)
    if owner is None or owner.status is not TaskStatus.ACCEPTED:
        return False
    return owner.kind in {TaskKind.ITEM, TaskKind.ITEM_GATE}


def _criterion(
    criterion: Mapping[str, Any],
    by_key: Mapping[str, Task],
    acceptances: Sequence[AcceptanceDecision],
    checks: Sequence[CheckExecution],
    deviations: Sequence[DeviationAcceptance],
    gate: GateInputs,
) -> CriterionCoverage:
    task = _owner(criterion["owner"], by_key)
    evidence: Literal["check", "review", "deviation", "none"] = "none"
    if task is not None and task.status is TaskStatus.ACCEPTED:
        own = [
            a
            for a in acceptances
            if a.task_id == task.id
            and a.run_id == task.run_id
            and a.decision == "accepted"
            and a.attempt_id == task.accepted_attempt_id
            and a.output_id == task.accepted_output_id
        ]
        decision = max(own, key=lambda a: a.decided_at, default=None)
        if any(
            d.run_id == task.run_id
            and d.task_id in {task.id, gate.task.id}
            and d.scope == "coverage"
            and str(d.criterion_id) == str(criterion["id"])
            for d in deviations
        ):
            evidence = "deviation"
        elif decision and decision.basis.clearance not in {
            ReviewClearance.SELF,
            ReviewClearance.WAIVED,
            ReviewClearance.REPORT,
        }:
            evidence = "review"
        elif decision and any(
            c.task_id == task.id
            and c.run_id == task.run_id
            and c.output_id == task.accepted_output_id
            and c.attempt_id == task.accepted_attempt_id
            and c.state == "passed"
            and c.id in decision.basis.check_execution_ids
            and c.check_key in criterion.get("checks", ())
            for c in checks
        ):
            evidence = "check"
    return CriterionCoverage(criterion["key"], criterion["owner"], evidence)


def _checks(
    reasons: list[AcceptanceReason],
    checks: Sequence[CheckExecution],
    manual: Mapping[CheckExecutionId, ManualVerdict],
    required: frozenset[EntityId],
) -> tuple[list[CheckExecutionId], list[ManualVerdictId]]:
    latest: dict[EntityId, CheckExecution] = {}
    for check in checks:
        if check.check_spec_id not in latest or check.round_no > latest[check.check_spec_id].round_no:
            latest[check.check_spec_id] = check
    wanted = required | {c.check_spec_id for c in checks if c.required or c.kind is CheckKind.MANUAL}
    passed: list[CheckExecutionId] = []
    verdicts: list[ManualVerdictId] = []
    for spec in sorted(wanted, key=str):
        check = latest.get(spec)
        code = "REQUIRED_CHECK_NOT_PASSED"
        if check is not None:
            verdict = manual.get(check.id)
            if check.kind is CheckKind.MANUAL:
                if verdict is None or verdict.check_execution_id != check.id:
                    code = "MANUAL_PENDING"
                elif verdict.verdict == "fail":
                    code = "MANUAL_FAILED"
                elif check.state is CheckState.PASSED:
                    passed.append(check.id)
                    verdicts.append(verdict.id)
                    continue
            elif check.state is CheckState.PASSED:
                passed.append(check.id)
                continue
        reasons.append(AcceptanceReason(code, {"check_spec_id": str(spec)}))
    return passed, verdicts
