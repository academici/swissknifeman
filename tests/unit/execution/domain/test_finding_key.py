"""Stable finding key and logical findings (execution §5.8, D-EX-4)."""

from __future__ import annotations

import dataclasses
import re
from typing import Any
from uuid import UUID

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.modules.execution.domain.finding import (
    SEVERITY_RANK,
    Finding,
    FindingState,
    Severity,
    finding_key,
    logical_findings,
    normalize,
    place,
)

LOCATION: dict[str, Any] = {"mount": "api", "path": "src/auth/rotation.py", "line_start": 41, "line_end": 44}
SCENARIO = "On a node whose clock runs 2 minutes behind, an expired token is rotated."


def uid(n: int) -> Any:
    return UUID(int=n)


def key(
    location: dict[str, Any] = LOCATION, category: str = "time", scenario: str = SCENARIO, message: str = "m"
) -> str:
    return finding_key(location, category, scenario, message)


def test_key_format() -> None:
    assert re.fullmatch(r"fk-[0-9a-f]{16}", key())


def test_key_ignores_severity_confidence_line_and_local_id() -> None:
    base = key()
    assert key({**LOCATION, "line_start": 7, "line_end": 9}) == base
    assert key({"mount": "api", "path": "src/auth/rotation.py"}) == base
    first = make(1, Severity.BLOCKER, "high")
    second = make(7, Severity.MINOR, "low")
    assert first.finding_key == second.finding_key == base


def test_key_changes_with_file_category_or_essence() -> None:
    base = key()
    assert key({**LOCATION, "path": "src/auth/other.py"}) != base
    assert key({**LOCATION, "mount": "web"}) != base
    assert key(category="security/token") != base
    assert key(scenario="An expired token is accepted by the refresh endpoint.") != base


def test_key_normalization() -> None:
    base = key()
    assert (
        key(scenario="  on a NODE whose clock runs 5 minutes behind — an expired token is rotated!! ") == base
    )
    assert key({**LOCATION, "path": "./src\\auth\\rotation.py "}) == base
    assert key(category="  TIME ") == base
    assert normalize("A_b,  c-3d!") == "a b c d"
    assert len(normalize("x " * 500)) <= 160
    assert (place(""), place("./././a")) == ("-", "a")


def test_message_stands_in_only_for_an_empty_scenario() -> None:
    assert key(scenario="  ", message="Expiry uses the local clock") == key(
        scenario="", message="expiry uses the local clock."
    )
    assert key(message="other message") == key()


def make(
    n: int, severity: Severity, confidence: str, *, review: int = 600, state: FindingState = FindingState.OPEN
) -> Finding:
    return Finding(
        id=uid(800 + n),
        review_id=uid(review),
        local_id=f"F{n}",
        finding_key=key({**LOCATION, "line_start": n}),
        severity=severity,
        confidence=confidence,  # type: ignore[arg-type]
        basis="correctness",
        category="time",
        message="m",
        failure_scenario=SCENARIO,
        location={**LOCATION, "line_start": n},
        reproduction=None,
        first_seen_review_id=uid(600),
        state=state,
    )


def test_lowered_severity_keeps_the_key_so_drift_is_visible() -> None:
    before = make(1, Severity.MAJOR, "high", review=600, state=FindingState.CONFIRMED)
    after = make(2, Severity.MINOR, "high", review=601, state=FindingState.CONFIRMED)
    (logical,) = logical_findings([before, after], {uid(600): 1, uid(601): 2})
    assert logical == after
    assert before.finding_key == after.finding_key
    assert SEVERITY_RANK[after.severity] < SEVERITY_RANK[before.severity]  # a lowering, not a new defect


def test_logical_finding_is_the_latest_round_and_foreign_rows_are_refused() -> None:
    first = make(1, Severity.BLOCKER, "high", review=600, state=FindingState.CONFIRMED)
    later = dataclasses.replace(make(2, Severity.BLOCKER, "high", review=601), state=FindingState.RESOLVED)
    assert logical_findings([later, first], {uid(600): 1, uid(601): 2}) == (later,)
    with pytest.raises(SkmError) as caught:
        logical_findings([first], {uid(601): 2})
    assert caught.value.code is ErrorCode.SCHEMA_INVALID
    twin = make(3, Severity.NIT, "low", review=600)
    with pytest.raises(SkmError):
        logical_findings([first, twin], {uid(600): 1})


def test_finding_row_invariants() -> None:
    with pytest.raises(SkmError):
        dataclasses.replace(make(1, Severity.NIT, "low"), finding_key="fk-xyz")
    with pytest.raises(SkmError):
        dataclasses.replace(make(1, Severity.NIT, "low"), local_id="X1")
