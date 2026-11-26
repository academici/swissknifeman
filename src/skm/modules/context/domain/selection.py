"""Select validated materials, skills, steering, retrieval and execution candidates."""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, cast

from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.context.domain.blocks import BlockType
from skm.modules.context.domain.candidates import metadata, objects, strings
from skm.modules.context.domain.skill_selection import SkillRequest, select_skill_metadata
from skm.modules.context.domain.steering_selection import select_steering
from skm.modules.context.domain.validation import preserve_groups

if TYPE_CHECKING:
    from skm.modules.context.domain.contracts import Candidate, Selected, Validated
    from skm.modules.context.domain.policy import ContextPolicy
    from skm.modules.context.domain.request import ContextRequest


def select(valid: Validated, request: ContextRequest, policy: ContextPolicy, groups: JsonObject) -> Selected:
    candidates = copy.deepcopy(objects(valid.get("included")))
    included: list[JsonValue] = []
    excluded: list[JsonValue] = list(objects(valid.get("excluded")))
    history = [c for c in candidates if c["block_type"] == "history"]
    keep_history = history[-policy.history_max_steps :] if policy.history_max_steps else []
    memory = [c for c in candidates if c["block_type"] == "memory"][: policy.memory_top_k]
    special = {"skills", "steering", "skill_index"}
    for candidate in candidates:
        kind = BlockType(str(candidate["block_type"]))
        if kind.value in special:
            continue
        mandatory = bool(candidate.get("mandatory"))
        reason: str | None = None
        if not mandatory and kind not in policy.include:
            reason = "type_not_in_policy"
        elif kind is BlockType.MATERIALS and not mandatory and not policy.include_optional_materials:
            reason = "optional_disabled"
        elif kind is BlockType.HISTORY and candidate not in keep_history:
            reason = "history_window"
        elif (kind is BlockType.MEMORY and candidate not in memory) or (
            kind is BlockType.REPO_INSTRUCTIONS and policy.repo_mode == "none"
        ):
            reason = "type_not_in_policy"
        if reason:
            excluded.append(_excluded(candidate, reason))
            continue
        if kind is BlockType.REPO_INSTRUCTIONS and policy.repo_mode == "constraints":
            candidate["content"] = extract_sections(str(candidate.get("content", "")), policy.repo_sections)
            if not candidate["content"]:
                excluded.append(_excluded(candidate, "no_matching_sections"))
                continue
        if kind is BlockType.MATERIALS:
            _select_material(candidate, mandatory)
        else:
            candidate["reason"] = (
                "mandatory"
                if mandatory
                else "recent_history"
                if kind is BlockType.HISTORY
                else "memory_match"
                if kind is BlockType.MEMORY
                else "execution_input"
            )
        included.append(candidate)
    steering = [c for c in candidates if c["block_type"] == "steering"]
    if BlockType.STEERING in policy.include:
        result = select_steering(steering, request, policy)
        included.extend(objects(result.get("included")))
        excluded.extend(objects(result.get("excluded")))
    else:
        excluded.extend(_excluded(c, "type_not_in_policy") for c in steering)
    skills = _select_skills(candidates, request, policy, groups)
    included.extend(objects(skills.get("included")))
    excluded.extend(objects(skills.get("excluded")))
    return preserve_groups(
        {
            "included": included,
            "conditional": skills.get("conditional", []),
            "excluded": excluded,
            "skills_trace": skills.get("trace", {}),
            "diagnostics": valid.get("diagnostics", []),
        },
        candidates,
    )


