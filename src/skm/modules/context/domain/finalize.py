"""Pure Phase-B context finalization and server-side finalization verification (context §5.9-§5.13)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from hashlib import sha256
from typing import cast
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.ids import (
    FileVersionId,
    PlanId,
    ProjectId,
    ResourceVersionId,
    RevisionId,
    WorkspaceId,
)
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.tokens import TokenEstimator
from skm.modules.context.domain.blocks import ASSEMBLER_VERSION, BlockType, BudgetClass
from skm.modules.context.domain.contracts import Digest, HostFactsMeta
from skm.modules.context.domain.decide import (
    HOST_STATUS_TO_EXCLUDE_REASON,
    Selection,
    decide_with_diagnostics,
    host_include_reason,
)
from skm.modules.context.domain.draft import ContextDraft, compute_draft_digest, draft_meta_of
from skm.modules.context.domain.host_inputs import (
    HostBlock,
    HostBlockMeta,
    HostFacts,
    HostInputKind,
    HostInputRequest,
    HostReadStatus,
)
from skm.modules.context.domain.manifest import (
    ClassUsage,
    ContextManifest,
    ManifestBlock,
    ManifestState,
    draft_block_to_manifest_row,
    draft_meta_from_manifest,
)
from skm.modules.context.domain.reasons import ExcludeReason, IncludeReason
from skm.modules.context.domain.render import format_host_block, render, render_block_text
from skm.modules.context.domain.request import StepPurpose

__all__ = [
    "FinalizedContext",
    "build_host_manifest_rows",
    "finalize",
    "host_facts_to_meta",
    "sha256_text",
    "verify_finalization",
]

_EPOCH_UTC = datetime(1970, 1, 1, tzinfo=UTC)
_NIL_UUID = UUID(int=0)


@dataclass(frozen=True, slots=True)
class FinalizedContext:
    manifest: ContextManifest
    rendered_prompt: str
    prompt_digest: Digest
    selection: Selection


def sha256_text(text: str) -> Digest:
    """Return ``sha256:<hex>`` of UTF-8 encoded ``text``."""
    return f"sha256:{sha256(text.encode('utf-8')).hexdigest()}"


def host_facts_to_meta(facts: HostFacts) -> HostFactsMeta:
    """Serialize ``HostFacts`` into canonical ``HostFactsMeta`` JSON dictionary."""
    sorted_paths = sorted(facts.work_paths)
    deps_j = list[JsonValue](sorted(facts.deps))
    wp_j: list[JsonValue] = [list[JsonValue]([mount, path]) for mount, path in sorted_paths]
    return {
        "deps": deps_j,
        "work_paths_count": len(sorted_paths),
        "work_paths_truncated": facts.work_paths_truncated,
        "work_paths": wp_j,
    }


def _host_block_to_meta(
    hb: HostBlock,
    req: HostInputRequest,
    draft: ContextDraft,
    estimator: TokenEstimator,
) -> HostBlockMeta:
    if (
        hb.status is not HostReadStatus.OK
        or req.kind is HostInputKind.DEPENDENCY_MANIFEST
        or req.block_type is None
    ):
        return HostBlockMeta(
            request_id=hb.request_id,
            status=hb.status,
            resolved_path=hb.resolved_path,
            text_digest=hb.text_digest,
            size_bytes=hb.size_bytes,
            tokens_estimate=hb.tokens_estimate,
            research_query_ids=(),
        )
    if hb.text is None:
        raise ValidationFailed(
            ErrorCode.CONTEXT_MANIFEST_TAMPERED,
            f"OK host block '{hb.request_id}' is missing text",
            details={"request_id": hb.request_id},
        )
    raw_bytes = len(hb.text.encode("utf-8"))
    size_bytes = raw_bytes if hb.size_bytes is None else hb.size_bytes
    if size_bytes != raw_bytes:
        raise ValidationFailed(
            ErrorCode.CONTEXT_MANIFEST_TAMPERED,
            f"OK host block '{hb.request_id}' size_bytes does not match UTF-8 length",
            details={"request_id": hb.request_id, "declared": size_bytes, "actual": raw_bytes},
        )
    raw_digest = sha256_text(hb.text)
    if hb.text_digest is not None and hb.text_digest != raw_digest:
        raise ValidationFailed(
            ErrorCode.CONTEXT_MANIFEST_TAMPERED,
            f"OK host block '{hb.request_id}' text_digest mismatch",
            details={"request_id": hb.request_id, "declared": hb.text_digest, "actual": raw_digest},
        )
    btype, title, body, source_ref = format_host_block(req, hb)
    wrapped = render_block_text(
        block_type=btype,
        title=title,
        content=body,
        source_ref=source_ref,
        templates=draft.templates,
        prompt_plan=draft.prompt_plan,
        variables=draft.variables,
    )
    computed_tokens = estimator.estimate(wrapped)
    if hb.tokens_estimate is not None and hb.tokens_estimate != computed_tokens:
        raise ValidationFailed(
            ErrorCode.CONTEXT_MANIFEST_TAMPERED,
            f"OK host block '{hb.request_id}' tokens_estimate mismatch",
            details={"request_id": hb.request_id, "declared": hb.tokens_estimate, "actual": computed_tokens},
        )
    return HostBlockMeta(
        request_id=hb.request_id,
        status=hb.status,
        resolved_path=hb.resolved_path,
        text_digest=raw_digest,
        size_bytes=size_bytes,
        tokens_estimate=computed_tokens,
        research_query_ids=(),
    )


def build_host_manifest_rows(
    *,
    start_ordinal: int,
    host_inputs: Sequence[HostInputRequest],
    host_meta: Sequence[HostBlockMeta],
    selection: Selection,
    store_content: bool,
) -> tuple[ManifestBlock, ...]:
    """Construct finalized ``ManifestBlock`` rows (``h:hi:<n>``) for planned host inputs."""
    included_pos = dict(selection.included)
    excluded_map = {ref: (reason, detail) for ref, reason, detail in selection.excluded}
    meta_by_id = {hm.request_id: hm for hm in host_meta}
    rows: list[ManifestBlock] = []
    ordinal = start_ordinal
    source_kind_map = {
        HostInputKind.REPO_INSTRUCTIONS: "repository_path",
        HostInputKind.REPOSITORY_PATH: "repository_path",
        HostInputKind.RESEARCH_QUERY: "external",
    }
    for req in host_inputs:
        if req.kind is HostInputKind.DEPENDENCY_MANIFEST or req.block_type is None:
            continue
        hm = meta_by_id[req.request_id]
        btype = req.block_type
        bclass = (
            BudgetClass.SUPPORTING
            if btype in (BlockType.REPO_INSTRUCTIONS, BlockType.MATERIALS)
            else BudgetClass.RETRIEVAL
        )
        block_ref = f"h:{req.request_id}"
        if block_ref in included_pos:
            included = True
            position: int | None = included_pos[block_ref]
            reason = host_include_reason(req.kind, required=req.required).value
            detail: str | None = hm.resolved_path
            stored = store_content and hm.text_digest is not None
        else:
            included = False
            position = None
            exc_reason, exc_detail = excluded_map.get(
                block_ref,
                (
                    HOST_STATUS_TO_EXCLUDE_REASON.get(hm.status, ExcludeReason.OVER_TOTAL_BUDGET),
                    hm.resolved_path,
                ),
            )
            reason = exc_reason.value
            detail = exc_detail if exc_detail is not None else hm.resolved_path
            stored = False
        rows.append(
            ManifestBlock(
                ordinal=ordinal,
                block_ref=block_ref,
                position=position,
                block_type=btype,
                budget_class=bclass,
                mandatory=req.required and btype is BlockType.MATERIALS,
                source_kind=source_kind_map[req.kind],
                source_ref=req.source_ref,
                source_version=None,
                trust=req.trust,
                tokens_estimate=hm.tokens_estimate,
                content_digest=hm.text_digest,
                included=included,
                reason=reason,
                detail=detail,
                atomic_group=None,
                content_stored=stored,
                research_query_ids=hm.research_query_ids,
            )
        )
        ordinal += 1
    return tuple(rows)


def _apply_selection_to_draft_rows(
    draft_blocks: Sequence[ManifestBlock],
    selection: Selection,
) -> tuple[ManifestBlock, ...]:
    included_pos = dict(selection.included)
    excluded_map = {ref: (reason, detail) for ref, reason, detail in selection.excluded}
    updated: list[ManifestBlock] = []
    for row in draft_blocks:
        if row.block_ref.startswith("x:"):
            updated.append(row)
            continue
        if row.block_ref in included_pos:
            reason = IncludeReason.TRIGGER_DEP.value if row.block_ref.startswith("c:") else row.reason
            updated.append(replace(row, included=True, position=included_pos[row.block_ref], reason=reason))
        else:
            exc_reason, exc_detail = excluded_map[row.block_ref]
            updated.append(
                replace(
                    row,
                    included=False,
                    position=None,
                    reason=exc_reason.value,
                    detail=exc_detail if exc_detail is not None else row.detail,
                )
            )
    return tuple(updated)


def _fallback_draft_manifest(draft: ContextDraft) -> ContextManifest:
    draft_rows: list[ManifestBlock] = [draft_block_to_manifest_row(b, prefix="d") for b in draft.blocks]
    draft_rows.extend(draft_block_to_manifest_row(cb.block, prefix="c") for cb in draft.conditional)
    draft_rows.extend(draft.excluded)
    draft_rows.sort(key=lambda r: r.ordinal)
    role_ns = draft.variables.get("role")
    runtime_ns = draft.variables.get("runtime")
    run_ns = draft.variables.get("run")
    role_map: Mapping[str, JsonValue] = (
        cast("Mapping[str, JsonValue]", role_ns) if isinstance(role_ns, Mapping) else {}
    )
    rt_map: Mapping[str, JsonValue] = (
        cast("Mapping[str, JsonValue]", runtime_ns) if isinstance(runtime_ns, Mapping) else {}
    )
    run_map: Mapping[str, JsonValue] = (
        cast("Mapping[str, JsonValue]", run_ns) if isinstance(run_ns, Mapping) else {}
    )
    role_name = str(role_map.get("name", "executor"))
    runtime_id = str(rt_map.get("id", "default_runtime"))
    model_id = str(rt_map.get("model", "default"))
    att_raw, rnd_raw = run_map.get("attempt_no"), run_map.get("round_no")
    attempt_no = int(att_raw) if isinstance(att_raw, int) and not isinstance(att_raw, bool) else 1
    round_no = int(rnd_raw) if isinstance(rnd_raw, int) and not isinstance(rnd_raw, bool) else 1
    step_ref = f"stp_{draft.manifest_id}"
    empty_deg: list[JsonValue] = []
    empty_sl: list[JsonValue] = []
    return ContextManifest(
        id=draft.manifest_id,
        state=ManifestState.DRAFT,
        workspace_id=WorkspaceId(_NIL_UUID),
        project_id=ProjectId(_NIL_UUID),
        plan_id=PlanId(_NIL_UUID),
        revision_id=RevisionId(_NIL_UUID),
        entity_id=None,
        purpose=StepPurpose(
            role=role_name,
            stage_id=role_name,
            step_ref=step_ref,
            attempt_no=attempt_no,
            round_no=round_no,
        ),
        agent_profile_version_id=ResourceVersionId(_NIL_UUID),
        runtime_id=runtime_id,
        model=model_id,
        route={
            "route_source": "default",
            "operation": "agent_step",
            "config_mode": "isolated",
            "degraded": empty_deg,
            "self_loads": empty_sl,
            "self_loads_observed": None,
        },
        draft_digest=draft.draft_digest,
        mode=None,
        task_digest=None,
        prompt_digest=None,
        prompt_file_version_id=None,
        total_tokens_estimate=None,
        total_limit=draft.budget.total_limit,
        budgets={
            cls: ClassUsage(tokens=None, limit=draft.budget.class_limits.get(cls)) for cls in BudgetClass
        },
        blocks=tuple(draft_rows),
        host_facts=None,
        skills_trace=draft.skills_trace,
        diagnostics=draft.diagnostics,
        estimator_id=draft.budget.estimator_id,
        assembler_version=ASSEMBLER_VERSION,
        created_at=_EPOCH_UTC,
        finalized_at=None,
        owner_ref=f"step:{step_ref}",
        host_inputs=draft.host_inputs,
    )


def finalize(
    draft: ContextDraft, host_blocks: Sequence[HostBlock], facts: HostFacts, estimator: TokenEstimator
) -> FinalizedContext:
    """Deterministic Phase-B finalization: ``decide`` + ``render`` + ``prompt_digest`` + final manifest."""
    if estimator.estimator_id != draft.budget.estimator_id:
        raise ValidationFailed(
            ErrorCode.CONTEXT_MANIFEST_TAMPERED,
            "token estimator mismatch between draft and finalize",
            details={"expected": draft.budget.estimator_id, "actual": estimator.estimator_id},
        )

    req_by_id = {req.request_id: req for req in draft.host_inputs}
    meta_list: list[HostBlockMeta] = []
    normalized_blocks: list[HostBlock] = []
    for hb in host_blocks:
        req = req_by_id.get(hb.request_id)
        if req is None:
            raise ValidationFailed(
                ErrorCode.CONTEXT_MANIFEST_TAMPERED,
                f"unknown host block request_id '{hb.request_id}'",
                details={"request_id": hb.request_id},
            )
        hm = _host_block_to_meta(hb, req, draft, estimator)
        meta_list.append(hm)
        normalized_blocks.append(
            HostBlock(
                request_id=hb.request_id,
                status=hb.status,
                resolved_path=hb.resolved_path,
                text=hb.text,
                text_digest=hm.text_digest,
                size_bytes=hm.size_bytes,
                tokens_estimate=hm.tokens_estimate,
            )
        )

    draft_meta = draft_meta_of(
        manifest_id=draft.manifest_id,
        blocks=draft.blocks,
        conditional=draft.conditional,
        host_inputs=draft.host_inputs,
        budget=draft.budget,
        resume=draft.resume,
        repo_max_files=draft.repo_max_files,
    )
    computed_draft_digest = compute_draft_digest(draft_meta)
    if draft.draft_digest != computed_draft_digest:
        raise ValidationFailed(
            ErrorCode.CONTEXT_MANIFEST_TAMPERED,
            "draft_digest does not match draft metadata",
            details={"expected": computed_draft_digest, "actual": draft.draft_digest},
        )

    selection, budget_diags = decide_with_diagnostics(draft_meta, meta_list, facts)
    rendered_prompt, _pieces = render(draft, normalized_blocks, selection)
    p_digest = sha256_text(rendered_prompt)

    base = draft.manifest if draft.manifest is not None else _fallback_draft_manifest(draft)
    updated_draft_rows = _apply_selection_to_draft_rows(base.blocks, selection)
    next_ordinal = max((r.ordinal for r in updated_draft_rows), default=-1) + 1
    host_rows = build_host_manifest_rows(
        start_ordinal=next_ordinal,
        host_inputs=draft.host_inputs,
        host_meta=meta_list,
        selection=selection,
        store_content=False,
    )
    final_budgets = {
        cls: ClassUsage(
            tokens=selection.class_usage[cls],
            limit=draft.budget.class_limits.get(cls),
        )
        for cls in BudgetClass
    }
    final_manifest = replace(
        base,
        state=ManifestState.FINAL,
        mode=selection.mode,
        task_digest=selection.task_digest,
        prompt_digest=p_digest,
        total_tokens_estimate=selection.total_tokens,
        budgets=final_budgets,
        blocks=(*updated_draft_rows, *host_rows),
        host_facts=host_facts_to_meta(facts),
        diagnostics=(*base.diagnostics, *budget_diags),
        finalized_at=base.created_at,
    )
    return FinalizedContext(
        manifest=final_manifest,
        rendered_prompt=rendered_prompt,
        prompt_digest=p_digest,
        selection=selection,
    )


def verify_finalization(  # noqa: PLR0913 -- explicit protocol fields of finalize-manifest.v1
    stored_draft: ContextManifest,
    *,
    draft_digest: Digest,
    estimator_id: str,
    host_meta: Sequence[HostBlockMeta],
    facts_meta: HostFactsMeta,
    claimed_selection: Selection,
    rendered_prompt_digest: Digest,
    artifact_prompt_digest: Digest,
    prompt_file_version_id: FileVersionId,
    finalized_at: datetime,
    store_host_content: bool = False,
    runtime_self_loaded: Sequence[JsonObject] = (),
) -> tuple[ContextManifest, tuple[ManifestBlock, ...]]:
    """Server-side Phase-C verification: recompute ``decide`` from stored draft rows and compare."""
    if stored_draft.state is not ManifestState.DRAFT:
        raise ValidationFailed(
            ErrorCode.CONTEXT_MANIFEST_TAMPERED,
            "manifest is not in draft state",
            details={"state": stored_draft.state.value},
        )
    if draft_digest != stored_draft.draft_digest:
        raise ValidationFailed(
            ErrorCode.CONTEXT_MANIFEST_TAMPERED,
            "draft_digest mismatch",
            details={"expected": stored_draft.draft_digest, "actual": draft_digest},
        )
    if estimator_id != stored_draft.estimator_id:
        raise ValidationFailed(
            ErrorCode.CONTEXT_MANIFEST_TAMPERED,
            "estimator_id mismatch",
            details={"expected": stored_draft.estimator_id, "actual": estimator_id},
        )
    if rendered_prompt_digest != artifact_prompt_digest:
        raise ValidationFailed(
            ErrorCode.CONTEXT_MANIFEST_TAMPERED,
            "prompt artifact digest does not match rendered_prompt_digest",
            details={"expected": rendered_prompt_digest, "actual": artifact_prompt_digest},
        )

    rebuilt_meta = draft_meta_from_manifest(stored_draft)
    recomputed, budget_diags = decide_with_diagnostics(rebuilt_meta, host_meta, facts_meta)
    if (
        recomputed.included != claimed_selection.included
        or recomputed.excluded != claimed_selection.excluded
        or recomputed.total_tokens != claimed_selection.total_tokens
        or recomputed.task_digest != claimed_selection.task_digest
        or recomputed.mode != claimed_selection.mode
        or dict(recomputed.class_usage) != dict(claimed_selection.class_usage)
    ):
        raise ValidationFailed(
            ErrorCode.CONTEXT_MANIFEST_TAMPERED,
            "server selection recomputation does not match worker selection",
            details={"manifest_id": str(stored_draft.id)},
        )

    updated_draft_rows = _apply_selection_to_draft_rows(stored_draft.blocks, recomputed)
    next_ordinal = max((r.ordinal for r in updated_draft_rows), default=-1) + 1
    host_rows = build_host_manifest_rows(
        start_ordinal=next_ordinal,
        host_inputs=stored_draft.host_inputs,
        host_meta=host_meta,
        selection=recomputed,
        store_content=store_host_content,
    )
    final_budgets = {
        cls: ClassUsage(
            tokens=recomputed.class_usage[cls],
            limit=stored_draft.budgets[cls].limit if cls in stored_draft.budgets else None,
        )
        for cls in BudgetClass
    }
    updated_route = dict(stored_draft.route)
    obs_j: list[JsonValue] = [dict(item) for item in runtime_self_loaded]
    updated_route["self_loads_observed"] = obs_j
    final_manifest = replace(
        stored_draft,
        state=ManifestState.FINAL,
        route=updated_route,
        mode=recomputed.mode,
        task_digest=recomputed.task_digest,
        prompt_digest=rendered_prompt_digest,
        prompt_file_version_id=prompt_file_version_id,
        total_tokens_estimate=recomputed.total_tokens,
        budgets=final_budgets,
        blocks=(*updated_draft_rows, *host_rows),
        host_facts=dict(facts_meta),
        diagnostics=(*stored_draft.diagnostics, *budget_diags),
        finalized_at=finalized_at,
    )
    return final_manifest, host_rows
