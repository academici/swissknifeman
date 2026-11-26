"""Deterministic Phase-B / server-side block selection and budget cutting (context §§5.9, 5.10)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed, ValidationFailed
from skm.modules.context.domain.blocks import (
    LADDER_ORDER,
    ROUND_TYPES,
    BlockType,
    BudgetClass,
)
from skm.modules.context.domain.blocks import (
    canonical_json_digest as jsonc_digest,
)
from skm.modules.context.domain.host_inputs import HostFacts, HostInputKind, HostReadStatus
from skm.modules.context.domain.reasons import ExcludeReason, IncludeReason

if TYPE_CHECKING:
    from skm.kernel.json_types import JsonObject, JsonValue
    from skm.modules.context.domain.contracts import Diagnostic, Digest, DraftMeta, HostFactsMeta
    from skm.modules.context.domain.host_inputs import HostBlockMeta

__all__ = [
    "HOST_STATUS_TO_EXCLUDE_REASON",
    "Selection",
    "decide",
    "decide_with_diagnostics",
    "host_include_reason",
]


@dataclass(frozen=True, slots=True)
class Selection:
    included: tuple[tuple[str, int], ...]
    excluded: tuple[tuple[str, ExcludeReason, str | None], ...]
    class_usage: Mapping[BudgetClass, int]
    total_tokens: int
    task_digest: Digest
    mode: Literal["full", "delta"]


@dataclass(frozen=True, slots=True)
class _Candidate:
    block_ref: str
    block_type: BlockType
    budget_class: BudgetClass
    mandatory: bool
    source_ref: str
    atomic_group: str | None
    tokens: int
    content_digest: str


HOST_STATUS_TO_EXCLUDE_REASON: Mapping[HostReadStatus, ExcludeReason] = MappingProxyType(
    {
        HostReadStatus.MISSING: ExcludeReason.NOT_FOUND,
        HostReadStatus.TOO_LARGE: ExcludeReason.TOO_LARGE,
        HostReadStatus.BINARY: ExcludeReason.BINARY_CONTENT,
        HostReadStatus.PATH_INVALID: ExcludeReason.PATH_INVALID,
        HostReadStatus.SYMLINK_OUTSIDE: ExcludeReason.SYMLINK_REFUSED,
        HostReadStatus.SYMLINK_REFUSED: ExcludeReason.SYMLINK_REFUSED,
        HostReadStatus.NO_MATCHING_SECTIONS: ExcludeReason.NO_MATCHING_SECTIONS,
        HostReadStatus.BUDGET_EXCEEDED: ExcludeReason.HOST_BUDGET_EXCEEDED,
        HostReadStatus.OVER_MAX_FILES: ExcludeReason.REPO_INSTRUCTIONS_MAX_FILES,
        HostReadStatus.SELF_LOADED: ExcludeReason.RUNTIME_SELF_LOADED,
    }
)

_CLASS_OVER_REASON: Mapping[BudgetClass, ExcludeReason] = MappingProxyType(
    {
        BudgetClass.CORE: ExcludeReason.OVER_BUDGET_CORE,
        BudgetClass.TASK: ExcludeReason.OVER_TOTAL_BUDGET,
        BudgetClass.SUPPORTING: ExcludeReason.OVER_BUDGET_SUPPORTING,
        BudgetClass.RETRIEVAL: ExcludeReason.OVER_BUDGET_RETRIEVAL,
    }
)


def host_include_reason(kind: HostInputKind, *, required: bool) -> IncludeReason:
    if kind is HostInputKind.REPO_INSTRUCTIONS:
        return IncludeReason.CARRIER_FOR_WRITE_SCOPE
    if kind is HostInputKind.RESEARCH_QUERY:
        return IncludeReason.RESEARCH_RESULT
    return IncludeReason.REQUIRED_MATERIAL if required else IncludeReason.OPTIONAL_MATERIAL


def _tampered(message: str, **details: object) -> ValidationFailed:
    det: JsonObject = {
        k: (v if isinstance(v, str | int | bool) or v is None else str(v)) for k, v in details.items()
    }
    return ValidationFailed(ErrorCode.CONTEXT_MANIFEST_TAMPERED, message, details=det)


def _extract_deps(facts: HostFacts | HostFactsMeta) -> frozenset[str]:
    if isinstance(facts, HostFacts):
        return facts.deps
    raw = facts.get("deps", ())
    if isinstance(raw, Sequence) and not isinstance(raw, str | bytes):
        return frozenset(str(item) for item in cast("Sequence[object]", raw))
    return frozenset()


def _parse_draft_candidates(draft_meta: DraftMeta) -> list[_Candidate]:
    raw_blocks = draft_meta.get("blocks", ())
    if not isinstance(raw_blocks, Sequence) or isinstance(raw_blocks, str | bytes):
        raise _tampered("draft_meta.blocks must be a sequence")
    out: list[_Candidate] = []
    for entry in cast("Sequence[object]", raw_blocks):
        if not isinstance(entry, Mapping):
            raise _tampered("draft block entry must be an object")
        raw = cast("Mapping[str, object]", entry)
        atomic_raw = raw.get("atomic_group")
        out.append(
            _Candidate(
                block_ref=str(raw["block_ref"]),
                block_type=BlockType(str(raw["block_type"])),
                budget_class=BudgetClass(str(raw["budget_class"])),
                mandatory=bool(raw["mandatory"]),
                source_ref=str(raw["source_ref"]),
                atomic_group=None if atomic_raw is None else str(atomic_raw),
                tokens=int(cast("int", raw["tokens_estimate"])),
                content_digest=str(raw["content_digest"]),
            )
        )
    return out


def _skills_count_remaining(draft_meta: DraftMeta, bmap: Mapping[str, object]) -> int:
    explicit_rem = bmap.get("count_remaining", bmap.get("skills_count_remaining"))
    if explicit_rem is not None:
        return max(0, int(cast("int", explicit_rem)))
    raw_max = bmap.get("skills_max_count", bmap.get("max_count", draft_meta.get("skills_max_count", 8)))
    max_count = int(cast("int", raw_max))
    raw_blocks = draft_meta.get("blocks", ())
    used_count = 0
    if isinstance(raw_blocks, Sequence) and not isinstance(raw_blocks, str | bytes):
        for item in cast("Sequence[object]", raw_blocks):
            if not isinstance(item, Mapping):
                continue
            raw = cast("Mapping[str, object]", item)
            if (
                str(raw.get("block_type", "")) == BlockType.SKILLS.value
                and not bool(raw.get("mandatory", False))
                and str(raw.get("reason", ""))
                not in (IncludeReason.EXPLICIT_PLAN.value, IncludeReason.EXPLICIT_PROFILE.value)
            ):
                used_count += 1
    return max(0, max_count - used_count)


def _evaluate_conditionals(
    draft_meta: DraftMeta,
    deps: frozenset[str],
    skills_budget_remaining: int,
    skills_count_remaining: int,
) -> tuple[list[_Candidate], list[tuple[str, ExcludeReason, str | None]]]:
    raw_cond = draft_meta.get("conditional", ())
    if not isinstance(raw_cond, Sequence) or isinstance(raw_cond, str | bytes):
        raise _tampered("draft_meta.conditional must be a sequence")
    included: list[_Candidate] = []
    excluded: list[tuple[str, ExcludeReason, str | None]] = []
    remaining = skills_budget_remaining
    count_remaining = skills_count_remaining
    for entry in cast("Sequence[object]", raw_cond):
        if not isinstance(entry, Mapping):
            raise _tampered("conditional block entry must be an object")
        raw = cast("Mapping[str, object]", entry)
        block_ref = str(raw["block_ref"])
        raw_deps = raw.get("deps", ())
        req_deps: frozenset[str] = (
            frozenset(str(d) for d in cast("Sequence[object]", raw_deps))
            if isinstance(raw_deps, Sequence) and not isinstance(raw_deps, str | bytes)
            else frozenset()
        )
        if not (req_deps & deps):
            excluded.append((block_ref, ExcludeReason.TRIGGER_NOT_MET, None))
            continue
        tokens = int(cast("int", raw["tokens_estimate"]))
        if not bool(raw.get("explicit", False)):
            if tokens > remaining:
                excluded.append((block_ref, ExcludeReason.OVER_SKILL_BUDGET, None))
                continue
            if count_remaining <= 0:
                excluded.append((block_ref, ExcludeReason.OVER_SKILL_COUNT, None))
                continue
            remaining -= tokens
            count_remaining -= 1
        atomic_raw = raw.get("atomic_group")
        included.append(
            _Candidate(
                block_ref=block_ref,
                block_type=BlockType(str(raw["block_type"])),
                budget_class=BudgetClass(str(raw["budget_class"])),
                mandatory=bool(raw.get("mandatory", False)),
                source_ref=str(raw["source_ref"]),
                atomic_group=None if atomic_raw is None else str(atomic_raw),
                tokens=tokens,
                content_digest=str(raw["content_digest"]),
            )
        )
    return included, excluded


def _index_host_meta(
    draft_meta: DraftMeta, host_meta: Sequence[HostBlockMeta]
) -> tuple[list[str], dict[str, Mapping[str, object]], dict[str, HostBlockMeta]]:
    raw_inputs = draft_meta.get("host_inputs", ())
    if not isinstance(raw_inputs, Sequence) or isinstance(raw_inputs, str | bytes):
        raise _tampered("draft_meta.host_inputs must be a sequence")
    planned: dict[str, Mapping[str, object]] = {}
    order: list[str] = []
    for entry in cast("Sequence[object]", raw_inputs):
        if not isinstance(entry, Mapping):
            raise _tampered("host_input entry must be an object")
        raw_entry = cast("Mapping[str, object]", entry)
        req_id = str(raw_entry["request_id"])
        planned[req_id] = raw_entry
        order.append(req_id)
    seen: dict[str, HostBlockMeta] = {}
    for hm in host_meta:
        if hm.request_id in seen:
            raise _tampered("duplicate host block request_id", request_id=hm.request_id)
        if hm.request_id not in planned:
            raise _tampered("unknown host block request_id", request_id=hm.request_id)
        seen[hm.request_id] = hm
    if len(seen) != len(planned):
        missing_id = next(req_id for req_id in order if req_id not in seen)
        raise _tampered("missing planned host input in host_meta", request_id=missing_id)
    return order, planned, seen


def _validate_single_host_status(
    req: Mapping[str, object],
    hm: HostBlockMeta,
    *,
    repo_ok_count: int,
    repo_max_files: int,
) -> int:
    req_id = str(req["request_id"])
    kind = HostInputKind(str(req["kind"]))
    max_bytes = int(cast("int", req["max_bytes"]))
    if hm.status is HostReadStatus.OK:
        if hm.size_bytes is not None and (hm.size_bytes < 0 or hm.size_bytes > max_bytes):
            raise _tampered(
                "OK host block exceeds max_bytes",
                request_id=req_id,
                size_bytes=hm.size_bytes,
                max_bytes=max_bytes,
            )
        if kind is not HostInputKind.DEPENDENCY_MANIFEST and hm.size_bytes is None:
            raise _tampered("OK host block is missing size_bytes", request_id=req_id)
        if kind is HostInputKind.REPO_INSTRUCTIONS:
            repo_ok_count += 1
            if repo_ok_count > repo_max_files:
                raise _tampered(
                    "OK repo_instructions count exceeds repo_max_files",
                    request_id=req_id,
                    repo_max_files=repo_max_files,
                )
        return repo_ok_count

    if (
        kind is HostInputKind.REPO_INSTRUCTIONS
        and hm.status is HostReadStatus.OVER_MAX_FILES
        and repo_ok_count < repo_max_files
    ):
        raise _tampered(
            "OVER_MAX_FILES reported before repo_max_files OK blocks",
            request_id=req_id,
            ok_count=repo_ok_count,
            repo_max_files=repo_max_files,
        )
    if hm.status is HostReadStatus.SELF_LOADED:
        raw_skip = req.get("skip_if_resolved_in", ())
        skip_names: frozenset[str] = (
            frozenset(str(s) for s in cast("Sequence[object]", raw_skip))
            if isinstance(raw_skip, Sequence) and not isinstance(raw_skip, str | bytes)
            else frozenset()
        )
        basename = hm.resolved_path.rstrip("/").rsplit("/", 1)[-1] if hm.resolved_path else ""
        if not basename or basename not in skip_names:
            raise _tampered(
                "SELF_LOADED basename not in skip_if_resolved_in",
                request_id=req_id,
                resolved_path=hm.resolved_path,
            )
    if bool(req["required"]):
        raise PreconditionFailed(
            ErrorCode.CONTEXT_INPUT_MISSING,
            f"required host input '{req_id}' could not be read ({hm.status.value})",
            details={"request_id": req_id, "path": str(req["path"]), "status": hm.status.value},
        )
    return repo_ok_count


def _evaluate_host_blocks(
    draft_meta: DraftMeta,
    host_meta: Sequence[HostBlockMeta],
) -> tuple[list[_Candidate], list[tuple[str, ExcludeReason, str | None]]]:
    order, planned, seen = _index_host_meta(draft_meta, host_meta)
    repo_max_files = int(cast("int", draft_meta.get("repo_max_files", 8)))
    repo_ok_count = 0
    candidates: list[_Candidate] = []
    excluded: list[tuple[str, ExcludeReason, str | None]] = []

    for req_id in order:
        req = planned[req_id]
        hm = seen[req_id]
        repo_ok_count = _validate_single_host_status(
            req, hm, repo_ok_count=repo_ok_count, repo_max_files=repo_max_files
        )
        kind = HostInputKind(str(req["kind"]))
        block_type_raw = req.get("block_type")
        if kind is HostInputKind.DEPENDENCY_MANIFEST or block_type_raw is None:
            continue
        block_ref = f"h:{req_id}"
        if hm.status is not HostReadStatus.OK:
            excluded.append((block_ref, HOST_STATUS_TO_EXCLUDE_REASON[hm.status], hm.resolved_path))
            continue
        if hm.tokens_estimate is None or hm.tokens_estimate < 0 or not hm.text_digest:
            raise _tampered("OK host block missing tokens_estimate or text_digest", request_id=req_id)
        btype = BlockType(str(block_type_raw))
        bclass = (
            BudgetClass.SUPPORTING
            if btype in (BlockType.REPO_INSTRUCTIONS, BlockType.MATERIALS)
            else BudgetClass.RETRIEVAL
        )
        candidates.append(
            _Candidate(
                block_ref=block_ref,
                block_type=btype,
                budget_class=bclass,
                mandatory=bool(req["required"]) and btype is BlockType.MATERIALS,
                source_ref=str(req["source_ref"]),
                atomic_group=None,
                tokens=hm.tokens_estimate,
                content_digest=hm.text_digest,
            )
        )
    return candidates, excluded


def _group_members(pool: Sequence[_Candidate], target: _Candidate) -> tuple[_Candidate, ...]:
    if target.atomic_group is None:
        return (target,)
    return tuple(c for c in pool if c.atomic_group == target.atomic_group)


def _group_detail(members: Sequence[_Candidate]) -> str | None:
    if len(members) <= 1 and (not members or members[0].atomic_group is None):
        return None
    refs = ",".join(m.block_ref for m in members)
    return f"atomic_group:{members[0].atomic_group}[{refs}]"


def _find_droppable_group(items: Sequence[_Candidate]) -> tuple[_Candidate, ...] | None:
    for candidate in reversed(items):
        members = _group_members(items, candidate)
        if not any(m.mandatory for m in members):
            return members
    return None


def _apply_class_budgets(
    active: list[_Candidate],
    class_limits: Mapping[BudgetClass, int | None],
    excluded: list[tuple[str, ExcludeReason, str | None]],
    diagnostics: list[Diagnostic],
) -> list[_Candidate]:
    for bclass in (BudgetClass.CORE, BudgetClass.TASK, BudgetClass.SUPPORTING, BudgetClass.RETRIEVAL):
        limit = class_limits.get(bclass)
        if limit is None:
            continue
        while True:
            class_items = [c for c in active if c.budget_class is bclass]
            class_sum = sum(c.tokens for c in class_items)
            if class_sum <= limit:
                break
            victim_group = _find_droppable_group(class_items)
            if victim_group is None:
                diagnostics.append(
                    {
                        "code": "CLASS_OVER_LIMIT",
                        "severity": "warning",
                        "budget_class": bclass.value,
                        "tokens": class_sum,
                        "limit": limit,
                    }
                )
                break
            drop_refs = {m.block_ref for m in victim_group}
            detail = _group_detail(victim_group)
            reason = _CLASS_OVER_REASON[bclass]
            excluded.extend((m.block_ref, reason, detail) for m in reversed(victim_group))
            active = [c for c in active if c.block_ref not in drop_refs]
    return active


def _apply_total_budget(
    active: list[_Candidate],
    total_limit: int,
    excluded: list[tuple[str, ExcludeReason, str | None]],
) -> list[_Candidate]:
    while True:
        total_sum = sum(c.tokens for c in active)
        if total_sum <= total_limit:
            return active
        victim_group = _find_droppable_group(active)
        if victim_group is None:
            mandatory_tokens = sum(c.tokens for c in active if c.mandatory)
            raise PreconditionFailed(
                ErrorCode.CONTEXT_OVER_BUDGET,
                "mandatory context blocks exceed total token limit",
                details={"total": total_sum, "limit": total_limit, "mandatory": mandatory_tokens},
            )
        drop_refs = {m.block_ref for m in victim_group}
        detail = _group_detail(victim_group)
        excluded.extend(
            (m.block_ref, ExcludeReason.OVER_TOTAL_BUDGET, detail) for m in reversed(victim_group)
        )
        active = [c for c in active if c.block_ref not in drop_refs]


def _apply_resume_mode(
    active: list[_Candidate],
    *,
    prev_digest: str | None,
    computed_task_digest: str,
    excluded: list[tuple[str, ExcludeReason, str | None]],
) -> tuple[Literal["full", "delta"], list[_Candidate]]:
    kept: list[_Candidate] = []
    if prev_digest is not None and prev_digest == computed_task_digest:
        for c in active:
            if c.block_type is BlockType.RESUME_NOTE or (
                c.block_type in ROUND_TYPES and c.block_type is not BlockType.HISTORY
            ):
                kept.append(c)
            else:
                excluded.append((c.block_ref, ExcludeReason.IN_RESUMED_SESSION, None))
        return "delta", kept
    for c in active:
        if c.block_type is BlockType.RESUME_NOTE:
            excluded.append((c.block_ref, ExcludeReason.FULL_PROMPT, None))
        else:
            kept.append(c)
    return "full", kept


def decide_with_diagnostics(
    draft_meta: DraftMeta,
    host_meta: Sequence[HostBlockMeta],
    facts: HostFacts | HostFactsMeta,
) -> tuple[Selection, tuple[Diagnostic, ...]]:
    """Run deterministic Phase-B / server selection, returning ``(Selection, diagnostics)``."""
    budget_meta = draft_meta.get("budget")
    if not isinstance(budget_meta, Mapping):
        raise _tampered("draft_meta.budget must be an object")
    bmap = cast("Mapping[str, object]", budget_meta)
    total_limit = int(cast("int", bmap["total_limit"]))
    raw_class_limits = bmap.get("class_limits", {})
    class_limits: dict[BudgetClass, int | None] = {}
    if isinstance(raw_class_limits, Mapping):
        cmap = cast("Mapping[str, object]", raw_class_limits)
        for cls in BudgetClass:
            val = cmap.get(cls.value)
            class_limits[cls] = None if val is None else int(cast("int", val))
    skills_remaining = int(cast("int", bmap.get("skills_remaining", bmap.get("skills_budget", 0))))
    skills_count_remaining = _skills_count_remaining(draft_meta, bmap)

    deps = _extract_deps(facts)
    draft_candidates = _parse_draft_candidates(draft_meta)
    cond_candidates, cond_excluded = _evaluate_conditionals(
        draft_meta, deps, skills_remaining, skills_count_remaining
    )
    host_candidates, host_excluded = _evaluate_host_blocks(draft_meta, host_meta)

    excluded: list[tuple[str, ExcludeReason, str | None]] = [*cond_excluded, *host_excluded]
    diagnostics: list[Diagnostic] = []
    active = sorted(
        [*draft_candidates, *cond_candidates, *host_candidates],
        key=lambda c: (LADDER_ORDER[c.block_type], c.source_ref, c.block_ref),
    )
    active = _apply_class_budgets(active, class_limits, excluded, diagnostics)
    active = _apply_total_budget(active, total_limit, excluded)

    task_entries: list[JsonValue] = [
        [c.block_type.value, c.source_ref, c.content_digest]
        for c in active
        if c.block_type not in ROUND_TYPES
    ]
    computed_task_digest = jsonc_digest(task_entries)

    resume_raw = draft_meta.get("resume")
    prev_digest: str | None = None
    if isinstance(resume_raw, Mapping):
        rmap = cast("Mapping[str, object]", resume_raw)
        if rmap.get("previous_task_digest") is not None:
            prev_digest = str(rmap["previous_task_digest"])
    mode, active = _apply_resume_mode(
        active,
        prev_digest=prev_digest,
        computed_task_digest=computed_task_digest,
        excluded=excluded,
    )

    included = tuple((c.block_ref, idx) for idx, c in enumerate(active))
    class_usage = {cls: sum(c.tokens for c in active if c.budget_class is cls) for cls in BudgetClass}
    total_tokens = sum(c.tokens for c in active)
    return (
        Selection(
            included=included,
            excluded=tuple(excluded),
            class_usage=class_usage,
            total_tokens=total_tokens,
            task_digest=computed_task_digest,
            mode=mode,
        ),
        tuple(diagnostics),
    )


def decide(
    draft_meta: DraftMeta, host_meta: Sequence[HostBlockMeta], facts: HostFacts | HostFactsMeta
) -> Selection:
    """Pure decision function shared identically between host Phase B and server Phase C."""
    selection, _diagnostics = decide_with_diagnostics(draft_meta, host_meta, facts)
    return selection
