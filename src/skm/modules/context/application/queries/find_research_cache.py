"""Live authorization and policy checks precede every cache response (context §5.14)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from skm.application_bus.registry import QuerySpec
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, NotFound, ValidationFailed
from skm.kernel.ids import ProjectId, ScopeId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.kernel.scopes import ScopeKind, ScopeRef, ScopeRegistry
from skm.modules.access import public as access
from skm.modules.context.domain.research import (
    ResearchBatch,
    ResearchResult,
    ResearchSourceConfig,
    result_from_json,
    result_to_json,
)
from skm.modules.context.domain.research_render import render_research
from skm.modules.context.domain.research_rules import (
    CLASSIFICATIONS,
    DEFAULT_DENY,
    PROFILE_FIELDS,
    digest_text,
    invalid,
    normalize_query,
    profile_allows,
    profile_limits,
    query_digest,
    source_config,
    validate_result,
)
from skm.modules.context.generated.queries import CheckResearchAccess, FindResearchCache
from skm.modules.context.generated.views import (
    ResearchAccessView,
    ResearchCacheView,
    research_cache_view_from_json,
)
from skm.modules.context.ports import ContextOwnerGuard, ResearchRepository
from skm.modules.workspace import public as workspace

if TYPE_CHECKING:
    from skm.application_bus.context import CommandContext, QueryContext
    from skm.kernel.ports_uow import UnitOfWork


def scope_of(query: FindResearchCache) -> ScopeRef:
    return ScopeRef(ScopeKind.PROJECT, ScopeId(UUID(cast("str", query["project_id"]))))


def research_scope(
    ctx: CommandContext | QueryContext, uow: UnitOfWork, project_id: str, *, permission: str = "context.read"
) -> tuple[WorkspaceId, ProjectId]:
    pid = ProjectId(UUID(project_id))
    scope = ScopeRef(ScopeKind.PROJECT, ScopeId(pid))
    if ctx.scope != scope:
        raise NotFound(ErrorCode.NOT_FOUND, "research project not found")
    project = workspace.get_project(uow, pid)
    chain = uow.repo(ScopeRegistry).ancestors(scope.id)
    if not chain or chain[-1].workspace_id != project.workspace_id:
        raise NotFound(ErrorCode.NOT_FOUND, "research project not found")
    verdict = access.RbacAuthorizer(ctx.clock).authorize(uow, ctx.actor, permission, chain)
    if not verdict.allowed:
        raise Forbidden(ErrorCode.FORBIDDEN, "research permission denied")
    return WorkspaceId(project.workspace_id), pid


POLICY_KEYS = (
    "context.max_classification_for_runtime",
    "context.research.disabled_sources",
    *("context.research.profile." + key for key in PROFILE_FIELDS),
    "context.research.allow_deep",
    "context.research.url_deny",
    "context.research.cache.enabled",
    "context.research.cache.max_ttl_seconds",
    "context.research.excerpt_max_chars",
    "context.research.query_max_chars",
    "context.research.max_documents",
)


def research_policy(
    ctx: CommandContext | QueryContext,
    uow: UnitOfWork,
    workspace_id: WorkspaceId,
    project_id: ProjectId,
    *,
    step_ref: str | None = None,
    for_update: bool = False,
    permission: str = "context.read",
) -> JsonObject:
    bound = ctx.gateways.get(ContextOwnerGuard).research_policy(
        uow,
        ctx.actor,
        project_id,
        step_ref=step_ref,
        for_update=for_update,
        now=ctx.clock.now(),
        permission=permission,
    )
    policy = bound
    if ctx.actor.kind is not PrincipalKind.WORKER:
        policy = {**bound, **{key: ctx.config.get(key) for key in POLICY_KEYS}}
        policy["context.max_classification_for_runtime"] = access.workspace_classification_ceiling(
            uow,
            ctx.actor,
            workspace_id,
            clock=ctx.clock,
        )
    prefix = "context.research."
    bounds = {key.removeprefix(prefix): value for key, value in policy.items() if key.startswith(prefix)}
    limited = profile_limits(bounds, {key: policy.get(prefix + "profile." + key) for key in PROFILE_FIELDS})
    return {**policy, **{prefix + key: value for key, value in limited.items()}}


def actor_ceiling(policy: JsonObject) -> str:
    ceiling = str(policy["context.max_classification_for_runtime"])
    if ceiling not in CLASSIFICATIONS:
        raise invalid("invalid_classification_ceiling")
    return ceiling


def source_allowed(policy: JsonObject, source_id: str) -> bool:
    sources = cast("dict[str, Any]", policy["context.research.sources"] or {})
    return (
        source_id in sources
        and source_id not in cast("list[str]", policy["context.research.disabled_sources"] or [])
        and profile_allows({"sources": policy.get("context.research.profile.sources")}, source_id)
        and (
            sources[source_id]["tier"] != "deep_research" or policy.get("context.research.allow_deep") is True
        )
    )


def configured_source(policy: JsonObject, source_id: str) -> ResearchSourceConfig:
    sources = cast("dict[str, Any]", policy["context.research.sources"] or {})
    if source_id not in sources:
        raise NotFound(ErrorCode.NOT_FOUND, "research source not found")
    return source_config(source_id, sources[source_id], {})


def url_denials(policy: JsonObject) -> tuple[str, ...]:
    return (*DEFAULT_DENY, *cast("list[str]", policy["context.research.url_deny"] or []))


def result_visible(result: ResearchResult, policy: JsonObject) -> bool:
    ceiling = actor_ceiling(policy)
    if not source_allowed(policy, result.source_id):
        return False
    return not validate_result(
        result,
        config=configured_source(policy, result.source_id),
        max_documents=int(cast("int", policy["context.research.max_documents"])),
        excerpt_max_chars=int(cast("int", policy["context.research.excerpt_max_chars"])),
        url_deny=url_denials(policy),
    ) and all(
        CLASSIFICATIONS.index(doc.classification) <= CLASSIFICATIONS.index(ceiling)
        for doc in result.documents
    )


def design_research_evidence(
    ctx: CommandContext,
    uow: UnitOfWork,
    workspace_id: WorkspaceId,
    project_id: ProjectId,
    query_ids: tuple[str, ...],
) -> JsonObject:
    """Read evidence in the caller's transaction and return only D4-rendered content digests."""
    if not query_ids:
        return {}
    policy = research_policy(ctx, uow, workspace_id, project_id)
    repository = uow.repo(ResearchRepository)
    evidence: JsonObject = {}
    for query_id in query_ids:
        try:
            raw = repository.get(query_id)
            if raw["project_id"] != str(project_id) or raw["workspace_id"] != str(workspace_id):
                continue
            result = result_from_json(cast("dict[str, Any]", raw))
            text = normalize_query(
                str(raw["query_text"]),
                query_max_chars=cast("int", policy["context.research.query_max_chars"]),
            )
        except (NotFound, ValidationFailed):
            continue
        if (
            result.query_id == query_id
            and result.query_digest == query_digest(text)
            and (result.tier.value != "deep_research" or raw["depth"] == "deep")
            and result_visible(result, policy)
            and any(
                doc.content_digest and doc.excerpt and not doc.origin.startswith("answer:")
                for doc in result.documents
            )
        ):
            evidence[query_id] = digest_text(
                render_research(ResearchBatch(text, result.query_digest, (result,)))
            )
    return evidence


