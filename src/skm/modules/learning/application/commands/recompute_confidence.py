"""Rebuild empirical counters and freshness from the candidate's signals."""

from typing import Any, cast
from uuid import UUID

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.ids import ProjectId, WorkspaceId
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.knowledge import public as knowledge
from skm.modules.learning.domain.activity import LearningSettings
from skm.modules.learning.domain.candidate import CandidateId, CandidateState
from skm.modules.learning.domain.recompute import recompute
from skm.modules.learning.generated.commands import RecomputeConfidence
from skm.modules.learning.generated.results import (
    RecomputeConfidenceResult,
    RecomputeConfidenceResultTransitions,
)
from skm.modules.learning.ports import CandidateRepository, SignalRepository

from .extract_candidates import project_settings
from .review_candidate import CandidateStateChanged, require_candidate, workspace_ref


def handle(cmd: dict[str, Any], ctx: CommandContext, uow: UnitOfWork) -> RecomputeConfidenceResult:
    workspace_id = WorkspaceId(UUID(cmd["workspace_id"]))
    project_id = ProjectId(UUID(cmd["project_id"])) if "project_id" in cmd else None
    candidates = uow.repo(CandidateRepository)
    signals = uow.repo(SignalRepository)
    now = ctx.clock.now()
    totals = RecomputeConfidenceResultTransitions(
        to_candidate=0, deprecated=0, curated_ready=0, lesson_decay=0
    )
    recomputed = 0
    projects: dict[ProjectId, tuple[LearningSettings, int]] = {}
    after: CandidateId | None = None
    while batch := candidates.ids_for_recompute(workspace_id, after=after, limit=cmd.get("batch", 500)):
        after = batch[-1]
        for candidate_id in batch:
            candidate = require_candidate(candidates, candidate_id, workspace_id)
            if project_id is not None and candidate.project_id != project_id:
                continue
            if candidate.project_id not in projects:
                projects[candidate.project_id] = (
                    project_settings(uow, ctx.config, candidate.project_id),
                    signals.count_activities_for_project(candidate.project_id),
                )
            settings, sessions = projects[candidate.project_id]
            updated, transition = recompute(
                candidate,
                signals.for_candidate(candidate_id),
                now=now,
                project_sessions=sessions,
                t=settings,
            )
            if updated != candidate:
                candidates.save(updated, expected_version=candidate.row_version)
            recomputed += 1
            totals["curated_ready"] += int(transition.curated_ready)
            if transition.reason is not None:
                uow.record(
                    CandidateStateChanged(
                        candidate_id, workspace_id, candidate.state, updated.state, transition.reason
                    )
                )
                totals["to_candidate"] += int(updated.state is CandidateState.CANDIDATE)
                totals["deprecated"] += int(updated.state is CandidateState.DEPRECATED)
            if transition.lesson_decay and candidate.lesson_id is not None:
                knowledge.flag_lesson_decay(
                    uow,
                    candidate.lesson_id,
                    confidence=updated.support_score,
                    stale=updated.stale,
                    deprecate_conf=settings.thresholds.deprecate_conf,
                    now=now,
                )
                totals["lesson_decay"] += 1
    return RecomputeConfidenceResult(recomputed=recomputed, transitions=totals)


SPEC = CommandSpec(
    name="learning.recompute_confidence",
    dto=cast("type[dict[str, Any]]", RecomputeConfidence),
    result=RecomputeConfidenceResult,
    permission="lesson.curate",
    permission_alternatives=("system.internal",),
    scope_of=lambda cmd: workspace_ref(cmd["workspace_id"]),
    handler=handle,
    idempotency=IdempotencyMode.REQUIRED,
)
