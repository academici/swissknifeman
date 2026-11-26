"""Facade of the context module (context §13)."""

from __future__ import annotations

from dataclasses import replace
from importlib import import_module
from typing import TYPE_CHECKING, Any, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.context.application.assemble_draft import assemble_draft as _assemble_draft
from skm.modules.context.application.queries.find_research_cache import (
    design_research_evidence as design_research_evidence,
)
from skm.modules.context.application.registry import COMMANDS as _RESEARCH_COMMANDS
from skm.modules.context.application.registry import QUERIES as _RESEARCH_QUERIES
from skm.modules.context.domain.blocks import BlockType as BlockType
from skm.modules.context.domain.blocks import BudgetClass as BudgetClass
from skm.modules.context.domain.blocks import TrustLevel as TrustLevel
from skm.modules.context.domain.decide import Selection as Selection
from skm.modules.context.domain.delegation_compiler import DelegationCompiler as DelegationCompiler
from skm.modules.context.domain.deps import project_deps
from skm.modules.context.domain.draft import ContextDraft as ContextDraft
from skm.modules.context.domain.draft import DraftBlock as DraftBlock
from skm.modules.context.domain.finalize import FinalizedContext as FinalizedContext
from skm.modules.context.domain.finalize import finalize as _finalize_domain
from skm.modules.context.domain.finalize import host_facts_to_meta, sha256_text
from skm.modules.context.domain.host_inputs import HostBlock as HostBlock
from skm.modules.context.domain.host_inputs import HostBlockMeta as HostBlockMeta
from skm.modules.context.domain.host_inputs import HostFacts as HostFacts
from skm.modules.context.domain.host_inputs import HostInputKind, HostReadStatus, HostSelector
from skm.modules.context.domain.host_inputs import HostInputRequest as HostInputRequest
from skm.modules.context.domain.manifest import ContextManifest as ContextManifest
from skm.modules.context.domain.manifest import ManifestState as ManifestState
from skm.modules.context.domain.payload_compiler import PayloadCompiler as PayloadCompiler
from skm.modules.context.domain.prefix_compiler import PrefixStablePrompt as PrefixStablePrompt
from skm.modules.context.domain.prefix_compiler import (
    PrefixStablePromptCompiler as PrefixStablePromptCompiler,
)
from skm.modules.context.domain.render import format_host_block, render_block_text
from skm.modules.context.domain.request import ContextRequest as ContextRequest
from skm.modules.context.domain.request import ExecutionBlocks as ExecutionBlocks
from skm.modules.context.domain.request import PermissionsSummary as PermissionsSummary
from skm.modules.context.domain.request import ResumeInfo as ResumeInfo
from skm.modules.context.domain.request import RunParams as RunParams
from skm.modules.context.domain.request import RuntimeTarget as RuntimeTarget
from skm.modules.context.domain.request import StepPurpose as StepPurpose
from skm.modules.context.domain.research import Claim as Claim
from skm.modules.context.domain.research import RawDocument as RawDocument
from skm.modules.context.domain.research import RawSourceReply as RawSourceReply
from skm.modules.context.domain.research import ResearchBatch as ResearchBatch
from skm.modules.context.domain.research import ResearchDocument as ResearchDocument
from skm.modules.context.domain.research import ResearchItem as ResearchItem
from skm.modules.context.domain.research import ResearchQuerySpec as ResearchQuerySpec
from skm.modules.context.domain.research import ResearchResult as ResearchResult
from skm.modules.context.domain.research import ResearchSourceConfig as ResearchSourceConfig
from skm.modules.context.domain.research import SourceQuery as SourceQuery
from skm.modules.context.domain.research import result_from_json
from skm.modules.context.domain.research_render import render_research
from skm.modules.context.domain.sections import extract_heading, extract_line_range, extract_sections
from skm.modules.context.ports import ContextOwnerClaim as ContextOwnerClaim
from skm.modules.context.ports import ContextRepository, ReadOutcome, ResearchRepository
from skm.modules.context.ports import ResearchSource as ResearchSource

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from skm.kernel.actor import Actor
    from skm.kernel.gateways import Gateways
    from skm.kernel.ids import ContextManifestId, FileVersionId
    from skm.kernel.ports_uow import UnitOfWork
    from skm.kernel.tokens import TokenEstimator
    from skm.modules.context.ports import CheckoutReader
    from skm.platform.config import EffectiveConfig


