"""Review and append-only proposal projections."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal, NewType
from uuid import UUID

from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.ids import PrincipalId, ScopeId
from skm.modules.knowledge.public import LessonKind

from .activity import ActivityRecordId
from .candidate import CandidateId, ReviewStatus
from .promotion import require_human

CandidateProposalId = NewType("CandidateProposalId", UUID)

CandidateReviewId = NewType("CandidateReviewId", UUID)


class ReviewVerdict(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    EDIT = "edit"
    COMMENT = "comment"


@dataclass(frozen=True, slots=True)
class CandidateReview:
    id: CandidateReviewId
    candidate_id: CandidateId
    reviewer_id: PrincipalId
    reviewer_kind: PrincipalKind
    verdict: ReviewVerdict
    note: str | None
    edited_trigger: str | None
    edited_action: str | None
    edited_kind: LessonKind | None
    proposal_id: CandidateProposalId | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class CandidateProposal:
    id: CandidateProposalId
    scope_id: ScopeId
    candidate_id: CandidateId
    source_candidate_id: CandidateId
    source_activity_id: ActivityRecordId
    source_key: str
    observed_at: datetime
    received_at: datetime
    kind: LessonKind
    trigger: str
    action: str
    fingerprint: str
    detector_version: str
    relation: Literal["update", "conflict"]


def validate_review(
    actor: Actor,
    verdict: ReviewVerdict,
    *,
    proposal_id: CandidateProposalId | None = None,
) -> None:
    if verdict in (ReviewVerdict.EDIT, ReviewVerdict.REJECT):
        require_human(actor)
    elif proposal_id is not None:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Only edit or reject can address a proposal")


def review_status(reviews: Iterable[CandidateReview]) -> ReviewStatus:
    latest = max(
        (
            review
            for review in reviews
            if review.reviewer_kind is PrincipalKind.HUMAN
            and review.verdict is not ReviewVerdict.COMMENT
            and not (review.verdict is ReviewVerdict.REJECT and review.proposal_id is not None)
        ),
        key=lambda review: (review.created_at, review.id),
        default=None,
    )
    if latest is None:
        return "unreviewed"
    match latest.verdict:
        case ReviewVerdict.APPROVE:
            return "approved"
        case ReviewVerdict.EDIT:
            return "edited"
        case ReviewVerdict.REJECT:
            return "rejected"
        case ReviewVerdict.COMMENT:
            return "unreviewed"


def proposed_update(
    proposals: Iterable[CandidateProposal],
    reviews: Iterable[CandidateReview],
) -> CandidateProposal | None:
    addressed = {
        review.proposal_id
        for review in reviews
        if review.reviewer_kind is PrincipalKind.HUMAN
        and review.verdict in (ReviewVerdict.EDIT, ReviewVerdict.REJECT)
    }
    return max(
        (proposal for proposal in proposals if proposal.id not in addressed),
        key=lambda proposal: (proposal.observed_at, proposal.source_key, proposal.fingerprint),
        default=None,
    )
