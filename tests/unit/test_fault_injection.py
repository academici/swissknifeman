"""Fault schedules distinguish pre-effect failures from lost post-effect responses."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from support.fault_injection import FaultPlan, FaultPoint, InjectedFault


@given(occurrence=st.integers(min_value=1, max_value=30))
def test_fault_fires_once_on_the_requested_passage(occurrence: int) -> None:
    point = FaultPoint.UOW_AFTER_COMMIT
    plan = FaultPlan({point: occurrence})
    for _ in range(occurrence - 1):
        plan.maybe_fail(point)
    with pytest.raises(InjectedFault) as error:
        plan.maybe_fail(point)
    assert error.value.point is point
    assert plan.hits[point] == occurrence
    plan.maybe_fail(point)
    assert plan.hits[point] == occurrence + 1


def test_points_and_plans_count_independently() -> None:
    first = FaultPoint.UOW_BEFORE_COMMIT
    second = FaultPoint.BLOB_AFTER_PROMOTE
    configured = {first: 2}
    plan = FaultPlan(configured)
    other = FaultPlan(configured)
    configured.clear()
    plan.maybe_fail(first)
    plan.maybe_fail(second)
    with pytest.raises(InjectedFault):
        plan.maybe_fail(first)
    other.maybe_fail(first)
    assert other.hits == {first: 1}
    assert plan.hits == {first: 2, second: 1}


@pytest.mark.parametrize("occurrence", [0, -1, True, 1.5])
def test_rejects_unreachable_or_ambiguous_occurrence(occurrence) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        FaultPlan({FaultPoint.VCS_AFTER_PUSH: occurrence})


def test_rejects_unknown_fault_points() -> None:
    with pytest.raises(ValueError, match="FaultPoint"):
        FaultPlan({"unknown": 1})  # type: ignore[dict-item]


@pytest.mark.parametrize("hits", [-1, True, 1.5])
def test_rejects_invalid_initial_hit_counts(hits) -> None:
    with pytest.raises(ValueError, match="nonnegative integers"):
        FaultPlan({}, hits={FaultPoint.UOW_BEFORE_COMMIT: hits})