def assemble_draft(
    uow: UnitOfWork,
    gateways: Gateways,
    request: ContextRequest,
    *,
    config: EffectiveConfig,
    owner_ref: str,
    actor: Actor | None = None,
    manifest_id: ContextManifestId | None = None,
    inline_task: tuple[str, str] | None = None,
) -> ContextDraft:
    return _assemble_draft(
        uow,
        gateways,
        request,
        config=config,
        owner_ref=owner_ref,
        actor=actor,
        manifest_id=manifest_id,
        inline_task=inline_task,
    )


def get_manifest(uow: UnitOfWork, manifest_id: ContextManifestId) -> ContextManifest:
    return uow.repo(ContextRepository).get(manifest_id)


def require_final(uow: UnitOfWork, manifest_id: ContextManifestId) -> ContextManifest:
    manifest = uow.repo(ContextRepository).get(manifest_id)
    if manifest.state is not ManifestState.FINAL:
        raise PreconditionFailed(
            ErrorCode.CONTEXT_NOT_FINALIZED,
            "context manifest is not finalized",
            details={"manifest_id": str(manifest_id), "state": manifest.state.value},
        )
    return manifest


def research_documents(uow: UnitOfWork, document_ids: Sequence[str]) -> tuple[ResearchDocument, ...]:
    return uow.repo(ResearchRepository).documents(document_ids)


def research_batches_for_step(uow: UnitOfWork, step_ref: str) -> tuple[ResearchResult, ...]:
    return tuple(
        result_from_json(cast("dict[str, Any]", raw))
        for raw in uow.repo(ResearchRepository).results_for_step(step_ref)
    )


def _select(text: str, selector: HostSelector) -> str:
    match selector.kind:
        case "whole":
            return text
        case "markdown_sections":
            return extract_sections(text, selector.sections)[0]
        case "markdown_heading":
            return extract_heading(text, selector.heading or "")
        case "line_range":
            if selector.line_from is None or selector.line_to is None:
                raise ValueError("line range requires both bounds")
            return extract_line_range(text, selector.line_from, selector.line_to)


def _excluded(req: HostInputRequest, outcome: ReadOutcome, status: HostReadStatus | None = None) -> HostBlock:
    return HostBlock(
        req.request_id,
        status or HostReadStatus(outcome.status),
        outcome.resolved_path,
        None,
        None,
        outcome.size,
        None,
    )


def _repo_probe(
    req: HostInputRequest, reader: CheckoutReader, repo_count: int, repo_max: int
) -> HostBlock | ReadOutcome:
    # A zero-byte probe chooses the first existing alternative without reading its contents.
    probe = reader.first_existing(req.mount, req.path, req.alternatives, max_bytes=0, follow_symlinks=False)
    if probe.status not in {"ok", "too_large"}:
        return _excluded(req, probe)
    if probe.resolved_path and probe.resolved_path.rsplit("/", 1)[-1] in req.skip_if_resolved_in:
        return _excluded(req, probe, HostReadStatus.SELF_LOADED)
    if repo_count >= repo_max:
        return _excluded(req, probe, HostReadStatus.OVER_MAX_FILES)
    return probe


def _work_paths(
    reader: CheckoutReader, patterns: Sequence[tuple[str, str]], maximum: int
) -> tuple[tuple[tuple[str, str], ...], bool]:
    paths: dict[tuple[str, str], None] = {}
    truncated = False
    for mount, pattern in patterns:
        if (mount, pattern) not in paths:
            if len(paths) >= maximum:
                truncated = True
            else:
                paths[mount, pattern] = None
        remaining = maximum - len(paths)
        matches, more = reader.expand(mount, pattern, limit=maximum)
        truncated |= more
        for path in matches:
            if (mount, path) in paths:
                continue
            if remaining <= 0:
                truncated = True
                continue
            paths[mount, path] = None
            remaining -= 1
    return tuple(paths), truncated


def _research_block(req: HostInputRequest, batch: ResearchBatch | None, remaining: int) -> HostBlock:
    if batch is None:
        return _excluded(req, ReadOutcome("missing", None, None, None))
    text = render_research(batch)
    size = len(text.encode("utf-8"))
    status = (
        HostReadStatus.TOO_LARGE
        if size > req.max_bytes
        else HostReadStatus.BUDGET_EXCEEDED
        if size > remaining
        else HostReadStatus.OK
    )
    return HostBlock(
        req.request_id,
        status,
        None,
        text if status is HostReadStatus.OK else None,
        sha256_text(text) if status is HostReadStatus.OK else None,
        size,
        None,
        tuple(result.query_id for result in batch.results),
    )


