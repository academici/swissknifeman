"""Composition root: the only place that chooses implementations (mechanisms/01, kernel-platform §5)."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from skm.bootstrap._knowledge_wiring import current_checkout_revision as current_checkout_revision

__all__ = ["current_checkout_revision"]


def __getattr__(name: str) -> object:
    if name == "current_checkout_revision":
        from skm.bootstrap._knowledge_wiring import current_checkout_revision

        return current_checkout_revision
    raise AttributeError(name)
