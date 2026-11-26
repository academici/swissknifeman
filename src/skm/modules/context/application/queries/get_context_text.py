"""Return captured block text, re-render stored research, or link the prompt artifact."""

from __future__ import annotations

from dataclasses import fields
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from skm.application_bus.registry import QuerySpec
from skm.kernel.errors import NotFound
from skm.kernel.ids import ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.context.application.queries.explain_context import load_manifest
from skm.modules.context.application.query_dtos import ContextTextResponse, GetContextTextRequest
from skm.modules.context.domain.blocks import BlockType
from skm.modules.context.domain.finalize import sha256_text
from skm.modules.context.domain.reasons import HIDDEN_REASONS
from skm.modules.context.domain.research import (
    Citation,
    Claim,
    DocumentTrust,
    ResearchBatch,
    ResearchDocument,
    ResearchError,
    ResearchResult,
    ResearchTier,
    ResearchUsage,
)
from skm.modules.context.domain.research_render import render_research
from skm.modules.context.generated.views import ContextTextView
from skm.modules.context.ports import ResearchRepository, TextStore

if TYPE_CHECKING:
    from skm.application_bus.context import QueryContext
    from skm.kernel.ports_uow import UnitOfWork
    from skm.modules.context.domain.manifest import ContextManifest, ManifestBlock


def scope_of(query: GetContextTextRequest) -> ScopeRef:
    return ScopeRef(ScopeKind.PROJECT, ScopeId(UUID(cast("str", query["project_id"]))))


def _date(value: str | datetime) -> datetime:
    return datetime.fromisoformat(value) if isinstance(value, str) else value


def _result(raw: dict[str, Any]) -> ResearchResult:
    """Decode the stored result's domain fields; scope metadata is checked separately."""
    values = {field.name: raw[field.name] for field in fields(ResearchResult)}
    values["tier"] = ResearchTier(values["tier"])
    values["retrieved_at"] = _date(values["retrieved_at"])
    values["expires_at"] = _date(values["expires_at"]) if values["expires_at"] else None
    documents: list[ResearchDocument] = []
    for doc in values["documents"]:
        data = {field.name: doc[field.name] for field in fields(ResearchDocument)}
        data["retrieved_at"] = _date(data["retrieved_at"])
        data["trust_class"] = DocumentTrust(data["trust_class"])
        documents.append(ResearchDocument(**data))
    values["documents"] = tuple(documents)
    values["citations"] = tuple(Citation(**item) for item in values["citations"])
    values["claims"] = tuple(Claim(item["text"], tuple(item["document_ids"])) for item in values["claims"])
    values["limitations"] = tuple(values["limitations"])
    values["error"] = ResearchError(**values["error"]) if values["error"] else None
    values["usage"] = ResearchUsage(**values["usage"]) if values["usage"] else None
    return ResearchResult(**values)


def _research_text(uow: UnitOfWork, manifest: ContextManifest, block: ManifestBlock) -> str | None:
    if not block.research_query_ids:
        return None
    results: list[ResearchResult] = []
    query_text: str | None = None
    query_digest: str | None = None
    for query_id in block.research_query_ids:
        raw = cast("dict[str, Any]", uow.repo(ResearchRepository).get(query_id))
        if str(raw.get("project_id")) != str(manifest.project_id) or str(raw.get("workspace_id")) != str(
            manifest.workspace_id
        ):
            return None
        if query_text is None:
            query_text, query_digest = raw["query_text"], raw["query_digest"]
        elif (raw["query_text"], raw["query_digest"]) != (query_text, query_digest):
            return None
        results.append(_result(raw.get("result", raw)))
    return render_research(ResearchBatch(query_text or "", query_digest or "", tuple(results)))


def handle(query: GetContextTextRequest, ctx: QueryContext, uow: UnitOfWork) -> ContextTextView:
    manifest = load_manifest(
        uow, ctx.actor.principal_id, cast("str", query["project_id"]), cast("str", query["manifest_id"])
    )
    position = cast("int", query["position"]) if "position" in query else None
    if position is None:
        artifact = manifest.prompt_file_version_id
        return {
            "text": None,
            "available": artifact is not None,
            "prompt_file_version_id": str(artifact) if artifact is not None else None,
        }
    unavailable: ContextTextView = {"text": None, "available": False, "prompt_file_version_id": None}
    block = next(
        (
            b
            for b in manifest.blocks
            if b.position == position and b.included and b.reason not in HIDDEN_REASONS
        ),
        None,
    )
    if block is None or block.content_digest is None:
        return unavailable
    try:
        if block.block_type is BlockType.RESEARCH:
            text = _research_text(uow, manifest, block)
        elif block.content_stored:
            text = uow.repo(TextStore).get_many((block.content_digest,)).get(block.content_digest)
        else:
            text = None
    except NotFound:
        return unavailable
    if text is None or sha256_text(text) != block.content_digest:
        return unavailable
    return {"text": text, "available": True, "prompt_file_version_id": None}


SPEC = QuerySpec(
    name="context.get_context_text",
    dto=GetContextTextRequest,
    result=ContextTextResponse,
    permission="context.read",
    scope_of=scope_of,
    handler=handle,
)
