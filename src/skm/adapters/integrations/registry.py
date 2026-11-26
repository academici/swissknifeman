"""Static registry of implemented ``IntegrationTarget`` gateways (integrations §6)."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound
from skm.modules.integrations.domain.target import TargetId
from skm.modules.integrations.ports import IntegrationTarget

from .antigravity.target import AntigravityTarget
from .claude_code.target import ClaudeCodeTarget
from .codex.target import CodexTarget
from .cursor.target import CursorTarget
from .gemini_cli.target import GeminiCliTarget
from .grok.target import GrokTarget

__all__ = [
    "TARGETS",
    "StaticIntegrationTargetRegistry",
    "default_target_registry",
]

TARGETS: Mapping[str, IntegrationTarget] = MappingProxyType(
    {
        TargetId.ANTIGRAVITY.value: AntigravityTarget(),
        TargetId.CLAUDE_CODE.value: ClaudeCodeTarget(),
        TargetId.CODEX.value: CodexTarget(),
        TargetId.CURSOR.value: CursorTarget(),
        TargetId.GEMINI_CLI.value: GeminiCliTarget(),
        TargetId.GROK.value: GrokTarget(),
    }
)


class StaticIntegrationTargetRegistry:
    """In-process ``IntegrationTargetRegistry`` backed by registered target adapters."""

    __slots__ = ("_by_id",)

    def __init__(self, targets: Mapping[str, IntegrationTarget] | None = None) -> None:
        source = TARGETS if targets is None else targets
        self._by_id: dict[TargetId, IntegrationTarget] = {
            TargetId(key): target for key, target in source.items()
        }

    def get(self, target: TargetId) -> IntegrationTarget:
        resolved = self._by_id.get(TargetId(target))
        if resolved is None:
            raise NotFound(
                ErrorCode.NOT_FOUND,
                f"integration target {target!r} is not registered",
                details={"target": str(target)},
            )
        return resolved

    def all(self) -> tuple[IntegrationTarget, ...]:
        return tuple(self._by_id[key] for key in sorted(self._by_id, key=lambda item: item.value))


def default_target_registry() -> StaticIntegrationTargetRegistry:
    """Return a ``StaticIntegrationTargetRegistry`` populated with ``TARGETS``."""
    return StaticIntegrationTargetRegistry(TARGETS)
