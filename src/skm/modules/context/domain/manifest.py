"""Immutable two-phase ``ContextManifest`` domain model and ``DraftMeta`` reconstruction (context §5.13)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from typing import TYPE_CHECKING, Literal, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed
from skm.kernel.ids import (
    ContextManifestId,
    EntityId,
    FileVersionId,
    PlanId,
    ProjectId,
    ResourceVersionId,
    RevisionId,
    WorkspaceId,
)
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.context.domain.blocks import (
    ASSEMBLER_VERSION,
    BLOCK_SPECS,
    BlockType,
    BudgetClass,
    TrustLevel,
)
from skm.modules.context.domain.draft import (
    BudgetPolicy,
    ConditionalBlock,
    ContextDraft,
    DraftBlock,
    compute_draft_digest,
    draft_meta_of,
    host_input_from_json,
    host_input_to_json,
)
from skm.modules.context.domain.reasons import ExcludeReason, IncludeReason
from skm.modules.context.domain.render import render_block_text
from skm.modules.context.domain.request import ContextRequest, StepPurpose

if TYPE_CHECKING:
    from skm.kernel.tokens import TokenEstimator
    from skm.modules.context.domain.contracts import (
        Diagnostic,
        Digest,
        DraftMeta,
        HostFactsMeta,
        RouteRecord,
        SkillSelectionTrace,
    )
    from skm.modules.context.domain.host_inputs import HostInputRequest

__all__ = [
    "ClassUsage",
    "ContextManifest",
    "DraftAssembler",
    "ManifestBlock",
    "ManifestState",
    "build_manifest",
    "draft_block_to_manifest_row",
    "draft_meta_from_manifest",
]


class ManifestState(StrEnum):
    DRAFT = "draft"
    FINAL = "final"


@dataclass(frozen=True, slots=True)
class ClassUsage:
    tokens: int | None
    limit: int | None


@dataclass(frozen=True, slots=True)
class ManifestBlock:
    ordinal: int
    block_ref: str
    position: int | None
    block_type: BlockType
    budget_class: BudgetClass
    mandatory: bool
    source_kind: str
    source_ref: str
    source_version: str | None
    trust: TrustLevel
    tokens_estimate: int | None
    content_digest: Digest | None
    included: bool | None
    reason: str
    detail: str | None
    atomic_group: str | None
    content_stored: bool
    research_query_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ContextManifest:
    id: ContextManifestId
    state: ManifestState
    workspace_id: WorkspaceId
    project_id: ProjectId
    plan_id: PlanId | None
    revision_id: RevisionId | None
    entity_id: EntityId | None
    purpose: StepPurpose
    agent_profile_version_id: ResourceVersionId
    runtime_id: str
    model: str
    route: RouteRecord
    draft_digest: Digest
    mode: Literal["full", "delta"] | None
    task_digest: Digest | None
    prompt_digest: Digest | None
    prompt_file_version_id: FileVersionId | None
    total_tokens_estimate: int | None
    total_limit: int
    budgets: Mapping[BudgetClass, ClassUsage]
    blocks: tuple[ManifestBlock, ...]
    host_facts: HostFactsMeta | None
    skills_trace: SkillSelectionTrace
    diagnostics: tuple[Diagnostic, ...]
    estimator_id: str
    assembler_version: int
    created_at: datetime
    finalized_at: datetime | None
    owner_ref: str = ""
    host_inputs: tuple[HostInputRequest, ...] = ()


def draft_meta_from_manifest(manifest: ContextManifest) -> DraftMeta:
    """Reconstruct ``DraftMeta`` on the server from a stored ``draft`` ``ContextManifest``."""
    trace = manifest.skills_trace
    cond_deps_map = trace.get("conditional_deps", {})
    skills_budget = int(cast("int", trace.get("skills_budget", 0)))
    skills_remaining = int(cast("int", trace.get("skills_remaining", skills_budget)))
    repo_max_files = int(cast("int", trace.get("repo_max_files", 8)))
    resume_raw = trace.get("resume")

    d_blocks: list[JsonValue] = []
    c_blocks: list[JsonValue] = []
    for b in sorted(manifest.blocks, key=lambda row: row.ordinal):
        common: dict[str, JsonValue] = {
            "block_ref": b.block_ref,
            "ordinal": b.ordinal,
            "block_type": b.block_type.value,
            "budget_class": b.budget_class.value,
            "mandatory": b.mandatory,
            "source_kind": b.source_kind,
            "source_ref": b.source_ref,
            "source_version": b.source_version,
            "trust": b.trust.value,
            "atomic_group": b.atomic_group,
            "tokens_estimate": 0 if b.tokens_estimate is None else b.tokens_estimate,
            "content_digest": b.content_digest or "",
            "reason": b.reason,
        }
        if b.block_ref.startswith("d:"):
            d_blocks.append(common)
        elif b.block_ref.startswith("c:"):
            raw_deps = (
                cast("Mapping[str, JsonValue]", cond_deps_map).get(b.block_ref, ())
                if isinstance(cond_deps_map, Mapping)
                else ()
            )
            deps_j: list[JsonValue] = (
                list[JsonValue](sorted(str(d) for d in cast("Sequence[JsonValue]", raw_deps)))
                if isinstance(raw_deps, Sequence) and not isinstance(raw_deps, str | bytes)
                else []
            )
            c_blocks.append(
                {
                    **common,
                    "condition": "deps_any",
                    "deps": deps_j,
                    "explicit": b.reason
                    in (IncludeReason.EXPLICIT_PLAN.value, IncludeReason.EXPLICIT_PROFILE.value),
                }
            )
    hi_j: list[JsonValue] = [host_input_to_json(hi) for hi in manifest.host_inputs]
    cls_j: JsonObject = {
        cls.value: (manifest.budgets[cls].limit if cls in manifest.budgets else None)
        for cls in sorted(BudgetClass, key=lambda c: c.value)
    }
    resume_j: JsonValue = (
        dict(cast("Mapping[str, JsonValue]", resume_raw)) if isinstance(resume_raw, Mapping) else None
    )
    return {
        "manifest_id": str(manifest.id),
        "blocks": d_blocks,
        "conditional": c_blocks,
        "host_inputs": hi_j,
        "budget": {
            "total_limit": manifest.total_limit,
            "class_limits": cls_j,
            "skills_budget": skills_budget,
            "skills_remaining": skills_remaining,
            "estimator_id": manifest.estimator_id,
        },
        "repo_max_files": repo_max_files,
        "resume": resume_j,
    }


def build_manifest(inputs: JsonObject) -> ContextManifest:
    """Construct a ``ContextManifest`` from canonical JSON fields."""
    p_raw = cast("Mapping[str, JsonValue]", inputs["purpose"])
    purpose = StepPurpose(
        role=str(p_raw["role"]),
        stage_id=str(p_raw["stage_id"]),
        step_ref=None if p_raw["step_ref"] is None else str(p_raw["step_ref"]),
        attempt_no=int(cast("int", p_raw["attempt_no"])),
        round_no=int(cast("int", p_raw["round_no"])),
    )
    b_raw = cast("Mapping[str, Mapping[str, JsonValue]]", inputs.get("budgets", {}))
    budgets: dict[BudgetClass, ClassUsage] = {}
    for cls in BudgetClass:
        entry = b_raw.get(cls.value, {})
        tok, lim = entry.get("tokens"), entry.get("limit")
        budgets[cls] = ClassUsage(
            tokens=None if tok is None else int(cast("int", tok)),
            limit=None if lim is None else int(cast("int", lim)),
        )
    blocks = tuple(
        ManifestBlock(
            ordinal=int(cast("int", b["ordinal"])),
            block_ref=str(b["block_ref"]),
            position=None if b.get("position") is None else int(cast("int", b["position"])),
            block_type=BlockType(str(b["block_type"])),
            budget_class=BudgetClass(str(b["budget_class"])),
            mandatory=bool(b["mandatory"]),
            source_kind=str(b["source_kind"]),
            source_ref=str(b["source_ref"]),
            source_version=None if b.get("source_version") is None else str(b["source_version"]),
            trust=TrustLevel(str(b["trust"])),
            tokens_estimate=None
            if b.get("tokens_estimate") is None
            else int(cast("int", b["tokens_estimate"])),
            content_digest=None if b.get("content_digest") is None else str(b["content_digest"]),
            included=None if b.get("included") is None else bool(b["included"]),
            reason=str(b["reason"]),
            detail=None if b.get("detail") is None else str(b["detail"]),
            atomic_group=None if b.get("atomic_group") is None else str(b["atomic_group"]),
            content_stored=bool(b.get("content_stored", False)),
            research_query_ids=tuple(
                str(q) for q in cast("Sequence[JsonValue]", b.get("research_query_ids") or ())
            ),
        )
        for b in cast("Sequence[Mapping[str, JsonValue]]", inputs.get("blocks", ()))
    )
    ent_raw, pfv_raw, fin_raw, mode_raw = (
        inputs.get("entity_id"),
        inputs.get("prompt_file_version_id"),
        inputs.get("finalized_at"),
        inputs.get("mode"),
    )
    tot_est = inputs.get("total_tokens_estimate")
    hf_raw = inputs.get("host_facts")
    hi_raw = cast("Sequence[Mapping[str, JsonValue]]", inputs.get("host_inputs", ()))
    return ContextManifest(
        id=ContextManifestId(UUID(str(inputs["id"]))),
        state=ManifestState(str(inputs["state"])),
        workspace_id=WorkspaceId(UUID(str(inputs["workspace_id"]))),
        project_id=ProjectId(UUID(str(inputs["project_id"]))),
        plan_id=None if inputs["plan_id"] is None else PlanId(UUID(str(inputs["plan_id"]))),
        revision_id=None if inputs["revision_id"] is None else RevisionId(UUID(str(inputs["revision_id"]))),
        entity_id=None if ent_raw is None else EntityId(UUID(str(ent_raw))),
        purpose=purpose,
        agent_profile_version_id=ResourceVersionId(UUID(str(inputs["agent_profile_version_id"]))),
        runtime_id=str(inputs["runtime_id"]),
        model=str(inputs["model"]),
        route=dict(cast("Mapping[str, JsonValue]", inputs["route"])),
        draft_digest=str(inputs["draft_digest"]),
        mode=None if mode_raw is None else cast("Literal['full', 'delta']", str(mode_raw)),
        task_digest=None if inputs.get("task_digest") is None else str(inputs["task_digest"]),
        prompt_digest=None if inputs.get("prompt_digest") is None else str(inputs["prompt_digest"]),
        prompt_file_version_id=None if pfv_raw is None else FileVersionId(UUID(str(pfv_raw))),
        total_tokens_estimate=None if tot_est is None else int(cast("int", tot_est)),
        total_limit=int(cast("int", inputs["total_limit"])),
        budgets=budgets,
        blocks=blocks,
        host_facts=None if hf_raw is None else dict(cast("Mapping[str, JsonValue]", hf_raw)),
        skills_trace=dict(cast("Mapping[str, JsonValue]", inputs.get("skills_trace", {}))),
        diagnostics=tuple(cast("Sequence[JsonObject]", inputs.get("diagnostics", ()))),
        estimator_id=str(inputs.get("estimator_id", "heuristic-v1")),
        assembler_version=int(cast("int", inputs.get("assembler_version", ASSEMBLER_VERSION))),
        created_at=datetime.fromisoformat(str(inputs["created_at"])),
        finalized_at=None if fin_raw is None else datetime.fromisoformat(str(fin_raw)),
        owner_ref=str(inputs.get("owner_ref") or f"step:{purpose.step_ref}"),
        host_inputs=tuple(host_input_from_json(hi) for hi in hi_raw),
    )


def draft_block_to_manifest_row(block: DraftBlock, *, prefix: Literal["d", "c"] = "d") -> ManifestBlock:
    """Convert a Phase-A ``DraftBlock`` into an unfinalized ``ManifestBlock`` row (``included=None``)."""
    return ManifestBlock(
        ordinal=block.ordinal,
        block_ref=f"{prefix}:{block.ordinal}",
        position=None,
        block_type=block.block_type,
        budget_class=block.budget_class,
        mandatory=block.mandatory,
        source_kind=block.source_kind,
        source_ref=block.source_ref,
        source_version=block.source_version,
        trust=block.trust,
        tokens_estimate=block.tokens_estimate,
        content_digest=block.content_digest,
        included=None,
        reason=block.reason.value,
        detail=None,
        atomic_group=block.atomic_group,
        content_stored=True,
    )


@dataclass
class DraftAssembler:
    """Pure Phase-A accumulator producing ``ContextDraft`` and ``ContextManifest(state='draft')``."""

    estimator: TokenEstimator
    max_block_tokens: int
    templates: Mapping[str, str]
    prompt_plan: Mapping[BlockType, tuple[str, ...]]
    variables: Mapping[str, JsonValue]
    draft_blocks: list[DraftBlock] = field(default_factory=list[DraftBlock])
    conditional_blocks: list[ConditionalBlock] = field(default_factory=list[ConditionalBlock])
    excluded_rows: list[ManifestBlock] = field(default_factory=list[ManifestBlock])
    host_inputs: list[HostInputRequest] = field(default_factory=list["HostInputRequest"])
    diagnostics: list[JsonObject] = field(default_factory=list[JsonObject])
    ordinal: int = 0
    hi_index: int = 0

    def add(  # noqa: PLR0913 -- phase-A block metadata fields
        self,
        btype: BlockType,
        title: str,
        content: str,
        source_kind: str,
        source_ref: str,
        *,
        source_version: str | None = None,
        trust: TrustLevel | None = None,
        mandatory: bool | None = None,
        reason: IncludeReason | None = None,
        atomic_group: str | None = None,
    ) -> None:
        spec = BLOCK_SPECS[btype]
        eff_mand = (spec.mandatory == "always") if mandatory is None else mandatory
        eff_trust = spec.default_trust if trust is None else trust
        eff_reason = (
            (IncludeReason.MANDATORY if eff_mand else IncludeReason.EXECUTION_INPUT)
            if reason is None
            else reason
        )
        norm = content.strip()
        cdigest = f"sha256:{sha256(norm.encode('utf-8')).hexdigest()}"
        rendered = render_block_text(
            block_type=btype,
            title=title,
            content=norm,
            source_ref=source_ref,
            templates=self.templates,
            prompt_plan=self.prompt_plan,
            variables=self.variables,
        )
        tok = self.estimator.estimate(rendered)
        if tok > self.max_block_tokens:
            if eff_mand:
                raise PreconditionFailed(
                    ErrorCode.CONTEXT_OVER_BUDGET,
                    f"mandatory block {btype.value} exceeds context.block.max_tokens",
                    details={"block_type": btype.value, "tokens": tok, "max_tokens": self.max_block_tokens},
                )
            self.excluded_rows.append(
                ManifestBlock(
                    ordinal=self.ordinal,
                    block_ref=f"x:{self.ordinal}",
                    position=None,
                    block_type=btype,
                    budget_class=spec.budget_class,
                    mandatory=False,
                    source_kind=source_kind,
                    source_ref=source_ref,
                    source_version=source_version,
                    trust=eff_trust,
                    tokens_estimate=tok,
                    content_digest=cdigest,
                    included=False,
                    reason=ExcludeReason.TOO_LARGE.value,
                    detail=f"tokens={tok} > max_tokens={self.max_block_tokens}",
                    atomic_group=atomic_group,
                    content_stored=False,
                )
            )
            self.ordinal += 1
            return
        self.draft_blocks.append(
            DraftBlock(
                ordinal=self.ordinal,
                block_type=btype,
                budget_class=spec.budget_class,
                mandatory=eff_mand,
                source_kind=source_kind,
                source_ref=source_ref,
                source_version=source_version,
                trust=eff_trust,
                atomic_group=atomic_group,
                title=title,
                content=norm,
                content_digest=cdigest,
                tokens_estimate=tok,
                reason=eff_reason,
            )
        )
        self.ordinal += 1

    def exclude(
        self,
        btype: BlockType,
        source_kind: str,
        source_ref: str,
        reason: ExcludeReason,
        *,
        source_version: str | None = None,
        trust: TrustLevel = TrustLevel.PROJECT,
        detail: str | None = None,
    ) -> None:
        self.excluded_rows.append(
            ManifestBlock(
                ordinal=self.ordinal,
                block_ref=f"x:{self.ordinal}",
                position=None,
                block_type=btype,
                budget_class=BLOCK_SPECS[btype].budget_class,
                mandatory=False,
                source_kind=source_kind,
                source_ref=source_ref,
                source_version=source_version,
                trust=trust,
                tokens_estimate=None,
                content_digest=None,
                included=False,
                reason=reason.value,
                detail=detail,
                atomic_group=None,
                content_stored=False,
            )
        )
        self.ordinal += 1

    def next_hi(self) -> str:
        hid = f"hi:{self.hi_index}"
        self.hi_index += 1
        return hid

    def build(
        self,
        req: ContextRequest,
        *,
        total_limit: int,
        class_limits: Mapping[BudgetClass, int | None],
        skills_budget: int,
        repo_max_files: int,
        owner_ref: str,
        created_at: datetime,
        manifest_id: ContextManifestId | None = None,
    ) -> tuple[ContextDraft, ContextManifest, dict[str, str]]:
        mand_tok = sum(db.tokens_estimate for db in self.draft_blocks if db.mandatory)
        if mand_tok > total_limit:
            raise PreconditionFailed(
                ErrorCode.CONTEXT_OVER_BUDGET,
                "mandatory Phase-A blocks exceed context total_limit",
                details={"mandatory_tokens": mand_tok, "total_limit": total_limit},
            )
        budget = BudgetPolicy(
            total_limit=total_limit,
            class_limits=dict(class_limits),
            skills_budget=skills_budget,
            estimator_id=self.estimator.estimator_id,
        )
        mid = manifest_id or ContextManifestId(
            uuid5(NAMESPACE_URL, f"skm:context:manifest:{req.workspace_id}:{req.purpose.step_ref}")
        )
        meta = draft_meta_of(
            manifest_id=mid,
            blocks=self.draft_blocks,
            conditional=self.conditional_blocks,
            host_inputs=self.host_inputs,
            budget=budget,
            resume=req.resume,
            repo_max_files=repo_max_files,
        )
        d_digest = compute_draft_digest(meta)
        cond_deps_j: JsonObject = {}
        for cb in self.conditional_blocks:
            cond_deps_j[f"c:{cb.block.ordinal}"] = list[JsonValue](sorted(cb.deps))
        res_j: JsonValue = (
            None
            if req.resume is None
            else {
                "session_ref": req.resume.session_ref,
                "previous_task_digest": req.resume.previous_task_digest,
            }
        )
        skills_trace: JsonObject = {
            "mode": "none",
            "skills_budget": budget.skills_budget,
            "skills_remaining": cast("Mapping[str, JsonValue]", meta["budget"])["skills_remaining"],
            "repo_max_files": repo_max_files,
            "conditional_deps": cond_deps_j,
            "resume": res_j,
        }
        rows = [draft_block_to_manifest_row(db, prefix="d") for db in self.draft_blocks]
        rows.extend(draft_block_to_manifest_row(cb.block, prefix="c") for cb in self.conditional_blocks)
        rows.extend(self.excluded_rows)
        rows.sort(key=lambda r: r.ordinal)
        deg_j = list[JsonValue](sorted(req.runtime.degraded))
        sl_j: list[JsonValue] = [dict(sl) for sl in req.runtime.self_loads]
        manifest = ContextManifest(
            id=mid,
            state=ManifestState.DRAFT,
            workspace_id=req.workspace_id,
            project_id=req.project_id,
            plan_id=req.plan_id,
            revision_id=req.revision_id,
            entity_id=req.entity_id,
            purpose=req.purpose,
            agent_profile_version_id=req.agent_profile_version_id,
            runtime_id=req.runtime.runtime_id,
            model=req.runtime.model,
            route={
                "route_source": req.runtime.route_source,
                "operation": req.runtime.operation,
                "config_mode": req.runtime.config_mode,
                "degraded": deg_j,
                "self_loads": sl_j,
                "self_loads_observed": None,
            },
            draft_digest=d_digest,
            mode=None,
            task_digest=None,
            prompt_digest=None,
            prompt_file_version_id=None,
            total_tokens_estimate=None,
            total_limit=budget.total_limit,
            budgets={cls: ClassUsage(tokens=None, limit=budget.class_limits.get(cls)) for cls in BudgetClass},
            blocks=tuple(rows),
            host_facts=None,
            skills_trace=skills_trace,
            diagnostics=tuple(self.diagnostics),
            estimator_id=budget.estimator_id,
            assembler_version=ASSEMBLER_VERSION,
            created_at=created_at,
            finalized_at=None,
            owner_ref=owner_ref,
            host_inputs=tuple(self.host_inputs),
        )
        texts = {db.content_digest: db.content for db in self.draft_blocks}
        texts.update({cb.block.content_digest: cb.block.content for cb in self.conditional_blocks})
        draft = ContextDraft(
            manifest_id=mid,
            blocks=tuple(self.draft_blocks),
            conditional=tuple(self.conditional_blocks),
            excluded=tuple(self.excluded_rows),
            host_inputs=tuple(self.host_inputs),
            templates=dict(self.templates),
            prompt_plan=dict(self.prompt_plan),
            variables=dict(self.variables),
            budget=budget,
            resume=req.resume,
            skills_trace=skills_trace,
            diagnostics=tuple(self.diagnostics),
            draft_digest=d_digest,
            manifest=manifest,
            repo_max_files=repo_max_files,
        )
        return draft, manifest, texts
