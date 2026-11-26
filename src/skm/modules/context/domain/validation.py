"""Validate whole candidates and closed conflict groups before exposing source identities."""

from __future__ import annotations

import copy
from collections.abc import Sequence
from typing import TYPE_CHECKING

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, PreconditionFailed
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.context.domain.blocks import ALWAYS_MANDATORY_TYPES, BlockType, canonical_json_digest
from skm.modules.context.domain.candidates import metadata, objects, strings
from skm.modules.context.domain.reasons import HIDDEN_REASONS, ExcludeReason
from skm.modules.context.domain.snapshot import estimate_text

if TYPE_CHECKING:
    from skm.modules.context.domain.contracts import Candidate, Validated
    from skm.modules.context.domain.policy import ContextPolicy

_CLASSIFICATIONS = ("public", "internal", "confidential", "restricted")


def exclusion_reason(candidate: Candidate, policy: ContextPolicy) -> ExcludeReason | None:
    """All checks inspect server metadata, never instructions embedded in source text."""
    meta = metadata(candidate)
    if meta.get("authorized", True) is not True:
        return ExcludeReason.CLASSIFICATION_FORBIDDEN
    classifications = (
        str(meta.get("classification", "public")),
        *strings(meta.get("source_classifications")),
    )
    if any(
        c not in _CLASSIFICATIONS
        or _CLASSIFICATIONS.index(c) > _CLASSIFICATIONS.index(policy.max_classification)
        for c in classifications
    ):
        return ExcludeReason.CLASSIFICATION_FORBIDDEN
    if meta.get("quarantined", False):
        return ExcludeReason.QUARANTINED
    if candidate.get("trust") == "third_party" and not policy.allow_third_party:
        return ExcludeReason.TRUST_FORBIDDEN
    if not meta.get("version_available", True):
        return ExcludeReason.VERSION_UNAVAILABLE
    if not meta.get("ready", True):
        return ExcludeReason.FILE_VERSION_NOT_READY
    if meta.get("missing", False):
        return ExcludeReason.NOT_FOUND
    return _content_reason(candidate, policy)


def _content_reason(candidate: Candidate, policy: ContextPolicy) -> ExcludeReason | None:
    meta = metadata(candidate)
    content = candidate.get("content", "")
    if not isinstance(content, str) or not meta.get("encoding_valid", True):
        return ExcludeReason.ENCODING_INVALID
    try:
        content.encode("utf-8")
    except UnicodeEncodeError:
        return ExcludeReason.ENCODING_INVALID
    estimate = candidate.get("tokens_estimate", estimate_text(content))
    if not isinstance(estimate, int) or isinstance(estimate, bool) or estimate < 0:
        return ExcludeReason.ENCODING_INVALID
    if estimate > policy.block_max_tokens:
        return ExcludeReason.TOO_LARGE
    return None


def safe_exclusion(candidate: Candidate, reason: ExcludeReason, *, group: bool = False) -> JsonObject | None:
    if reason in HIDDEN_REASONS:
        return None
    return {
        "block_type": candidate["block_type"],
        "source_ref": candidate["source_ref"],
        "reason": reason.value,
        "detail": "conflict_group_incomplete" if group else None,
    }


def validate(candidates: Sequence[Candidate], policy: ContextPolicy) -> Validated:
    """Close server atomic/conflict links, validate each member, and suppress inaccessible metadata."""
    pool = [copy.deepcopy(c) for c in candidates]
    for candidate in pool:
        content = candidate.get("content")
        if isinstance(content, str):
            candidate.setdefault("tokens_estimate", estimate_text(content))
    by_ref = {str(c["source_ref"]): c for c in pool}
    links: dict[str, set[str]] = {ref: set() for ref in by_ref}
    groups: dict[str, list[str]] = {}
    for ref, candidate in by_ref.items():
        if candidate.get("atomic_group"):
            groups.setdefault(str(candidate["atomic_group"]), []).append(ref)
        for other in strings(metadata(candidate).get("conflict_refs")):
            links[ref].add(other)
            links.setdefault(other, set()).add(ref)
    for members in groups.values():
        for ref in members:
            links[ref].update(members)
    included: list[JsonValue] = []
    excluded: list[JsonValue] = []
    visited: set[str] = set()
    for ref in by_ref:
        if ref in visited:
            continue
        closure = _closure(ref, links)
        visited.update(closure)
        members = [by_ref[r] for r in sorted(closure) if r in by_ref]
        is_group = len(closure) > 1 or bool(members[0].get("atomic_group"))
        reasons = {str(c["source_ref"]): exclusion_reason(c, policy) for c in members}
        failure = (
            ExcludeReason.NOT_FOUND
            if closure - by_ref.keys()
            else next((r for r in reasons.values() if r is not None), None)
        )
        if failure is None:
            if is_group:
                existing = {str(c["atomic_group"]) for c in members if c.get("atomic_group")}
                group_id = (
                    next(iter(existing)) if len(existing) == 1 else canonical_json_digest(sorted(closure))
                )
                for candidate in members:
                    candidate["atomic_group"] = group_id
            included.extend(members)
            continue
        if any(c.get("mandatory") for c in members):
            _mandatory_failure(members, failure, is_group)
        excluded.extend(_excluded_members(members, reasons, failure, is_group))
    included = list[JsonValue](_preserve_classification(c) for c in objects(included))
    present = {BlockType(str(c["block_type"])) for c in pool}
    if ALWAYS_MANDATORY_TYPES - present:
        raise NotFound(ErrorCode.NOT_FOUND, "required core prompt blocks are missing")
    return {"included": included, "excluded": excluded, "diagnostics": []}


