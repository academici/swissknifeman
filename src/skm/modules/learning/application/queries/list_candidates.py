"""Read candidate summaries from the authorized workspace and project scopes."""

from typing import Any, cast
from uuid import UUID

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound
from skm.kernel.ids import ProjectId, ScopeId, WorkspaceId
from skm.kernel.pagination import Cursor
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRegistry
from skm.modules.learning.application.commands.extract_candidates import CandidateStorage
from skm.modules.learning.application.commands.review_candidate import workspace_ref
from skm.modules.learning.domain.candidate import Candidate, CandidateState, ConfidenceTier
from skm.modules.learning.generated.queries import ListCandidates
from skm.modules.learning.generated.views import (
    CandidateSummaryView,
    CandidatesView,
    candidate_summary_view_from_json,
)
from skm.modules.learning.ports import CandidateRepository
from skm.modules.workspace import public as workspace

_TIERS = tuple(ConfidenceTier)


def require_project_workspace(uow: UnitOfWork, project_id: str, workspace_id: str) -> ScopeId:
    project = ProjectId(UUID(project_id))
    if workspace.workspace_of_project(uow, project) != WorkspaceId(UUID(workspace_id)):
        raise NotFound(ErrorCode.NOT_FOUND, "Project not found")
    return ScopeId(project)


def _scopes(uow: UnitOfWork, cmd: dict[str, Any]) -> tuple[ScopeId, ...]:
    if "project_id" in cmd:
        return (require_project_workspace(uow, cmd["project_id"], cmd["workspace_id"]),)
    workspace_id = WorkspaceId(UUID(cmd["workspace_id"]))
    scopes = uow.repo(ScopeRegistry)
    project_ids: list[ScopeId] = []
    after: ScopeId | None = None
    while batch := scopes.list_scopes(after=after, limit=500):
        project_ids.extend(
            s.id for s in batch if s.workspace_id == workspace_id and s.kind is ScopeKind.PROJECT
        )
        after = batch[-1].id
    return tuple(project_ids)


def _summary(row: Candidate, repo: CandidateStorage) -> CandidateSummaryView:
    return candidate_summary_view_from_json(
        {
            "candidate_id": str(row.id),
            "display_key": row.display_key,
            "detector": row.detector.value,
            "pathology_code": row.pathology_code.value if row.pathology_code else None,
            "kind": row.kind.value,
            "trigger": row.trigger,
            "state": row.state.value,
            "confidence": row.confidence,
            "confidence_tier": row.confidence_tier.value,
            "n_total": row.n_total,
            "curated_ready": row.curated_ready,
            "conflicts_with": str(row.conflicts_with_id) if row.conflicts_with_id else None,
            "updated_at": repo.updated_at(row.id).isoformat(),
        }
    )


def handle(cmd: dict[str, Any], _ctx: QueryContext, uow: UnitOfWork) -> CandidatesView:
    scope_ids = _scopes(uow, cmd)
    states = frozenset(CandidateState(state) for state in cmd.get("states", ["candidate"]))
    repo = cast("CandidateStorage", uow.repo(CandidateRepository))
    after = cmd.get("after")
    limit = cmd.get("limit", 100)
    detector = cmd.get("detector")
    min_tier = _TIERS.index(ConfidenceTier(cmd.get("min_tier", "none")))
    items: list[CandidateSummaryView] = []
    while True:
        page = repo.list(
            scope_ids, states=states, after=Cursor(after) if after else None, limit=limit - len(items)
        )
        items.extend(
            _summary(row, repo)
            for row in page.items
            if row.workspace_id == UUID(cmd["workspace_id"])
            and (detector is None or row.detector == detector)
            and _TIERS.index(row.confidence_tier) >= min_tier
        )
        after = page.next
        if after is None or len(items) == limit:
            return CandidatesView(items=items, next_cursor=after, has_more=after is not None)


SPEC = QuerySpec(
    name="learning.list_candidates",
    dto=cast("type[dict[str, Any]]", ListCandidates),
    result=CandidatesView,
    permission="lesson.read",
    scope_of=lambda cmd: workspace_ref(cmd["workspace_id"]),
    handler=handle,
)
