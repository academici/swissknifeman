"""Acceptance invariant A1-A12, check states, manual verdict history and review freshness."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest

from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.modules.execution.domain.acceptance import (
    ACCEPTANCE_CODES,
    AcceptanceDecision,
    Accepted,
    NotAcceptable,
    decide_acceptance,
    record_acceptance,
)
from skm.modules.execution.domain.attempt import Attempt, AttemptState
from skm.modules.execution.domain.check_execution import (
    CHECK_TRANSITIONS,
    CheckExecution,
    CheckKind,
    CheckState,
    check_summary,
    classify_check_result,
    may_reuse,
    transition_check,
)
from skm.modules.execution.domain.deviation import WRITE_SCOPE_CATEGORY, DeviationAcceptance, accept_deviation
from skm.modules.execution.domain.finding import Finding, FindingState, Severity, finding_key
from skm.modules.execution.domain.manual_verdict import ManualVerdict, current_verdict, record_manual_verdict
from skm.modules.execution.domain.output import (
    ChangedPath,
    DiffStats,
    Output,
    OutputManifest,
    OutputMount,
    OutputSource,
    manifest_digest,
)
from skm.modules.execution.domain.review import (
    Freshness,
    Review,
    ReviewClearance,
    ReviewerKind,
    ReviewState,
    Verdict,
    freshness_of,
)
from skm.modules.execution.domain.task import ReviewMode, Task, TaskKind, TaskStatus

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
FP = "sha256:" + "e" * 64


def uid(n: int) -> Any:
    return UUID(int=n)


RUN, WS, TASK, ATTEMPT, OUT, OUT_A = uid(1), uid(2), uid(100), uid(200), uid(300), uid(301)
SPEC_CMD, SPEC_MANUAL = uid(400), uid(401)
CHECK_CMD, CHECK_MANUAL = uid(500), uid(501)
REVIEW_1 = uid(600)
HUMAN = Actor(uid(900), PrincipalKind.HUMAN, "Ann")


def make_task(**changes: Any) -> Task:
    values: dict[str, Any] = {
        "id": TASK,
        "run_id": RUN,
        "workspace_id": WS,
        "kind": TaskKind.ITEM,
        "spec_entity_id": uid(3),
        "display_key": "P1.1",
        "origin": None,
        "position": 0,
        "status": TaskStatus.INTEGRATING,
        "work_kind": "code",
        "review_mode": ReviewMode.REQUIRED,
        "review_profile": None,
        "declared_write_scope": None,
        "required_host_id": None,
        "current_attempt_id": ATTEMPT,
        "accepted_attempt_id": None,
        "accepted_output_id": None,
        "check_fix_rounds": 0,
        "review_rounds": 1,
        "attempt_count": 1,
        "blocking_reason": None,
        "row_version": 1,
    }
    values.update(changes)
    return Task(**values)


def make_attempt(state: AttemptState = AttemptState.RUNNING, **changes: Any) -> Attempt:
    terminal = state in {AttemptState.COMPLETED, AttemptState.OWNERSHIP_LOST, AttemptState.ABANDONED}
    values: dict[str, Any] = {
        "id": ATTEMPT,
        "run_id": RUN,
        "task_id": TASK,
        "workspace_id": WS,
        "attempt_no": 1,
        "state": state,
        "worker_id": uid(4),
        "host_id": uid(5),
        "environment_id": uid(6),
        "current_output_id": OUT,
        "executor_route": None,
        "continuation": None,
        "started_at": NOW,
        "finished_at": NOW if terminal else None,
        "end_reason": "LEASE_LOST" if terminal else None,
    }
    values.update(changes)
    return Attempt(**values)


def changed(path: str) -> ChangedPath:
    import base64

    raw = base64.urlsafe_b64encode(path.encode()).decode().rstrip("=")
    return ChangedPath("app", path, raw, "modified", None, None, "100644 " + "a" * 40)


def make_output(output_id: Any = OUT, outside: tuple[str, ...] = (), seq: int = 1) -> Output:
    paths = tuple(changed(path) for path in ("src/app/x.py", *outside))
    manifest = OutputManifest(
        algorithm="skm-output-v2",
        mounts=(OutputMount("app", uid(7), "sha1", "a" * 40, "b" * 40, "c" * 40),),
        changed_paths=paths,
        tree_digest="sha256:" + "d" * 64,
        outside_write_scope=tuple(changed(path) for path in outside),
        excluded_paths=(),
        patch_file_version_id=None,
        diff_stats=DiffStats(len(paths), 1, 0),
        empty=False,
    )
    return Output(
        id=output_id,
        attempt_id=ATTEMPT,
        task_id=TASK,
        run_id=RUN,
        seq=seq,
        source=OutputSource.EXECUTOR,
        manifest=manifest,
        manifest_digest=manifest_digest(manifest),
        sealed_at=NOW,
        produced_by_step_id=uid(8),
    )


def make_check(
    check_id: Any = CHECK_CMD,
    spec: Any = SPEC_CMD,
    *,
    kind: CheckKind = CheckKind.COMMAND,
    state: CheckState = CheckState.PASSED,
    output_id: Any = OUT,
    **changes: Any,
) -> CheckExecution:
    values: dict[str, Any] = {
        "id": check_id,
        "workspace_id": WS,
        "run_id": RUN,
        "task_id": TASK,
        "attempt_id": ATTEMPT,
        "output_id": output_id,
        "check_spec_id": spec,
        "check_key": "P1.1:V1" if kind is not CheckKind.MANUAL else "P1.1:M1",
        "kind": kind,
        "required": True,
        "state": state,
        "exit_code": 0 if state is CheckState.PASSED and kind is not CheckKind.MANUAL else None,
        "summary": "",
        "error_code": None,
        "reused_from_id": None,
        "fingerprint": FP,
        "started_at": NOW,
        "finished_at": NOW,
        "round_no": 1,
    }
    values.update(changes)
    return CheckExecution(**values)


def verdict(value: str = "pass", check_id: Any = CHECK_MANUAL, n: int = 700, **changes: Any) -> ManualVerdict:
    values: dict[str, Any] = {
        "id": uid(n),
        "check_execution_id": check_id,
        "principal_id": HUMAN.principal_id,
        "verdict": value,
        "comment": "",
        "recorded_at": NOW,
        "supersedes_id": None,
    }
    values.update(changes)
    return ManualVerdict(**values)


def make_review(
    review_id: Any = REVIEW_1,
    *,
    round_no: int = 1,
    output_id: Any = OUT,
    verdict_: Verdict = Verdict.GREEN,
    **changes: Any,
) -> Review:
    values: dict[str, Any] = {
        "id": review_id,
        "workspace_id": WS,
        "run_id": RUN,
        "task_id": TASK,
        "attempt_id": ATTEMPT,
        "output_id": output_id,
        "round_no": round_no,
        "reviewer_kind": ReviewerKind.AGENT,
        "reviewer_ref": {"step_id": "step-review", "runtime_id": "runtime-b"},
        "profile_key": "reviewer",
        "profile_version_id": uid(9),
        "audit_scope": "full" if round_no == 1 else "corrected",
        "state": ReviewState.COMPLETED,
        "verdict": verdict_,
        "freshness": Freshness.FRESH,
        "base_output_id": None if round_no == 1 else OUT_A,
        "residual_risk": "",
        "completed_at": NOW,
    }
    values.update(changes)
    return Review(**values)


def make_finding(
    n: int,
    severity: Severity,
    state: FindingState,
    *,
    review_id: Any = REVIEW_1,
    category: str = "logic",
    path: str = "src/app/x.py",
) -> Finding:
    location: dict[str, Any] = {"mount": "app", "path": path, "line_start": n}
    scenario = f"defect number {chr(ord('a') + n)} breaks the flow"
    return Finding(
        id=uid(800 + n + (1000 if review_id != REVIEW_1 else 0)),
        review_id=review_id,
        local_id=f"F{n}",
        finding_key=finding_key(location, category, scenario, "msg"),
        severity=severity,
        confidence="high",
        basis="correctness",
        category=category,
        message="msg",
        failure_scenario=scenario,
        location=location,
        reproduction=None,
        first_seen_review_id=review_id,
        state=state,
    )


def deviation(
    scope: str = "attention_verdict", *, finding_id: Any = None, task_id: Any = TASK, n: int = 950
) -> Any:
    return DeviationAcceptance(
        id=uid(n),
        run_id=RUN,
        task_id=task_id,
        criterion_id=None,
        finding_id=finding_id,
        reason="accepted by the owner",
        approved_by=HUMAN.principal_id,
        approved_at=NOW,
        scope=scope,  # type: ignore[arg-type]
    )


def args(**changes: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "task": make_task(),
        "attempt": make_attempt(),
        "output": make_output(),
        "checks": (
            make_check(),
            make_check(CHECK_MANUAL, SPEC_MANUAL, kind=CheckKind.MANUAL, state=CheckState.PASSED),
        ),
        "manual": {CHECK_MANUAL: verdict()},
        "reviews": (make_review(),),
        "findings": (),
        "deviations": (),
        "review_req": {"mode": "required", "executor_step_ids": ["step-executor"]},
        "clearance": ReviewClearance.GREEN,
        "policy_live_ok": True,
        "budget_ok": True,
        "revision_current_for_task": True,
        "evidence_available": True,
        "evidence_required": True,
        "required_checks": {SPEC_CMD, SPEC_MANUAL},
    }
    values.update(changes)
    return values


def decide(**changes: Any) -> Accepted | NotAcceptable:
    return decide_acceptance(**args(**changes))


def codes(result: Accepted | NotAcceptable) -> tuple[str, ...]:
    assert isinstance(result, NotAcceptable), result
    return result.codes


# --- the invariant --------------------------------------------------------------------------------------


def test_all_conditions_met_is_accepted_with_its_basis() -> None:
    result = decide()
    assert isinstance(result, Accepted)
    assert result.clearance is ReviewClearance.GREEN
    assert set(result.basis.check_execution_ids) == {CHECK_CMD, CHECK_MANUAL}
    assert result.basis.manual_verdict_ids == (uid(700),)
    assert result.basis.review_id == REVIEW_1
    assert result.basis.review_debt is False
    assert result.basis.reasons == ()


BLOCKER = make_finding(1, Severity.BLOCKER, FindingState.CONFIRMED)
MAJOR = make_finding(2, Severity.MAJOR, FindingState.CONFIRMED)

SINGLE: list[tuple[str, dict[str, Any], str]] = [
    (
        "A1",
        {"attempt": make_attempt(AttemptState.OWNERSHIP_LOST)},
        "ATTEMPT_NOT_CURRENT",
    ),
    ("A2", {"attempt": make_attempt(current_output_id=OUT_A)}, "OUTPUT_NOT_CURRENT"),
    (
        "A3",
        {
            "checks": (
                make_check(state=CheckState.FAILED, exit_code=1),
                make_check(CHECK_MANUAL, SPEC_MANUAL, kind=CheckKind.MANUAL),
            )
        },
        "REQUIRED_CHECK_NOT_PASSED",
    ),
    (
        "A4",
        {
            "checks": (
                make_check(),
                make_check(CHECK_MANUAL, SPEC_MANUAL, kind=CheckKind.MANUAL, state=CheckState.MANUAL_PENDING),
            ),
            "manual": {},
        },
        "MANUAL_PENDING",
    ),
    (
        "A4-fail",
        {
            "checks": (
                make_check(),
                make_check(CHECK_MANUAL, SPEC_MANUAL, kind=CheckKind.MANUAL, state=CheckState.FAILED),
            ),
            "manual": {CHECK_MANUAL: verdict("fail")},
        },
        "MANUAL_FAILED",
    ),
    ("A5", {"reviews": ()}, "REVIEW_MISSING"),
    (
        "A6",
        {
            "findings": (BLOCKER,),
            "clearance": ReviewClearance.FINDINGS_ONLY,
            "reviews": (make_review(output_id=OUT_A),),
            "output": make_output(seq=2),
            "outputs": (make_output(OUT_A),),
            "review_req": {
                "mode": "required",
                "corrected_only": True,
                "executor_step_ids": ["step-executor"],
            },
        },
        "BLOCKER_OPEN",
    ),
    (
        "A7",
        {
            "reviews": (make_review(verdict_=Verdict.ATTENTION),),
            "findings": (MAJOR,),
            "deviations": (deviation(),),
            "clearance": ReviewClearance.DEVIATION,
        },
        "DEVIATION_REQUIRED",
    ),
    ("A8", {"evidence_available": False}, "EVIDENCE_MISSING"),
    ("A9", {"policy_live_ok": False}, "POLICY_DENIES"),
    ("A10", {"budget_ok": False}, "BUDGET_EXHAUSTED"),
    ("A11", {"revision_current_for_task": False}, "TASK_SUPERSEDED"),
    ("A12", {"output": make_output(outside=("docs/other.md",))}, "WRITE_SCOPE_VIOLATION"),
]


@pytest.mark.parametrize(("condition", "change", "code"), SINGLE, ids=[case[0] for case in SINGLE])
def test_each_condition_blocks_on_its_own(condition: str, change: dict[str, Any], code: str) -> None:
    assert codes(decide(**change)) == (code,), condition


def test_all_conditions_together_report_every_reason_in_order() -> None:
    stale_review = make_review(output_id=OUT_A, verdict_=Verdict.ATTENTION, profile_key="other")
    result = decide(
        attempt=make_attempt(AttemptState.OWNERSHIP_LOST, current_output_id=OUT_A),
        output=make_output(outside=("docs/other.md",)),
        checks=(
            make_check(state=CheckState.FAILED, exit_code=1),
            make_check(CHECK_MANUAL, SPEC_MANUAL, kind=CheckKind.MANUAL, state=CheckState.MANUAL_PENDING),
        ),
        manual={},
        reviews=(stale_review,),
        findings=(BLOCKER,),
        review_req={"mode": "required", "review_profile": "reviewer", "executor_step_ids": []},
        clearance=ReviewClearance.DEVIATION,
        policy_live_ok=False,
        budget_ok=False,
        revision_current_for_task=False,
        evidence_available=False,
    )
    found = codes(result)
    assert set(found) == {
        "ATTEMPT_NOT_CURRENT",
        "OUTPUT_NOT_CURRENT",
        "REQUIRED_CHECK_NOT_PASSED",
        "MANUAL_PENDING",
        "REVIEW_MISSING",
        "REVIEW_STALE",
        "BLOCKER_OPEN",
        "DEVIATION_REQUIRED",
        "EVIDENCE_MISSING",
        "POLICY_DENIES",
        "BUDGET_EXHAUSTED",
        "TASK_SUPERSEDED",
        "WRITE_SCOPE_VIOLATION",
    }
    assert list(found) == sorted(found, key=ACCEPTANCE_CODES.index)
    assert isinstance(result, NotAcceptable)
    assert not result.waiting_only


def test_agent_said_done_without_checks_is_not_accepted() -> None:
    result = decide(checks=(), manual={})
    assert codes(result) == ("REQUIRED_CHECK_NOT_PASSED",)
    assert isinstance(result, NotAcceptable)
    assert set(result.reasons[0].refs["missing_check_spec_ids"]) == {str(SPEC_CMD), str(SPEC_MANUAL)}  # type: ignore[arg-type]


def test_evidence_not_required_lifts_a8() -> None:
    assert isinstance(decide(evidence_available=False, evidence_required=False), Accepted)


def test_manual_pending_is_a_wait_not_a_failure() -> None:
    result = decide(
        checks=(
            make_check(),
            make_check(CHECK_MANUAL, SPEC_MANUAL, kind=CheckKind.MANUAL, state=CheckState.MANUAL_PENDING),
        ),
        manual={},
    )
    assert isinstance(result, NotAcceptable)
    assert result.codes == ("MANUAL_PENDING",)
    assert result.waiting_only


@pytest.mark.parametrize(
    ("clearance", "code"),
    [(ReviewClearance.GREEN, "REVIEW_NOT_GREEN"), (ReviewClearance.DEVIATION, "DEVIATION_REQUIRED")],
)
def test_red_review_without_a_decision_is_not_accepted(clearance: ReviewClearance, code: str) -> None:
    assert codes(decide(reviews=(make_review(verdict_=Verdict.RED),), clearance=clearance)) == (code,)


# --- output binding: output A never accepts output B -------------------------------------------------


def test_checks_review_and_verdict_of_output_a_do_not_accept_output_b() -> None:
    old_checks = (
        make_check(output_id=OUT_A),
        make_check(
            CHECK_MANUAL, SPEC_MANUAL, kind=CheckKind.MANUAL, state=CheckState.PASSED, output_id=OUT_A
        ),
    )
    result = decide(checks=old_checks, reviews=(make_review(output_id=OUT_A),))
    assert codes(result) == ("REQUIRED_CHECK_NOT_PASSED", "REVIEW_STALE")


def test_review_of_another_output_is_stale_and_of_another_task_is_missing() -> None:
    assert codes(decide(reviews=(make_review(output_id=OUT_A),))) == ("REVIEW_STALE",)
    foreign = make_review(task_id=uid(101))
    assert codes(decide(reviews=(foreign,))) == ("REVIEW_MISSING",)


def test_a_verdict_of_another_check_does_not_decide_this_one() -> None:
    result = decide(
        checks=(
            make_check(),
            make_check(CHECK_MANUAL, SPEC_MANUAL, kind=CheckKind.MANUAL, state=CheckState.MANUAL_PENDING),
        ),
        manual={CHECK_MANUAL: verdict(check_id=uid(599))},
    )
    assert codes(result) == ("MANUAL_PENDING",)


def test_a_passed_manual_projection_without_a_verdict_is_not_accepted() -> None:
    assert codes(decide(manual={})) == ("REQUIRED_CHECK_NOT_PASSED",)


def test_only_the_latest_round_of_a_check_counts() -> None:
    rounds = (
        make_check(),
        make_check(uid(502), state=CheckState.FAILED, exit_code=1, round_no=2),
        make_check(CHECK_MANUAL, SPEC_MANUAL, kind=CheckKind.MANUAL),
    )
    assert codes(decide(checks=rounds)) == ("REQUIRED_CHECK_NOT_PASSED",)


# --- receipts and intensity ---------------------------------------------------------------------------


def test_exact_reused_receipt_counts_and_timeout_or_missing_does_not() -> None:
    reused = make_check(reused_from_id=uid(510))
    assert isinstance(decide(checks=(reused, *args()["checks"][1:])), Accepted)
    state, error = classify_check_result(CheckKind.COMMAND, None, True, None, False)
    timed_out = make_check(state=state, error_code=error, exit_code=None)
    assert codes(decide(checks=(timed_out, *args()["checks"][1:]))) == ("REQUIRED_CHECK_NOT_PASSED",)


def test_may_reuse_only_an_exact_available_green_receipt() -> None:
    source = make_check()
    exact: dict[str, Any] = {
        "workspace_id": WS,
        "check_spec_id": SPEC_CMD,
        "fingerprint": FP,
        "evidence_available": True,
        "post_integration": False,
    }
    assert may_reuse(source, **exact)
    for change in (
        {"fingerprint": None},
        {"fingerprint": "sha256:" + "f" * 64},
        {"evidence_available": False},
        {"post_integration": True},
        {"workspace_id": uid(99)},
        {"check_spec_id": uid(98)},
    ):
        assert not may_reuse(source, **{**exact, **change}), change
    assert not may_reuse(make_check(state=CheckState.ERROR, error_code="RUNTIME_TIMEOUT"), **exact)
    manual = make_check(kind=CheckKind.MANUAL, state=CheckState.PASSED)
    assert not may_reuse(manual, **exact)
    assert may_reuse(manual, **exact, attested=True)


@pytest.mark.parametrize("intensity", ["light", "medium", "heavy"])
def test_light_intensity_removes_no_required_review_independence_or_check(intensity: str) -> None:
    req = {"mode": "required", "verification_intensity": intensity, "executor_step_ids": ["step-executor"]}
    assert codes(decide(review_req=req, reviews=())) == ("REVIEW_MISSING",)
    assert codes(decide(review_req=req, clearance=ReviewClearance.SELF)) == ("REVIEW_MISSING",)
    human = {**req, "independence": "human"}
    assert codes(decide(review_req=human)) == ("REVIEW_MISSING",)
    security = {**req, "review_profile": "security"}
    assert codes(decide(review_req=security)) == ("REVIEW_MISSING",)
    assert codes(decide(review_req=req, checks=(), manual={})) == ("REQUIRED_CHECK_NOT_PASSED",)


# --- review clearances ----------------------------------------------------------------------------------


def test_independence_of_the_reviewer() -> None:
    same_step = make_review(reviewer_ref={"step_id": "step-executor"})
    assert codes(decide(reviews=(same_step,))) == ("REVIEW_MISSING",)
    unknown = {"mode": "required", "independence": "separate_runtime"}
    assert codes(decide(review_req=unknown)) == ("REVIEW_MISSING",)
    human_review = make_review(reviewer_kind=ReviewerKind.HUMAN, reviewer_ref={"principal_id": str(uid(900))})
    assert isinstance(
        decide(review_req={"mode": "required", "independence": "human"}, reviews=(human_review,)), Accepted
    )


@pytest.mark.parametrize(
    ("reviewer", "accepted"),
    [
        (None, False),
        ({"runtime": "cursor", "family": None}, False),
        ({"runtime": "cursor", "family": "openai"}, False),
        ({"runtime": "codex", "family": "claude"}, False),
        ({"runtime": "cursor", "family": "claude"}, True),
    ],
)
def test_separate_runtime_requires_observed_cross_family_identity(reviewer: Any, accepted: bool) -> None:
    req = {
        "mode": "required",
        "independence": "separate_runtime",
        "executor_identities": [{"runtime": "codex", "family": "openai"}],
        "reviewer_identities": {"step-review": reviewer},
    }
    assert isinstance(decide(review_req=req), Accepted) is accepted


def test_separate_session_needs_a_known_distinct_executor() -> None:
    # without the executor's step ids the reviewer cannot be shown to be another session
    for unknown in ({"mode": "required"}, {"mode": "required", "executor_step_ids": []}):
        assert codes(decide(review_req=unknown)) == ("REVIEW_MISSING",)
        session = {**unknown, "independence": "separate_session"}
        assert codes(decide(review_req=session)) == ("REVIEW_MISSING",)
    no_step = make_review(reviewer_ref={"runtime_id": "runtime-b"})
    assert codes(decide(reviews=(no_step,))) == ("REVIEW_MISSING",)
    assert isinstance(decide(), Accepted)


def test_a_stored_security_profile_is_enforced() -> None:
    req = {"mode": "required", "executor_step_ids": ["step-executor"]}
    secure_task = make_task(review_profile="security")
    # the task stores the security profile: a reviewer review does not clear it
    assert codes(decide(task=secure_task)) == ("REVIEW_MISSING",)
    # nor can a weaker chosen profile replace the security profile of the requirement
    weaker = {**req, "profile": "security", "review_profile": "reviewer"}
    assert codes(decide(review_req=weaker)) == ("REVIEW_MISSING",)
    secure_review = make_review(profile_key="security")
    assert isinstance(decide(task=secure_task, reviews=(secure_review,)), Accepted)
    assert isinstance(decide(review_req=weaker, reviews=(secure_review,)), Accepted)


def test_attention_needs_a_human_deviation_of_this_task() -> None:
    attention = (make_review(verdict_=Verdict.ATTENTION),)
    base: dict[str, Any] = {"reviews": attention, "clearance": ReviewClearance.DEVIATION}
    assert codes(decide(**base)) == ("DEVIATION_REQUIRED",)
    assert codes(decide(**base, deviations=(deviation(task_id=uid(101)),))) == ("DEVIATION_REQUIRED",)
    assert isinstance(decide(**base, deviations=(deviation(),)), Accepted)
    covered = (deviation("finding", finding_id=MAJOR.id),)
    waived_major = dataclasses.replace(MAJOR, state=FindingState.WAIVED)
    assert isinstance(decide(**base, findings=(waived_major,), deviations=covered), Accepted)


def test_cleared_by_triage_needs_no_open_or_rejected_major_findings() -> None:
    triaged = (make_review(verdict_=Verdict.ATTENTION),)
    base: dict[str, Any] = {"reviews": triaged, "clearance": ReviewClearance.CLEARED_BY_TRIAGE}
    rejected_minor = make_finding(3, Severity.MINOR, FindingState.REJECTED)
    assert isinstance(decide(**base, findings=(rejected_minor,)), Accepted)
    confirmed_minor = make_finding(4, Severity.MINOR, FindingState.CONFIRMED)
    assert codes(decide(**base, findings=(confirmed_minor,))) == ("REVIEW_NOT_GREEN",)
    gate = make_task(kind=TaskKind.ITEM_GATE, declared_write_scope=())
    assert isinstance(decide(**base, task=gate, findings=(confirmed_minor,)), Accepted)
    rejected_major = make_finding(5, Severity.MAJOR, FindingState.REJECTED)
    assert codes(decide(**base, findings=(rejected_major,))) == ("REVIEW_NOT_GREEN",)


def test_findings_only_needs_the_corrected_only_fact() -> None:
    earlier = make_review(output_id=OUT_A, verdict_=Verdict.ATTENTION)
    base: dict[str, Any] = {
        "reviews": (earlier,),
        "clearance": ReviewClearance.FINDINGS_ONLY,
        "output": make_output(seq=2),
        "outputs": (make_output(OUT_A, seq=1),),
    }
    assert codes(decide(**base)) == ("REVIEW_STALE",)
    corrected = {"mode": "required", "corrected_only": True, "executor_step_ids": ["step-executor"]}
    result = decide(**base, review_req=corrected)
    assert isinstance(result, Accepted)
    assert result.basis.review_debt is True


def test_findings_only_needs_a_real_earlier_output_of_the_same_attempt() -> None:
    earlier = make_review(output_id=OUT_A, verdict_=Verdict.ATTENTION)
    corrected = {"mode": "required", "corrected_only": True, "executor_step_ids": ["step-executor"]}
    base: dict[str, Any] = {
        "reviews": (earlier,),
        "clearance": ReviewClearance.FINDINGS_ONLY,
        "review_req": corrected,
        "output": make_output(seq=2),
    }
    # the reviewed output is unknown: H7 alone does not clear it
    assert codes(decide(**base)) == ("REVIEW_STALE",)
    # the reviewed output is not earlier than the accepted one
    assert codes(decide(**base, outputs=(make_output(OUT_A, seq=3),))) == ("REVIEW_STALE",)
    # an output of another attempt with the reviewed id does not count
    foreign = dataclasses.replace(make_output(OUT_A, seq=1), attempt_id=uid(201))
    assert codes(decide(**base, outputs=(foreign,))) == ("REVIEW_STALE",)
    # the H7 policy switched off refuses findings_only even with every fact present
    off = {**corrected, "review_accept_findings_only": False}
    known = (make_output(OUT_A, seq=1),)
    assert codes(decide(**base | {"review_req": off}, outputs=known)) == ("REVIEW_MISSING",)
    assert isinstance(decide(**base, outputs=known), Accepted)


@pytest.mark.parametrize("verdict", list(Verdict))
@pytest.mark.parametrize("corrected_only", [False, True])
def test_findings_only_never_clears_a_review_of_the_current_output(
    verdict: Verdict, corrected_only: bool
) -> None:
    req = {"mode": "required", "corrected_only": corrected_only, "executor_step_ids": ["step-executor"]}
    assert codes(
        decide(
            reviews=(make_review(verdict_=verdict),), review_req=req, clearance=ReviewClearance.FINDINGS_ONLY
        )
    ) == ("REVIEW_STALE",)


@pytest.mark.parametrize("identities", [[None], [""], [" "], ["step-executor", None], "step-executor"])
def test_malformed_executor_identity_does_not_prove_independence(identities: Any) -> None:
    assert codes(decide(review_req={"mode": "required", "executor_step_ids": identities})) == (
        "REVIEW_MISSING",
    )


def test_self_and_waived_clearances() -> None:
    self_req = {"mode": "self", "self_check": True}
    assert isinstance(
        decide(
            task=make_task(review_mode=ReviewMode.SELF),
            review_req=self_req,
            reviews=(),
            clearance=ReviewClearance.SELF,
        ),
        Accepted,
    )
    missing = decide(
        task=make_task(review_mode=ReviewMode.SELF),
        review_req={"mode": "self"},
        reviews=(),
        clearance=ReviewClearance.SELF,
    )
    assert codes(missing) == ("SELF_CHECK_MISSING",)
    waived_task = make_task(review_mode=ReviewMode.WAIVED)
    waived = {"mode": "waived", "reason": "docs only", "waived_by": "owner"}
    assert isinstance(
        decide(task=waived_task, review_req=waived, reviews=(), clearance=ReviewClearance.WAIVED), Accepted
    )
    no_reason = {"mode": "waived", "waived_by": "owner"}
    assert codes(
        decide(task=waived_task, review_req=no_reason, reviews=(), clearance=ReviewClearance.WAIVED)
    ) == ("REVIEW_MISSING",)
    # the stricter of task mode and requirement wins: a waived requirement cannot waive a required task
    assert codes(decide(review_req=waived, reviews=(), clearance=ReviewClearance.WAIVED)) == (
        "REVIEW_MISSING",
    )


def test_report_clearance_checks_only_a1_a2_a9_a11() -> None:
    report: dict[str, Any] = {
        "clearance": ReviewClearance.REPORT,
        "review_req": {"mode": "required", "run_kind": "review_request"},
    }
    assert isinstance(
        decide(checks=(), manual={}, reviews=(), evidence_available=False, budget_ok=False, **report),
        Accepted,
    )
    assert codes(decide(policy_live_ok=False, revision_current_for_task=False, **report)) == (
        "POLICY_DENIES",
        "TASK_SUPERSEDED",
    )


@pytest.mark.parametrize("run_kind", [None, "plan", "readiness_audit"])
def test_report_clearance_needs_a_review_request_run(run_kind: str | None) -> None:
    req: dict[str, Any] = {"mode": "required", "executor_step_ids": ["step-executor"]}
    if run_kind is not None:
        req["run_kind"] = run_kind
    # every condition is checked: report does not skip the checks and the review of a plan task
    result = decide(checks=(), manual={}, clearance=ReviewClearance.REPORT, review_req=req)
    assert codes(result) == ("REQUIRED_CHECK_NOT_PASSED", "REVIEW_MISSING")
    assert codes(decide(clearance=ReviewClearance.REPORT, review_req=req)) == ("REVIEW_MISSING",)


# --- blockers of every round, write scope -----------------------------------------------------------


def test_a_blocker_of_an_earlier_round_stays_open_until_resolved() -> None:
    round_two = make_review(uid(601), output_id=OUT_A, round_no=2, verdict_=Verdict.GREEN)
    reviews = (make_review(output_id=OUT_A, verdict_=Verdict.RED), round_two)
    base: dict[str, Any] = {
        "reviews": reviews,
        "clearance": ReviewClearance.FINDINGS_ONLY,
        "output": make_output(seq=2),
        "outputs": (make_output(OUT_A),),
        "review_req": {"mode": "required", "corrected_only": True, "executor_step_ids": ["step-executor"]},
    }
    assert codes(decide(**base, findings=(BLOCKER,))) == ("BLOCKER_OPEN",)
    resolved = dataclasses.replace(BLOCKER, state=FindingState.RESOLVED)
    assert isinstance(decide(**base, findings=(resolved,)), Accepted)
    waived = dataclasses.replace(BLOCKER, state=FindingState.WAIVED)
    assert codes(decide(**base, findings=(waived,))) == ("BLOCKER_OPEN",)
    assert isinstance(
        decide(**base, findings=(waived,), deviations=(deviation("finding", finding_id=BLOCKER.id),)),
        Accepted,
    )
    # a later row of the same key decides: reconfirmed in round 2 is open again
    again = make_finding(1, Severity.BLOCKER, FindingState.CONFIRMED, review_id=uid(601))
    assert codes(decide(**base, findings=(resolved, again))) == ("BLOCKER_OPEN",)


def test_a_finding_of_a_foreign_review_is_refused() -> None:
    with pytest.raises(SkmError) as caught:
        decide(findings=(make_finding(1, Severity.NIT, FindingState.OPEN, review_id=uid(699)),))
    assert caught.value.code is ErrorCode.SCHEMA_INVALID


def test_outside_write_scope_is_cleared_only_by_an_accepted_scope_finding() -> None:
    output = make_output(outside=("docs/other.md",))
    scope = make_finding(
        6, Severity.MAJOR, FindingState.WAIVED, category=WRITE_SCOPE_CATEGORY, path="docs/other.md"
    )
    # without the human deviation the waived scope finding is still an open major finding
    assert codes(decide(output=output, findings=(scope,))) == ("REVIEW_NOT_GREEN", "WRITE_SCOPE_VIOLATION")
    accepted = (deviation("finding", finding_id=scope.id),)
    assert isinstance(decide(output=output, findings=(scope,), deviations=accepted), Accepted)


# --- the decision record ----------------------------------------------------------------------------


def test_acceptance_decision_is_immutable_and_carries_no_commit() -> None:
    result = decide()
    decision = record_acceptance(
        result,
        clearance=ReviewClearance.GREEN,
        decision_id=uid(990),
        task=make_task(),
        attempt=make_attempt(),
        output=make_output(),
        actor_id=uid(1),
        now=NOW,
    )
    assert decision.decision == "accepted"
    assert {field.name for field in dataclasses.fields(AcceptanceDecision)} == {
        "id", "workspace_id", "run_id", "task_id", "attempt_id", "output_id", "decision", "actor_id",
        "basis", "decided_at",
    }  # fmt: skip
    with pytest.raises(dataclasses.FrozenInstanceError):
        decision.decision = "rejected"  # type: ignore[misc]
    rejected = record_acceptance(
        decide(budget_ok=False),
        clearance=ReviewClearance.GREEN,
        decision_id=uid(991),
        task=make_task(),
        attempt=make_attempt(),
        output=make_output(),
        actor_id=uid(1),
        now=NOW,
    )
    assert rejected.decision == "rejected"
    assert rejected.basis.reasons == ("BUDGET_EXHAUSTED",)
    with pytest.raises(SkmError):
        dataclasses.replace(decision, decision="rejected")
    # the decision is a fact about the output, not the terminal accepted status of the task
    assert make_task().status is TaskStatus.INTEGRATING


# --- check states ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("inputs", "expected"),
    [
        ((CheckKind.COMMAND, 0, False, "ENOENT", False), (CheckState.ERROR, ErrorCode.RUNTIME_CRASHED)),
        ((CheckKind.COMMAND, 0, True, None, False), (CheckState.ERROR, ErrorCode.RUNTIME_TIMEOUT)),
        ((CheckKind.COMMAND, None, False, None, True), (CheckState.UNKNOWN, None)),
        ((CheckKind.COMMAND, 0, False, None, False), (CheckState.PASSED, None)),
        ((CheckKind.SHELL, 2, False, None, False), (CheckState.FAILED, None)),
        ((CheckKind.MANUAL, None, False, None, False), (CheckState.MANUAL_PENDING, ErrorCode.MANUAL_PENDING)),
        ((CheckKind.EXTERNAL, None, False, None, False), (CheckState.UNKNOWN, None)),
    ],
)
def test_classify_check_result(inputs: tuple[Any, ...], expected: tuple[CheckState, Any]) -> None:
    assert classify_check_result(*inputs) == expected


def test_eight_check_states_and_their_transitions() -> None:
    assert {state.value for state in CheckState} == {
        "pending", "running", "passed", "failed", "manual_pending", "error", "cancelled", "unknown",
    }  # fmt: skip
    for state in (CheckState.PENDING, CheckState.RUNNING, CheckState.MANUAL_PENDING):
        assert CheckState.CANCELLED in CHECK_TRANSITIONS[state]
    for state in (CheckState.ERROR, CheckState.CANCELLED, CheckState.UNKNOWN):
        assert CHECK_TRANSITIONS[state] == frozenset()
    with pytest.raises(SkmError) as caught:
        transition_check(make_check(state=CheckState.ERROR, error_code="RUNTIME_CRASHED"), CheckState.PASSED)
    assert caught.value.code is ErrorCode.INVALID_TRANSITION
    with pytest.raises(SkmError):  # a command result is never flipped by a verdict
        transition_check(make_check(), CheckState.FAILED)
    with pytest.raises(SkmError):  # only a manual check waits for a human
        make_check(state=CheckState.MANUAL_PENDING)
    summary = check_summary("\n".join(f"line {n}" for n in range(500)))
    assert summary.endswith("line 499")
    assert "line 459" not in summary
    assert len(summary) <= 4000


# --- manual verdict history and the human gate -----------------------------------------------------


def pending_manual() -> CheckExecution:
    return make_check(CHECK_MANUAL, SPEC_MANUAL, kind=CheckKind.MANUAL, state=CheckState.MANUAL_PENDING)


def record(
    check: CheckExecution, history: tuple[ManualVerdict, ...], value: str, n: int, **changes: Any
) -> Any:
    values: dict[str, Any] = {
        "actor": HUMAN,
        "actor_roles": {"qa"},
        "required_role": "qa",
        "current_output_id": OUT,
        "verdict": value,
        "comment": f"verdict {n}",
        "supersedes_id": history[-1].id if history else None,
        "verdict_id": uid(n),
        "now": NOW + timedelta(minutes=n - 700),
    }
    values.update(changes)
    return record_manual_verdict(check, history, **values)


def test_pass_then_fail_keeps_both_verdicts_and_fails_acceptance() -> None:
    first, passed_check = record(pending_manual(), (), "pass", 700)
    assert passed_check.state is CheckState.PASSED
    second, failed_check = record(passed_check, (first,), "fail", 701)
    history = (first, second)
    assert (second.supersedes_id, first.verdict) == (first.id, "pass")
    assert current_verdict(history) == second
    assert current_verdict(tuple(reversed(history))) == second
    assert failed_check.state is CheckState.FAILED
    result = decide(checks=(make_check(), failed_check), manual={CHECK_MANUAL: current_verdict(history)})
    assert codes(result) == ("MANUAL_FAILED",)


@pytest.mark.parametrize("kind", [PrincipalKind.SERVICE, PrincipalKind.WORKER])
def test_only_a_trusted_human_records_a_verdict_or_accepts_a_deviation(kind: PrincipalKind) -> None:
    machine = Actor(uid(901), kind, "owner")
    with pytest.raises(SkmError) as caught:
        record(pending_manual(), (), "pass", 700, actor=machine)
    assert caught.value.code is ErrorCode.FORBIDDEN
    with pytest.raises(SkmError) as caught:
        accept_deviation(
            make_task(), actor=machine, scope="attention_verdict", criterion_id=None, finding_id=None,
            reason="fine", deviation_id=uid(960), now=NOW,
        )  # fmt: skip
    assert caught.value.code is ErrorCode.FORBIDDEN
    made = accept_deviation(
        make_task(), actor=HUMAN, scope="attention_verdict", criterion_id=None, finding_id=None,
        reason="fine", deviation_id=uid(960), now=NOW,
    )  # fmt: skip
    assert made.approved_by == HUMAN.principal_id
    with pytest.raises(SkmError):
        dataclasses.replace(made, reason=" ")


def test_verdict_needs_the_actor_role_the_current_output_and_the_current_head() -> None:
    with pytest.raises(SkmError) as caught:
        record(pending_manual(), (), "pass", 700, actor_roles=set())
    assert caught.value.code is ErrorCode.FORBIDDEN
    with pytest.raises(SkmError) as caught:
        record(pending_manual(), (), "pass", 700, current_output_id=OUT_A)
    assert caught.value.code is ErrorCode.INVALID_TRANSITION
    first, passed_check = record(pending_manual(), (), "pass", 700)
    with pytest.raises(SkmError) as caught:
        record(passed_check, (first,), "fail", 701, supersedes_id=None)
    assert caught.value.code is ErrorCode.VERSION_CONFLICT
    with pytest.raises(SkmError) as caught:
        record(make_check(), (), "pass", 700)
    assert caught.value.code is ErrorCode.INVALID_TRANSITION


def test_a_broken_supersedes_chain_is_never_guessed() -> None:
    root = verdict("pass", n=700)
    fork_a = verdict("fail", n=701, supersedes_id=root.id)
    fork_b = verdict("pass", n=702, supersedes_id=root.id)
    for broken in (
        (root, fork_a, fork_b),
        (fork_a,),
        (root, verdict("fail", n=703)),
        (root, verdict(check_id=uid(1), n=704, supersedes_id=root.id)),
    ):
        with pytest.raises(SkmError) as caught:
            current_verdict(broken)
        assert caught.value.code is ErrorCode.SCHEMA_INVALID
    early = verdict("fail", n=705, supersedes_id=root.id, recorded_at=NOW - timedelta(minutes=1))
    with pytest.raises(SkmError):
        current_verdict((root, early))
    assert current_verdict(()) is None


# --- freshness ------------------------------------------------------------------------------------------


def test_freshness_of_a_review_for_an_output() -> None:
    review = make_review(output_id=OUT_A)
    later, earlier = make_output(seq=2), make_output(OUT_A, seq=1)
    assert freshness_of(make_review(), make_output()) is Freshness.FRESH
    assert freshness_of(review, later) is Freshness.STALE
    assert freshness_of(review, later, reviewed=earlier) is Freshness.STALE
    assert freshness_of(review, later, reviewed=earlier, corrected_only=True) is Freshness.FINDINGS_ONLY
    # H7 without the reviewed output, or with an output that is not earlier, proves nothing
    assert freshness_of(review, later, corrected_only=True) is Freshness.STALE
    assert (
        freshness_of(review, later, reviewed=make_output(OUT_A, seq=2), corrected_only=True)
        is Freshness.STALE
    )
    assert freshness_of(review, later, reviewed=make_output(uid(302)), corrected_only=True) is Freshness.STALE
    assert (
        freshness_of(make_review(attempt_id=uid(201)), later, reviewed=earlier, corrected_only=True)
        is Freshness.STALE
    )
    with pytest.raises(SkmError):
        make_review(freshness=Freshness.STALE)
