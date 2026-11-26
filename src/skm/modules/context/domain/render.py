"""Deterministic prompt template substitution, safe code fencing, and block rendering (context §5.10)."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.json_types import JsonValue
from skm.kernel.languages import FENCE_TAGS
from skm.modules.context.domain.blocks import BlockType, TrustLevel
from skm.modules.context.domain.reasons import ExcludeReason, IncludeReason
from skm.modules.context.domain.request import format_work_policy_trailer
from skm.modules.context.domain.research_render import (
    NOTICE,
    batch_trust,
    fence_research,
    render_research_item,
)

if TYPE_CHECKING:
    from skm.modules.context.domain.decide import Selection
    from skm.modules.context.domain.draft import ContextDraft, DraftBlock
    from skm.modules.context.domain.host_inputs import HostBlock, HostInputRequest
    from skm.modules.context.domain.manifest import DraftAssembler
    from skm.modules.context.domain.request import ContextRequest, ValidatedWorkPolicy

__all__ = [
    "ALLOWED_NAMESPACES",
    "CODE_EXTENSIONS",
    "EntityPromptScope",
    "build_prompt_variables",
    "emit_execution_state_blocks",
    "fence",
    "fence_tag_for_path",
    "format_host_block",
    "render",
    "render_block_text",
    "render_task_contract_markdown",
    "substitute",
]

ALLOWED_NAMESPACES: Final[frozenset[str]] = frozenset(
    ("task", "plan", "run", "role", "runtime", "permissions", "block")
)

CODE_EXTENSIONS: Final[Mapping[str, str]] = FENCE_TAGS

_PLACEHOLDER_RE: Final[re.Pattern[str]] = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)
_KEY_RE: Final[re.Pattern[str]] = re.compile(r"^([a-z_][a-z0-9_]*)\.([a-z_][a-z0-9_]*)$")
_BACKTICK_RUN_RE: Final[re.Pattern[str]] = re.compile(r"`+")


def fence_tag_for_path(path: str) -> str | None:
    """Return code fence language tag for code-like extensions, or ``None`` for prose/markdown."""
    lowered = path.lower()
    for ext, tag in CODE_EXTENSIONS.items():
        if lowered.endswith(ext):
            return tag
    return None


def fence(text: str, tag: str) -> str:
    """Wrap ``text`` in a Markdown code fence strictly longer than any backtick run in ``text``."""
    longest = max((len(match.group(0)) for match in _BACKTICK_RUN_RE.finditer(text)), default=0)
    ticks = "`" * max(3, longest + 1)
    body = text[:-1] if text.endswith("\n") else text
    if not body:
        return f"{ticks}{tag}\n{ticks}"
    return f"{ticks}{tag}\n{body}\n{ticks}"


def _format_scalar(value: JsonValue) -> str:
    if value is None:
        return "none"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    if isinstance(value, int | float):
        return str(value)
    return str(value)


def _format_value(value: JsonValue) -> str:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        seq = cast("Sequence[JsonValue]", value)
        if not seq:
            return "(none)"
        return "\n".join(f"- {_format_scalar(item)}" for item in seq)
    if isinstance(value, Mapping):
        mp = cast("Mapping[str, JsonValue]", value)
        if not mp:
            return "(none)"
        return "\n".join(f"- {k}: {_format_scalar(v)}" for k, v in sorted(mp.items()))
    return _format_scalar(value)


def _lookup_variable(variables: Mapping[str, JsonValue], namespace: str, key: str) -> JsonValue:
    dotted = f"{namespace}.{key}"
    if dotted in variables:
        return variables[dotted]
    ns_obj = variables.get(namespace)
    if isinstance(ns_obj, Mapping):
        ns_map = cast("Mapping[str, JsonValue]", ns_obj)
        if key in ns_map:
            return ns_map[key]
    raise ValidationFailed(
        ErrorCode.CONTEXT_TEMPLATE_INVALID,
        f"unknown template variable '{dotted}'",
        details={"variable": dotted},
    )


def substitute(template: str, variables: Mapping[str, JsonValue]) -> str:
    """Single-pass ``{{ namespace.key }}`` substitution without recursive expansion."""
    stripped_pairs = _PLACEHOLDER_RE.sub("", template)
    if "{{" in stripped_pairs or "}}" in stripped_pairs:
        raise ValidationFailed(
            ErrorCode.CONTEXT_TEMPLATE_INVALID,
            "unbalanced '{{' or '}}' in prompt template",
            details={"reason": "unbalanced_braces"},
        )

    def _replace(match: re.Match[str]) -> str:
        expr = match.group(1).strip()
        parsed = _KEY_RE.match(expr)
        if parsed is None:
            raise ValidationFailed(
                ErrorCode.CONTEXT_TEMPLATE_INVALID,
                f"invalid placeholder syntax '{expr}'",
                details={"placeholder": expr},
            )
        namespace, key = parsed.group(1), parsed.group(2)
        if namespace not in ALLOWED_NAMESPACES:
            raise ValidationFailed(
                ErrorCode.CONTEXT_TEMPLATE_INVALID,
                f"disallowed template namespace '{namespace}'",
                details={"variable": expr},
            )
        return _format_value(_lookup_variable(variables, namespace, key))

    return _PLACEHOLDER_RE.sub(_replace, template)


def render_block_text(
    *,
    block_type: BlockType,
    title: str,
    content: str,
    source_ref: str,
    templates: Mapping[str, str],
    prompt_plan: Mapping[BlockType, tuple[str, ...]],
    variables: Mapping[str, JsonValue],
) -> str:
    """Render a single block using ``prompt_plan`` or ``shared/block_wrapper``."""
    base_block = variables.get("block")
    merged_block: dict[str, JsonValue] = (
        dict(cast("Mapping[str, JsonValue]", base_block)) if isinstance(base_block, Mapping) else {}
    )
    merged_block.update({"title": title, "content": content, "source": source_ref})
    scoped_vars: dict[str, JsonValue] = {**variables, "block": merged_block}

    plan_keys = prompt_plan.get(block_type, ())
    if plan_keys:
        parts: list[str] = []
        uses_block_content = False
        for tpl_key in plan_keys:
            if tpl_key not in templates:
                raise ValidationFailed(
                    ErrorCode.CONTEXT_TEMPLATE_INVALID,
                    f"missing prompt block template '{tpl_key}'",
                    details={"template": tpl_key, "block_type": block_type.value},
                )
            raw_tpl = templates[tpl_key]
            if "block.content" in raw_tpl:
                uses_block_content = True
            parts.append(substitute(raw_tpl, scoped_vars).rstrip("\n"))
        rendered = "\n\n".join(part for part in parts if part)
        if not uses_block_content and content and content != rendered and content.startswith(rendered):
            return content.rstrip("\n")
        return rendered

    wrapper = templates.get("shared/block_wrapper")
    if wrapper is not None and title:
        return substitute(wrapper, scoped_vars).rstrip("\n")
    if title:
        return f"## {title}\n\n{content}".rstrip("\n") if content else f"## {title}"
    return content.rstrip("\n")


def format_host_block(req: HostInputRequest, hb: HostBlock) -> tuple[BlockType, str, str, str]:
    """Return ``(block_type, title, body, source_ref)`` for an ``OK`` host block."""
    if hb.text is None or req.block_type is None:
        raise ValidationFailed(
            ErrorCode.CONTEXT_MANIFEST_TAMPERED,
            f"included host block 'h:{req.request_id}' is missing text or request metadata",
            details={"block_ref": f"h:{req.request_id}"},
        )
    display_path = hb.resolved_path or req.path or req.source_ref
    title = (
        f"Repository instructions ({display_path})"
        if req.block_type is BlockType.REPO_INSTRUCTIONS
        else (
            f"Research ({req.source_ref})"
            if req.block_type is BlockType.RESEARCH
            else f"Material ({display_path})"
        )
    )
    body = hb.text
    if req.block_type is BlockType.RESEARCH:
        # Host text is a separate trust boundary, even for clients that skip the built-in collector.
        body = NOTICE + "\n" + fence_research(body)
    if req.block_type in (BlockType.MATERIALS, BlockType.REPO_INSTRUCTIONS):
        tag = fence_tag_for_path(display_path)
        if tag is not None:
            body = fence(body, tag)
    return req.block_type, title, body, req.source_ref


def _resolve_included_block(
    block_ref: str,
    draft_by_ref: Mapping[str, DraftBlock],
    host_by_id: Mapping[str, HostBlock],
    host_req_by_id: Mapping[str, HostInputRequest],
) -> tuple[BlockType, str, str, str]:
    if block_ref in draft_by_ref:
        db = draft_by_ref[block_ref]
        return db.block_type, db.title, db.content, db.source_ref
    if block_ref.startswith("h:"):
        req_id = block_ref[2:]
        req = host_req_by_id.get(req_id)
        hb = host_by_id.get(req_id)
        if req is None or hb is None:
            raise ValidationFailed(
                ErrorCode.CONTEXT_MANIFEST_TAMPERED,
                f"included host block '{block_ref}' is missing text or request metadata",
                details={"block_ref": block_ref},
            )
        return format_host_block(req, hb)
    raise ValidationFailed(
        ErrorCode.CONTEXT_MANIFEST_TAMPERED,
        f"unknown included block_ref '{block_ref}'",
        details={"block_ref": block_ref},
    )


def render(
    draft: ContextDraft, host_blocks: Sequence[HostBlock], selection: Selection
) -> tuple[str, tuple[str, ...]]:
    """Render selected blocks in position order; concatenation of returned pieces equals the prompt."""
    if not selection.included:
        return "", ()

    draft_by_ref: dict[str, DraftBlock] = {f"d:{b.ordinal}": b for b in draft.blocks}
    for cb in draft.conditional:
        draft_by_ref[f"c:{cb.block.ordinal}"] = cb.block
    host_by_id = {hb.request_id: hb for hb in host_blocks}
    host_req_by_id = {req.request_id: req for req in draft.host_inputs}

    ordered = sorted(selection.included, key=lambda item: item[1])
    rendered_bodies: list[str] = []
    for expected_pos, (block_ref, pos) in enumerate(ordered):
        if pos != expected_pos:
            raise ValidationFailed(
                ErrorCode.CONTEXT_MANIFEST_TAMPERED,
                "selection positions must be contiguous 0..n-1",
                details={"expected": expected_pos, "actual": pos, "block_ref": block_ref},
            )
        block_type, title, content, source_ref = _resolve_included_block(
            block_ref, draft_by_ref, host_by_id, host_req_by_id
        )
        rendered_bodies.append(
            render_block_text(
                block_type=block_type,
                title=title,
                content=content,
                source_ref=source_ref,
                templates=draft.templates,
                prompt_plan=draft.prompt_plan,
                variables=draft.variables,
            )
        )

    pieces: list[str] = []
    last_idx = len(rendered_bodies) - 1
    for idx, body in enumerate(rendered_bodies):
        suffix = "\n" if idx == last_idx else "\n\n"
        pieces.append(body + suffix)
    prompt = "".join(pieces)
    return prompt, tuple(pieces)


@dataclass(frozen=True, slots=True)
class EntityPromptScope:
    key: str
    title: str
    goal: str
    why: str
    work_kind: str
    instructions: str
    guidance: str
    write_paths: tuple[str, ...]
    forbidden_paths: tuple[str, ...]
    deliverables: tuple[str, ...]
    outputs: tuple[str, ...]
    rules: tuple[str, ...]
    chain_keys: frozenset[str]


def _jlist(items: Sequence[str]) -> list[JsonValue]:
    return list[JsonValue](items)


def build_prompt_variables(  # noqa: PLR0913 -- closed template namespaces (context §5.10)
    request: ContextRequest,
    escope: EntityPromptScope,
    *,
    plan_alias: str,
    plan_title: str,
    plan_goal: str,
    revision_no: int | None,
    profile_key: str,
    result_schema: str,
    wp: ValidatedWorkPolicy,
    output_lang: str,
    rules_extra: Sequence[str],
) -> dict[str, JsonValue]:
    """Build closed template variable namespaces for Phase-A/B substitution."""
    eff_writes = _jlist(escope.write_paths or request.permissions.write_scope)
    em_val: JsonValue = "none" if wp.emergency_wall_seconds is None else wp.emergency_wall_seconds
    repro_val: JsonValue = "none" if wp.repro_warn_seconds is None else wp.repro_warn_seconds
    return {
        "task": {
            "id": escope.key if request.entity_id is None else str(request.entity_id),
            "key": escope.key,
            "display_key": escope.key,
            "title": escope.title,
            "goal": escope.goal,
            "why": escope.why,
            "kind": escope.work_kind,
            "work_kind": escope.work_kind,
            "instructions": escope.instructions,
            "write_scope": eff_writes,
            "write_paths": eff_writes,
            "forbidden_paths": _jlist(escope.forbidden_paths),
            "deliverables": _jlist(escope.deliverables),
            "outputs": _jlist(escope.outputs),
            "rules": _jlist(escope.rules),
            "guidance": escope.guidance,
            "work_policy_digest": wp.digest,
        },
        "plan": {
            "id": None if request.plan_id is None else str(request.plan_id),
            "alias": plan_alias,
            "display_key": plan_alias,
            "title": plan_title,
            "goal": plan_goal or plan_title,
            "revision_id": None if request.revision_id is None else str(request.revision_id),
            "revision_no": revision_no,
        },
        "run": {
            "id": request.run.run_id,
            "step_ref": request.purpose.step_ref,
            "stage_id": request.purpose.stage_id,
            "attempt_no": request.purpose.attempt_no,
            "round_no": request.purpose.round_no,
            "workflow": request.run.workflow_key,
            "integration_branch": request.run.integration_branch,
            "commit_policy": request.run.commit_policy,
            "progress_format": request.run.progress_format,
            "output_language": output_lang,
            "rules_extra": _jlist(rules_extra),
            "verification_intensity": wp.verification_intensity,
        },
        "role": {
            "name": request.purpose.role,
            "profile_key": profile_key,
            "result_schema": result_schema,
            "intensity": wp.role_intensity,
            "warn_seconds": wp.warn_seconds,
            "emergency_wall_seconds": em_val,
            "triage_repro_warn_seconds": repro_val,
        },
        "runtime": {
            "id": request.runtime.runtime_id,
            "model": request.runtime.model,
            "context_window_tokens": request.runtime.context_window_tokens,
        },
        "permissions": {
            "write_scope": _jlist(request.permissions.write_scope),
            "read_scope": _jlist(request.permissions.read_scope),
            "commands_allowed": _jlist(request.permissions.commands_allowed),
            "commands_denied": _jlist(request.permissions.commands_denied),
            "network": request.permissions.network,
            "network_allow": _jlist(request.permissions.network_allow),
            "external_effects": _jlist(request.permissions.external_effects),
        },
        "block": {"title": "", "content": "", "source": ""},
    }


def render_task_contract_markdown(
    escope: EntityPromptScope,
    wp: ValidatedWorkPolicy,
    templates: Mapping[str, str],
    prompt_plan: Mapping[BlockType, tuple[str, ...]],
    variables: Mapping[str, JsonValue],
) -> str:
    """Render mandatory ``task_contract`` markdown including work policy and continuation rule."""
    plan_keys = prompt_plan.get(BlockType.TASK_CONTRACT, ())
    base_parts = [substitute(templates[k], variables).rstrip("\n") for k in plan_keys]
    if not base_parts:
        ws = "\n".join(f"- {p}" for p in escope.write_paths) if escope.write_paths else "(none)"
        fp = "\n".join(f"- {p}" for p in escope.forbidden_paths) if escope.forbidden_paths else "(none)"
        base_parts.append(
            f"## Task {escope.key}: {escope.title}\n\nGoal: {escope.goal}\n\n"
            f"Write scope:\n{ws}\n\nForbidden paths:\n{fp}"
        )
        if "shared/work_policy" in templates:
            base_parts.append(substitute(templates["shared/work_policy"], variables).rstrip("\n"))
    if "shared/work_policy" not in plan_keys and "shared/work_policy" not in templates:
        em_s = "none" if wp.emergency_wall_seconds is None else f"{wp.emergency_wall_seconds}s"
        base_parts.append(
            f"## Work policy\n\nRole ({wp.role}) intensity: {wp.role_intensity}; "
            f"verification intensity: {wp.verification_intensity}; soft target: {wp.warn_seconds}s; "
            f"emergency ceiling: {em_s}; policy digest: {wp.digest}.\n"
            "Exceeding expected time warn_seconds is an advisory soft warning, not a hard cutoff: "
            "examine progress and continue authorized work when justified to satisfy acceptance criteria."
        )
    trailer = format_work_policy_trailer(wp)
    if trailer:
        base_parts.append(f"### Policy diagnostics\n\n{trailer}")
    return "\n\n".join(p for p in base_parts if p)


def emit_execution_state_blocks(
    b: DraftAssembler, req: ContextRequest, candidate_diff_text: str | None, *, history_cap: int = 0
) -> None:
    """Emit pure execution-state and history blocks into ``DraftAssembler``."""
    eb, sref = req.execution_blocks, req.purpose.step_ref
    if eb.operator_steering:
        b.add(
            BlockType.STEERING,
            "Operator instructions",
            eb.operator_steering,
            "execution",
            f"steer:{sref}",
            trust=TrustLevel.OPERATOR,
            mandatory=True,
        )
    if eb.decision_answers:
        txt = "\n".join(
            f"- [{a.request_id}] ({a.answered_by_kind}) {a.question}: {json.dumps(a.answer)}"
            for a in eb.decision_answers
        )
        b.add(BlockType.DECISION_ANSWERS, "Answers", txt, "execution", f"answers:{sref}")
    if eb.review_feedback is not None:
        txt = json.dumps(dict(eb.review_feedback), sort_keys=True, indent=2)
        b.add(BlockType.REVIEW_FEEDBACK, "Review Feedback", txt, "execution", f"fix_brief:{sref}")
    if eb.previous_attempt is not None:
        pa = eb.previous_attempt
        txt = f"Attempt {pa.attempt_no}: {pa.outcome} ({pa.reason_code})\nNote: {pa.note}"
        b.add(BlockType.PREVIOUS_ATTEMPT, "Previous Attempt", txt, "execution", f"attempt:{pa.attempt_no}")
    if eb.candidate is not None and candidate_diff_text is not None:
        is_rev = req.purpose.role in ("reviewer", "triager")
        fref = f"file_version:{eb.candidate.diff_file_version_id}"
        rsn = IncludeReason.MANDATORY if is_rev else IncludeReason.EXECUTION_INPUT
        b.add(
            BlockType.CANDIDATE_DIFF,
            "Candidate Diff",
            fence(candidate_diff_text, "diff"),
            "file_version",
            fref,
            source_version=eb.candidate.manifest_digest,
            mandatory=is_rev,
            reason=rsn,
        )
    if eb.findings_under_review:
        txt = "\n".join(f"- {json.dumps(dict(f), sort_keys=True)}" for f in eb.findings_under_review)
        b.add(
            BlockType.FINDINGS_UNDER_REVIEW,
            "Findings Under Review",
            txt,
            "execution",
            f"findings:{sref}",
        )
    if eb.context_map is not None:
        cm = eb.context_map
        b.add(
            BlockType.CONTEXT_MAP,
            "Context Map",
            cm.text,
            "execution",
            f"context_map:{cm.step_ref}",
            source_version=cm.digest,
        )
    for idx, ritem in enumerate(eb.research):
        b.add(
            BlockType.RESEARCH,
            "Research",
            render_research_item(ritem),
            "execution",
            f"exec:research:{ritem.step_ref}:{idx}",
            trust=batch_trust(ritem.documents),
        )
    if eb.history and history_cap > 0:
        for old in eb.history[:-history_cap]:
            b.exclude(
                BlockType.HISTORY,
                "execution",
                f"history:{old.step_ref}",
                ExcludeReason.HISTORY_WINDOW,
                trust=TrustLevel.MODEL,
            )
        htxt = "\n".join(
            f"- [{h.step_ref}] ({h.role} -> {h.outcome}): {h.summary}" for h in eb.history[-history_cap:]
        )
        b.add(
            BlockType.HISTORY,
            "Recent Step History",
            htxt,
            "execution",
            f"history:{sref}",
            reason=IncludeReason.RECENT_HISTORY,
        )