def _read_file(
    req: HostInputRequest, reader: CheckoutReader, remaining: int, probe: ReadOutcome | None
) -> tuple[HostBlock, str | None, int]:
    if remaining == 0:
        return (
            _excluded(
                req, probe or ReadOutcome("budget_exceeded", None, None, None), HostReadStatus.BUDGET_EXCEEDED
            ),
            None,
            0,
        )
    limit = min(req.max_bytes, remaining)
    outcome = reader.read(
        req.mount,
        (probe.resolved_path if probe else None) or req.path,
        max_bytes=limit,
        follow_symlinks=False if probe else req.follow_symlinks,
    )
    status = HostReadStatus(outcome.status)
    if (
        status is HostReadStatus.TOO_LARGE
        and limit < req.max_bytes
        and outcome.size is not None
        and outcome.size <= req.max_bytes
    ):
        status = HostReadStatus.BUDGET_EXCEEDED
    if status is not HostReadStatus.OK or outcome.data is None:
        measured = getattr(outcome, "bytes_read", None)
        # Readers without IO measurements are charged conservatively for rejected reads.
        read_bytes = (
            min(outcome.size or limit + 1, limit + 1)
            if status in {HostReadStatus.TOO_LARGE, HostReadStatus.BUDGET_EXCEEDED, HostReadStatus.BINARY}
            else 0
        )
        if isinstance(measured, int) and measured >= 0:
            read_bytes = measured
        return (
            _excluded(req, outcome, status),
            None,
            read_bytes,
        )
    consumed = len(outcome.data)
    try:
        raw = outcome.data.decode("utf-8")
        text = _select(raw, req.selector)
    except UnicodeError:
        return _excluded(req, outcome, HostReadStatus.BINARY), None, consumed
    except ValueError:
        return _excluded(req, outcome, HostReadStatus.PATH_INVALID), None, consumed
    if not text and req.kind is not HostInputKind.DEPENDENCY_MANIFEST:
        return _excluded(req, outcome, HostReadStatus.NO_MATCHING_SECTIONS), None, consumed
    return (
        HostBlock(
            req.request_id,
            status,
            outcome.resolved_path,
            text,
            sha256_text(text),
            len(text.encode("utf-8")),
            None,
        ),
        raw,
        consumed,
    )


def collect_host_blocks(  # noqa: PLR0913 -- preserve the host facade while accepting its render snapshot
    requests: Sequence[HostInputRequest],
    reader: CheckoutReader,
    estimator: TokenEstimator,
    *,
    total_max_bytes: int,
    max_work_paths: int,
    repo_max_files: int,
    path_patterns: Sequence[tuple[str, str]],
    research: Mapping[str, ResearchBatch],
    draft: ContextDraft | None = None,
) -> tuple[tuple[HostBlock, ...], HostFacts]:
    """Estimate with the actual draft, or defer exact estimation to finalize when absent."""
    if min(total_max_bytes, max_work_paths, repo_max_files) < 0:
        raise ValueError("host limits must be nonnegative")
    blocks: list[HostBlock] = []
    manifests: dict[str, str] = {}
    consumed = repo_count = 0
    for req in requests:
        remaining = max(0, total_max_bytes - consumed)
        raw: str | None = None
        if req.kind is HostInputKind.RESEARCH_QUERY:
            hb = _research_block(req, research.get(req.request_id), remaining)
            consumed += (hb.size_bytes or 0) if hb.status is HostReadStatus.OK else 0
        else:
            probe = (
                _repo_probe(req, reader, repo_count, repo_max_files)
                if req.kind is HostInputKind.REPO_INSTRUCTIONS
                else None
            )
            if isinstance(probe, HostBlock):
                hb = probe
            else:
                hb, raw, read_bytes = _read_file(req, reader, remaining, probe)
                consumed += read_bytes
        if req.required and hb.status is not HostReadStatus.OK:
            raise PreconditionFailed(
                ErrorCode.CONTEXT_INPUT_MISSING,
                "required context input is unavailable",
                details={"request_id": req.request_id, "path": req.path, "status": hb.status.value},
            )
        if req.kind is HostInputKind.DEPENDENCY_MANIFEST:
            if raw is not None:
                manifests[f"{req.mount}/{req.path}"] = raw
            continue
        if hb.status is HostReadStatus.OK:
            if req.kind is HostInputKind.REPO_INSTRUCTIONS:
                repo_count += 1
            if draft is not None:
                block_type, title, body, source_ref = format_host_block(req, hb)
                wrapped = render_block_text(
                    block_type=block_type,
                    title=title,
                    content=body,
                    source_ref=source_ref,
                    templates=draft.templates,
                    prompt_plan=draft.prompt_plan,
                    variables=draft.variables,
                )
                hb = replace(hb, tokens_estimate=estimator.estimate(wrapped))
        blocks.append(hb)
    paths, truncated = _work_paths(reader, path_patterns, max_work_paths)
    baseline = cast("Mapping[str, str]", getattr(reader, "baseline", {}))
    return tuple(blocks), HostFacts(project_deps(manifests), paths, truncated, dict(baseline))


