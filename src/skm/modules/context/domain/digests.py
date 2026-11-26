"""Wire-compatible context digests shared by host/server assembly."""

from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256
from typing import TYPE_CHECKING

from skm.modules.context.domain.blocks import LADDER_ORDER, ROUND_TYPES, canonical_json_digest

if TYPE_CHECKING:
    from skm.modules.context.domain.manifest import ManifestBlock


def task_digest(blocks: Sequence[ManifestBlock]) -> str:
    ordered = sorted(blocks, key=lambda b: (LADDER_ORDER[b.block_type], b.source_ref, b.block_ref))
    return canonical_json_digest(
        [
            [b.block_type.value, b.source_ref, b.content_digest]
            for b in ordered
            if (b.included is True or b.reason == "in_resumed_session") and b.block_type not in ROUND_TYPES
        ]
    )


def prompt_digest(text: str) -> str:
    return f"sha256:{sha256(text.encode('utf-8')).hexdigest()}"
