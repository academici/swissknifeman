"""Review profile, dynamic review and re-review scope (execution §4.2.1, §5.9).

The verification intensity changes only the depth of investigation: never the required review, its
independence, the security profile on risk or a waiver.
"""

from __future__ import annotations

import dataclasses
from typing import Any
from uuid import UUID

import pytest

from skm.modules.execution.domain.finding import Finding, FindingState, Severity, finding_key
from skm.modules.execution.domain.review import choose_review_profile
from skm.modules.execution.domain.review_strategy import decide_review, followup_findings, rereview_scope
from skm.modules.execution.domain.risk import RiskFacts, score
from skm.modules.execution.domain.task import PathPattern, ReviewMode, Task, TaskKind, TaskStatus


def uid(n: int) -> Any:
    return UUID(int=n)


def make_task(**changes: Any) -> Task:
    values: dict[str, Any] = {
        "id": uid(100),
        "run_id": uid(1),
        "workspace_id": uid(2),
        "kind": TaskKind.UNIT,
        "spec_entity_id": uid(3),
        "display_key": "P1.1/U1",
        "origin": None,
        "position": 0,
        "status": TaskStatus.CHECKING,
        "work_kind": "code",
        "review_mode": ReviewMode.SELF,
        "review_profile": None,
        "declared_write_scope": (PathPattern("app", "src/app/**"),),
        "required_host_id": None,
        "current_attempt_id": uid(200),
        "accepted_attempt_id": None,
        "accepted_output_id": None,
        "check_fix_rounds": 0,
        "review_rounds": 0,
        "attempt_count": 1,
        "blocking_reason": None,
        "row_version": 1,
    }
    values.update(changes)
    return Task(**values)


def risk_of(*changed: str, **changes: Any) -> Any:
    values: dict[str, Any] = {
        "changed": changed,
        "outside": (),
        "diff_lines": 1,
        "red_first": False,
        "deviation": False,
        "recommended": False,
    }
    values.update(changes)
    return score(RiskFacts(**values), {})


SECURITY_RISK = risk_of("src/auth/login.py")
LOW_RISK = risk_of("src/app/x.py")


def test_revision_profile_then_config_then_default() -> None:
    assert choose_review_profile(make_task(review_profile="reviewer-strict"), {}) == "reviewer-strict"
    assert choose_review_profile(make_task(), {"review_profile": "code-review"}) == "code-review"
    assert choose_review_profile(make_task(), {}) == "reviewer"


def test_security_profile_by_risk_or_task_path() -> None:
    assert choose_review_profile(make_task(), {}, SECURITY_RISK) == "security"
    assert choose_review_profile(make_task(review_profile="custom"), {}, SECURITY_RISK) == "security"
    assert choose_review_profile(make_task(), {}, LOW_RISK, ["src/app/secrets.py"]) == "security"
    scoped = make_task(declared_write_scope=(PathPattern("app", "src/auth/**"),))
    assert choose_review_profile(scoped, {}) == "security"
    assert choose_review_profile(make_task(), {"security_review_on_risk": False}, SECURITY_RISK) == "reviewer"
    custom: dict[str, Any] = {"risk_patterns": {"security": ["src/app/vault/**"]}}
    assert choose_review_profile(make_task(), custom, None, ["src/app/vault/k.py"]) == "security"


