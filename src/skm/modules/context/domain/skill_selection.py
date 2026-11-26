"""Deterministic selection of already resolved/pinned skills (context §5.3; no IO)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from skm.kernel.ids import ResourceVersionId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.context.domain.blocks import TrustLevel
from skm.modules.context.domain.candidates import path_matches, strings
from skm.modules.context.domain.policy import SkillsMode
from skm.modules.context.domain.reasons import ExcludeReason, IncludeReason
from skm.modules.context.domain.request import ROLE_NAMES
from skm.modules.extensions.public import SkillManifest, VersionConstraint

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(frozen=True, slots=True)
class SkillEntry:
    key: str
    version_id: ResourceVersionId
    manifest: SkillManifest
    body_tokens: int
    trust: TrustLevel
    quarantined: bool = False


@dataclass(frozen=True, slots=True)
class SkillRequest:
    role: str
    runtime_id: str
    capabilities: frozenset[str]
    tools: frozenset[str]
    path_patterns: tuple[str, ...]
    explicit_plan: tuple[tuple[str, VersionConstraint | None], ...]
    explicit_profile: tuple[str, ...]
    exclude: frozenset[str]
    mode: SkillsMode
    budget: int
    max_count: int = 8
    skills_by_role: Mapping[str, Sequence[str]] = field(default_factory=dict[str, Sequence[str]])
    final_correction: bool = False


def select_skills(entries: Sequence[SkillEntry], request: SkillRequest, groups: JsonObject) -> JsonObject:
    """The caller obtains entries through extensions.public.list_resolved(..., pins=...).

    Domain selection never re-resolves a version against mutable installed-pack state.
    Role, adapter, quarantine and request exclusion checks apply to explicit skills.
    """
    manifests: dict[str, JsonObject] = {}
    constraints = dict(request.explicit_plan)
    for entry in entries:
        m = entry.manifest
        constraint = constraints.get(entry.key)
        manifests[entry.key] = {
            "version_matches": constraint is None or constraint.matches(m.version),
            "key": entry.key,
            "version": str(m.version),
            "version_id": str(entry.version_id),
            "kind": m.kind.value,
            "roles": list[JsonValue](m.roles),
            "requires": list[JsonValue](m.requires),
            "requires_tools": list[JsonValue](m.requires_tools),
            "adapters": list[JsonValue](m.adapters),
            "replaced_by": m.replaced_by,
            "exclusive_group": m.exclusive_group,
            "paths": list[JsonValue](m.triggers.paths),
            "deps": list[JsonValue](m.triggers.deps),
            "body_tokens": entry.body_tokens,
            "quarantined": entry.quarantined,
        }
    return select_skill_metadata(manifests, request, groups)


def _role_allows(meta: JsonObject, role: str) -> bool:
    return role in ROLE_NAMES and role in strings(meta.get("roles"))


def skill_filter_reason(meta: JsonObject, request: SkillRequest, *, explicit: bool) -> ExcludeReason | None:
    """First failing filter wins; callers suppress quarantine identities entirely."""
    key = str(meta["key"])
    if meta.get("quarantined", False):
        return ExcludeReason.QUARANTINED
    if key in request.exclude:
        return ExcludeReason.EXCLUDED
    if not _role_allows(meta, request.role):
        return ExcludeReason.ROLE_NOT_ALLOWED
    if not explicit and not set(strings(meta.get("requires_tools"))) <= request.tools:
        return ExcludeReason.TOOL_MISSING
    if not explicit and meta.get("kind", "domain") in ("router", "reference", "persona"):
        return ExcludeReason.KIND_NOT_PRELOADED
    if not explicit and meta.get("replaced_by") in (
        request.role,
        f"{request.role}/role",
        "role_contract",
        f"orch/roles/{request.role}.md",
    ):
        return ExcludeReason.DUPLICATED_BY_ROLE_CONTRACT
    adapters = strings(meta.get("adapters"))
    if adapters and request.runtime_id not in adapters:
        return ExcludeReason.ADAPTER_NOT_SUPPORTED
    return None


def _explicit_seeds(
    entries: Mapping[str, JsonObject], request: SkillRequest
) -> tuple[dict[str, str], dict[str, str]]:
    reasons: dict[str, str] = {}
    excluded: dict[str, str] = {}
    for key, constraint in request.explicit_plan:
        if key not in entries:
            excluded[key] = ExcludeReason.UNKNOWN_SKILL.value
        elif constraint is not None and not entries[key].get("version_matches", False):
            excluded[key] = ExcludeReason.VERSION_UNAVAILABLE.value
        else:
            reasons[key] = IncludeReason.EXPLICIT_PLAN.value
    role_skills = request.skills_by_role.get(request.role, ()) if request.role in ROLE_NAMES else ()
    for keys, reason in (
        (role_skills, IncludeReason.EXPLICIT_PLAN),
        (request.explicit_profile, IncludeReason.EXPLICIT_PROFILE),
    ):
        for key in keys:
            if key not in entries:
                excluded[key] = ExcludeReason.UNKNOWN_SKILL.value
            elif key not in excluded:
                reasons.setdefault(key, reason.value)
    return reasons, excluded


def _seeds(
    entries: Mapping[str, JsonObject], request: SkillRequest
) -> tuple[dict[str, str], dict[str, tuple[str, ...]], dict[str, str]]:
    reasons, excluded = _explicit_seeds(entries, request)
    conditions: dict[str, tuple[str, ...]] = {}
    if request.mode == "auto":
        for key, meta in sorted(entries.items()):
            if key in reasons or key in excluded:
                continue
            if any(path_matches(t, p) for t in strings(meta.get("paths")) for p in request.path_patterns):
                reasons[key] = IncludeReason.TRIGGER_PATH.value
            elif strings(meta.get("deps")):
                reasons[key] = IncludeReason.TRIGGER_DEP.value
                conditions[key] = strings(meta["deps"])
            else:
                excluded[key] = ExcludeReason.TRIGGER_NOT_MET.value
    if request.mode != "auto":
        excluded.update(dict.fromkeys(entries.keys() - reasons.keys() - excluded.keys(), "excluded"))
    return reasons, conditions, excluded


def _requires(
    entries: Mapping[str, JsonObject],
    role: str,
    reasons: dict[str, str],
    conditions: dict[str, tuple[str, ...]],
    excluded: dict[str, str],
) -> list[JsonValue]:
    """BFS closure, matching extensions requires semantics through facade-owned metadata.

    extensions.domain.requires is intentionally not imported across the module boundary.
    Conditions propagate per root; a later unconditional path promotes a conditional dependency.
    """
    diagnostics: list[JsonValue] = []
    pending = list(reasons)
    processed: set[tuple[str, tuple[str, ...]]] = set()
    while pending:
        parent = pending.pop(0)
        meta = entries[parent]
        if meta.get("quarantined", False) or not _role_allows(meta, role):
            continue
        deps = conditions.get(parent, ())
        if (parent, deps) in processed:
            continue
        processed.add((parent, deps))
        for key in strings(meta.get("requires")):
            if key not in entries:
                diagnostic: JsonValue = {"code": "SKILL_REQUIRED_UNKNOWN"}
                if diagnostic not in diagnostics:
                    diagnostics.append(diagnostic)
                continue
            if key in reasons and key not in conditions:
                continue
            reasons.setdefault(key, IncludeReason.REQUIRED.value)
            excluded.pop(key, None)
            if deps:
                conditions[key] = tuple(sorted(set(conditions.get(key, ())) | set(deps)))
            else:
                conditions.pop(key, None)
            pending.append(key)
    return diagnostics


def select_skill_metadata(
    entries: Mapping[str, JsonObject], request: SkillRequest, groups: JsonObject
) -> JsonObject:
    """Shared selection for typed SkillEntry and validated Candidate manifest metadata."""
    # Quarantined resource identifiers are not part of outward traces or counts.
    visible = {key: meta for key, meta in entries.items() if not meta.get("quarantined", False)}
    if request.mode == "none":
        return {
            "included": [],
            "conditional": [],
            "excluded": dict.fromkeys(visible, "skills_disabled"),
            "discoverable": [],
            "tokens": 0,
            "trace": {
                "mode": "none",
                "final_correction": request.final_correction,
                "skills_remaining": request.budget,
            },
        }
    reasons, conditions, excluded = _seeds(entries, request)
    diagnostics = _requires(entries, request.role, reasons, conditions, excluded)
    accepted: list[JsonValue] = []
    conditional: list[JsonValue] = []
    discoverable: list[JsonValue] = []
    used = count = 0
    group_counts: dict[str, int] = {}
    order = sorted(
        reasons,
        key=lambda k: (
            k in conditions,
            reasons[k] not in ("explicit_plan", "explicit_profile"),
            list(reasons).index(k),
        ),
    )
    for key in order:
        meta, reason = entries[key], reasons[key]
        explicit = reason in ("explicit_plan", "explicit_profile")
        failure = skill_filter_reason(meta, request, explicit=explicit)
        group = str(meta.get("exclusive_group") or "")
        group_spec = groups.get(group, {})
        maximum = int(cast("int", group_spec.get("max", 1))) if isinstance(group_spec, dict) else 1
        tokens = int(cast("int", meta.get("body_tokens", 0)))
        if failure is None and not explicit and group and group_counts.get(group, 0) >= maximum:
            failure = ExcludeReason.EXCLUSIVE_GROUP
        if failure is None and not explicit and key not in conditions:
            if used + tokens > request.budget:
                failure = ExcludeReason.OVER_SKILL_BUDGET
            elif count >= request.max_count:
                failure = ExcludeReason.OVER_SKILL_COUNT
        if failure is not None:
            excluded[key] = failure.value
            if failure is ExcludeReason.KIND_NOT_PRELOADED:
                discoverable.append(key)
            continue
        if group:
            group_counts[group] = group_counts.get(group, 0) + 1
        if key in conditions:
            conditional.append({"key": key, "deps": list[JsonValue](conditions[key]), "reason": reason})
        else:
            accepted.append(key)
            if not explicit:
                used += tokens
                count += 1
    excluded = {k: v for k, v in excluded.items() if k not in entries or k in visible}
    visible_reasons = {k: reasons[k] for k in reasons if k in visible and k not in excluded}
    return {
        "included": accepted,
        "conditional": conditional,
        "excluded": dict[str, JsonValue](excluded),
        "discoverable": discoverable,
        "tokens": used,
        "trace": {
            "mode": request.mode,
            "final_correction": request.final_correction,
            "reasons": dict[str, JsonValue](visible_reasons),
            "diagnostics": diagnostics,
            "skills_budget": request.budget,
            "skills_remaining": max(0, request.budget - used),
            "count_remaining": max(0, request.max_count - count),
            "versions": {k: visible[k].get("version_id") for k in visible_reasons},
        },
    }
