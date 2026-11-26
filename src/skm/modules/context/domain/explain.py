"""Data rows for the canonical explain table and occurrence-aware manifest diffs."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.context.domain.reasons import HIDDEN_REASONS

if TYPE_CHECKING:
    from collections.abc import Sequence

    from skm.modules.context.domain.manifest import ContextManifest, ManifestBlock


def _visible(block: ManifestBlock) -> bool:
    # Never print inaccessible identities or reveal their number through placeholders.
    return block.reason not in HIDDEN_REASONS


def explain_rows(manifest: ContextManifest) -> tuple[JsonObject, ...]:
    return tuple(
        {
            "pos": b.position,
            "block_type": b.block_type.value,
            "source": b.source_ref,
            "tokens": b.tokens_estimate,
            "digest": (b.content_digest or "").removeprefix("sha256:")[:12],
            "trust": b.trust.value,
            "reason": b.reason,
            "included": b.included,
            "selector": b.source_ref.partition("#")[2] or None,
            "detail": b.detail if b.detail == "conflict_group_incomplete" else None,
        }
        for b in sorted(manifest.blocks, key=lambda b: (b.position is None, b.position or 0, b.ordinal))
        if _visible(b)
    )


def _index(blocks: Sequence[ManifestBlock]) -> dict[tuple[str, str, int], ManifestBlock]:
    result: dict[tuple[str, str, int], ManifestBlock] = {}
    occurrences: dict[tuple[str, str], int] = defaultdict(int)
    for block in sorted(blocks, key=lambda b: b.ordinal):
        if not _visible(block) or block.included is False:
            continue
        key = (block.block_type.value, block.source_ref)
        number = occurrences[key]
        occurrences[key] += 1
        result[(*key, number)] = block
    return result


def diff_manifests(base: ContextManifest, target: ContextManifest) -> JsonObject:
    before, after = _index(base.blocks), _index(target.blocks)
    rows: list[JsonValue] = []
    for key in sorted(before.keys() | after.keys()):
        left, right = before.get(key), after.get(key)
        status = (
            "added"
            if left is None
            else "removed"
            if right is None
            else "same"
            if left.content_digest == right.content_digest
            else "changed"
        )
        rows.append(
            {
                "block_type": key[0],
                "source": key[1],
                "occurrence": key[2],
                "status": status,
                "base_tokens": left.tokens_estimate if left else None,
                "target_tokens": right.tokens_estimate if right else None,
            }
        )
    # Totals are derived only from visible rows, never from potentially hidden manifest aggregates.
    base_tokens = sum(b.tokens_estimate or 0 for b in before.values() if b.included)
    target_tokens = sum(b.tokens_estimate or 0 for b in after.values() if b.included)
    return {
        "blocks": rows,
        "tokens": {"base": base_tokens, "target": target_tokens, "delta": target_tokens - base_tokens},
        "budgets": {
            cls.value: {"base": usage.limit, "target": target.budgets[cls].limit}
            for cls, usage in base.budgets.items()
            if cls in target.budgets
        },
    }