@pytest.mark.parametrize("intensity", ["light", "medium", "heavy"])
def test_intensity_changes_only_the_investigation(intensity: str) -> None:
    required = make_task(review_mode=ReviewMode.REQUIRED)
    decision = decide_review(
        required,
        {},
        risk=LOW_RISK,
        review_req={"independence": "separate_runtime"},
        verification_intensity=intensity,
    )
    assert (decision.required, decision.profile, decision.independence) == (
        True,
        "reviewer",
        "separate_runtime",
    )
    assert decision.investigation == intensity
    secure = decide_review(make_task(), {}, risk=SECURITY_RISK, verification_intensity=intensity)
    assert (secure.required, secure.profile, secure.dynamic) == (True, "security", True)
    waived = decide_review(
        make_task(review_mode=ReviewMode.WAIVED), {}, risk=SECURITY_RISK, verification_intensity=intensity
    )
    assert waived.required is False  # a human waiver is never overridden by dynamic review
    for task, risk in ((required, LOW_RISK), (make_task(), SECURITY_RISK), (make_task(), LOW_RISK)):
        light = decide_review(task, {}, risk=risk, verification_intensity="light")
        heavy = decide_review(task, {}, risk=risk, verification_intensity="heavy")
        assert dataclasses.replace(light, investigation="heavy") == heavy


def test_dynamic_review_by_score_threshold_and_strategy() -> None:
    risky = risk_of("src/app/x.py", recommended=True, deviation=True, red_first=True)
    added = decide_review(make_task(), {"risk_threshold": 50}, risk=risky)
    assert (added.required, added.dynamic, added.diagnostics) == (True, True, ("DYNAMIC_REVIEW_ADDED",))
    assert decide_review(make_task(), {"risk_threshold": 60}, risk=risky).required is False
    per_task = decide_review(make_task(), {"review_strategy": "per_task", "risk_threshold": 0}, risk=risky)
    assert per_task.required is False
    assert decide_review(make_task(), {}, risk=None).required is False


def test_rereview_of_a_corrected_finding_stays_corrected_without_widening() -> None:
    corrected = rereview_scope(
        2,
        configured="corrected",
        is_range=False,
        changed_paths=["src/app/x.py", "tests/test_x.py"],
        finding_paths=["src/app/x.py", "src/app/y.py"],
        allowed=["tests/**"],
    )
    assert corrected == ("corrected", ("src/app/x.py", "src/app/y.py", "tests/test_x.py"))
    widened = rereview_scope(
        2,
        configured="corrected",
        is_range=False,
        changed_paths=["src/other.py"],
        finding_paths=["src/app/x.py"],
    )
    assert widened == ("full", ())
    assert rereview_scope(1, configured="corrected", is_range=False, changed_paths=[], finding_paths=[]) == (
        "full",
        (),
    )
    assert (
        rereview_scope(3, configured="full", is_range=False, changed_paths=[], finding_paths=[])[0] == "full"
    )
    assert (
        rereview_scope(2, configured="corrected", is_range=True, changed_paths=[], finding_paths=[])[0]
        == "range"
    )


def _finding(n: int, severity: Severity, state: FindingState) -> Finding:
    location: dict[str, Any] = {"mount": "app", "path": f"src/{n}.py"}
    return Finding(
        id=uid(800 + n),
        review_id=uid(600),
        local_id=f"F{n}",
        finding_key=finding_key(location, "logic", f"scenario {chr(97 + n)}", "m"),
        severity=severity,
        confidence="high",
        basis="correctness",
        category="logic",
        message="m",
        failure_scenario=f"scenario {chr(97 + n)}",
        location=location,
        reproduction=None,
        first_seen_review_id=uid(600),
        state=state,
    )


def test_followups_are_confirmed_major_or_blocker_and_capped() -> None:
    findings = [
        _finding(1, Severity.MAJOR, FindingState.CONFIRMED),
        _finding(2, Severity.BLOCKER, FindingState.CONFIRMED),
        _finding(3, Severity.MINOR, FindingState.CONFIRMED),
        _finding(4, Severity.MAJOR, FindingState.REJECTED),
        _finding(5, Severity.MAJOR, FindingState.OPEN),
        _finding(6, Severity.MAJOR, FindingState.DEFERRED),
    ]
    chosen = followup_findings(findings, {})
    assert chosen[0].local_id == "F2"
    assert {finding.local_id for finding in chosen} == {"F1", "F2", "F6"}
    assert len(followup_findings(findings, {"followups_max": 1})) == 1