def _mandatory_failure(members: list[Candidate], reason: ExcludeReason, group: bool) -> None:
    if group:
        raise PreconditionFailed(
            ErrorCode.CONTEXT_CONFLICT,
            "mandatory conflict group is unavailable",
            details={"reason": "conflict_group_incomplete"},
        )
    if (
        members[0]["block_type"] in (BlockType.ROLE_CONTRACT, BlockType.RESULT_CONTRACT)
        and reason is ExcludeReason.NOT_FOUND
    ):
        raise NotFound(ErrorCode.NOT_FOUND, "required prompt block is missing")
    if reason is ExcludeReason.TOO_LARGE and members[0]["block_type"] != BlockType.MATERIALS:
        raise PreconditionFailed(
            ErrorCode.CONTEXT_OVER_BUDGET,
            "mandatory context block exceeds block_max_tokens",
            details={"reason": reason.value},
        )
    raise PreconditionFailed(
        ErrorCode.CONTEXT_MATERIAL_UNAVAILABLE,
        "mandatory context material unavailable",
        details={"reason": reason.value},
    )


def _excluded_members(
    members: list[Candidate], reasons: dict[str, ExcludeReason | None], failure: ExcludeReason, group: bool
) -> list[JsonValue]:
    result: list[JsonValue] = []
    for candidate in members:
        if reasons[str(candidate["source_ref"])] in HIDDEN_REASONS:
            continue
        row = safe_exclusion(candidate, failure, group=group)
        if row is not None:
            result.append(row)
        elif group:
            result.append(
                {
                    "block_type": candidate["block_type"],
                    "source_ref": candidate["source_ref"],
                    "reason": failure.value,
                    "detail": "conflict_group_incomplete",
                }
            )
    return result


def preserve_groups(selected: Validated, candidates: Sequence[Candidate]) -> Validated:
    """Role/window filters cannot silently retain part of an atomic group."""
    included = objects(selected.get("included"))
    conditional = objects(selected.get("conditional"))
    accepted = {str(c["source_ref"]) for c in included + conditional}
    rejected = {
        str(c["atomic_group"])
        for c in candidates
        if c.get("atomic_group") and str(c["source_ref"]) not in accepted
    }
    excluded: list[JsonValue] = list(objects(selected.get("excluded")))
    for candidate in included + conditional:
        if candidate.get("atomic_group") in rejected:
            if candidate.get("mandatory"):
                raise PreconditionFailed(ErrorCode.CONTEXT_CONFLICT, "mandatory atomic group is incomplete")
            excluded.append(
                {
                    "block_type": candidate["block_type"],
                    "source_ref": candidate["source_ref"],
                    "reason": "conflict_lower_priority",
                    "detail": "conflict_group_incomplete",
                }
            )
    return {
        **selected,
        "included": [c for c in included if c.get("atomic_group") not in rejected],
        "conditional": [c for c in conditional if c.get("atomic_group") not in rejected],
        "excluded": excluded,
    }


def _closure(ref: str, links: dict[str, set[str]]) -> set[str]:
    closure, pending = set[str](), [ref]
    while pending:
        current = pending.pop()
        if current not in closure:
            closure.add(current)
            pending.extend(links.get(current, set()) - closure)
    return closure


def _preserve_classification(candidate: Candidate) -> Candidate:
    meta = metadata(candidate)
    classifications = (
        str(meta.get("classification", "public")),
        *strings(meta.get("source_classifications")),
    )
    candidate["metadata"] = {**meta, "classification": max(classifications, key=_CLASSIFICATIONS.index)}
    return candidate
