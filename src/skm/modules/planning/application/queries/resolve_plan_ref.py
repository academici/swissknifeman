"""``planning.resolve_plan_ref`` (planning §8): resolve alias, ``plan:<uuid>``, or UUID prefix."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from skm.application_bus.registry import QuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, ValidationFailed
from skm.kernel.ids import PlanId, ProjectId, ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.planning.application.source_reader import require_project
from skm.modules.planning.domain.plan import Plan
from skm.modules.planning.generated.queries import ResolvePlanRef
from skm.modules.planning.generated.settings import PlanningSettings
from skm.modules.planning.generated.views import PlanRefView
from skm.modules.planning.ports import PlanRepository

if TYPE_CHECKING:
    from skm.application_bus.context import QueryContext
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["SPEC", "handle", "scope_of"]

_HEX_CHARS = frozenset("0123456789abcdefABCDEF-")


def scope_of(query: ResolvePlanRef) -> ScopeRef:
    return ScopeRef(ScopeKind.PROJECT, ScopeId(query.project_id))


def _resolve_uuid_or_prefix(
    plan_repo: PlanRepository, project_id: ProjectId, raw_target: str, original_ref: str
) -> Plan:
    try:
        full_uuid = UUID(raw_target)
    except ValueError:
        full_uuid = None

    if full_uuid is not None and len(raw_target.replace("-", "")) == 32:
        plan = plan_repo.get(PlanId(full_uuid))
        if plan.project_id != project_id:
            raise NotFound(
                ErrorCode.NOT_FOUND,
                "plan not found",
                details={"kind": "plan", "ref": original_ref},
            )
        return plan

    hex_only = raw_target.replace("-", "")
    if not raw_target or not all(ch in _HEX_CHARS for ch in raw_target) or len(hex_only) < 12:
        raise ValidationFailed(
            ErrorCode.INVALID_REFERENCE,
            "plan UUID prefix must contain at least 12 hexadecimal characters",
            details={"ref": original_ref},
        )

    matches = plan_repo.find_by_id_prefix(project_id, raw_target.lower(), limit=2)
    if len(matches) > 1:
        raise ValidationFailed(
            ErrorCode.AMBIGUOUS_REFERENCE,
            "plan reference matches multiple plans",
            details={"ref": original_ref, "candidates": [m.alias for m in matches]},
        )
    if len(matches) == 1:
        return matches[0]
    raise NotFound(
        ErrorCode.NOT_FOUND,
        "plan not found",
        details={"kind": "plan", "ref": original_ref},
    )


def _resolve_initial_plan(plan_repo: PlanRepository, project_id: ProjectId, raw_ref: str) -> Plan:
    ref = raw_ref.strip()
    if not ref or any(ch.isspace() for ch in ref):
        raise ValidationFailed(
            ErrorCode.INVALID_REFERENCE,
            "invalid plan reference",
            details={"ref": raw_ref},
        )

    if ref.startswith("plan:"):
        return _resolve_uuid_or_prefix(plan_repo, project_id, ref[5:], raw_ref)

    found = plan_repo.find_by_alias(project_id, ref)
    if found is None and ref.upper() != ref:
        found = plan_repo.find_by_alias(project_id, ref.upper())
    if found is None and ref.lower() == "review-requests":
        found = plan_repo.find_review_requests_plan(project_id)
    if found is not None:
        return found

    if all(ch in _HEX_CHARS for ch in ref):
        return _resolve_uuid_or_prefix(plan_repo, project_id, ref, raw_ref)

    raise NotFound(
        ErrorCode.NOT_FOUND,
        "plan not found",
        details={"kind": "plan", "ref": raw_ref},
    )


def handle(query: ResolvePlanRef, ctx: QueryContext, uow: UnitOfWork) -> PlanRefView:
    project_id = require_project(uow, query.project_id)
    plan_repo = uow.repo(PlanRepository)
    current = _resolve_initial_plan(plan_repo, project_id, query.ref)

    chain: list[str] = [current.alias]
    truncated = False

    if query.follow_supersedes:
        max_hops = ctx.config.section(PlanningSettings).references.max_supersede_chain
        visited: set[PlanId] = {current.id}
        hops = 0
        while hops < max_hops:
            next_ids = plan_repo.superseded_by(current.id)
            next_plan: Plan | None = None
            for cand_id in next_ids:
                if cand_id in visited:
                    continue
                cand = plan_repo.get(cand_id)
                if cand.project_id == project_id:
                    next_plan = cand
                    break
            if next_plan is None:
                break
            visited.add(next_plan.id)
            current = next_plan
            chain.append(current.alias)
            hops += 1
        else:
            remaining = [cid for cid in plan_repo.superseded_by(current.id) if cid not in visited]
            if remaining:
                truncated = True

    return PlanRefView(
        plan_id=current.id,
        alias=current.alias,
        project_id=current.project_id,
        title=current.title,
        purpose=current.purpose.value,
        superseded_chain=tuple(chain),
        truncated=truncated,
    )


SPEC = QuerySpec(
    name="planning.resolve_plan_ref",
    dto=ResolvePlanRef,
    result=PlanRefView,
    permission="plan.read",
    permission_alternatives=("plan.edit", "plan.publish"),
    scope_of=scope_of,
    handler=handle,
)
