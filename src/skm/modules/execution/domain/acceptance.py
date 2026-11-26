"""The acceptance invariant A1-A12 and the immutable acceptance decision (execution §4.14, §5.4).

``decide_acceptance`` returns **every** unmet condition, each as an ``AcceptanceReason(code, refs)``; only
``MANUAL_PENDING``, ``DEVIATION_REQUIRED`` and ``BUDGET_EXHAUSTED`` are waits, every other reason is a
violation. "The agent said done" is not a condition. Evidence counts only when it is bound to this
task, its current attempt and that attempt's current output: a check or review of another output, a
deviation of another task or a verdict of another check never satisfies a condition, and a missing or
unknown fact never passes. A review request task checks only A1, A2, A9 and A11 (clearance ``report``);
``report`` on any run that is not ``review_request`` is ``REVIEW_MISSING`` and every condition is checked.

An ``AcceptanceDecision`` is append-only (K3): it records the acceptance of an output before integration,
not the terminal ``accepted`` status, and it carries no integration commit shas.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.execution.domain.attempt import Attempt, acceptable
from skm.modules.execution.domain.check_execution import CheckExecution, CheckKind, CheckState
from skm.modules.execution.domain.deviation import WRITE_SCOPE_CATEGORY, DeviationAcceptance
from skm.modules.execution.domain.finding import (
    OPEN_FINDING_STATES,
    SEVERITY_RANK,
    Finding,
    FindingState,
    Severity,
    logical_findings,
    place,
)
from skm.modules.execution.domain.ids import (
    CarryForwardId,
    CheckExecutionId,
    DeviationId,
    ManualVerdictId,
    ReviewId,
)
from skm.modules.execution.domain.manual_verdict import ManualVerdict
from skm.modules.execution.domain.output import Output
from skm.modules.execution.domain.review import (
    SECURITY_PROFILE,
    Freshness,
    Review,
    ReviewClearance,
    ReviewerKind,
    ReviewState,
    Verdict,
    freshness_of,
)
from skm.modules.execution.domain.task import WORK_KINDS, ReviewMode, Task, TaskStatus

if TYPE_CHECKING:
    from datetime import datetime
    from typing import Literal

    from skm.kernel.ids import AttemptId, EntityId, PrincipalId, RunId, TaskId, WorkspaceId
    from skm.modules.execution.domain.ids import AcceptanceDecisionId, OutputId

__all__ = [
    "ACCEPTANCE_CODES",
    "REVIEW_CLEARANCES",
    "WAITING_CODES",
    "AcceptanceBasis",
    "AcceptanceDecision",
    "AcceptanceReason",
    "Accepted",
    "NotAcceptable",
    "decide_acceptance",
    "record_acceptance",
]

# §5.4 reason codes in the order of A1-A12
ACCEPTANCE_CODES: Final = (
    "ATTEMPT_NOT_CURRENT",
    "OUTPUT_NOT_CURRENT",
    "REQUIRED_CHECK_NOT_PASSED",
    "MANUAL_PENDING",
    "MANUAL_FAILED",
    "REVIEW_MISSING",
    "REVIEW_NOT_GREEN",
    "REVIEW_STALE",
    "SELF_CHECK_MISSING",
    "BLOCKER_OPEN",
    "DEVIATION_REQUIRED",
    "EVIDENCE_MISSING",
    "POLICY_DENIES",
    "BUDGET_EXHAUSTED",
    "TASK_SUPERSEDED",
    "WRITE_SCOPE_VIOLATION",
)
WAITING_CODES: Final = frozenset({"MANUAL_PENDING", "DEVIATION_REQUIRED", "BUDGET_EXHAUSTED"})
# clearances proven by a review of the output; a required review accepts only these
REVIEW_CLEARANCES: Final = frozenset(
    {
        ReviewClearance.GREEN,
        ReviewClearance.FINDINGS_ONLY,
        ReviewClearance.CLEARED_BY_TRIAGE,
        ReviewClearance.DEVIATION,
    }
)
_MODE_CLEARANCES: Final = {
    ReviewMode.REQUIRED: REVIEW_CLEARANCES,
    ReviewMode.SELF: REVIEW_CLEARANCES | {ReviewClearance.SELF},
    ReviewMode.WAIVED: REVIEW_CLEARANCES | {ReviewClearance.WAIVED},
}
_MODE_RANK: Final = {ReviewMode.WAIVED: 0, ReviewMode.SELF: 1, ReviewMode.REQUIRED: 2}
# the only run kind whose review task is accepted with clearance ``report`` (§5.4, F7)
_REVIEW_REQUEST_RUN: Final = "review_request"
_MAJOR: Final = SEVERITY_RANK[Severity.MAJOR]


@dataclass(frozen=True, slots=True)
class AcceptanceDecision:
    id: AcceptanceDecisionId
    workspace_id: WorkspaceId
    run_id: RunId
    task_id: TaskId
    attempt_id: AttemptId
    output_id: OutputId | None
    decision: Literal["accepted", "rejected"]
    actor_id: PrincipalId
    basis: AcceptanceBasis
    decided_at: datetime

    def __post_init__(self) -> None:
        if (self.decision == "accepted") == bool(self.basis.reasons) or self.decision not in {
            "accepted",
            "rejected",
        }:
            raise error_for(
                ErrorCode.SCHEMA_INVALID,
                "an accepted decision has no reasons and a rejected decision states them",
                details={"acceptance_decision_id": str(self.id), "decision": self.decision},
            )


def decide_acceptance(  # noqa: PLR0913 -- exact owner contract, execution §5.4
    task: Task,
    attempt: Attempt,
    output: Output,
    checks: Sequence[CheckExecution],
    manual: Mapping[CheckExecutionId, ManualVerdict],
    reviews: Sequence[Review],
    findings: Sequence[Finding],
    deviations: Sequence[DeviationAcceptance],
    review_req: JsonObject,
    clearance: ReviewClearance,
    policy_live_ok: bool,
    budget_ok: bool,
    revision_current_for_task: bool,
    evidence_available: bool,
    evidence_required: bool,
    *,
    required_checks: Collection[EntityId],
    outputs: Sequence[Output] = (),
) -> Accepted | NotAcceptable:
    """All unmet A1-A12 conditions for accepting ``output`` with ``clearance``.

    ``required_checks`` are the check spec ids the task contract requires; without them a task whose
    check stage never ran would pass A3 by having no rows. ``manual`` maps a check execution to its
    current verdict (``current_verdict``). ``reviews``/``findings`` are all rounds of the task; a finding
    of another review is ``SCHEMA_INVALID``. ``outputs`` are the sealed outputs of the attempt: a
    ``findings_only`` review must audit one of them that is earlier than ``output``. ``review_req`` is the
    revision review requirement (``mode``, ``profile``, ``independence``, ``reason``, ``waived_by``) plus
    execution facts: ``run_kind`` (clearance ``report`` exists only for ``review_request``),
    ``review_profile`` (the chosen profile), ``self_check``, ``corrected_only`` (H7),
    ``review_accept_findings_only`` (default true) and the executor's ``executor_step_ids``/
    ``executor_runtime_ids`` for independence. Intensity keys in it change nothing.
    """
    reasons: list[AcceptanceReason] = []
    if attempt.task_id != task.id or attempt.id != task.current_attempt_id or not acceptable(attempt):
        reasons.append(_reason("ATTEMPT_NOT_CURRENT", attempt_id=str(attempt.id), state=attempt.state.value))
    if output.attempt_id != attempt.id or output.task_id != task.id or output.id != attempt.current_output_id:
        reasons.append(
            _reason(
                "OUTPUT_NOT_CURRENT",
                output_id=str(output.id),
                current_output_id=None
                if attempt.current_output_id is None
                else str(attempt.current_output_id),
            )
        )
    if clearance is ReviewClearance.REPORT and review_req.get("run_kind") == _REVIEW_REQUEST_RUN:
        _live_reasons(
            reasons, task, policy_live_ok=policy_live_ok, budget_ok=None, current=revision_current_for_task
        )
        return _result(reasons, clearance, AcceptanceBasis.empty(clearance))

    bound = [check for check in checks if _bound(check, task, attempt, output)]
    passed_ids, verdict_ids = _check_reasons(reasons, bound, manual, required_checks)

    own_reviews = [review for review in reviews if review.task_id == task.id and review.run_id == task.run_id]
    logical = logical_findings(findings, {review.id: review.round_no for review in own_reviews})
    own_deviations = [item for item in deviations if item.task_id == task.id and item.run_id == task.run_id]
    waived = _waived_keys(findings, own_deviations)
    review_id = _review_reasons(
        reasons,
        _ReviewFacts(
            task,
            output,
            own_reviews,
            logical,
            own_deviations,
            waived,
            review_req,
            {item.id: item for item in outputs},
        ),
        clearance,
    )
    blockers = [f.finding_key for f in logical if f.severity is Severity.BLOCKER and _open(f, waived)]
    if blockers:
        reasons.append(_reason("BLOCKER_OPEN", finding_keys=blockers))
    if evidence_required and not evidence_available:
        reasons.append(_reason("EVIDENCE_MISSING", output_id=str(output.id)))
    _live_reasons(
        reasons, task, policy_live_ok=policy_live_ok, budget_ok=budget_ok, current=revision_current_for_task
    )
    outside = _uncovered_outside(output, logical, waived)
    if outside:
        reasons.append(_reason("WRITE_SCOPE_VIOLATION", paths=outside))

    basis = AcceptanceBasis(
        clearance=clearance,
        check_execution_ids=tuple(sorted(passed_ids, key=str)),
        review_id=review_id,
        manual_verdict_ids=tuple(sorted(verdict_ids, key=str)),
        deviation_ids=tuple(sorted((item.id for item in own_deviations), key=str)),
        review_debt=clearance is ReviewClearance.FINDINGS_ONLY,
        coverage_report=None,
        carry_forward_id=None,
        reasons=(),
    )
    return _result(reasons, clearance, basis)


@dataclass(frozen=True, slots=True)
class AcceptanceBasis:
    clearance: ReviewClearance
    check_execution_ids: tuple[CheckExecutionId, ...]
    review_id: ReviewId | None
    manual_verdict_ids: tuple[ManualVerdictId, ...]
    deviation_ids: tuple[DeviationId, ...]
    review_debt: bool
    coverage_report: JsonObject | None
    carry_forward_id: CarryForwardId | None
    reasons: tuple[str, ...]

    @staticmethod
    def empty(clearance: ReviewClearance) -> AcceptanceBasis:
        return AcceptanceBasis(clearance, (), None, (), (), False, None, None, ())


@dataclass(frozen=True, slots=True)
class AcceptanceReason:
    code: str
    refs: Mapping[str, JsonValue]

    @property
    def waiting(self) -> bool:
        return self.code in WAITING_CODES


@dataclass(frozen=True, slots=True)
class Accepted:
    clearance: ReviewClearance
    basis: AcceptanceBasis


@dataclass(frozen=True, slots=True)
class NotAcceptable:
    reasons: tuple[AcceptanceReason, ...]

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(reason.code for reason in self.reasons)

    @property
    def waiting_only(self) -> bool:
        """K1: every reason is a wait (manual verdict, human decision, budget)."""
        return all(reason.waiting for reason in self.reasons)


def record_acceptance(
    result: Accepted | NotAcceptable,
    *,
    clearance: ReviewClearance,
    decision_id: AcceptanceDecisionId,
    task: Task,
    attempt: Attempt,
    output: Output | None,
    actor_id: PrincipalId,
    now: datetime,
) -> AcceptanceDecision:
    """The append-only decision of one ``decide_acceptance`` result; no commit shas are ever added."""
    if isinstance(result, Accepted):
        if result.clearance is not clearance:
            raise error_for(
                ErrorCode.SCHEMA_INVALID,
                "the decision records the clearance that was decided",
                details={"decided": result.clearance.value, "recorded": clearance.value},
            )
        basis, decision = result.basis, "accepted"
    else:
        codes = tuple(dict.fromkeys(reason.code for reason in result.reasons))
        basis = AcceptanceBasis(clearance, (), None, (), (), False, None, None, codes)
        decision = "rejected"
    return AcceptanceDecision(
        id=decision_id,
        workspace_id=task.workspace_id,
        run_id=task.run_id,
        task_id=task.id,
        attempt_id=attempt.id,
        output_id=None if output is None else output.id,
        decision=decision,
        actor_id=actor_id,
        basis=basis,
        decided_at=now,
    )


# --- A3/A4 --------------------------------------------------------------------------------------------


def _bound(check: CheckExecution, task: Task, attempt: Attempt, output: Output) -> bool:
    return (
        check.output_id == output.id
        and check.attempt_id == attempt.id
        and check.task_id == task.id
        and check.run_id == task.run_id
    )


def _check_reasons(
    reasons: list[AcceptanceReason],
    bound: Sequence[CheckExecution],
    manual: Mapping[CheckExecutionId, ManualVerdict],
    required_checks: Collection[EntityId],
) -> tuple[list[CheckExecutionId], list[ManualVerdictId]]:
    latest: dict[EntityId, CheckExecution] = {}
    for check in bound:
        seen = latest.get(check.check_spec_id)
        if seen is None or seen.round_no < check.round_no:
            latest[check.check_spec_id] = check
    wanted = set(required_checks) | {
        check.check_spec_id for check in bound if check.required or check.kind is CheckKind.MANUAL
    }
    missing: list[str] = []
    outcomes: dict[str, list[str]] = {"not_passed": [], "pending": [], "failed": []}
    passed: list[CheckExecutionId] = []
    verdicts: list[ManualVerdictId] = []
    for spec in sorted(wanted, key=str):
        check = latest.get(spec)
        if check is None:
            missing.append(str(spec))
            continue
        verdict = manual.get(check.id) if check.kind is CheckKind.MANUAL else None
        outcome = _check_outcome(check, verdict)
        if outcome == "passed":
            passed.append(check.id)
            if verdict is not None:
                verdicts.append(verdict.id)
        else:
            outcomes[outcome].append(check.check_key)
    not_passed, pending, failed = outcomes["not_passed"], outcomes["pending"], outcomes["failed"]
    if not_passed or missing:
        reasons.append(
            _reason(
                "REQUIRED_CHECK_NOT_PASSED", check_keys=sorted(not_passed), missing_check_spec_ids=missing
            )
        )
    if pending:
        reasons.append(_reason("MANUAL_PENDING", check_keys=sorted(pending)))
    if failed:
        reasons.append(_reason("MANUAL_FAILED", check_keys=sorted(failed)))
    return passed, verdicts


def _check_outcome(
    check: CheckExecution, verdict: ManualVerdict | None
) -> Literal["passed", "not_passed", "pending", "failed"]:
    """A3 for an automatic check; A4 for a manual one, decided only by its own current verdict."""
    if check.kind is not CheckKind.MANUAL:
        return "passed" if check.state is CheckState.PASSED else "not_passed"
    if verdict is not None and verdict.check_execution_id != check.id:
        verdict = None  # a verdict of another check never decides this one
    if verdict is not None and verdict.verdict == "fail":
        return "failed"
    if verdict is not None and check.state is CheckState.PASSED:
        return "passed"
    if check.state in {CheckState.MANUAL_PENDING, CheckState.PENDING}:
        return "pending"
    return "not_passed"  # e.g. a passed projection without a verdict, or a cancelled manual check


# --- A5/A7 --------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _ReviewFacts:
    task: Task
    output: Output
    reviews: Sequence[Review]
    logical: Sequence[Finding]
    deviations: Sequence[DeviationAcceptance]
    waived: frozenset[str]
    view: Mapping[str, JsonValue]
    outputs: Mapping[OutputId, Output]


def _review_reasons(  # noqa: PLR0911 -- fail-closed clearance gates precede the review modes
    reasons: list[AcceptanceReason], facts: _ReviewFacts, clearance: ReviewClearance
) -> ReviewId | None:
    mode = _review_mode(facts.task, facts.view)
    if clearance is ReviewClearance.REPORT:
        run_kind = facts.view.get("run_kind")
        reasons.append(
            _reason(
                "REVIEW_MISSING", clearance="report", run_kind=run_kind if isinstance(run_kind, str) else None
            )
        )
        return None
    if clearance is ReviewClearance.FINDINGS_ONLY and facts.view.get("review_accept_findings_only") is False:
        reasons.append(
            _reason("REVIEW_MISSING", clearance="findings_only", policy="review_accept_findings_only")
        )
        return None
    if clearance not in _MODE_CLEARANCES[mode]:
        reasons.append(_reason("REVIEW_MISSING", clearance=clearance.value, review_mode=mode.value))
        return None
    completed = [review for review in facts.reviews if review.state is ReviewState.COMPLETED]
    latest = max(completed, key=lambda review: review.round_no) if completed else None
    if clearance is ReviewClearance.WAIVED:
        reason, waived_by = facts.view.get("reason"), facts.view.get("waived_by")
        if not (
            isinstance(reason, str) and reason.strip() and isinstance(waived_by, str) and waived_by.strip()
        ):
            reasons.append(
                _reason("REVIEW_MISSING", clearance="waived", missing="waiver_reason_or_waived_by")
            )
        return None
    if clearance is ReviewClearance.SELF:
        if facts.view.get("self_check") is True:
            return None
        if (
            latest is not None
            and latest.verdict is Verdict.GREEN
            and not _review_gaps(latest, facts, fresh=True)
        ):
            return latest.id
        reasons.append(_reason("SELF_CHECK_MISSING", task_id=str(facts.task.id)))
        return None
    if latest is None:
        reasons.append(_reason("REVIEW_MISSING", clearance=clearance.value))
        return None
    gaps = _review_gaps(latest, facts, fresh=clearance is not ReviewClearance.FINDINGS_ONLY)
    reasons.extend(gaps)
    _verdict_reasons(reasons, latest, facts, clearance)
    return latest.id


def _review_gaps(review: Review, facts: _ReviewFacts, *, fresh: bool) -> list[AcceptanceReason]:
    gaps: list[AcceptanceReason] = []
    freshness = freshness_of(
        review,
        facts.output,
        reviewed=facts.outputs.get(review.output_id),
        corrected_only=facts.view.get("corrected_only") is True,
    )
    expected = Freshness.FRESH if fresh else Freshness.FINDINGS_ONLY
    if freshness is not expected:
        gaps.append(
            _reason(
                "REVIEW_STALE",
                review_id=str(review.id),
                review_output_id=str(review.output_id),
                output_id=str(facts.output.id),
            )
        )
    profile = _required_profile(facts.task, facts.view)
    if profile is not None and review.profile_key != profile:
        gaps.append(
            _reason("REVIEW_MISSING", review_id=str(review.id), profile=profile, got=review.profile_key)
        )
    independence = facts.view.get("independence", "separate_session")
    if not _independent(review, str(independence), facts.view):
        gaps.append(_reason("REVIEW_MISSING", review_id=str(review.id), independence=str(independence)))
    return gaps


def _required_profile(task: Task, view: Mapping[str, JsonValue]) -> str | None:
    """The chosen profile, else the revision's, else the task's; ``security`` from any of them wins.

    A stored ``security`` profile (on the task or in the requirement) is never replaced by a weaker
    chosen profile, so a ``reviewer`` review does not clear a security review.
    """
    stated = [
        value
        for value in (view.get("review_profile"), view.get("profile"), task.review_profile)
        if isinstance(value, str) and value
    ]
    if SECURITY_PROFILE in stated:
        return SECURITY_PROFILE
    return stated[0] if stated else None


def _independent(review: Review, independence: str, view: Mapping[str, JsonValue]) -> bool:
    """A human review is independent; an agent review needs the executor's identity to be known and other.

    ``separate_runtime`` requires observed, distinct runtimes and model families. Any other value is at least
    ``separate_session``: the reviewer's step differs from every known executor step, and an unknown
    executor (no ``executor_step_ids``) never passes.
    """
    if review.reviewer_kind is ReviewerKind.HUMAN:
        return True
    if independence == "human":
        return False
    ref = review.reviewer_ref
    step = ref.get("step_id")
    if independence == "separate_runtime":
        reviewers = view.get("reviewer_identities")
        reviewer = reviewers.get(step) if isinstance(reviewers, Mapping) and isinstance(step, str) else None
        executors = view.get("executor_identities")
        return (
            isinstance(executors, list | tuple)
            and bool(executors)
            and all(_distinct_observed_identity(reviewer, executor) for executor in executors)
        )
    steps = _strings(view.get("executor_step_ids"))
    return bool(steps) and isinstance(step, str) and bool(step.strip()) and step not in steps


def _distinct_observed_identity(left: object, right: object) -> bool:
    if not isinstance(left, Mapping) or not isinstance(right, Mapping):
        return False
    reviewer = cast("Mapping[str, object]", left)
    executor = cast("Mapping[str, object]", right)
    for key in ("runtime", "family"):
        actual, other = reviewer.get(key), executor.get(key)
        if (
            not isinstance(actual, str)
            or not isinstance(other, str)
            or not actual
            or not other
            or actual == other
        ):
            return False
    return True


def _verdict_reasons(
    reasons: list[AcceptanceReason], review: Review, facts: _ReviewFacts, clearance: ReviewClearance
) -> None:
    logical, waived = facts.logical, facts.waived
    open_major = [f.finding_key for f in logical if SEVERITY_RANK[f.severity] >= _MAJOR and _open(f, waived)]
    if clearance is ReviewClearance.GREEN:
        if review.verdict is not Verdict.GREEN:
            reasons.append(_reason("REVIEW_NOT_GREEN", review_id=str(review.id), verdict=_verdict(review)))
        if open_major:
            reasons.append(
                _reason("REVIEW_NOT_GREEN", review_id=str(review.id), open_finding_keys=open_major)
            )
    elif clearance is ReviewClearance.CLEARED_BY_TRIAGE:
        work = facts.task.kind in WORK_KINDS
        still_open = [
            f.finding_key for f in logical if _open(f, waived) and (work or f.finding_key in open_major)
        ]
        rejected_major = [
            f.finding_key
            for f in logical
            if f.review_id == review.id
            and f.state is FindingState.REJECTED
            and SEVERITY_RANK[f.severity] >= _MAJOR
        ]
        if still_open:
            reasons.append(
                _reason("REVIEW_NOT_GREEN", review_id=str(review.id), open_finding_keys=still_open)
            )
        if rejected_major:
            reasons.append(
                _reason(
                    "REVIEW_NOT_GREEN", review_id=str(review.id), rejected_major_finding_keys=rejected_major
                )
            )
    elif clearance is ReviewClearance.DEVIATION:
        uncovered = [
            f.finding_key
            for f in logical
            if SEVERITY_RANK[f.severity] >= _MAJOR
            and (f.state in OPEN_FINDING_STATES or f.state is FindingState.WAIVED)
            and f.finding_key not in waived
        ]
        if uncovered:
            reasons.append(_reason("DEVIATION_REQUIRED", finding_keys=uncovered))
        accepted = any(item.scope in {"finding", "attention_verdict"} for item in facts.deviations)
        if review.verdict is not Verdict.GREEN and not accepted:
            reasons.append(_reason("DEVIATION_REQUIRED", review_id=str(review.id), verdict=_verdict(review)))


def _review_mode(task: Task, view: Mapping[str, JsonValue]) -> ReviewMode:
    """The stricter of the task mode and the revision requirement, so neither can weaken the other."""
    stated = view.get("mode")
    found = ReviewMode(stated) if isinstance(stated, str) and stated in set(ReviewMode) else task.review_mode
    return max(found, task.review_mode, key=_MODE_RANK.__getitem__)


# --- findings, deviations, scope ----------------------------------------------------------------------


def _waived_keys(findings: Sequence[Finding], deviations: Sequence[DeviationAcceptance]) -> frozenset[str]:
    """Keys of the findings that one of the task's own finding deviations accepted (any row of the key)."""
    accepted = {item.finding_id for item in deviations if item.scope == "finding"}
    return frozenset(finding.finding_key for finding in findings if finding.id in accepted)