def _select_skills(
    candidates: list[Candidate], request: ContextRequest, policy: ContextPolicy, groups: JsonObject
) -> Selected:
    entries: dict[str, JsonObject] = {}
    by_key: dict[str, Candidate] = {}
    for candidate in candidates:
        if candidate["block_type"] == "skills":
            meta = metadata(candidate)
            key = str(meta.get("key", candidate["source_ref"]))
            by_key[key] = candidate
            entries[key] = {
                **meta,
                "key": key,
                "body_tokens": candidate.get("tokens_estimate", 0),
                "version_id": candidate.get("source_version"),
            }
    raw = select_skill_metadata(
        entries,
        SkillRequest(
            request.purpose.role,
            request.runtime.runtime_id,
            request.runtime.capabilities,
            request.runtime.tools,
            request.permissions.write_scope,
            tuple((key, None) for key in strings(groups.get("explicit_plan"))),
            policy.skills_include,
            policy.skills_exclude,
            policy.skills_mode if BlockType.SKILLS in policy.include else "none",
            policy.skills_budget,
            int(cast("int", groups.get("max_count", 8))),
        ),
        groups,
    )
    trace = raw.get("trace", {})
    reasons: JsonValue = trace.get("reasons", {}) if isinstance(trace, dict) else {}
    included: list[JsonValue] = []
    for key in strings(raw.get("included")):
        reason = reasons.get(key, "required") if isinstance(reasons, dict) else "required"
        included.append(
            {**by_key[key], "reason": reason, "mandatory": reason in ("explicit_plan", "explicit_profile")}
        )
    conditional: list[JsonValue] = [
        {**by_key[str(item["key"])], "deps": item["deps"], "reason": item["reason"]}
        for item in objects(raw.get("conditional"))
    ]
    excluded_map = raw.get("excluded", {})
    excluded = (
        [_excluded(by_key[k], str(v)) for k, v in excluded_map.items() if k in by_key]
        if isinstance(excluded_map, dict)
        else []
    )
    discoverable = strings(raw.get("discoverable"))
    if discoverable and BlockType.SKILL_INDEX in policy.include:
        included.append(
            {
                "block_type": "skill_index",
                "budget_class": "supporting",
                "mandatory": False,
                "source_kind": "core",
                "source_ref": "core:skill_index",
                "source_version": None,
                "trust": "system",
                "atomic_group": None,
                "reason": "discoverable_index",
                "content": "\n".join(discoverable),
            }
        )
    return {
        "included": included,
        "conditional": conditional,
        "excluded": list[JsonValue](excluded),
        "trace": trace,
    }


def _excluded(candidate: Candidate, reason: str) -> JsonObject:
    return {"block_type": candidate["block_type"], "source_ref": candidate["source_ref"], "reason": reason}


def extract_sections(text: str, headings: tuple[str, ...]) -> str:
    """Select complete Markdown sections, retaining nested headings and ordered procedures."""
    if headings == ("*",):
        return text
    selected: list[str] = []
    active_level: int | None = None
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        level = len(stripped) - len(stripped.lstrip("#"))
        if 1 <= level <= 6 and stripped[level : level + 1] == " ":
            if active_level is not None and level <= active_level:
                active_level = None
            if stripped[level:].strip().rstrip("#").strip().casefold() in {h.casefold() for h in headings}:
                active_level = level
        if active_level is not None:
            selected.append(line)
    return "".join(selected)


def _select_material(candidate: Candidate, required: bool) -> None:
    meta = metadata(candidate)
    media = str(meta.get("media_type", "text/plain"))
    if not media.startswith("text/") and media not in ("application/json", "application/toml"):
        file_id = str(candidate.get("source_version") or meta.get("file_version_id", ""))
        name = str(meta.get("filename", "material")).rsplit("/", 1)[-1]
        candidate["content"] = f"файл материализован в .skm/materials/{file_id}/{name}"
        candidate["reason"] = "binary_reference"
        return
    selector = meta.get("selector", {})
    if isinstance(selector, dict):
        text = str(candidate.get("content", ""))
        if selector.get("kind") == "markdown-heading":
            candidate["content"] = extract_sections(text, (str(selector.get("heading", "")),))
        elif selector.get("kind") == "line-range":
            start, end = int(cast("int", selector.get("start", 1))), int(cast("int", selector.get("end", 1)))
            candidate["content"] = "".join(text.splitlines(keepends=True)[max(0, start - 1) : max(0, end)])
    candidate["reason"] = (
        "external_reference"
        if meta.get("url_only")
        else "external_material"
        if str(candidate["source_ref"]).startswith("external:")
        else "required_material"
        if required
        else "optional_material"
    )
