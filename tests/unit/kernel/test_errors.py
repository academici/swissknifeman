"""Structured errors: one subclass per catalog category, safe details, catalog-driven defaults."""

import math
from typing import Any

import pytest

from skm.kernel import errors
from skm.kernel.error_codes import CATALOG, ErrorCategory, ErrorCode
from skm.kernel.errors import (
    BackendUnavailable,
    CapabilityUnavailable,
    Conflict,
    Forbidden,
    InternalError,
    NotFound,
    OutcomeUnknown,
    PreconditionFailed,
    SkmError,
    Unauthenticated,
    ValidationFailed,
    error_for,
)

SUBCLASSES: dict[ErrorCategory, type[SkmError]] = {
    ErrorCategory.NOT_FOUND: NotFound,
    ErrorCategory.VALIDATION: ValidationFailed,
    ErrorCategory.CONFLICT: Conflict,
    ErrorCategory.PRECONDITION: PreconditionFailed,
    ErrorCategory.FORBIDDEN: Forbidden,
    ErrorCategory.UNAUTHENTICATED: Unauthenticated,
    ErrorCategory.CAPABILITY: CapabilityUnavailable,
    ErrorCategory.BACKEND: BackendUnavailable,
    ErrorCategory.OUTCOME_UNKNOWN: OutcomeUnknown,
    ErrorCategory.INTERNAL: InternalError,
}
THROWABLE = [code for code, info in CATALOG.items() if info.category is not ErrorCategory.WAITING]
WAITING = [code for code, info in CATALOG.items() if info.category is ErrorCategory.WAITING]


def test_every_non_waiting_category_has_exactly_one_subclass() -> None:
    assert set(SUBCLASSES) == set(ErrorCategory) - {ErrorCategory.WAITING}
    for category, cls in SUBCLASSES.items():
        assert cls.category is category
        assert issubclass(cls, SkmError)


@pytest.mark.parametrize("code", THROWABLE, ids=lambda code: code.value)
def test_error_for_builds_the_subclass_of_the_catalog_category(code: ErrorCode) -> None:
    error = error_for(code, "boom")
    assert type(error) is SUBCLASSES[CATALOG[code].category]
    assert error.code is code
    assert error.retryable is CATALOG[code].retryable


@pytest.mark.parametrize("code", WAITING, ids=lambda code: code.value)
def test_waiting_codes_are_outcomes_not_exceptions(code: ErrorCode) -> None:
    with pytest.raises(TypeError, match="outcome"):
        error_for(code, "waits")
    for cls in SUBCLASSES.values():
        with pytest.raises(TypeError):
            cls(code, "waits")


def test_a_code_of_another_category_is_a_programming_error() -> None:
    with pytest.raises(TypeError, match="VERSION_CONFLICT"):
        NotFound(ErrorCode.VERSION_CONFLICT, "wrong class")
    with pytest.raises(TypeError, match="NOT_FOUND"):
        Conflict(ErrorCode.NOT_FOUND, "wrong class")


def test_the_base_class_is_not_instantiable() -> None:
    with pytest.raises(TypeError, match="no error category"):
        SkmError(ErrorCode.INTERNAL_ERROR, "abstract")


def test_unknown_code_is_rejected() -> None:
    bad: Any = "NO_SUCH_CODE"
    with pytest.raises(ValueError, match="NO_SUCH_CODE"):
        NotFound(bad, "unknown")


def test_to_problem_has_the_wire_shape() -> None:
    error = NotFound(
        ErrorCode.NOT_FOUND, "no such plan", details={"kind": "plan", "ref": "p-1", "n": [1, None]}
    )
    assert error.to_problem() == {
        "code": "NOT_FOUND",
        "message": "no such plan",
        "details": {"kind": "plan", "ref": "p-1", "n": [1, None]},
        "retryable": False,
    }
    assert list(error.to_problem()) == ["code", "message", "details", "retryable"]
    assert NotFound(ErrorCode.NOT_FOUND, "x").to_problem()["details"] == {}


def test_retryable_defaults_from_the_catalog_and_can_be_overridden() -> None:
    assert BackendUnavailable(ErrorCode.BACKEND_UNAVAILABLE, "db down").retryable is True
    assert NotFound(ErrorCode.NOT_FOUND, "gone").retryable is False
    assert BackendUnavailable(ErrorCode.BACKEND_UNAVAILABLE, "db down", retryable=False).retryable is False
    assert NotFound(ErrorCode.NOT_FOUND, "gone", retryable=True).to_problem()["retryable"] is True


def test_str_is_code_and_message() -> None:
    error = Forbidden(ErrorCode.FORBIDDEN, "no right", details={"permission": "plan.write"})
    assert str(error) == "FORBIDDEN: no right"
    assert error.args[0] is ErrorCode.FORBIDDEN


def test_details_are_an_immutable_copy() -> None:
    source: dict[str, Any] = {"items": [1, 2], "nested": {"a": 1}}
    error = Conflict(ErrorCode.ALREADY_EXISTS, "dup", details=source)
    source["items"].append(3)
    source["nested"]["a"] = 2
    source["extra"] = True
    assert dict(error.details) == {"items": [1, 2], "nested": {"a": 1}}
    mutable: Any = error.details
    with pytest.raises(TypeError):
        mutable["new"] = 1
    problem_details: Any = error.to_problem()["details"]
    problem_details["items"].append(99)
    assert dict(error.details) == {"items": [1, 2], "nested": {"a": 1}}


@pytest.mark.parametrize(
    "details",
    [
        {"obj": object()},
        {"deep": {"list": [1, {"bad": {1, 2}}]}},
        {"bytes": b"secret"},
        {"nan": math.nan},
        {"inf": math.inf},
        {"tuple": (1, 2)},
        {"nested": {1: "non-string key"}},
    ],
    ids=["object", "set-in-list", "bytes", "nan", "inf", "tuple", "int-key"],
)
def test_details_accept_only_json_values(details: Any) -> None:
    with pytest.raises(TypeError, match="details"):
        ValidationFailed(ErrorCode.SCHEMA_INVALID, "bad", details=details)


def test_a_secret_object_never_reaches_the_error_text() -> None:
    class Token:
        def __repr__(self) -> str:  # pyright: ignore[reportImplicitOverride]
            return "Token(hunter2)"

    with pytest.raises(TypeError) as raised:
        Unauthenticated(ErrorCode.UNAUTHENTICATED, "bad token", details={"token": Token()})  # pyright: ignore[reportArgumentType]
    assert "hunter2" not in str(raised.value)


def test_the_cause_and_secondary_failures_are_kept() -> None:
    cause = OSError("disk")

    def fail() -> None:
        try:
            raise cause
        except OSError as os_error:
            raise BackendUnavailable(ErrorCode.BACKEND_UNAVAILABLE, "storage failed") from os_error

    with pytest.raises(SkmError) as raised:
        fail()
    error = raised.value
    error.add_secondary("rollback failed: ConnectionError")
    assert error.__cause__ is cause
    assert error.__notes__ == ["rollback failed: ConnectionError"]
    assert str(error) == "BACKEND_UNAVAILABLE: storage failed"


def test_public_names_are_all_exported() -> None:
    assert set(errors.__all__) == {cls.__name__ for cls in SUBCLASSES.values()} | {"SkmError", "error_for"}
