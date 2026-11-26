"""Review requirement union and its document form (planning §4.2)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, cast

from skm.modules.planning.domain.reads import compact

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Literal

    from skm.kernel.json_types import JsonObject, JsonValue


class ReviewMode(StrEnum):
    REQUIRED = "required"
    SELF = "self"
    WAIVED = "waived"


type Reviewer = JsonObject


@dataclass(frozen=True, slots=True)
class RequiredReview:
    profile: str | None
    independence: Literal["separate_session", "separate_runtime", "human"]
    reviewer: Reviewer | None
    max_rounds: int | None
    covers: tuple[str, ...]
    required_evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SelfReview:
    reason: str


@dataclass(frozen=True, slots=True)
class WaivedReview:
    reason: str
    waived_by: str


type ReviewRequirement = RequiredReview | SelfReview | WaivedReview


def review_from_doc(doc: Mapping[str, JsonValue]) -> ReviewRequirement:
    match ReviewMode(str(doc["mode"])):
        case ReviewMode.REQUIRED:
            profile, reviewer, max_rounds = doc.get("profile"), doc.get("reviewer"), doc.get("max_rounds")
            return RequiredReview(
                profile=None if profile is None else str(profile),
                independence=cast(
                    "Literal['separate_session', 'separate_runtime', 'human']",
                    doc.get("independence", "separate_session"),
                ),
                reviewer=cast("JsonObject", reviewer) if reviewer is not None else None,
                max_rounds=None if max_rounds is None else int(cast("int", max_rounds)),
                covers=tuple(str(v) for v in cast("list[JsonValue]", doc.get("covers", []))),
                required_evidence=tuple(
                    str(v) for v in cast("list[JsonValue]", doc.get("required_evidence", []))
                ),
            )
        case ReviewMode.SELF:
            return SelfReview(str(doc["reason"]))
        case ReviewMode.WAIVED:
            return WaivedReview(str(doc["reason"]), str(doc["waived_by"]))


def review_to_doc(review: ReviewRequirement) -> JsonObject:
    match review:
        case RequiredReview():
            return compact(
                {
                    "mode": "required",
                    "profile": review.profile,
                    "independence": review.independence,
                    "reviewer": review.reviewer,
                    "max_rounds": review.max_rounds,
                    "covers": list(review.covers),
                    "required_evidence": list(review.required_evidence),
                }
            )
        case SelfReview():
            return {"mode": "self", "reason": review.reason}
        case WaivedReview():
            return {"mode": "waived", "reason": review.reason, "waived_by": review.waived_by}