def load_result(
    ctx: QueryContext, uow: UnitOfWork, project_id: str, query_id: str
) -> tuple[JsonObject, ResearchResult]:
    wid, pid = research_scope(ctx, uow, project_id)
    policy = research_policy(ctx, uow, wid, pid)
    raw = uow.repo(ResearchRepository).get(query_id)
    if raw["workspace_id"] != str(wid) or raw["project_id"] != str(pid):
        raise NotFound(ErrorCode.NOT_FOUND, "research query not found")
    result = result_from_json(cast("dict[str, Any]", raw))
    if not result_visible(result, policy):
        raise NotFound(ErrorCode.NOT_FOUND, "research query not found")
    return raw, result


def handle(query: FindResearchCache, ctx: QueryContext, uow: UnitOfWork) -> ResearchCacheView:
    data = cast("dict[str, Any]", query)
    wid, pid = research_scope(ctx, uow, data["project_id"])
    policy = research_policy(ctx, uow, wid, pid)
    requested = data["max_classification"]
    if requested not in CLASSIFICATIONS:
        raise invalid("invalid_classification")
    ceiling = min((requested, actor_ceiling(policy)), key=CLASSIFICATIONS.index)
    if not policy["context.research.cache.enabled"] or not source_allowed(policy, data["source_id"]):
        return {"hit": False}
    row = uow.repo(ResearchRepository).find_cached(
        workspace_id=wid, project_id=pid, cache_key=data["cache_key"], now=ctx.clock.now()
    )
    if row is None or row["source_id"] != data["source_id"]:
        return {"hit": False}
    result = result_from_json(cast("dict[str, Any]", row))
    if any(
        CLASSIFICATIONS.index(d.classification) > CLASSIFICATIONS.index(ceiling) for d in result.documents
    ):
        return research_cache_view_from_json(
            {
                "hit": False,
                "result": {"cache_status": "bypass", "limitations": ["cache_bypassed_classification"]},
            }
        )
    narrowed = {**policy, "context.max_classification_for_runtime": ceiling}
    if not result_visible(result, narrowed):
        return {"hit": False}
    wire = result_to_json(result)
    wire["cache_status"] = "hit"
    return research_cache_view_from_json({"hit": True, "result": wire})


SPEC = QuerySpec(
    name="context.find_research_cache",
    dto=FindResearchCache,
    result=ResearchCacheView,
    permission="context.read",
    scope_of=scope_of,
    handler=handle,
)


def _access_scope(query: CheckResearchAccess) -> ScopeRef:
    return ScopeRef(ScopeKind.PROJECT, ScopeId(UUID(cast("str", query["project_id"]))))


def _check_access(query: CheckResearchAccess, ctx: QueryContext, uow: UnitOfWork) -> ResearchAccessView:
    research_scope(ctx, uow, cast("str", query["project_id"]), permission="context.research")
    return {"allowed": True}


ACCESS_SPEC = QuerySpec(
    name="context.check_research_access",
    dto=CheckResearchAccess,
    result=ResearchAccessView,
    permission="context.research",
    scope_of=_access_scope,
    handler=_check_access,
)