def finalize(
    draft: ContextDraft, host_blocks: Sequence[HostBlock], facts: HostFacts, estimator: TokenEstimator
) -> FinalizedContext:
    return _finalize_domain(draft, host_blocks, facts, estimator)


def finalize_command(  # noqa: PLR0913 — legacy and staged artifact wire alternatives
    draft: ContextDraft,
    finalized: FinalizedContext,
    host_blocks: Sequence[HostBlock],
    facts: HostFacts,
    prompt_file_version_id: FileVersionId | None = None,
    *,
    claim: ContextOwnerClaim | None = None,
    store_content: bool,
    runtime_self_loaded: Sequence[JsonObject],
    prompt_staged_blob: JsonObject | None = None,
) -> JsonObject:
    """Build wire payload conforming to ``urn:skm:context:command:finalize-manifest:v1``."""
    if (prompt_file_version_id is None) == (prompt_staged_blob is None):
        raise ValueError("exactly one prompt artifact source is required")
    prompt_source: JsonObject = (
        {"prompt_file_version_id": str(prompt_file_version_id)}
        if prompt_staged_blob is None
        else {"prompt_staged_blob": prompt_staged_blob}
    )
    host_items: list[JsonValue] = []
    rendered_tokens = {block.block_ref: block.tokens_estimate for block in finalized.manifest.blocks}
    for hb in host_blocks:
        entry: dict[str, JsonValue] = {
            "request_id": hb.request_id,
            "status": hb.status.value,
            "resolved_path": hb.resolved_path,
            "text_digest": hb.text_digest,
            "size_bytes": hb.size_bytes,
            "tokens_estimate": rendered_tokens.get(f"h:{hb.request_id}", hb.tokens_estimate),
            "research_query_ids": [],
        }
        if store_content and hb.text is not None:
            entry["text"] = hb.text
        host_items.append(entry)
    sel = finalized.selection
    claim_payload: JsonObject = (
        {}
        if claim is None
        else {
            "claim": {
                "assignment_id": str(claim.assignment_id),
                "attempt_id": str(claim.attempt_id),
                "worker_id": str(claim.worker_id),
                "fencing_token": claim.fencing_token,
            }
        }
    )
    return {
        **claim_payload,
        "manifest_id": str(draft.manifest_id),
        "draft_digest": draft.draft_digest,
        "host_blocks": host_items,
        "host_facts": host_facts_to_meta(facts),
        "selection": {
            "included": [[ref, pos] for ref, pos in sel.included],
            "excluded": [[ref, reason.value, detail] for ref, reason, detail in sel.excluded],
            "class_usage": {cls.value: tok for cls, tok in sel.class_usage.items()},
            "total_tokens": sel.total_tokens,
            "task_digest": sel.task_digest,
            "mode": sel.mode,
        },
        "rendered_prompt_digest": finalized.prompt_digest,
        **prompt_source,
        "estimator_id": draft.budget.estimator_id,
        "runtime_self_loaded": [dict(item) for item in runtime_self_loaded],
    }


def task_research_query(entity_title: str, goal: str, why: str | None) -> str:
    parts = [entity_title.strip(), goal.strip()]
    if why is not None and why.strip():
        parts.append(why.strip())
    return "\n\n".join(p for p in parts if p)


# Bus DTO wrappers preserve the exact registered identity of generated JSON contracts.

