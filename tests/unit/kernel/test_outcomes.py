"""Diagnostics and waiting outcomes: values, validation and immutability."""

import dataclasses
from typing import Any
from uuid import UUID

import pytest

from skm.kernel.error_codes import CATALOG, ErrorCategory, ErrorCode
from skm.kernel.outcomes import Diagnostic, Severity, Waiting

WAITING = [code for code, info in CATALOG.items() if info.category is ErrorCategory.WAITING]
NOT_WAITING = [code for code, info in CATALOG.items() if info.category is not ErrorCategory.WAITING]


def test_severity_values() -> None:
    assert [item.value for item in Severity] == ["error", "warning", "info"]


def test_diagnostic_defaults_and_module_codes() -> None:
    plain = Diagnostic("PLAN_CYCLE_FOUND", "cycle", Severity.ERROR)
    assert plain.target is None
    assert dict(plain.details) == {}
    from_catalog = Diagnostic(ErrorCode.SCHEMA_INVALID, "bad", Severity.WARNING, target="/a/b")
    assert from_catalog.target == "/a/b"
    assert from_catalog.severity is Severity.WARNING


@pytest.mark.parametrize("code", ["", "plan_cycle", "1ST", "HAS SPACE", "DASH-ED", "lower"])
def test_diagnostic_code_must_be_upper_snake(code: str) -> None:
    with pytest.raises(ValueError, match="UPPER_SNAKE"):
        Diagnostic(code, "msg", Severity.INFO)


def test_diagnostic_is_frozen_and_copies_details() -> None:
    source: dict[str, Any] = {"path": ["a"]}
    diagnostic = Diagnostic("X_FOUND", "msg", Severity.INFO, details=source)
    source["path"].append("b")
    assert dict(diagnostic.details) == {"path": ["a"]}
    frozen: Any = diagnostic
    with pytest.raises(dataclasses.FrozenInstanceError):
        frozen.code = "OTHER"
    mutable: Any = diagnostic.details
    with pytest.raises(TypeError):
        mutable["x"] = 1


@pytest.mark.parametrize("code", WAITING, ids=lambda code: code.value)
def test_waiting_accepts_every_waiting_code(code: ErrorCode) -> None:
    request_id = UUID("00000000-0000-7000-8000-000000000042")
    outcome = Waiting(code, "wait", request_id=request_id, details={"who": "owner"})
    assert outcome.code is code
    assert outcome.request_id == request_id
    assert dict(outcome.details) == {"who": "owner"}


def test_waiting_accepts_a_plain_string_code_and_normalizes_it() -> None:
    plain: Any = "MANUAL_PENDING"
    assert Waiting(plain, "wait").code is ErrorCode.MANUAL_PENDING


@pytest.mark.parametrize("code", NOT_WAITING, ids=lambda code: code.value)
def test_waiting_rejects_codes_of_other_categories(code: ErrorCode) -> None:
    with pytest.raises(ValueError, match="waiting"):
        Waiting(code, "not a wait")


def test_waiting_is_frozen_and_has_no_request_id_by_default() -> None:
    outcome = Waiting(ErrorCode.APPROVAL_REQUIRED, "needs approval")
    assert outcome.request_id is None
    assert dict(outcome.details) == {}
    frozen: Any = outcome
    with pytest.raises(dataclasses.FrozenInstanceError):
        frozen.message = "other"


def test_waiting_is_not_an_exception() -> None:
    assert not issubclass(Waiting, BaseException)
