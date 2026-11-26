"""Phase-A context draft model, canonical ``DraftMeta`` serialization, and ``draft_digest`` (context §5.7)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, cast
from uuid import UUID

from skm.kernel.ids import ContextManifestId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.context.domain.blocks import (
    BlockType,
    BudgetClass,
    TrustLevel,
)
from skm.modules.context.domain.blocks import (
    canonical_json_digest as jsonc_digest,
)
from skm.modules.context.domain.host_inputs import HostInputKind, HostInputRequest, HostSelector
from skm.modules.context.domain.reasons import IncludeReason
from skm.modules.context.domain.request import ResumeInfo
from skm.modules.context.domain.research import ResearchQuerySpec

if TYPE_CHECKING:
    from skm.modules.context.domain.contracts import Diagnostic, Digest, DraftMeta, SkillSelectionTrace
    from skm.modules.context.domain.manifest import ContextManifest, ManifestBlock

__all__ = [
    "BudgetPolicy",
    "ConditionalBlock",
    "ContextDraft",
    "DraftBlock",
    "build_draft",
    "carrier_dirs",
    "compute_draft_digest",
    "draft_meta_of",
    "host_input_from_json",
    "host_input_to_json",
    "make_repo_instruction_requests",
    "make_repo_path_request",
    "make_research_request",
]


@dataclass(frozen=True, slots=True)
class DraftBlock:
    ordinal: int
    block_type: BlockType
    budget_class: BudgetClass
    mandatory: bool
    source_kind: str
    source_ref: str
    source_version: str | None
    trust: TrustLevel
    atomic_group: str | None
    title: str
    content: str
    content_digest: Digest
    tokens_estimate: int
    reason: IncludeReason


@dataclass(frozen=True, slots=True)
class ConditionalBlock:
    block: DraftBlock
    condition: Literal["deps_any"]
    deps: frozenset[str]


@dataclass(frozen=True, slots=True)
class BudgetPolicy:
    total_limit: int
    class_limits: Mapping[BudgetClass, int | None]
    skills_budget: int
    estimator_id: str


@dataclass(frozen=True, slots=True)
class ContextDraft:
    manifest_id: ContextManifestId
    blocks: tuple[DraftBlock, ...]
    conditional: tuple[ConditionalBlock, ...]
    excluded: tuple[ManifestBlock, ...]
    host_inputs: tuple[HostInputRequest, ...]
    templates: Mapping[str, str]
    prompt_plan: Mapping[BlockType, tuple[str, ...]]
    variables: Mapping[str, JsonValue]
    budget: BudgetPolicy
    resume: ResumeInfo | None
    skills_trace: SkillSelectionTrace
    diagnostics: tuple[Diagnostic, ...]
    draft_digest: Digest
    manifest: ContextManifest | None = None
    repo_max_files: int = 8


def host_input_to_json(req: HostInputRequest) -> JsonObject:
    """Serialize ``HostInputRequest`` to canonical JSON for ``draft_digest`` and manifest persistence."""
    research_json: JsonValue = None
    if req.research is not None:
        sources_json = list[JsonValue](req.research.sources)
        research_json = {
            "text": req.research.text,
            "sources": sources_json,
            "depth": req.research.depth,
            "max_documents": req.research.max_documents,
            "use_cache": req.research.use_cache,
            "save_as_material": req.research.save_as_material,
        }
    alts_json = list[JsonValue](req.alternatives)
    secs_json = list[JsonValue](req.selector.sections)
    skip_json = list[JsonValue](req.skip_if_resolved_in)
    return {
        "request_id": req.request_id,
        "kind": req.kind.value,
        "mount": req.mount,
        "path": req.path,
        "alternatives": alts_json,
        "selector": {
            "kind": req.selector.kind,
            "sections": secs_json,
            "heading": req.selector.heading,
            "line_from": req.selector.line_from,
            "line_to": req.selector.line_to,
        },
        "max_bytes": req.max_bytes,
        "required": req.required,
        "block_type": None if req.block_type is None else req.block_type.value,
        "trust": req.trust.value,
        "source_ref": req.source_ref,
        "follow_symlinks": req.follow_symlinks,
        "skip_if_resolved_in": skip_json,
        "research": research_json,
    }


def host_input_from_json(raw: Mapping[str, JsonValue]) -> HostInputRequest:
    """Deserialize ``HostInputRequest`` from JSON stored in ``skm_context.context_manifests``."""
    sel_raw = cast("Mapping[str, JsonValue]", raw["selector"])
    res_raw = raw.get("research")
    research: ResearchQuerySpec | None = None
    if isinstance(res_raw, Mapping):
        res_map = cast("Mapping[str, JsonValue]", res_raw)
        sources_raw = cast("Sequence[JsonValue]", res_map.get("sources", ()))
        research = ResearchQuerySpec(
            text=str(res_map["text"]),
            sources=tuple(str(s) for s in sources_raw),
            depth=cast("Literal['standard', 'deep']", str(res_map["depth"])),
            max_documents=int(cast("int", res_map["max_documents"])),
            use_cache=bool(res_map.get("use_cache", True)),
            save_as_material=bool(res_map.get("save_as_material", False)),
        )
    btype_raw = raw.get("block_type")
    alts_raw = cast("Sequence[JsonValue]", raw.get("alternatives", ()))
    skip_raw = cast("Sequence[JsonValue]", raw.get("skip_if_resolved_in", ()))
    secs_raw = cast("Sequence[JsonValue]", sel_raw.get("sections", ()))
    line_from = sel_raw.get("line_from")
    line_to = sel_raw.get("line_to")
    heading = sel_raw.get("heading")
    return HostInputRequest(
        request_id=str(raw["request_id"]),
        kind=HostInputKind(str(raw["kind"])),
        mount=str(raw["mount"]),
        path=str(raw["path"]),
        alternatives=tuple(str(x) for x in alts_raw),
        selector=HostSelector(
            kind=cast(
                "Literal['whole', 'markdown_sections', 'markdown_heading', 'line_range']",
                str(sel_raw["kind"]),
            ),
            sections=tuple(str(s) for s in secs_raw),
            heading=None if heading is None else str(heading),
            line_from=None if line_from is None else int(cast("int", line_from)),
            line_to=None if line_to is None else int(cast("int", line_to)),
        ),
        max_bytes=int(cast("int", raw["max_bytes"])),
        required=bool(raw["required"]),
        block_type=None if btype_raw is None else BlockType(str(btype_raw)),
        trust=TrustLevel(str(raw["trust"])),
        source_ref=str(raw["source_ref"]),
        follow_symlinks=bool(raw["follow_symlinks"]),
        skip_if_resolved_in=tuple(str(s) for s in skip_raw),
        research=research,
    )


def draft_meta_of(
    *,
    manifest_id: ContextManifestId,
    blocks: Sequence[DraftBlock],
    conditional: Sequence[ConditionalBlock],
    host_inputs: Sequence[HostInputRequest],
    budget: BudgetPolicy,
    resume: ResumeInfo | None,
    repo_max_files: int = 8,
    skills_remaining: int | None = None,
) -> DraftMeta:
    """Build content-free ``DraftMeta`` used by ``decide`` and ``draft_digest``."""
    non_explicit_skill_tokens = sum(
        b.tokens_estimate
        for b in blocks
        if b.block_type is BlockType.SKILLS
        and b.reason not in (IncludeReason.EXPLICIT_PLAN, IncludeReason.EXPLICIT_PROFILE)
    )
    effective_remaining = (
        max(0, budget.skills_budget - non_explicit_skill_tokens)
        if skills_remaining is None
        else skills_remaining
    )
    d_list: list[JsonValue] = [
        {
            "block_ref": f"d:{b.ordinal}",
            "ordinal": b.ordinal,
            "block_type": b.block_type.value,
            "budget_class": b.budget_class.value,
            "mandatory": b.mandatory,
            "source_kind": b.source_kind,
            "source_ref": b.source_ref,
            "source_version": b.source_version,
            "trust": b.trust.value,
            "atomic_group": b.atomic_group,
            "tokens_estimate": b.tokens_estimate,
            "content_digest": b.content_digest,
            "reason": b.reason.value,
        }
        for b in blocks
    ]
    c_list: list[JsonValue] = []
    for cb in conditional:
        deps_j = list[JsonValue](sorted(cb.deps))
        c_list.append(
            {
                "block_ref": f"c:{cb.block.ordinal}",
                "ordinal": cb.block.ordinal,
                "condition": cb.condition,
                "deps": deps_j,
                "block_type": cb.block.block_type.value,
                "budget_class": cb.block.budget_class.value,
                "mandatory": cb.block.mandatory,
                "source_kind": cb.block.source_kind,
                "source_ref": cb.block.source_ref,
                "source_version": cb.block.source_version,
                "trust": cb.block.trust.value,
                "atomic_group": cb.block.atomic_group,
                "tokens_estimate": cb.block.tokens_estimate,
                "content_digest": cb.block.content_digest,
                "reason": cb.block.reason.value,
                "explicit": cb.block.reason in (IncludeReason.EXPLICIT_PLAN, IncludeReason.EXPLICIT_PROFILE),
            }
        )
    hi_list: list[JsonValue] = [host_input_to_json(hi) for hi in host_inputs]
    cls_limits_j: JsonObject = {
        cls.value: budget.class_limits.get(cls) for cls in sorted(BudgetClass, key=lambda c: c.value)
    }
    resume_j: JsonValue = (
        None
        if resume is None
        else {"session_ref": resume.session_ref, "previous_task_digest": resume.previous_task_digest}
    )
    return {
        "manifest_id": str(manifest_id),
        "blocks": d_list,
        "conditional": c_list,
        "host_inputs": hi_list,
        "budget": {
            "total_limit": budget.total_limit,
            "class_limits": cls_limits_j,
            "skills_budget": budget.skills_budget,
            "skills_remaining": effective_remaining,
            "estimator_id": budget.estimator_id,
        },
        "repo_max_files": repo_max_files,
        "resume": resume_j,
    }


def compute_draft_digest(meta: DraftMeta) -> Digest:
    """Compute canonical ``sha256:...`` digest of ``DraftMeta``."""
    return jsonc_digest(meta)


def build_draft(inputs: JsonObject) -> ContextDraft:
    """Construct a ``ContextDraft`` and compute its canonical ``draft_digest`` from JSON inputs."""
    manifest_id = ContextManifestId(UUID(str(inputs["manifest_id"])))
    budget_raw = cast("Mapping[str, JsonValue]", inputs.get("budget", {}))
    raw_limits = cast("Mapping[str, JsonValue]", budget_raw.get("class_limits", {}))
    class_limits: dict[BudgetClass, int | None] = {
        cls: (None if raw_limits.get(cls.value) is None else int(cast("int", raw_limits[cls.value])))
        for cls in BudgetClass
    }
    budget = BudgetPolicy(
        total_limit=int(cast("int", budget_raw.get("total_limit", 150000))),
        class_limits=class_limits,
        skills_budget=int(cast("int", budget_raw.get("skills_budget", 8000))),
        estimator_id="heuristic-v1",
    )
    blocks_raw = cast("Sequence[Mapping[str, JsonValue]]", inputs.get("blocks", ()))
    blocks = tuple(
        DraftBlock(
            ordinal=int(cast("int", b["ordinal"])),
            block_type=BlockType(str(b["block_type"])),
            budget_class=BudgetClass(str(b["budget_class"])),
            mandatory=bool(b["mandatory"]),
            source_kind=str(b["source_kind"]),
            source_ref=str(b["source_ref"]),
            source_version=None if b.get("source_version") is None else str(b["source_version"]),
            trust=TrustLevel(str(b["trust"])),
            atomic_group=None if b.get("atomic_group") is None else str(b["atomic_group"]),
            title=str(b.get("title", "")),
            content=str(b.get("content", "")),
            content_digest=str(b["content_digest"]),
            tokens_estimate=int(cast("int", b["tokens_estimate"])),
            reason=IncludeReason(str(b["reason"])),
        )
        for b in blocks_raw
    )
    host_inputs_raw = cast("Sequence[Mapping[str, JsonValue]]", inputs.get("host_inputs", ()))
    host_inputs = tuple(host_input_from_json(hi) for hi in host_inputs_raw)
    resume_raw = inputs.get("resume")
    resume: ResumeInfo | None = None
    if isinstance(resume_raw, Mapping):
        rmap = cast("Mapping[str, JsonValue]", resume_raw)
        resume = ResumeInfo(
            session_ref=str(rmap["session_ref"]),
            previous_task_digest=str(rmap["previous_task_digest"]),
        )
    repo_max_files = int(cast("int", inputs.get("repo_max_files", 8)))
    meta = draft_meta_of(
        manifest_id=manifest_id,
        blocks=blocks,
        conditional=(),
        host_inputs=host_inputs,
        budget=budget,
        resume=resume,
        repo_max_files=repo_max_files,
    )
    templates_raw = cast("Mapping[str, JsonValue]", inputs.get("templates", {}))
    plan_raw = cast("Mapping[str, Sequence[JsonValue]]", inputs.get("prompt_plan", {}))
    vars_raw = cast("Mapping[str, JsonValue]", inputs.get("variables", {}))
    skills_trace = cast(
        "JsonObject", inputs.get("skills_trace", {"mode": "none", "selected": [], "excluded": []})
    )
    diags_raw = cast("Sequence[JsonObject]", inputs.get("diagnostics", ()))
    return ContextDraft(
        manifest_id=manifest_id,
        blocks=blocks,
        conditional=(),
        excluded=(),
        host_inputs=host_inputs,
        templates={str(k): str(v) for k, v in templates_raw.items()},
        prompt_plan={BlockType(str(k)): tuple(str(x) for x in v) for k, v in plan_raw.items()},
        variables=dict(vars_raw),
        budget=budget,
        resume=resume,
        skills_trace=dict(skills_trace),
        diagnostics=tuple(diags_raw),
        draft_digest=compute_draft_digest(meta),
        repo_max_files=repo_max_files,
    )


def carrier_dirs(write_paths: Sequence[str]) -> tuple[tuple[str, str], ...]:
    """Return sorted ``(mount, rel_dir)`` carrier directories from entity write-scope globs."""
    pairs: set[tuple[str, str]] = {("repo", "")}
    for entry in write_paths:
        mnt, sep, raw_glob = entry.partition(":")
        if not sep:
            mnt, raw_glob = "repo", entry
        pairs.add((mnt, ""))
        parts = [p for p in raw_glob.split("/") if p and "*" not in p and "?" not in p and "[" not in p]
        if parts and "." in parts[-1]:
            parts = parts[:-1]
        for idx in range(1, len(parts) + 1):
            pairs.add((mnt, "/".join(parts[:idx])))
    return tuple(sorted(pairs))


def make_repo_path_request(
    request_id: str, *, mount: str, path: str, max_bytes: int, required: bool
) -> HostInputRequest:
    """Build a ``HostInputKind.REPOSITORY_PATH`` request."""
    return HostInputRequest(
        request_id=request_id,
        kind=HostInputKind.REPOSITORY_PATH,
        mount=mount,
        path=path,
        alternatives=(),
        selector=HostSelector(kind="whole"),
        max_bytes=max_bytes,
        required=required,
        block_type=BlockType.MATERIALS,
        trust=TrustLevel.REPOSITORY,
        source_ref=f"repo:{mount}/{path}",
        follow_symlinks=True,
        skip_if_resolved_in=(),
        research=None,
    )


def make_repo_instruction_requests(
    start_index: int,
    *,
    write_paths: Sequence[str],
    max_files: int,
    files: tuple[str, ...],
    max_bytes: int,
    constraints_only: bool,
    sections: tuple[str, ...],
    self_loaded_files: tuple[str, ...],
) -> tuple[HostInputRequest, ...]:
    """Build ``HostInputKind.REPO_INSTRUCTIONS`` requests across carrier directories."""
    sel = (
        HostSelector(kind="markdown_sections", sections=sections)
        if constraints_only and sections
        else HostSelector(kind="whole")
    )
    out: list[HostInputRequest] = []
    for offset, (mnt, rel) in enumerate(carrier_dirs(write_paths)[:max_files]):
        out.append(
            HostInputRequest(
                request_id=f"hi:{start_index + offset}",
                kind=HostInputKind.REPO_INSTRUCTIONS,
                mount=mnt,
                path=f"{rel}/" if rel else "",
                alternatives=files,
                selector=sel,
                max_bytes=max_bytes,
                required=False,
                block_type=BlockType.REPO_INSTRUCTIONS,
                trust=TrustLevel.REPOSITORY,
                source_ref=f"repo:{mnt}/{rel or '.'}",
                follow_symlinks=False,
                skip_if_resolved_in=self_loaded_files if not rel else (),
                research=None,
            )
        )
    return tuple(out)


def make_research_request(
    request_id: str, *, query_spec: ResearchQuerySpec, query_digest: str, max_bytes: int
) -> HostInputRequest:
    """Build a ``HostInputKind.RESEARCH_QUERY`` request."""
    return HostInputRequest(
        request_id=request_id,
        kind=HostInputKind.RESEARCH_QUERY,
        mount="",
        path="",
        alternatives=(),
        selector=HostSelector(kind="whole"),
        max_bytes=max_bytes,
        required=False,
        block_type=BlockType.RESEARCH,
        trust=TrustLevel.EXTERNAL,
        source_ref=f"research:{query_digest}",
        follow_symlinks=False,
        skip_if_resolved_in=(),
        research=query_spec,
    )
