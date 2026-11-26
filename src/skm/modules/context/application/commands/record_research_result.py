"""Validate and atomically append host research and admitted captured materials."""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import timedelta
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, NotFound, error_for
from skm.kernel.ids import ScopeId, WorkspaceId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.artifacts import public as artifacts
from skm.modules.context.application.queries.find_research_cache import (
    actor_ceiling,
    configured_source,
    research_policy,
    research_scope,
    result_visible,
    source_allowed,
    url_denials,
)
from skm.modules.context.domain.research import (
    ResearchDocument,
    ResearchResult,
    result_from_json,
    result_to_json,
)
from skm.modules.context.domain.research_rules import (
    CLASSIFICATIONS,
    invalid,
    normalize_query,
    query_digest,
    validate_result,
)
from skm.modules.context.generated.commands import RecordResearchResult
from skm.modules.context.generated.results import (
    RecordResearchResultResult,
    record_research_result_result_from_json,
)
from skm.modules.context.ports import ResearchRepository
from skm.platform.logging.redaction import Redactor

if TYPE_CHECKING:
    from skm.application_bus.context import CommandContext
    from skm.kernel.ids import ProjectId
    from skm.kernel.ports_uow import UnitOfWork


def scope_of(cmd: RecordResearchResult) -> ScopeRef:
    return ScopeRef(ScopeKind.PROJECT, ScopeId(UUID(cast("str", cmd["project_id"]))))


def authorize(
    cmd: RecordResearchResult,
    ctx: CommandContext,
    uow: UnitOfWork,
    *,
    for_update: bool,
) -> tuple[WorkspaceId, ProjectId, JsonObject]:
    data = cast("dict[str, Any]", cmd)
    if ctx.actor.kind is PrincipalKind.WORKER and not data.get("step_ref"):
        raise Forbidden(ErrorCode.FORBIDDEN, "worker research requires its assignment step_ref")
    permission = "context.research"
    if ctx.actor.kind is PrincipalKind.WORKER:
        permission = (
            "context.read" if ctx.actor.grant and ctx.actor.grant.kind == "assignment" else "worker.claim"
        )
    wid, pid = research_scope(ctx, uow, data["project_id"], permission=permission)
    if str(wid) != data["workspace_id"]:
        raise NotFound(ErrorCode.NOT_FOUND, "research project not found")
    policy = research_policy(
        ctx,
        uow,
        wid,
        pid,
        step_ref=data.get("step_ref"),
        for_update=for_update,
        permission="context.research",
    )
    for result in data["results"]:
        if not source_allowed(policy, result["source_id"]) or (
            result["tier"] == "deep_research" and data["depth"] != "deep"
        ):
            raise Forbidden(ErrorCode.FORBIDDEN, "research source is disabled in the current scope")
        for doc in result["documents"]:
            if CLASSIFICATIONS.index(doc["classification"]) > CLASSIFICATIONS.index(actor_ceiling(policy)):
                raise Forbidden(
                    ErrorCode.FORBIDDEN, "research document exceeds the actor classification ceiling"
                )
    return wid, pid, policy


def replay_guard(cmd: RecordResearchResult, ctx: CommandContext, uow: UnitOfWork) -> None:
    _, _, policy = authorize(cmd, ctx, uow, for_update=False)
    data = cast("dict[str, Any]", cmd)
    normalize_query(
        data["query_text"], query_max_chars=int(cast("int", policy["context.research.query_max_chars"]))
    )
    for wire in data["results"]:
        result = result_from_json(wire)
        problems = validate_result(
            result,
            config=configured_source(policy, result.source_id),
            max_documents=int(cast("int", policy["context.research.max_documents"])),
            excerpt_max_chars=int(cast("int", policy["context.research.excerpt_max_chars"])),
            url_deny=url_denials(policy),
        )
        if problems:
            raise invalid(problems[0])


