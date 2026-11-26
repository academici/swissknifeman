"""Compile rendered manifest blocks into a stable prompt prefix and a dynamic tail."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.json_types import JsonObject
from skm.modules.context.domain.blocks import BlockType
from skm.modules.context.domain.digests import prompt_digest
from skm.modules.context.domain.manifest import ManifestState

if TYPE_CHECKING:
    from collections.abc import Mapping

    from skm.modules.context.domain.manifest import ContextManifest
    from skm.modules.context.domain.request import RuntimeTarget

_PREFIX_LAYERS: Final = (
    BlockType.SYSTEM_CONSTRAINTS,
    BlockType.ROLE_CONTRACT,
    BlockType.RUN_RULES,
    BlockType.RUNTIME_NOTES,
    BlockType.TASK_CONTRACT,
    BlockType.ACCEPTANCE,
)
_LAYER_INDEX: Final = {kind: index for index, kind in enumerate(_PREFIX_LAYERS)}
_COMPACTION_PERCENT: Final = 65


@dataclass(frozen=True, slots=True)
class PrefixStablePrompt:
    prefix: str
    tail: str
    prefix_digest: str
    cache_parameters: JsonObject
    should_compact: bool

    @property
    def prompt(self) -> str:
        separator = "\n" if self.prefix and self.tail else ""
        return self.prefix + separator + self.tail


@dataclass(frozen=True, slots=True)
class PrefixStablePromptCompiler:
    """Use target capabilities named ``cache_control``, ``prompt_cache_key`` and ``compaction``."""

    target: RuntimeTarget
    min_cacheable_tokens: int = 0

    def compile(
        self,
        manifest: ContextManifest,
        rendered_blocks: Mapping[str, str],
        *,
        context_tokens: int | None = None,
    ) -> PrefixStablePrompt:
        """Use block refs to look up rendered text. Draft output previews unconditional blocks.

        Cache control marks the end of the prefix. The cache key is request-level. Pass the
        occupied context size for a resumed session. Otherwise use the final input estimate, if available.
        """
        if manifest.state is ManifestState.DRAFT:
            rows = sorted(
                (b for b in manifest.blocks if b.block_ref.startswith("d:") and b.included is not False),
                key=lambda b: b.ordinal,
            )
        else:
            rows = sorted(
                (b for b in manifest.blocks if b.included is True),
                key=lambda b: b.position if b.position is not None else b.ordinal,
            )

        layers: list[list[str]] = [[] for _ in _PREFIX_LAYERS]
        tail: list[str] = []
        prefix_tokens = 0
        for row in rows:
            try:
                body = rendered_blocks[row.block_ref].rstrip("\n")
            except KeyError:
                raise ValidationFailed(
                    ErrorCode.CONTEXT_MANIFEST_TAMPERED,
                    "missing rendered text for manifest block",
                    details={"block_ref": row.block_ref},
                ) from None
            if not body:
                continue
            layer = _LAYER_INDEX.get(row.block_type)
            if layer is None:
                tail.append(body)
            else:
                layers[layer].append(body)
                if row.tokens_estimate is not None:
                    prefix_tokens += row.tokens_estimate

        prefix = _join([text for layer in layers for text in layer])
        digest = prompt_digest(prefix)
        capabilities = self.target.capabilities - self.target.degraded
        cache_parameters: JsonObject = {}
        if prefix and prefix_tokens >= self.min_cacheable_tokens:
            if "cache_control" in capabilities:
                cache_parameters["cache_control"] = {"type": "ephemeral"}
            if "prompt_cache_key" in capabilities:
                cache_parameters["prompt_cache_key"] = digest.removeprefix("sha256:")
        used_tokens = manifest.total_tokens_estimate if context_tokens is None else context_tokens
        window = self.target.context_window_tokens
        should_compact = (
            "compaction" in capabilities
            and used_tokens is not None
            and window > 0
            and used_tokens * 100 >= window * _COMPACTION_PERCENT
        )
        return PrefixStablePrompt(prefix, _join(tail), digest, cache_parameters, should_compact)


def _join(blocks: list[str]) -> str:
    return "\n\n".join(blocks) + "\n" if blocks else ""
