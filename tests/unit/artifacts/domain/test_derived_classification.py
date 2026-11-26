import pytest

from skm.kernel.errors import ValidationFailed
from skm.modules.artifacts.domain.classification import (
    Classification as C,
)
from skm.modules.artifacts.domain.classification import (
    allowed_for_runtime,
    derived_floor,
    ensure_not_lowered,
    max_classification,
)


def test_order_is_significant() -> None:
    assert max_classification(C.PUBLIC, C.RESTRICTED) is C.RESTRICTED
    assert max_classification(C.CONFIDENTIAL, C.INTERNAL) is C.CONFIDENTIAL
    assert allowed_for_runtime(C.INTERNAL, C.CONFIDENTIAL)
    assert not allowed_for_runtime(C.RESTRICTED, C.CONFIDENTIAL)


def test_derived_summary_of_confidential_stays_confidential() -> None:
    assert derived_floor(requested=C.PUBLIC, sources=[C.CONFIDENTIAL, C.INTERNAL]) is C.CONFIDENTIAL


def test_requested_and_admission_floor_can_only_raise() -> None:
    assert derived_floor(requested=C.RESTRICTED, sources=[C.PUBLIC]) is C.RESTRICTED
    assert derived_floor(requested=C.PUBLIC, sources=[], admission_floor=C.INTERNAL) is C.INTERNAL


def test_unknown_lineage_is_not_defaulted_to_internal() -> None:
    with pytest.raises(ValidationFailed) as e:
        derived_floor(requested=C.PUBLIC, sources=[C.PUBLIC, None])
    assert e.value.details["reason"] == "unknown_lineage"


def test_no_lowering() -> None:
    with pytest.raises(ValidationFailed):
        ensure_not_lowered(C.CONFIDENTIAL, C.PUBLIC)
    assert ensure_not_lowered(C.INTERNAL, C.INTERNAL) is C.INTERNAL