def _capture(
    doc: ResearchDocument,
    ctx: CommandContext,
    uow: UnitOfWork,
    workspace_id: WorkspaceId,
    project_id: ProjectId,
) -> tuple[str | None, str]:
    if doc.staged_blob is None:
        return None, doc.classification
    now = ctx.clock.now()
    staged = artifacts.consume_staged_blob(
        uow, ref=doc.staged_blob, workspace_id=workspace_id, request_id=ctx.meta.request_id, now=now
    )
    if doc.content_digest is None or staged.digest.value != doc.content_digest:
        raise error_for(ErrorCode.BLOB_DIGEST_MISMATCH, "captured document digest differs")
    rules = artifacts.build_safety_rules(ctx.config)
    name = (re.sub(r"[^\w.-]+", "-", doc.title, flags=re.UNICODE).strip(".-")[:120] or "research") + ".md"
    safety = artifacts.content_safety
    with ctx.gateways.get(artifacts.BlobStore).open(staged.location()) as stream:
        chunks: list[bytes] = []
        remaining = min(staged.size_bytes, rules.max_text_scan_bytes + 1)
        while remaining:
            chunk = stream.read(remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
    report = safety.scan_bytes(
        name,
        data[: rules.binary_probe_bytes],
        lambda: data,
        staged.size_bytes,
        rules,
        safety.ContentKind.UPLOAD,
        staged.media_type,
        staged.detected_media_type,
    )
    admission = safety.decide_admission(
        report, safety.ContentKind.UPLOAD, artifacts.Classification(doc.classification), ()
    )
    if isinstance(admission, safety.Reject):
        raise error_for(ErrorCode.CONTENT_UNSAFE, "captured research was blocked by safety admission")
    ref = artifacts.register_file_version(
        uow,
        workspace_id=workspace_id,
        project_id=project_id,
        title=doc.title,
        origin=artifacts.FileOrigin.CAPTURE,
        staged=staged,
        original_filename=name,
        media_type=staged.media_type,
        source=artifacts.VersionSource("capture", doc.document_id, now),
        classification=admission.classification,
        safety=admission.report,
        created_by=ctx.actor.principal_id,
        ids=ctx.ids,
        now=now,
    )
    return str(ref["file_version_id"]), admission.classification.value


def _cache_binding(
    result: ResearchResult,
    data: dict[str, Any],
    policy: JsonObject,
    ctx: CommandContext,
    uow: UnitOfWork,
    wid: WorkspaceId,
    pid: ProjectId,
) -> dict[str, Any] | None:
    if result.cache_status != "hit":
        return None
    if not data.get("step_ref") or not policy["context.research.cache.enabled"]:
        raise invalid("cached_result_already_recorded")
    stored = uow.repo(ResearchRepository).find_cached(
        workspace_id=wid, project_id=pid, cache_key=result.cache_key, now=ctx.clock.now()
    )
    if stored is None:
        raise invalid("cached_result_unavailable")
    previous = result_from_json(cast("dict[str, Any]", stored))
    if not result_visible(previous, policy) or len(previous.documents) != len(result.documents):
        raise invalid("cached_result_unavailable")
    mapping = {
        old.document_id: new.document_id
        for old, new in zip(previous.documents, result.documents, strict=True)
    }
    expected = replace(
        previous,
        query_id=result.query_id,
        cache_status="hit",
        documents=tuple(
            replace(doc, document_id=mapping[doc.document_id], staged_blob=None) for doc in previous.documents
        ),
        claims=tuple(
            replace(claim, document_ids=tuple(mapping[ref] for ref in claim.document_ids))
            for claim in previous.claims
        ),
        citations=tuple(
            replace(citation, document_id=mapping[citation.document_id]) for citation in previous.citations
        ),
    )
    if expected != result:
        raise invalid("cached_result_changed")
    return {mapping[str(doc["document_id"])]: doc for doc in cast("list[JsonObject]", stored["documents"])}


def _bounded(result: ResearchResult, policy: JsonObject) -> ResearchResult:
    ttl = int(cast("int", policy["context.research.cache.max_ttl_seconds"]))
    expiry = result.expires_at
    if (
        result.status == "error"
        or result.cache_status == "bypass"
        or not policy["context.research.cache.enabled"]
    ):
        expiry = None
    elif expiry is not None:
        expiry = min(expiry, result.retrieved_at + timedelta(seconds=ttl))
    return replace(
        result,
        expires_at=expiry,
        cache_status=("hit" if result.cache_status == "hit" else "miss") if expiry else "bypass",
    )


def handle(cmd: RecordResearchResult, ctx: CommandContext, uow: UnitOfWork) -> RecordResearchResultResult:
    data = cast("dict[str, Any]", cmd)
    wid, pid, policy = authorize(cmd, ctx, uow, for_update=True)
    text = normalize_query(
        data["query_text"],
        query_max_chars=int(cast("int", policy["context.research.query_max_chars"])),
    )
    redacted = Redactor().text(text)
    if query_digest(text) != data["query_digest"] or redacted != text:
        raise invalid("query_digest_mismatch" if redacted == text else "query_not_redacted")
    limit = min(int(cast("int", policy["context.research.max_documents"])), data["max_documents"])
    if not 1 <= data["max_documents"] <= 50 or not 1 <= len(data["results"]) <= 16:
        raise invalid("invalid_research_bounds")
    rows: list[JsonObject] = []
    output: list[JsonObject] = []
    for wire in data["results"]:
        result = result_from_json(cast("dict[str, Any]", wire))
        if result.query_digest != data["query_digest"] or not source_allowed(policy, result.source_id):
            raise invalid("research_source_or_query_mismatch")
        cached_documents = _cache_binding(result, data, policy, ctx, uow, wid, pid)
        problems = validate_result(
            result,
            config=configured_source(policy, result.source_id),
            max_documents=limit,
            excerpt_max_chars=int(cast("int", policy["context.research.excerpt_max_chars"])),
            url_deny=url_denials(policy),
        )
        if problems:
            raise invalid(problems[0])
        result = _bounded(result, policy)
        raw = result_to_json(result)
        raw.update(
            workspace_id=str(wid),
            project_id=str(pid),
            requested_by=str(ctx.actor.principal_id),
            query_text=text,
            depth=data["depth"],
            max_documents=data["max_documents"],
            step_ref=data.get("step_ref"),
            created_at=ctx.clock.now().isoformat(),
        )
        docs = cast("list[JsonObject]", raw["documents"])
        captured: list[JsonObject] = []
        for doc, stored in zip(result.documents, docs, strict=True):
            if cached_documents is not None:
                version_id = cached_documents[doc.document_id].get("captured_file_version_id")
                classification = doc.classification
            else:
                version_id, classification = _capture(doc, ctx, uow, wid, pid)
            stored.update(
                staged_blob=None,
                classification=classification,
                query_id=result.query_id,
                captured_file_version_id=version_id,
                provenance={
                    "source_id": result.source_id,
                    "source_kind": result.kind,
                    "tier": str(result.tier),
                    "adapter_version": None,
                    "raw_digest": None,
                },
            )
            item: JsonObject = {"document_id": doc.document_id}
            if version_id is not None:
                item["captured_file_version_id"] = version_id
            captured.append(item)
        rows.append(raw)
        output.append(
            {
                "query_id": result.query_id,
                "source_id": result.source_id,
                "status": result.status,
                "documents": cast("list[JsonValue]", captured),
            }
        )
    uow.repo(ResearchRepository).add_results(rows)
    return record_research_result_result_from_json({"results": output})


SPEC = CommandSpec(
    name="context.record_research_result",
    dto=RecordResearchResult,
    result=RecordResearchResultResult,
    permission="context.research",
    permission_alternatives=("context.read", "worker.claim"),
    replay_guard=replay_guard,
    scope_of=scope_of,
    handler=handle,
    idempotency=IdempotencyMode.REQUIRED,
)
