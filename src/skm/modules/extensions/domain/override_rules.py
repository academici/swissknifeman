"""Resource override rules across packs and trust tiers (extensions §4.13)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict
from skm.modules.extensions.domain.pack import TRUST_RANK, PackManifest, PackTrust

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable

    from skm.modules.extensions.domain.keys import ResourceKey
    from skm.modules.extensions.domain.kinds import ResourceKind

__all__ = ["TRUST_RANK", "OverrideDecision", "can_override"]


@dataclass(frozen=True, slots=True)
class OverrideDecision:
    allowed: bool
    overrides: bool
    kind: ResourceKind | None = None
    key: ResourceKey = ""
    owner_trust: PackTrust | None = None
    reason: str | None = None


def can_override(
    new: PackManifest | PackTrust,
    existing_owner_trust: PackTrust,
    declared: Collection[tuple[ResourceKind, ResourceKey]] | None = None,
    *,
    kind: ResourceKind | None = None,
    key: ResourceKey = "",
    same_pack: bool = False,
    holder_trusts: Iterable[PackTrust] = (),
) -> OverrideDecision:
    """Validate whether ``new`` may provide ``(kind, key)`` owned by ``existing_owner_trust`` (§4.13)."""
    strongest = max((existing_owner_trust, *holder_trusts), key=TRUST_RANK.__getitem__)
    if same_pack:
        return OverrideDecision(
            allowed=True,
            overrides=False,
            kind=kind,
            key=key,
            owner_trust=strongest,
            reason="same_pack",
        )

    new_trust = new.trust if isinstance(new, PackManifest) else new
    effective_declared: frozenset[tuple[ResourceKind, ResourceKey]]
    if declared is not None:
        effective_declared = frozenset(declared)
    elif isinstance(new, PackManifest):
        effective_declared = frozenset((item.kind, item.key) for item in new.overrides)
    else:
        effective_declared = frozenset()

    is_declared = (kind, key) in effective_declared if kind is not None and key else bool(effective_declared)
    rank_ok = TRUST_RANK[new_trust] >= TRUST_RANK[strongest]

    if not is_declared or not rank_ok:
        kind_val = kind.value if kind is not None else ""
        raise Conflict(
            ErrorCode.EXTENSION_OVERRIDE_NOT_DECLARED,
            f"{kind_val}:{key} belongs to another pack",
            details={
                "kind": kind_val,
                "key": key,
                "owner_trust": strongest.value,
            },
        )

    return OverrideDecision(
        allowed=True,
        overrides=True,
        kind=kind,
        key=key,
        owner_trust=strongest,
        reason="declared_override",
    )
