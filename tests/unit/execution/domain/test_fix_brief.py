"""Deterministic fix brief (execution §5.9 G4)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from functools import cache
from typing import Any, Literal
from uuid import UUID

import pytest

from skm.kernel.errors import SkmError
from skm.modules.execution.domain.check_execution import CheckExecution, CheckKind, CheckState
from skm.modules.execution.domain.finding import Finding, FindingState, Severity, finding_key
from skm.modules.execution.domain.fix_brief import (
    CheckLog,
    TriageNote,
    build_fix_brief,
    fix_brief_to_json,
)
from skm.platform.schema.registry import SchemaRegistry

URN = "urn:skm:execution:fix-brief:v1"
NOW = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
REPORT: Any = UUID(int=9032)
LOG: Any = UUID(int=9031)


@cache
def registry() -> SchemaRegistry:
    return SchemaRegistry.load_default()


def uid(n: int) -> Any:
    return UUID(int=n)


def finding(
    n: int,
    severity: Severity = Severity.MAJOR,
    *,
    confidence: str = "high",
    state: FindingState = FindingState.CONFIRMED,
    message: str = "message",
    scenario: str = "",
) -> Finding:
    location: dict[str, Any] = {"mount": "api", "path": f"src/m{n}.py", "line_start": n}
    text = scenario or f"scenario {n}"
    return Finding(
        id=uid(800 + n),
        review_id=uid(600),
        local_id=f"F{n}",
        finding_key=finding_key(location, "logic", text, message),
        severity=severity,
        confidence=confidence,  # type: ignore[arg-type]
        basis="correctness",
        category="logic",
        message=message,
        failure_scenario=text,
        location=location,
        reproduction={"argv": ["pytest", f"tests/test_{n}.py"], "expected_exit": 0},
        first_seen_review_id=uid(600),
        state=state,
    )


def triage(
    *findings: Finding, decision: Literal["fix_now", "defer"] = "fix_now", fix: str = "fix it"
) -> dict[str, TriageNote]:
    return {
        f.finding_key: TriageNote(decision, fix=fix, observed="boom", argv=("pytest", "-q"), exit_code=1)
        for f in findings
    }


def red_check(n: int = 1, *, required: bool = True, summary: str = "FAILED") -> CheckExecution:
    return CheckExecution(
        id=uid(500 + n),
        workspace_id=uid(2),
        run_id=uid(1),
        task_id=uid(100),
        attempt_id=uid(200),
        output_id=uid(300),
        check_spec_id=uid(400 + n),
        check_key=f"P2.1:V{n}",
        kind=CheckKind.COMMAND,
        required=required,
        state=CheckState.FAILED,
        exit_code=1,
        summary=summary,
        error_code=None,
        reused_from_id=None,
        fingerprint="sha256:" + "e" * 64,
        started_at=NOW,
        finished_at=NOW,
        round_no=1,
    )


def brief(
    findings: list[Finding],
    notes: dict[str, TriageNote],
    checks: Sequence[CheckExecution] = (),
    limits: dict[str, Any] | None = None,
    **changes: Any,
) -> Any:
    values: dict[str, Any] = {
        "brief_id": uid(170001),
        "task_id": uid(100),
        "attempt_id": uid(200),
        "source_review_id": uid(600),
        "source_check_round": None,
        "full_report_file_version_id": REPORT,
        "triage": notes,
    }
    values.update(changes)
    return build_fix_brief(findings, checks, limits or {}, **values)


def test_order_by_severity_confidence_and_key_and_only_triaged() -> None:
    items = [
        finding(1, Severity.MINOR),
        finding(2, Severity.BLOCKER, confidence="low"),
        finding(3, Severity.MAJOR, confidence="low"),
        finding(4, Severity.MAJOR, confidence="high"),
        finding(5, Severity.NIT),
    ]
    untriaged = finding(6, Severity.BLOCKER)
    deferred_by_triage = finding(7, Severity.MAJOR)
    rejected = finding(8, Severity.MAJOR, state=FindingState.REJECTED)
    notes = {**triage(*items, rejected), **triage(deferred_by_triage, decision="defer")}
    result = brief([*items, untriaged, deferred_by_triage, rejected], notes)
    assert [item.local_id for item in result.items] == ["F2", "F4", "F3", "F1", "F5"]
    assert (result.truncated, result.deferred_finding_keys) == (False, ())
    document = fix_brief_to_json(result)
    assert registry().validate(URN, document) == ()
    item = document["items"][0]  # type: ignore[index]
    assert item["reproduction"] == "pytest -q  (exit 1)"  # type: ignore[index]
    assert (item["observed"], item["fix"]) == ("boom", "fix it")  # type: ignore[index]


def test_blocker_is_never_left_out_beyond_the_limits() -> None:
    blockers = [finding(n, Severity.BLOCKER) for n in range(1, 4)]
    minors = [finding(n, Severity.MINOR) for n in range(4, 6)]
    result = brief([*blockers, *minors], triage(*blockers, *minors), limits={"max_findings": 2})
    assert {item.local_id for item in result.items} == {"F1", "F2", "F3"}
    assert set(result.deferred_finding_keys) == {f.finding_key for f in minors}
    assert result.truncated is True
    assert result.diagnostics == ("FIX_BRIEF_OVER",)


def test_findings_beyond_the_count_are_deferred_and_go_first_next_time() -> None:
    majors = [finding(n, Severity.MAJOR) for n in range(1, 5)]
    first = brief(majors, triage(*majors), limits={"max_findings": 2})
    assert (len(first.items), len(first.deferred_finding_keys)) == (2, 2)
    assert first.diagnostics == ()
    carried = [
        finding(n, Severity.MAJOR, state=FindingState.DEFERRED, confidence="low")
        for n in range(1, 5)
        if finding(n).finding_key in first.deferred_finding_keys
    ]
    fresh = [finding(n, Severity.MAJOR) for n in range(5, 8)]
    second = brief([*fresh, *carried], triage(*fresh, *carried), limits={"max_findings": 2})
    assert {item.finding_key for item in second.items} == {f.finding_key for f in carried}


def test_long_fields_are_clipped_with_a_marker_into_the_full_report() -> None:
    long = finding(1, Severity.MAJOR, message="x" * 5000)
    result = brief([long], triage(long, fix="y" * 3000))
    item = result.items[0]
    assert len(item.problem) <= 1200
    assert len(item.fix) <= 800
    assert f"full: file_version:{REPORT}#{long.finding_key}]" in item.problem
    assert item.problem.startswith("x")
    assert "clipped" in item.problem
    assert result.truncated is True
    assert sum(len(text) for text in (item.problem, item.fix, item.observed, item.reproduction)) <= 3000
    small = brief([long], triage(long, fix="y" * 3000), limits={"max_finding_chars": 1500}).items[0]
    assert len(small.problem) <= 600
    assert len(small.fix) <= 400


def test_two_megabyte_log_reaches_the_executor_only_as_a_short_tail() -> None:
    lines = [f"collected line {n} " + "z" * 40 for n in range(40000)]
    lines.append("FAILED tests/api/test_refresh.py::test_reuse - assert 200 == 401")
    log = "\n".join(lines)
    assert len(log.encode()) > 2_000_000
    result = brief(
        [],
        {},
        [red_check()],
        source_review_id=None,
        source_check_round=1,
        logs={uid(501): CheckLog(log, LOG)},
    )
    (check,) = result.checks
    assert check.tail_bytes <= 4000
    assert len(check.tail.encode()) == check.tail_bytes
    assert check.tail.endswith("assert 200 == 401")
    assert check.tail.startswith("… [clipped ")
    assert f"full: file_version:{LOG}" in check.tail
    assert len(check.tail.splitlines()) <= 41
    assert check.full_log_file_version_id == LOG
    assert result.truncated is True
    document = fix_brief_to_json(result)
    assert registry().validate(URN, document) == ()
    assert len(json.dumps(document).encode()) < 24000


def test_only_red_required_checks_enter_and_byte_limit_holds() -> None:
    result = brief(
        [], {}, [red_check(1), red_check(2, required=False)], source_review_id=None, source_check_round=1
    )
    assert [check.check_key for check in result.checks] == ["P2.1:V1"]
    assert (result.checks[0].tail, result.truncated) == ("FAILED", False)
    many = [finding(n, Severity.MINOR, message="w" * 1100) for n in range(1, 13)]
    capped = brief(many, triage(*many, fix="v" * 700), limits={"max_total_bytes": 6000})
    canonical = json.dumps(
        fix_brief_to_json(capped), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    assert len(canonical.encode()) <= 6000
    assert capped.deferred_finding_keys
    assert capped.truncated


def test_brief_is_deterministic_and_has_one_source() -> None:
    items = [finding(1), finding(2, Severity.BLOCKER)]
    first = brief(items, triage(*items))
    second = brief(list(reversed(items)), triage(*items))
    assert first == second
    assert first.digest.startswith("sha256:")
    assert len(first.digest) == 71
    other = brief(items, triage(*items, fix="another fix"))
    assert other.digest != first.digest
    with pytest.raises(SkmError):
        brief(items, triage(*items), source_check_round=1)
    with pytest.raises(SkmError):
        brief(items, triage(*items), source_review_id=None)


def document_size(result: Any) -> int:
    return len(
        json.dumps(
            fix_brief_to_json(result), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    )


@pytest.mark.parametrize("text", ["x" * 4000, ('quoted "\\\n' + "ёж") * 800], ids=["ascii", "escaped-utf8"])
def test_all_check_tails_share_the_whole_document_budget(text: str) -> None:
    checks = [red_check(n, summary=text[:4000]) for n in range(1, 8)]
    logs = {check.id: CheckLog(text, LOG) for check in checks}
    result = brief([], {}, checks, source_review_id=None, source_check_round=1, logs=logs)
    assert len(result.checks) == len(checks)
    assert {check.full_log_file_version_id for check in result.checks} == {LOG}
    assert all(check.tail_bytes == len(check.tail.encode()) <= 4000 for check in result.checks)
    assert document_size(result) <= 24000
    assert result.truncated
    assert result.diagnostics == ()
    assert result == brief(
        [], {}, list(reversed(checks)), source_review_id=None, source_check_round=1, logs=logs
    )


def test_check_summaries_without_logs_share_the_document_budget() -> None:
    result = brief(
        [],
        {},
        [red_check(n, summary="x" * 4000) for n in range(1, 8)],
        source_review_id=None,
        source_check_round=1,
    )
    assert len(result.checks) == 7
    assert document_size(result) <= 24000
    assert result.truncated
    assert result.diagnostics == ()


def test_checks_leave_room_for_blockers_and_cannot_cause_an_unjustified_overflow() -> None:
    blocker = finding(1, Severity.BLOCKER, message="b" * 5000)
    notes = {blocker.finding_key: TriageNote("fix_now", fix="f" * 800, observed="o" * 600, argv=("r" * 400,))}
    checks = [red_check(n, summary="x" * 4000) for n in range(1, 8)]
    result = brief([blocker], notes, checks, limits={"max_total_bytes": 6000})
    assert [item.finding_key for item in result.items] == [blocker.finding_key]
    assert len(result.checks) == 7
    assert document_size(result) <= 6000
    assert result.truncated
    assert result.diagnostics == ()
    over = brief([blocker], notes, checks, limits={"max_total_bytes": 4000})
    assert over.items == result.items
    assert len(over.checks) == 7
    assert over.diagnostics == ("FIX_BRIEF_OVER",)
    assert all(not check.tail for check in over.checks)


@pytest.mark.parametrize("with_blocker", [False, True])
def test_metadata_that_cannot_fit_is_refused_without_a_blocker_exception(with_blocker: bool) -> None:
    checks = [red_check(n) for n in range(1, 40)]
    findings = [finding(1, Severity.BLOCKER)] if with_blocker else []
    with pytest.raises(SkmError) as caught:
        brief(
            findings,
            triage(*findings),
            checks,
            limits={"max_total_bytes": 4000},
            source_review_id=None,
            source_check_round=1,
        )
    assert caught.value.code.value == "SCHEMA_INVALID"


def test_finding_markers_fit_the_minimum_supported_character_budget() -> None:
    long = finding(1, message="x" * 5000)
    note = TriageNote("fix_now", fix="f" * 5000, observed="o" * 5000, argv=("r" * 5000,))
    result = brief([long], {long.finding_key: note}, limits={"max_finding_chars": 500})
    fields = (
        result.items[0].problem,
        result.items[0].fix,
        result.items[0].observed,
        result.items[0].reproduction,
    )
    assert sum(map(len, fields)) <= 500
    assert all(f"full: file_version:{REPORT}#{long.finding_key}]" in text for text in fields)
    assert all(
        text.startswith(head) and text.endswith(tail)
        for text, head, tail in zip(fields, "xfor", "1for", strict=True)
    )
    assert result.truncated


@pytest.mark.parametrize("limit", [0, 1, 50, 100])
def test_small_inline_budget_keeps_log_references_without_partial_markers(limit: int) -> None:
    result = brief(
        [],
        {},
        [red_check()],
        limits={"max_inline_evidence_bytes": limit},
        source_review_id=None,
        source_check_round=1,
        logs={uid(501): CheckLog("x" * 5000, LOG)},
    )
    check = result.checks[0]
    assert check.tail_bytes <= limit
    assert check.full_log_file_version_id == LOG
    assert not check.tail or (
        check.tail.startswith("… [clipped ") and f"full: file_version:{LOG}]" in check.tail
    )
    assert result.truncated
