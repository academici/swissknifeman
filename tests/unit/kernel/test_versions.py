"""Optimistic concurrency checks keep both versions in the conflict."""

from typing import Any

import pytest

from skm.kernel.error_codes import ErrorCategory, ErrorCode
from skm.kernel.errors import Conflict
from skm.kernel.versions import ExpectedVersion, check_expected, expected_version_from


def test_no_expectation_checks_nothing() -> None:
    check_expected(7, None)
    check_expected(1, expected_version_from(None))


def test_matching_version_passes() -> None:
    check_expected(3, ExpectedVersion(3))


@pytest.mark.parametrize(("actual", "expected"), [(4, 3), (2, 3), (1, 2)])
def test_mismatch_is_version_conflict_with_actual_and_expected(actual: int, expected: int) -> None:
    with pytest.raises(Conflict) as raised:
        check_expected(actual, ExpectedVersion(expected))
    error = raised.value
    assert error.code is ErrorCode.VERSION_CONFLICT
    assert error.category is ErrorCategory.CONFLICT
    assert dict(error.details) == {"expected": expected, "actual": actual}
    assert error.to_problem()["details"] == {"expected": expected, "actual": actual}
    assert str(expected) in error.message
    assert str(actual) in error.message
    assert error.retryable is False


@pytest.mark.parametrize("value", [0, -1])
def test_expected_version_must_be_at_least_one(value: int) -> None:
    with pytest.raises(ValueError, match=">= 1"):
        ExpectedVersion(value)


@pytest.mark.parametrize("value", [True, 1.0, "1"])
def test_expected_version_must_be_an_int(value: object) -> None:
    bad: Any = value
    with pytest.raises(TypeError):
        ExpectedVersion(bad)


def test_expected_version_from_wraps_and_validates() -> None:
    assert expected_version_from(5) == ExpectedVersion(5)
    with pytest.raises(ValueError, match=">= 1"):
        expected_version_from(0)
