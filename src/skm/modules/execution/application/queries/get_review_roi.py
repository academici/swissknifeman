"""Read-only review outcome and cost summary for one run."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator, Mapping
from decimal import Decimal
from typing import TYPE_CHECKING

from skm.application_bus.registry import QuerySpec
from skm.kernel.ids import RunId, ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.execution.application._primitives import attempts_for_run
from skm.modules.execution.domain.finding import FindingState, logical_findings
from skm.modules.execution.domain.review import ReviewerKind, ReviewState
from skm.modules.execution.domain.step import AttemptStep, RoleId, StepState
from skm.modules.execution.generated.queries import GetReviewRoi
from skm.modules.execution.generated.views import ReviewRoiView
from skm.modules.execution.ports import (
    ReviewRepository,
    RunRepository,
    StageRepository,
    StepRepository,
    TaskRepository,
)
from skm.modules.runtimes.public import UsageStatus

if TYPE_CHECKING:
    from skm.application_bus.context import QueryContext
    from skm.kernel.ports_uow import UnitOfWork
    from skm.modules.execution.domain.ids import ReviewId

__all__ = ["SPEC", "handle"]


def _review_outcomes(uow: UnitOfWork, run_id: RunId) -> tuple[Counter[ReviewerKind], Counter[FindingState]]:
    reviews = Counter[ReviewerKind]()
    findings = Counter[FindingState]()
    repo = uow.repo(ReviewRepository)
    for task in uow.repo(TaskRepository).list_for_run(run_id):
        rounds: dict[ReviewId, int] = {}
        for review in repo.for_task(task.id):
            if review.state is ReviewState.COMPLETED and review.run_id == run_id:
                reviews[review.reviewer_kind] += 1
                rounds[review.id] = review.round_no
        if rounds:
            rows = tuple(
                finding for finding in repo.findings_for_task(task.id) if finding.review_id in rounds
            )
            findings.update(finding.state for finding in logical_findings(rows, rounds))
    return reviews, findings


def _finished_reviewer_steps(uow: UnitOfWork, run_id: RunId) -> Iterator[AttemptStep]:
    stages, steps = uow.repo(StageRepository), uow.repo(StepRepository)
    for attempt in attempts_for_run(uow, run_id):
        for entry in stages.history(attempt.id).entries:
            for step in steps.for_stage(entry.record.id):
                if step.role is RoleId.REVIEWER and step.state is not StepState.STARTED:
                    yield step


def _capture_duration_ms(step: AttemptStep) -> int | None:
    timing = step.runtime_observation.get("timing") if step.runtime_observation is not None else None
    duration = timing.get("duration_ms") if isinstance(timing, Mapping) else None
    return duration if type(duration) is int and duration >= 0 else None


def handle(query: GetReviewRoi, _ctx: QueryContext, uow: UnitOfWork) -> ReviewRoiView:
    run_id = RunId(query.run_id)
    uow.repo(RunRepository).get(run_id)
    reviews, findings = _review_outcomes(uow, run_id)
    finished_steps = priced_steps = timed_steps = cost_micros = duration_ms = 0
    for step in _finished_reviewer_steps(uow, run_id):
        finished_steps += 1
        usage = step.usage
        if usage is not None and usage.status is UsageStatus.REPORTED and usage.cost_usd_micros is not None:
            priced_steps += 1
            cost_micros += usage.cost_usd_micros
        duration = _capture_duration_ms(step)
        if duration is not None:
            timed_steps += 1
            duration_ms += duration

    return ReviewRoiView(
        run_id=run_id,
        completed_agent_reviews=reviews[ReviewerKind.AGENT],
        completed_human_reviews=reviews[ReviewerKind.HUMAN],
        unique_findings=findings.total(),
        resolved_findings=findings[FindingState.RESOLVED],
        rejected_findings=findings[FindingState.REJECTED],
        finished_reviewer_steps=finished_steps,
        priced_reviewer_steps=priced_steps,
        observed_cost_usd=f"{Decimal(cost_micros).scaleb(-6):.6f}" if priced_steps else None,
        timed_reviewer_steps=timed_steps,
        observed_duration_ms=duration_ms if timed_steps else None,
    )


SPEC = QuerySpec(
    name="execution.get_review_roi",
    dto=GetReviewRoi,
    result=ReviewRoiView,
    permission="run.read",
    scope_of=lambda q: ScopeRef(ScopeKind.RUN, ScopeId(q.run_id)),
    handler=handle,
)
