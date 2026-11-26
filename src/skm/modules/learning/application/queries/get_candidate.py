"""Project a candidate with evidence, confidence gates and proposal history."""

from dataclasses import asdict
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol, cast
from uuid import UUID

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.ids import WorkspaceId
from skm.kernel.pagination import Cursor
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.learning.application.commands.extract_candidates import project_settings
from skm.modules.learning.application.commands.review_candidate import require_candidate, workspace_ref
from skm.modules.learning.domain.candidate import Candidate, CandidateId
from skm.modules.learning.domain.confidence import aggregate
from skm.modules.learning.domain.recompute import confidence_gates
from skm.modules.learning.domain.review import CandidateReview
from skm.modules.learning.domain.tokens import jaccard
from skm.modules.learning.generated.queries import GetCandidate
from skm.modules.learning.generated.views import CandidateView, candidate_view_from_json
from skm.modules.learning.ports import (
    ActivityRecordRepository,
    CandidateProposalRepository,
    CandidateRepository,
    CandidateReviewRepository,
    SignalRepository,
)


class _ReviewHistory(CandidateReviewRepository, Protocol):
    def for_proposals(self, candidate_id: CandidateId) -> tuple[CandidateReview, ...]: ...


def record_json(data: dict[str, Any]) -> dict[str, Any]:
    return {
        key: str(value)
        if isinstance(value, UUID)
        else value.isoformat()
        if isinstance(value, datetime)
        else value.value
        if isinstance(value, StrEnum)
        else value
        for key, value in data.items()
    }


def _similar(c: Candidate, candidates: CandidateRepository, threshold: float) -> list[dict[str, Any]]:
    matching = [
        (
            -jaccard(c.trigger, str(row["trigger"])),
            -jaccard(c.action, str(row["action"])),
            str(row["fingerprint"]),
            str(row["candidate_id"]),
        )
        for row in candidates.shortlist_pool(c.scope_id, limit=2000)
        if row["candidate_id"] != str(c.id)
        and jaccard(f"{c.trigger} {c.action}", f"{row['trigger']} {row['action']}") >= threshold
    ]
    return [
        {"candidate_id": candidate_id, "tsim": -trigger, "asim": -action}
        for trigger, action, _, candidate_id in sorted(matching)[:20]
    ]


def handle(cmd: dict[str, Any], ctx: QueryContext, uow: UnitOfWork) -> CandidateView:
    candidates = uow.repo(CandidateRepository)
    candidate = require_candidate(
        candidates, CandidateId(UUID(cmd["candidate_id"])), WorkspaceId(UUID(cmd["workspace_id"]))
    )
    reviews = cast("_ReviewHistory", uow.repo(CandidateReviewRepository))
    proposals = uow.repo(CandidateProposalRepository)
    activities = uow.repo(ActivityRecordRepository)
    signals = uow.repo(SignalRepository)
    settings = project_settings(uow, ctx.config, candidate.project_id)
    inputs = aggregate(signals.for_candidate(candidate.id), ctx.clock.now(), settings)
    gates = asdict(confidence_gates(inputs, activities.count_for_project(candidate.project_id), settings))
    for gate in gates.values():
        gate["missing_conditions"] = list(gate["missing_conditions"])
    after = cmd.get("proposals_after")
    page = proposals.list(
        candidate.id, after=Cursor(after) if after else None, limit=cmd.get("proposals_limit", 50)
    )
    page_ids = {proposal.id for proposal in page.items}
    related_reviews = (r for r in reviews.for_proposals(candidate.id) if r.proposal_id in page_ids)
    review_history = {r.id: r for r in (*reviews.for_candidate(candidate.id), *related_reviews)}
    data = record_json(asdict(candidate))
    data["evidence"] = list(data["evidence"])
    return candidate_view_from_json(
        {
            **data,
            "gates": gates,
            "reviews": [
                record_json(asdict(r))
                for r in sorted(review_history.values(), key=lambda r: (r.created_at, r.id))
            ],
            "proposals": [record_json(asdict(p)) for p in page.items],
            "proposals_next": page.next,
            "similar": _similar(candidate, candidates, settings.consolidation.shortlist_threshold),
            "lesson_ref": data["lesson_id"],
        }
    )


SPEC = QuerySpec(
    name="learning.get_candidate",
    dto=cast("type[dict[str, Any]]", GetCandidate),
    result=CandidateView,
    permission="lesson.read",
    scope_of=lambda cmd: workspace_ref(cmd["workspace_id"]),
    handler=handle,
)