RecordResearchResult = next(s.dto for s in _RESEARCH_COMMANDS if s.name == "context.record_research_result")
RecordResearchResultResult = next(
    s.result for s in _RESEARCH_COMMANDS if s.name == "context.record_research_result"
)
CheckResearchAccess = next(s.dto for s in _RESEARCH_QUERIES if s.name == "context.check_research_access")
ResearchAccessView = next(s.result for s in _RESEARCH_QUERIES if s.name == "context.check_research_access")
FindResearchCache = next(s.dto for s in _RESEARCH_QUERIES if s.name == "context.find_research_cache")
ResearchCacheView = next(s.result for s in _RESEARCH_QUERIES if s.name == "context.find_research_cache")
GetResearchQuery = next(s.dto for s in _RESEARCH_QUERIES if s.name == "context.get_research_query")
ResearchResultView = next(s.result for s in _RESEARCH_QUERIES if s.name == "context.get_research_query")
ListExternalSources = next(s.dto for s in _RESEARCH_QUERIES if s.name == "context.list_external_sources")
ExternalSourcesView = next(s.result for s in _RESEARCH_QUERIES if s.name == "context.list_external_sources")


if TYPE_CHECKING:
    from .application.commands.finalize_manifest import (
        FinalizeManifest as FinalizeManifest,
    )
    from .application.commands.finalize_manifest import (
        FinalizeManifestResult as FinalizeManifestResult,
    )
    from .application.query_dtos import (
        ContextDiffResponse as ContextDiffResponse,
    )
    from .application.query_dtos import (
        ContextExplainResponse as ContextExplainResponse,
    )
    from .application.query_dtos import (
        ContextTextResponse as ContextTextResponse,
    )
    from .application.query_dtos import (
        DiffContextsRequest as DiffContextsRequest,
    )
    from .application.query_dtos import (
        ExplainContextRequest as ExplainContextRequest,
    )
    from .application.query_dtos import (
        GetContextTextRequest as GetContextTextRequest,
    )
    from .generated.commands import AssembleContext as AssembleContext
    from .generated.results import AssembleContextResult as AssembleContextResult

_LAZY_EXPORTS: dict[str, str] = {
    "AssembleContext": ".generated.commands",
    "AssembleContextResult": ".generated.results",
    **dict.fromkeys(
        ("FinalizeManifest", "FinalizeManifestResult"), ".application.commands.finalize_manifest"
    ),
    **dict.fromkeys(
        (
            "ContextDiffResponse",
            "ContextExplainResponse",
            "ContextTextResponse",
            "DiffContextsRequest",
            "ExplainContextRequest",
            "GetContextTextRequest",
        ),
        ".application.query_dtos",
    ),
}


def __getattr__(name: str) -> object:
    module_name = _LAZY_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name, __package__), name)
    globals()[name] = value
    return value


__all__ = [
    "AssembleContext",
    "AssembleContextResult",
    "BlockType",
    "BudgetClass",
    "CheckResearchAccess",
    "Claim",
    "ContextDiffResponse",
    "ContextDraft",
    "ContextExplainResponse",
    "ContextManifest",
    "ContextOwnerClaim",
    "ContextRequest",
    "ContextTextResponse",
    "DelegationCompiler",
    "DiffContextsRequest",
    "DraftBlock",
    "ExecutionBlocks",
    "ExplainContextRequest",
    "ExternalSourcesView",
    "FinalizeManifest",
    "FinalizeManifestResult",
    "FinalizedContext",
    "FindResearchCache",
    "GetContextTextRequest",
    "GetResearchQuery",
    "HostBlock",
    "HostBlockMeta",
    "HostFacts",
    "HostInputKind",
    "HostInputRequest",
    "ListExternalSources",
    "ManifestState",
    "PayloadCompiler",
    "PermissionsSummary",
    "PrefixStablePrompt",
    "PrefixStablePromptCompiler",
    "RecordResearchResult",
    "RecordResearchResultResult",
    "ResearchAccessView",
    "ResearchBatch",
    "ResearchCacheView",
    "ResearchDocument",
    "ResearchItem",
    "ResearchQuerySpec",
    "ResearchResult",
    "ResearchResultView",
    "ResumeInfo",
    "RunParams",
    "RuntimeTarget",
    "Selection",
    "StepPurpose",
    "TrustLevel",
    "assemble_draft",
    "collect_host_blocks",
    "design_research_evidence",
    "finalize",
    "finalize_command",
    "get_manifest",
    "require_final",
    "research_batches_for_step",
    "research_documents",
    "task_research_query",
]
