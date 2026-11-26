"""Capture whole selected texts with exact digests and a deterministic token estimate."""

from __future__ import annotations

import math
from collections.abc import Mapping
from hashlib import sha256
from typing import TYPE_CHECKING

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed
from skm.modules.context.domain.blocks import BlockType
from skm.modules.context.domain.candidates import objects
from skm.modules.context.domain.render import render_block_text

if TYPE_CHECKING:
    from skm.kernel.tokens import TokenEstimator
    from skm.modules.context.domain.contracts import Selected, SnapshotBlock


def estimate_text(text: str) -> int:
    """heuristic-v1: 2.9 Cyrillic / 3.4 other characters per token, as on the host."""
    cyr = sum(1 for ch in text if "\u0400" <= ch <= "\u052f")
    return math.ceil(cyr / 2.9 + (len(text) - cyr) / 3.4)


def snapshot(
    selected: Selected, texts: Mapping[str, str], *, estimator: TokenEstimator | None = None
) -> tuple[SnapshotBlock, ...]:
    result: list[SnapshotBlock] = []
    for candidate in objects(selected.get("included")) + objects(selected.get("conditional")):
        ref = str(candidate["source_ref"])
        content = candidate.get("content")
        if not isinstance(content, str):
            content = texts.get(str(candidate.get("payload_ref", ref)))
        if content is None:
            raise PreconditionFailed(ErrorCode.CONTEXT_MATERIAL_UNAVAILABLE, "selected text unavailable")
        rendered = render_block_text(
            block_type=BlockType(str(candidate["block_type"])),
            title=str(candidate.get("title", "")),
            content=content,
            source_ref=ref,
            templates={},
            prompt_plan={},
            variables={},
        )
        result.append(
            {
                **candidate,
                "content": content,
                "content_digest": f"sha256:{sha256(content.encode('utf-8')).hexdigest()}",
                "tokens_estimate": estimator.estimate(rendered) if estimator else estimate_text(rendered),
            }
        )
    return tuple(result)
