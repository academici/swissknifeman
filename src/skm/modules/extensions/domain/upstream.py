"""Pure comparison of recorded provenance digests with fetched upstream bytes (extensions §9).

Tracks upstream drift across ``replace``, ``notify``, ``fork`` and ``merge`` strategies without mutating local
pack state or auto-applying remote changes. Unreachable upstream files are always reported as ``unreachable``,
never silently treated as ``up_to_date``.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, cast

from skm.modules.extensions.domain.provenance import (
    Provenance,
    ProvenanceSource,
    parse_provenance,
)

if TYPE_CHECKING:
    from skm.kernel.json_types import JsonObject
    from skm.modules.extensions.domain.kinds import ResourceKind

__all__ = [
    "UpstreamFileResult",
    "UpstreamItem",
    "UpstreamStatus",
    "compare_upstream",
]

type UpstreamStatus = Literal["up_to_date", "changed", "unreachable", "local"]


def _normalize_hex(digest: str) -> str:
    return digest.removeprefix("sha256:").lower()


def _format_sha256(content: bytes, reference: str) -> str:
    raw_hex = hashlib.sha256(content).hexdigest()
    if reference.startswith("sha256:"):
        return f"sha256:{raw_hex}"
    return raw_hex


def _coerce_provenance(provenance: Provenance | Mapping[str, object] | None) -> Provenance:
    if isinstance(provenance, Provenance):
        return provenance
    if not provenance:
        return Provenance(source=ProvenanceSource.LOCAL)
    nested = provenance.get("provenance")
    if isinstance(nested, Mapping):
        return parse_provenance(cast("Mapping[str, object]", nested))
    if "source" in provenance or "files" in provenance or "strategy" in provenance:
        return parse_provenance(provenance)
    return Provenance(source=ProvenanceSource.LOCAL)


@dataclass(frozen=True, slots=True)
class UpstreamFileResult:
    """Comparison result for a single tracked file in a resource's provenance."""

    path: str
    recorded_sha256: str
    upstream_sha256: str | None

    def to_json(self) -> JsonObject:
        return {
            "path": self.path,
            "recorded_sha256": self.recorded_sha256,
            "upstream_sha256": self.upstream_sha256,
        }


@dataclass(frozen=True, slots=True)
class UpstreamItem:
    """Upstream comparison outcome for one extension resource."""

    kind: ResourceKind
    key: str
    strategy: str | None
    status: UpstreamStatus
    files: tuple[UpstreamFileResult, ...] = ()

    def to_json(self) -> JsonObject:
        return {
            "kind": self.kind.value,
            "key": self.key,
            "strategy": self.strategy,
            "status": self.status,
            "files": [item.to_json() for item in self.files],
        }


def compare_upstream(
    kind: ResourceKind,
    key: str,
    provenance: Provenance | Mapping[str, object] | None,
    fetched: Mapping[str, bytes | None] | None = None,
    *,
    local_files: Mapping[str, bytes] | None = None,
) -> UpstreamItem:
    """Compare recorded provenance digests (and optional local file bytes) with fetched upstream bytes.

    Pure domain function: performs no IO and never mutates local resource state regardless of strategy
    (``replace``, ``notify``, ``fork``, ``merge``).
    """
    prov = _coerce_provenance(provenance)
    strategy = prov.strategy.value if prov.strategy is not None else None
    if prov.source is ProvenanceSource.LOCAL:
        return UpstreamItem(
            kind=kind,
            key=key,
            strategy=strategy,
            status="local",
            files=(),
        )

    fetched_map = fetched or {}
    file_results: list[UpstreamFileResult] = []
    any_unreachable = False
    any_changed = False

    for tracked in prov.files:
        if tracked.path in fetched_map:
            content = fetched_map[tracked.path]
        elif tracked.url and tracked.url in fetched_map:
            content = fetched_map[tracked.url]
        else:
            content = None

        if content is None:
            any_unreachable = True
            file_results.append(
                UpstreamFileResult(
                    path=tracked.path,
                    recorded_sha256=tracked.sha256,
                    upstream_sha256=None,
                )
            )
            continue

        upstream_sha = _format_sha256(content, tracked.sha256)
        recorded_norm = _normalize_hex(tracked.sha256)
        upstream_norm = _normalize_hex(upstream_sha)
        if upstream_norm != recorded_norm:
            any_changed = True
        elif local_files is not None and tracked.path in local_files:
            local_norm = hashlib.sha256(local_files[tracked.path]).hexdigest()
            if local_norm != upstream_norm:
                any_changed = True

        file_results.append(
            UpstreamFileResult(
                path=tracked.path,
                recorded_sha256=tracked.sha256,
                upstream_sha256=upstream_sha,
            )
        )

    status: UpstreamStatus
    if any_unreachable or not prov.files:
        status = "unreachable"
    elif any_changed:
        status = "changed"
    else:
        status = "up_to_date"

    return UpstreamItem(
        kind=kind,
        key=key,
        strategy=strategy,
        status=status,
        files=tuple(file_results),
    )