def _open(finding: Finding, waived: frozenset[str]) -> bool:
    if finding.state is FindingState.WAIVED:
        return finding.finding_key not in waived
    return finding.state in OPEN_FINDING_STATES


def _uncovered_outside(output: Output, logical: Sequence[Finding], waived: frozenset[str]) -> list[str]:
    covered = {
        (str(f.location.get("mount", "")), place(str(f.location.get("path", ""))))
        for f in logical
        if f.category == WRITE_SCOPE_CATEGORY and f.finding_key in waived
    }
    return sorted(
        f"{path.mount}:{path.path}"
        for path in output.manifest.outside_write_scope
        if (path.mount, place(path.path)) not in covered
    )


def _live_reasons(
    reasons: list[AcceptanceReason],
    task: Task,
    *,
    policy_live_ok: bool,
    budget_ok: bool | None,
    current: bool,
) -> None:
    if not policy_live_ok:
        reasons.append(_reason("POLICY_DENIES", task_id=str(task.id)))
    if budget_ok is False:
        reasons.append(_reason("BUDGET_EXHAUSTED", task_id=str(task.id)))
    if not current or task.status in {TaskStatus.SUPERSEDED, TaskStatus.CANCELLED}:
        reasons.append(_reason("TASK_SUPERSEDED", task_id=str(task.id), status=task.status.value))


def _result(
    reasons: list[AcceptanceReason], clearance: ReviewClearance, basis: AcceptanceBasis
) -> Accepted | NotAcceptable:
    if reasons:
        order = {code: index for index, code in enumerate(ACCEPTANCE_CODES)}
        return NotAcceptable(tuple(sorted(reasons, key=lambda reason: order[reason.code])))
    return Accepted(clearance, basis)


def _reason(code: str, **refs: str | Sequence[str] | None) -> AcceptanceReason:
    return AcceptanceReason(
        code,
        {
            name: value if value is None or isinstance(value, str) else list[JsonValue](value)
            for name, value in refs.items()
        },
    )


def _verdict(review: Review) -> str | None:
    return None if review.verdict is None else review.verdict.value


def _strings(value: JsonValue | None) -> frozenset[str]:
    if isinstance(value, Sequence) and not isinstance(value, str):
        items = cast("Sequence[JsonValue]", value)
        if all(isinstance(item, str) and item.strip() for item in items):
            return frozenset(cast("Sequence[str]", items))
    return frozenset()
