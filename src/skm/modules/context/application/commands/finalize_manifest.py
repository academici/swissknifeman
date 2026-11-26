"""Atomic finalization: live execution ownership, then the context row, then immutable content.

Without host texts, prompt integrity is a trusted worker attestation. A digest alone cannot prove
that a worker honestly collected host inputs. Frozen render data permits full verification with texts.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any, cast
from uuid import UUID

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, error_for
from skm.kernel.ids import ContextManifestId, FileVersionId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeId, ScopeKind, ScopeRef
from skm.kernel.tokens import TokenEstimator
from skm.modules.access import public as access
from skm.modules.artifacts import public as artifacts
from skm.modules.context.application.prompt_artifact import publish_staged_prompt
from skm.modules.context.domain.blocks import BlockType, BudgetClass, canonical_json_digest
from skm.modules.context.domain.decide import Selection
from skm.modules.context.domain.finalize import sha256_text, verify_finalization
from skm.modules.context.domain.host_inputs import HostBlock, HostBlockMeta, HostInputKind, HostReadStatus
from skm.modules.context.domain.manifest import ContextManifest, ManifestState
from skm.modules.context.domain.reasons import ExcludeReason
from skm.modules.context.domain.render import format_host_block, render_block_text
from skm.modules.context.domain.request import validate_owner_ref
from skm.modules.context.generated.commands import finalize_manifest_from_json, finalize_manifest_to_json
from skm.modules.context.generated.results import (
    finalize_manifest_result_from_json,
    finalize_manifest_result_to_json,
)
from skm.modules.context.ports import ContextOwnerClaim, ContextOwnerGuard, ContextRepository, TextStore


class FinalizeManifest(dict[str, Any]):
    """Bus identity for the generated JSON-mode DTO; generated codecs own its wire fields."""

    SCHEMA_URN = "urn:skm:context:command:finalize-manifest:v1"

    @classmethod
    def from_json(cls, data: Any) -> FinalizeManifest:
        return cls(finalize_manifest_from_json(data))

    def to_json(self) -> Any:
        return finalize_manifest_to_json(cast("Any", self))


class FinalizeManifestResult(dict[str, Any]):
    SCHEMA_URN = "urn:skm:context:result:finalize-manifest:v1"

    @classmethod
    def from_json(cls, data: Any) -> FinalizeManifestResult:
        return cls(finalize_manifest_result_from_json(data))

    def to_json(self) -> Any:
        return finalize_manifest_result_to_json(cast("Any", self))


def scope_of_manifest(cmd: FinalizeManifest, uow: UnitOfWork) -> ScopeRef | None:
    try:
        manifest = uow.repo(ContextRepository).get(ContextManifestId(UUID(cmd["manifest_id"])))
    except NotFound:
        return None
    return ScopeRef(ScopeKind.PROJECT, ScopeId(manifest.project_id))


def _binding(manifest: ContextManifest) -> tuple[object, ...]:
    return (
        manifest.owner_ref,
        manifest.workspace_id,
        manifest.project_id,
        manifest.plan_id,
        manifest.revision_id,
        manifest.purpose,
    )


def _selection(cmd: FinalizeManifest) -> Selection:
    raw = cmd["selection"]
    try:
        return Selection(
            included=tuple((str(ref), int(pos)) for ref, pos in raw["included"]),
            excluded=tuple(
                (str(ref), ExcludeReason(str(reason)), detail) for ref, reason, detail in raw["excluded"]
            ),
            class_usage={BudgetClass(k): v for k, v in raw["class_usage"].items()},
            total_tokens=raw["total_tokens"],
            task_digest=raw["task_digest"],
            mode=raw["mode"],
        )
    except (TypeError, ValueError) as exc:
        raise error_for(ErrorCode.CONTEXT_MANIFEST_TAMPERED, "invalid selection metadata") from exc


def _result(manifest: ContextManifest) -> FinalizeManifestResult:
    if (
        manifest.mode is None
        or manifest.task_digest is None
        or manifest.prompt_digest is None
        or manifest.total_tokens_estimate is None
    ):
        raise error_for(ErrorCode.INTERNAL_ERROR, "final manifest has incomplete result fields")
    return FinalizeManifestResult(
        manifest_id=str(manifest.id),
        state="final",
        mode=manifest.mode,
        task_digest=manifest.task_digest,
        prompt_digest=manifest.prompt_digest,
        total_tokens_estimate=manifest.total_tokens_estimate,
    )


def _host_inputs(
    cmd: FinalizeManifest, manifest: ContextManifest
) -> tuple[list[HostBlockMeta], dict[str, str]]:
    requests = {req.request_id: req for req in manifest.host_inputs}
    metas: list[HostBlockMeta] = []
    texts: dict[str, str] = {}
    seen: set[str] = set()
    for item in cmd["host_blocks"]:
        rid = item["request_id"]
        if rid not in requests or rid in seen:
            raise error_for(
                ErrorCode.CONTEXT_MANIFEST_TAMPERED,
                "unknown or repeated host request",
                details={"request_id": rid},
            )
        seen.add(rid)
        req, status = requests[rid], HostReadStatus(item["status"])
        if req.required and status is not HostReadStatus.OK:
            raise error_for(
                ErrorCode.CONTEXT_INPUT_MISSING,
                "required host input is unavailable",
                details={"request_id": rid},
            )
        if (
            status is HostReadStatus.OK
            and req.kind is not HostInputKind.DEPENDENCY_MANIFEST
            and any(item[k] is None for k in ("text_digest", "size_bytes", "tokens_estimate"))
        ):
            raise error_for(ErrorCode.CONTEXT_MANIFEST_TAMPERED, "OK input lacks content metadata")
        if "text" in item:
            text = item["text"]
            if sha256_text(text) != item["text_digest"]:
                raise error_for(ErrorCode.BLOB_DIGEST_MISMATCH, "host text digest differs")
            if len(text.encode("utf-8")) != item["size_bytes"]:
                raise error_for(ErrorCode.CONTEXT_MANIFEST_TAMPERED, "host text UTF-8 size differs")
            if status is not HostReadStatus.OK:
                raise error_for(ErrorCode.CONTEXT_MANIFEST_TAMPERED, "non-OK input carries text")
            texts[cast("str", item["text_digest"])] = text
        metas.append(
            HostBlockMeta(
                rid,
                status,
                item["resolved_path"],
                item["text_digest"],
                item["size_bytes"],
                item["tokens_estimate"],
                tuple(item.get("research_query_ids", ())),
            )
        )
    if seen != requests.keys():
        raise error_for(ErrorCode.CONTEXT_MANIFEST_TAMPERED, "host requests are not fully accounted for")
    return metas, texts


def _verify_render(
    cmd: FinalizeManifest, manifest: ContextManifest, uow: UnitOfWork, estimator: TokenEstimator, prompt: str
) -> None:
    """Render only from the admitted snapshot, never live settings or newly resolved resources."""
    snapshot = manifest.route.get("render_snapshot")
    if not isinstance(snapshot, Mapping):
        raise error_for(ErrorCode.CONTEXT_MANIFEST_TAMPERED, "draft has no frozen render snapshot")
    frozen = cast("dict[str, Any]", snapshot)
    templates = frozen["templates"]
    plan = {BlockType(k): tuple(v) for k, v in frozen["prompt_plan"].items()}
    variables = frozen["variables"]
    stored = {b.block_ref: b for b in manifest.blocks}
    texts = uow.repo(TextStore).get_many(tuple(b.content_digest for b in manifest.blocks if b.content_digest))
    host = {f"h:{item['request_id']}": item for item in cmd["host_blocks"]}
    requests = {req.request_id: req for req in manifest.host_inputs}
    bodies: list[str] = []
    for ref, _ in sorted(_selection(cmd).included, key=lambda pair: pair[1]):
        if ref in stored:
            row = stored[ref]
            content = texts.get(row.content_digest or "")
            if content is None or sha256_text(content) != row.content_digest:
                raise error_for(ErrorCode.CONTEXT_MANIFEST_TAMPERED, "server text is unavailable or changed")
            btype, title, source = row.block_type, frozen["titles"][ref], row.source_ref
        else:
            item = host[ref]
            hb = HostBlock(
                item["request_id"],
                HostReadStatus(item["status"]),
                item["resolved_path"],
                item.get("text"),
                item["text_digest"],
                item["size_bytes"],
                item["tokens_estimate"],
            )
            btype, title, content, source = format_host_block(requests[hb.request_id], hb)
        body = render_block_text(
            block_type=btype,
            title=title,
            content=content,
            source_ref=source,
            templates=templates,
            prompt_plan=plan,
            variables=variables,
        )
        if ref in host and estimator.estimate(body) != host[ref]["tokens_estimate"]:
            raise error_for(ErrorCode.CONTEXT_MANIFEST_TAMPERED, "host token estimate differs")
        bodies.append(body)
    expected = "\n\n".join(bodies) + ("\n" if bodies else "")
    if prompt != expected:
        raise error_for(ErrorCode.BLOB_DIGEST_MISMATCH, "prompt differs from deterministic full render")


def _authorize_owner(
    uow: UnitOfWork, ctx: CommandContext, observed: ContextManifest, claim: JsonObject | None
) -> None:
    permissions = access.effective_permissions(uow, ctx.actor, ScopeId(observed.project_id))
    owner = validate_owner_ref(observed.owner_ref, observed.purpose.step_ref)
    if owner is not None:
        if owner != ctx.actor.principal_id or "context.assemble" not in permissions:
            raise error_for(
                ErrorCode.FORBIDDEN,
                "standalone context finalization requires the owner and project permission",
            )
        if claim is not None:
            raise error_for(
                ErrorCode.SCHEMA_INVALID, "standalone context finalization has no execution claim"
            )
        return
    if not {"worker.claim", "run.control"} & permissions:
        raise error_for(
            ErrorCode.FORBIDDEN, "context finalization requires current worker or operator authority"
        )
    if claim is None:
        raise error_for(ErrorCode.SCHEMA_INVALID, "step finalization requires the current execution claim")
    ctx.gateways.get(ContextOwnerGuard).require_current(
        uow,
        ctx.actor,
        observed.owner_ref,
        ContextOwnerClaim(
            UUID(str(claim["assignment_id"])),
            UUID(str(claim["attempt_id"])),
            UUID(str(claim["worker_id"])),
            cast("int", claim["fencing_token"]),
        ),
        ctx.clock.now(),
    )


def handle(cmd: FinalizeManifest, ctx: CommandContext, uow: UnitOfWork) -> FinalizeManifestResult:
    repo = uow.repo(ContextRepository)
    mid = ContextManifestId(UUID(cmd["manifest_id"]))
    observed = repo.get(mid)  # Immutable binding only; execution owns the first row locks.
    if (
        ctx.scope != ScopeRef(ScopeKind.PROJECT, ScopeId(observed.project_id))
        or ctx.scope_chain[-1].workspace_id != observed.workspace_id
    ):
        raise error_for(ErrorCode.NOT_FOUND, "manifest does not belong to the authorized project")
    _authorize_owner(uow, ctx, observed, cmd.get("claim"))
    manifest = repo.get(mid, for_update=True)
    if _binding(manifest) != _binding(observed):
        raise error_for(ErrorCode.NOT_FOUND, "manifest ownership or scope changed")
    request_digest = canonical_json_digest(cast("JsonObject", cmd))
    if manifest.state is ManifestState.FINAL:
        if manifest.route.get("finalization_request_digest") != request_digest:
            raise error_for(ErrorCode.INVALID_TRANSITION, "final manifest has a different request body")
        return _result(manifest)
    metas, texts = _host_inputs(cmd, manifest)
    if cmd["host_facts"]["work_paths_count"] != len(cmd["host_facts"]["work_paths"]):
        raise error_for(ErrorCode.CONTEXT_MANIFEST_TAMPERED, "work_paths_count differs from work_paths")
    version_id = (
        publish_staged_prompt(uow, ctx, manifest, cmd["prompt_staged_blob"], cmd["rendered_prompt_digest"])
        if "prompt_staged_blob" in cmd
        else FileVersionId(UUID(cmd["prompt_file_version_id"]))
    )
    artifacts.require_ready_versions(uow, manifest.workspace_id, (version_id,))
    artifact = artifacts.get_file_version(uow, version_id)
    if artifact.digest != cmd["rendered_prompt_digest"]:
        raise error_for(ErrorCode.BLOB_DIGEST_MISMATCH, "prompt artifact digest differs")
    prompt = artifacts.read_text_content(uow, version_id, max_bytes=artifact.size_bytes)
    if prompt is None or sha256_text(prompt) != artifact.digest:
        raise error_for(ErrorCode.BLOB_DIGEST_MISMATCH, "prompt artifact bytes differ")
    snapshot = manifest.route.get("render_snapshot")
    store_content = (
        bool(snapshot.get("store_host_content", False)) if isinstance(snapshot, Mapping) else False
    )
    if store_content and any(item["status"] == "ok" and "text" not in item for item in cmd["host_blocks"]):
        raise error_for(ErrorCode.CONTEXT_MANIFEST_TAMPERED, "admitted content policy requires host texts")
    final, rows = verify_finalization(
        manifest,
        draft_digest=cmd["draft_digest"],
        estimator_id=cmd["estimator_id"],
        host_meta=metas,
        facts_meta=cast("JsonObject", cmd["host_facts"]),
        claimed_selection=_selection(cmd),
        rendered_prompt_digest=cmd["rendered_prompt_digest"],
        artifact_prompt_digest=artifact.digest,
        prompt_file_version_id=version_id,
        finalized_at=ctx.clock.now(),
        store_host_content=store_content,
        runtime_self_loaded=cast("list[JsonObject]", cmd["runtime_self_loaded"]),
    )
    if all(item["status"] != "ok" or "text" in item for item in cmd["host_blocks"]):
        estimator = ctx.gateways.get(TokenEstimator)
        if estimator.estimator_id != manifest.estimator_id:
            raise error_for(
                ErrorCode.CONTEXT_MANIFEST_TAMPERED, "render estimator differs from admitted draft"
            )
        _verify_render(cmd, manifest, uow, estimator, prompt)
    route = {**final.route, "finalization_request_digest": request_digest}
    diagnostics = final.diagnostics

    def sources(items: JsonValue) -> list[tuple[str, tuple[str, ...]]]:
        return sorted(
            (str(v.get("kind")), tuple(sorted(cast("list[str]", v.get("files", [])))))
            for v in cast("list[JsonObject]", items or [])
        )

    if sources(manifest.route.get("self_loads")) != sources(cast("JsonValue", cmd["runtime_self_loaded"])):
        diagnostics = (
            *diagnostics,
            {
                "code": "RUNTIME_SELF_LOADS_MISMATCH",
                "severity": "warning",
                "message": "Observed runtime self-loads differ from the admitted route",
            },
        )
    if store_content:
        uow.repo(TextStore).put_many(texts)
    repo.finalize(replace(final, route=route, diagnostics=diagnostics), rows)
    return _result(final)


SPEC = CommandSpec(
    name="context.finalize_manifest",
    dto=FinalizeManifest,
    result=FinalizeManifestResult,
    permission="worker.claim",
    permission_alternatives=("run.control", "context.assemble"),
    scope_of=None,
    scope_resolver=scope_of_manifest,
    handler=handle,
    idempotency=IdempotencyMode.FORBIDDEN,
)
