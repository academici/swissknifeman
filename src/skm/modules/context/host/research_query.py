"""Host-only research orchestration; all persistence crosses the client bus."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, replace
from typing import TYPE_CHECKING, Any, Protocol, cast
from uuid import UUID

from skm.kernel.errors import NotFound
from skm.kernel.ids import ProjectId, WorkspaceId, uuid7
from skm.kernel.json_types import JsonObject
from skm.modules.context.domain.research import (
    RawSourceReply,
    ResearchBatch,
    ResearchDocument,
    ResearchError,
    ResearchQuerySpec,
    ResearchResult,
    SourceQuery,
    result_from_json,
    result_to_json,
)
from skm.modules.context.domain.research_render import render_research
from skm.modules.context.domain.research_rules import (
    PROFILE_FIELDS,
    cache_key,
    invalid,
    ladder_stop,
    normalize_query,
    normalize_reply,
    plan_limitations,
    plan_sources,
    profile_limits,
    query_digest,
)
from skm.modules.context.ports import ResearchSourceRegistry
from skm.modules.context.public import (
    CheckResearchAccess,
    FindResearchCache,
    GetResearchQuery,
    RecordResearchResult,
)
from skm.modules.planning.public import GetPlan, PlanView
from skm.modules.workspace.public import CheckoutLocationView, GetProject, ProjectView, ResolveCheckout
from skm.platform.logging.redaction import Redactor

if TYPE_CHECKING:
    from skm.application_bus.host import HostContext
    from skm.kernel.clock import Clock
    from skm.kernel.id_generator import IdGenerator

__all__ = ["ResearchQueryOperation", "research_query", "run"]


class _ResearchDependencies(Protocol):
    clock: Clock
    ids: IdGenerator


def settings_of(config: object) -> JsonObject:
    getter = cast("Any", config).get
    keys = (
        "sources",
        "disabled_sources",
        "allow_deep",
        "max_documents",
        "min_documents",
        "query_max_chars",
        "excerpt_max_chars",
        "url_deny",
        "cache.enabled",
        "cache.max_ttl_seconds",
        "cache.default_ttl_seconds",
    )
    values: dict[str, Any] = {}
    for key in keys:
        value = getter("context.research." + key)
        if value is not None:
            if key.startswith("cache."):
                values.setdefault("cache", {})[key.split(".")[1]] = value
            else:
                values[key] = value
    profile = {key: getter("context.research.profile." + key) for key in PROFILE_FIELDS}
    return profile_limits(
        {
            "max_documents": 50,
            "query_max_chars": 4000,
            "excerpt_max_chars": 2000,
            **values,
            "profile": profile,
        },
        profile,
    )


def research_query(  # noqa: PLR0912, PLR0915 -- ordered host pipeline and cancellation boundaries
    hctx: HostContext,
    spec: ResearchQuerySpec,
    *,
    workspace_id: WorkspaceId,
    project_id: ProjectId,
    step_ref: str | None,
    mounts: Mapping[str, str],
) -> ResearchBatch:
    hctx.cancel.raise_if_cancelled()
    settings = settings_of(hctx.config)
    registry = hctx.gateways.get(ResearchSourceRegistry)
    redact = cast("Redactor", getattr(registry, "redactor", Redactor())).text
    query_limit = cast("int", settings.get("query_max_chars", 4000))
    original = normalize_query(spec.text, query_max_chars=query_limit)
    text = normalize_query(redact(spec.text), query_max_chars=query_limit)
    if spec.depth not in ("standard", "deep") or not 1 <= spec.max_documents <= 50:
        raise invalid("invalid_research_bounds")
    sources = plan_sources(settings, spec)
    if len(sources) > 16:
        raise invalid("too_many_research_sources")
    replay_key = cache_key(
        {
            "workspace_id": str(workspace_id),
            "project_id": str(project_id),
            "step_ref": step_ref,
            "spec": cast("Any", asdict(spec)),
            "settings": settings,
            "mounts": dict(mounts),
        }
    )
    query = SourceQuery(
        text, min(spec.max_documents, cast("int", settings["max_documents"])), spec.depth, mounts
    )
    dependencies = cast("_ResearchDependencies", registry)
    clock, ids = dependencies.clock, dependencies.ids
    results: list[ResearchResult] = []
    replies: dict[str, RawSourceReply] = {}
    common = plan_limitations(settings, spec) + (("query_redacted",) if text != original else ())
    state_reader = getattr(registry, "checkout_state", None)
    stored_ids: set[str] = set()
    bound_hits: set[str] = set()
    for index, source in enumerate(sources):
        hctx.cancel.raise_if_cancelled()
        now = clock.now()
        qid = str(ids.new_id())
        restored = None
        if step_ref:
            seed = cache_key({"invocation": replay_key, "source": source.source_id})[7:]
            step_id = UUID(step_ref.removeprefix("step:"))
            bits = int(seed, 16)
            qid = str(uuid7(step_id.int >> 80, (bits >> 62) & 4095, bits & ((1 << 62) - 1)))
            try:
                saved = cast(
                    "dict[str, Any]",
                    hctx.client.ask(
                        GetResearchQuery.from_json({"project_id": str(project_id), "query_id": qid})
                    ),
                )
                restored = result_from_json(saved["result"])
                stored_ids.add(qid)
            except NotFound:
                pass
        checkout_state = (
            cast("str | None", state_reader(mounts, hctx.cancel, source=source))
            if restored is None
            and callable(state_reader)
            and (source.kind == "filesystem" or source.reads_checkout)
            else None
        )
        result = normalize_reply(
            RawSourceReply((), None, (), None, ""),
            source,
            query,
            query_id=qid,
            now=now,
            document_ids=(),
            settings=settings,
            workspace_id=workspace_id,
            project_id=project_id,
            checkout_state=checkout_state,
            redact=redact,
        )
        cached: dict[str, Any] = {}
        # Step batches must be recorded against this step. Existing cache rows retain their owner.
        if restored is None and spec.use_cache and result.expires_at is not None:
            cached = cast(
                "dict[str, Any]",
                hctx.client.ask(
                    FindResearchCache.from_json(
                        {
                            "project_id": str(project_id),
                            "source_id": source.source_id,
                            "cache_key": result.cache_key,
                            "max_classification": source.classification,
                        }
                    )
                ),
            )
        if restored is not None:
            if (
                restored.source_id,
                restored.kind,
                restored.tier,
                restored.query_digest,
                restored.source_config_digest,
            ) != (
                result.source_id,
                result.kind,
                result.tier,
                result.query_digest,
                result.source_config_digest,
            ):
                raise invalid("research_replay_mismatch")
            result = restored
        elif cached.get("hit"):
            result = replace(result_from_json(cached["result"]), cache_status="hit")
            if step_ref:
                mapping = {doc.document_id: str(ids.new_id()) for doc in result.documents}
                result = replace(
                    result,
                    query_id=qid,
                    documents=tuple(
                        replace(doc, document_id=mapping[doc.document_id], staged_blob=None)
                        for doc in result.documents
                    ),
                    claims=tuple(
                        replace(claim, document_ids=tuple(mapping[ref] for ref in claim.document_ids))
                        for claim in result.claims
                    ),
                    citations=tuple(
                        replace(citation, document_id=mapping[citation.document_id])
                        for citation in result.citations
                    ),
                )
                bound_hits.add(qid)
        else:
            try:
                adapter = registry.get(source.kind)
                if adapter.validate_config(source):
                    raise ValueError("RESEARCH_SOURCE_INVALID")
                reply = adapter.search(source, query, cancel=hctx.cancel)
                replies[source.source_id] = reply
                result = normalize_reply(
                    reply,
                    source,
                    query,
                    query_id=result.query_id,
                    now=now,
                    document_ids=tuple(str(ids.new_id()) for _ in range(50)),
                    settings=settings,
                    workspace_id=workspace_id,
                    project_id=project_id,
                    checkout_state=checkout_state,
                    redact=redact,
                )
                if (
                    callable(state_reader)
                    and (source.kind == "filesystem" or source.reads_checkout)
                    and state_reader(mounts, hctx.cancel, source=source) != checkout_state
                ):
                    result = replace(result, cache_status="bypass", expires_at=None)
                result = replace(
                    result,
                    limitations=tuple(
                        dict.fromkeys(
                            (
                                *result.limitations,
                                *(
                                    redact(lim)
                                    for lim in cast("tuple[str, ...]", getattr(reply, "limitations", ()))
                                ),
                            )
                        )
                    ),
                )
            except (OSError, ValueError, KeyError) as exc:
                code = (
                    "RESEARCH_SOURCE_TIMEOUT"
                    if isinstance(exc, TimeoutError)
                    else str(getattr(exc, "code", "RESEARCH_SOURCE_UNAVAILABLE"))
                )
                if code not in {
                    "RESEARCH_SOURCE_UNAVAILABLE",
                    "RESEARCH_SOURCE_TIMEOUT",
                    "RESEARCH_SOURCE_INVALID",
                }:
                    code = "RESEARCH_SOURCE_UNAVAILABLE"
                if str(exc) == "RESEARCH_SOURCE_INVALID":
                    code = "RESEARCH_SOURCE_INVALID"
                result = replace(
                    result,
                    status="error",
                    error=ResearchError(code, "Research source failed"),
                    expires_at=None,
                    limitations=(
                        "source_timeout" if isinstance(exc, TimeoutError) else "source_unavailable",
                    ),
                )
            if not spec.use_cache:
                result = replace(result, cache_status="bypass", expires_at=None)
            if cached.get("result", {}).get("cache_status") == "bypass":
                result = replace(
                    result,
                    cache_status="bypass",
                    expires_at=None,
                    limitations=(*result.limitations, "cache_bypassed_classification"),
                )
        if result.query_id not in stored_ids and result.query_id not in bound_hits:
            result = replace(result, limitations=tuple(dict.fromkeys((*result.limitations, *common))))
        results.append(result)
        end_tier = index + 1 == len(sources) or sources[index + 1].tier != source.tier
        if not spec.sources and end_tier:
            stop = ladder_stop(
                results, source.tier, min_documents=cast("int", settings.get("min_documents", 2))
            )
            if stop:
                if result.query_id not in stored_ids and result.query_id not in bound_hits:
                    results[-1] = replace(
                        result, limitations=tuple(dict.fromkeys((*result.limitations, stop)))
                    )
                break
    hctx.cancel.raise_if_cancelled()
    for index, result in enumerate(results):
        if result.query_id in stored_ids or result.cache_status == "hit" or not spec.save_as_material:
            continue
        raw = replies.get(result.source_id)
        texts = (
            {redact(doc.origin): redact(doc.text) for doc in raw.documents if doc.text is not None}
            if raw
            else {}
        )
        if raw and raw.answer_text is not None:
            texts["answer:" + result.source_id] = redact(raw.answer_text)
        documents: list[ResearchDocument] = []
        for doc in result.documents:
            hctx.cancel.raise_if_cancelled()
            body = texts.get(doc.origin)
            if body is not None:
                content = body.encode("utf-8")
                staged = hctx.client.upload_blob(
                    workspace_id,
                    (content,),
                    size=len(content),
                    expected_digest=doc.content_digest,
                    media_type="text/plain",
                )
                documents.append(replace(doc, staged_blob=cast("Any", staged.to_json())))
            else:
                documents.append(doc)
        results[index] = replace(result, documents=tuple(documents))
    hctx.cancel.raise_if_cancelled()
    pending = [
        result_to_json(result)
        for result in results
        if result.query_id not in stored_ids
        and (result.cache_status != "hit" or result.query_id in bound_hits)
    ]
    if pending:
        command: JsonObject = {
            "workspace_id": str(workspace_id),
            "project_id": str(project_id),
            "query_text": text,
            "query_digest": query_digest(text),
            "depth": spec.depth,
            "max_documents": query.max_documents,
            "results": cast("Any", pending),
        }
        if step_ref is not None:
            command["step_ref"] = step_ref
        dto = RecordResearchResult.from_json(command)
        hctx.client.dispatch(
            dto,
            idempotency_key="research:" + (step_ref or str(ids.new_id())) + ":" + replay_key[7:],
        )
    return ResearchBatch(text, query_digest(text), tuple(results))


class ResearchQueryOperation:
    def __call__(self, ctx: HostContext, request: JsonObject) -> JsonObject:
        return run(ctx, request)


def run(ctx: HostContext, request: JsonObject) -> JsonObject:
    """Wire wrapper shared by CLI and worker; executable source settings never come from the request."""
    action = request.get("action", "query")
    if action == "sources":
        spec = ResearchQuerySpec("sources", (), "deep", 50, False, False)
        settings = settings_of(ctx.config)
        settings["allow_deep"] = True
        return {
            "sources": [
                {
                    "order": s.order,
                    "id": s.source_id,
                    "kind": s.kind,
                    "tier": s.tier.value,
                    "capabilities": [str(capability) for capability in sorted(s.capabilities)],
                }
                for s in sorted(plan_sources(settings, spec), key=lambda s: (s.order, s.source_id))
            ]
        }
    if action == "show":
        return cast(
            "JsonObject",
            ctx.client.ask(
                GetResearchQuery.from_json(
                    {"project_id": str(request["project_id"]), "query_id": str(request["query_id"])}
                )
            ),
        )
    plan = None
    if action == "plan":
        ctx.cancel.raise_if_cancelled()
        plan = cast("PlanView", ctx.client.ask(GetPlan.from_json({"plan_id": request["plan_id"]})))
        project_id = str(plan.project_id)
        ctx.client.ask(CheckResearchAccess.from_json({"project_id": project_id}))
        request = {
            "workspace_id": str(plan.workspace_id),
            "project_id": project_id,
            "spec": request["spec"],
        }
    project_config = getattr(ctx.config, "for_research_project", None)
    if callable(project_config):
        ctx = replace(ctx, config=project_config(str(request["project_id"])))
    raw = cast("dict[str, Any]", request.get("spec", request))
    spec = ResearchQuerySpec(
        raw["text"],
        tuple(raw.get("sources", ())),
        raw.get("depth", "standard"),
        raw.get("max_documents", 10),
        raw.get("use_cache", True),
        raw.get("save_as_material", False),
    )
    provided_mounts = request.get("mounts")
    mounts: dict[str, str] = dict(cast("Mapping[str, str]", provided_mounts or {}))
    if provided_mounts is None:
        selected = plan_sources(settings_of(ctx.config), spec)
        if any(source.kind == "filesystem" or source.reads_checkout for source in selected):
            project = cast(
                "ProjectView",
                ctx.client.ask(GetProject(project_id=UUID(str(request["project_id"])))),
            )
            for mount in project.mounts:
                location = cast(
                    "CheckoutLocationView",
                    ctx.client.ask(ResolveCheckout(project.project_id, mount.mount_name, ctx.host_id)),
                )
                if location.state != "active" or location.is_stale:
                    raise invalid("checkout_unavailable")
                mounts[mount.mount_name] = location.local_locator
    batch = research_query(
        ctx,
        spec,
        workspace_id=WorkspaceId(UUID(str(request["workspace_id"]))),
        project_id=ProjectId(UUID(str(request["project_id"]))),
        step_ref=cast("str | None", request.get("step_ref")),
        mounts=mounts,
    )
    return {
        "query_text": batch.query_text,
        "query_digest": batch.query_digest,
        "results": [result_to_json(result) for result in batch.results],
        **(
            {"plan_id": str(plan.plan_id), "research_markdown": render_research(batch)}
            if plan is not None
            else {}
        ),
    }
