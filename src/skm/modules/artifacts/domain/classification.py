"""Classification order and the monotonic floor of derived artifacts (artifacts §4.2a, ARTIFACT-01/02/05)."""

from collections.abc import Iterable
from enum import StrEnum

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed

__all__ = [
    "Classification",
    "allowed_for_runtime",
    "derived_floor",
    "ensure_not_lowered",
    "max_classification",
]


class Classification(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


_ORDER = tuple(Classification)


def _rank(value: Classification) -> int:
    return _ORDER.index(value)


def max_classification(a: Classification, b: Classification) -> Classification:
    return a if _rank(a) >= _rank(b) else b


def allowed_for_runtime(c: Classification, limit: Classification) -> bool:
    return _rank(c) <= _rank(limit)


def ensure_not_lowered(current: Classification, new: Classification) -> Classification:
    """Classification only rises; there is no declassification in v2.0 (§4.2a)."""
    if _rank(new) < _rank(current):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "classification cannot be lowered",
            details={
                "field": "classification",
                "reason": "declassification",
                "current": current.value,
                "requested": new.value,
            },
        )
    return new


def derived_floor(
    *,
    requested: Classification,
    sources: Iterable[Classification | None],
    admission_floor: Classification | None = None,
) -> Classification:
    """``max(requested, every used source, admission floor)``.

    Redaction, summary, translation or a clean safety scan never lower it. A source with unknown
    classification (``None``) is not replaced by ``internal``: the floor is not established, so it is refused.
    """
    floor = requested
    for source in sources:
        if source is None:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "source classification is unknown; the floor of a derived artifact is not established",
                details={"field": "classification", "reason": "unknown_lineage"},
            )
        floor = max_classification(floor, source)
    if admission_floor is not None:
        floor = max_classification(floor, admission_floor)
    return floor
