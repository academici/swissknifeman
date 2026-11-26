"""Skill ``requires`` dependency BFS resolution and diagnostic aggregation (extensions §4.11)."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from typing import Literal

    from skm.modules.extensions.domain.keys import ResourceKey

__all__ = ["RequiresDiagnostic", "RequiresNode", "resolve_requires"]


@dataclass(frozen=True, slots=True)
class RequiresNode:
    key: ResourceKey
    requires: tuple[ResourceKey, ...]
    exclude_tokens: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class RequiresDiagnostic:
    code: Literal["SKILL_REQUIRED_UNKNOWN", "SKILL_REQUIRED_EXCLUDED"]
    required: ResourceKey
    requesters: tuple[ResourceKey, ...]


def resolve_requires(
    seed: Sequence[tuple[ResourceKey, ResourceKey]],
    lookup: Callable[[ResourceKey], RequiresNode | None],
    selected: frozenset[ResourceKey] = frozenset(),
    exclude: frozenset[str] = frozenset(),
    *,
    already_selected: frozenset[ResourceKey] | None = None,
    exclude_tokens: frozenset[str] | None = None,
) -> tuple[
    tuple[tuple[RequiresNode, ResourceKey], ...],
    frozenset[ResourceKey],
    tuple[RequiresDiagnostic, ...],
]:
    """Resolve transitive skill dependencies in BFS order, aggregating unknown/excluded diagnostics."""
    effective_selected = already_selected if already_selected is not None else selected
    effective_exclude = exclude_tokens if exclude_tokens is not None else exclude
    queue: deque[tuple[ResourceKey, ResourceKey]] = deque(seed)
    seen_selected: set[ResourceKey] = set(effective_selected)
    resolved: list[tuple[RequiresNode, ResourceKey]] = []
    diag_requesters: dict[
        tuple[Literal["SKILL_REQUIRED_UNKNOWN", "SKILL_REQUIRED_EXCLUDED"], ResourceKey],
        set[ResourceKey],
    ] = {}

    while queue:
        dep, requester = queue.popleft()
        if dep in seen_selected:
            continue
        node = lookup(dep)
        if node is None:
            diag_requesters.setdefault(("SKILL_REQUIRED_UNKNOWN", dep), set()).add(requester)
            continue
        if node.exclude_tokens & effective_exclude:
            diag_requesters.setdefault(("SKILL_REQUIRED_EXCLUDED", dep), set()).add(requester)
            continue
        seen_selected.add(node.key)
        resolved.append((node, requester))
        for child in node.requires:
            if child not in seen_selected:
                queue.append((child, node.key))

    diagnostics = tuple(
        RequiresDiagnostic(code=code, required=req, requesters=tuple(sorted(requesters)))
        for (code, req), requesters in sorted(diag_requesters.items())
    )
    return tuple(resolved), frozenset(seen_selected), diagnostics
