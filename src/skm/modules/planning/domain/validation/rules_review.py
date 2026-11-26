"""Review rules (planning §5.7, module ``review``)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from skm.modules.planning.domain.review_requirement import RequiredReview
from skm.modules.planning.domain.validation.context import Locator
from skm.modules.planning.domain.validation.findings import FindingCode, finding

if TYPE_CHECKING:
    from collections.abc import Iterator

    from skm.modules.planning.domain.validation.context import ValidationContext
    from skm.modules.planning.domain.validation.findings import Finding


def review_reviewer_unset(ctx: ValidationContext) -> Iterator[Finding]:
    loc = Locator(ctx.document)
    for item in ctx.spec.items:
        review = item.review
        if isinstance(review, RequiredReview) and review.reviewer is None and review.max_rounds is None:
            yield finding(
                FindingCode.REVIEW_REVIEWER_UNSET,
                f"required review of {item.key} names no reviewer and no round limit; run defaults apply",
                key=item.key,
                entity_id=item.id,
                pointer=loc.pointer(item.key, "review"),
            )


RULES: Final = (review_reviewer_unset,)
