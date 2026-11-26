"""Discover wire declarations without importing handler manifests (DAG-02)."""

from collections.abc import Iterable
from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from skm.entrypoints.api.routing import Route

    ROUTES: tuple[Route, ...]

__all__ = ["MODULE_IDS", "ROUTES", "SURFACE_IDS", "discover_routes"]

MODULE_IDS = (
    "access",
    "settings",
    "workspace",
    "artifacts",
    "policy",
    "extensions",
    "runtimes",
    "planning",
    "context",
    "execution",
    "integrations",
    "knowledge",
    "learning",
    "exports",
)
SURFACE_IDS = ("worker", "platform")


def discover_routes(enabled_module_ids: Iterable[str]) -> tuple["Route", ...]:
    enabled = frozenset(enabled_module_ids)
    if unknown := enabled - set(MODULE_IDS):
        raise ValueError(f"Unknown module IDs: {sorted(unknown)}")
    surfaces = tuple(
        surface
        for surface, required in (
            ("worker", {"settings", "workspace", "execution", "context"}),
            ("platform", {"access", "settings", "workspace"}),
        )
        if required <= enabled
    )
    routes: list[Route] = []
    for module_id in (*[name for name in MODULE_IDS if name in enabled], *surfaces):
        name = f"{__name__}.{module_id}"
        try:
            module = import_module(name)
        except ModuleNotFoundError as error:
            if error.name != name:
                raise
            continue
        routes.extend(module.ROUTES)
    return tuple(routes)


def __getattr__(name: str) -> tuple["Route", ...]:
    """Compatibility view of all available declarations, computed only when requested."""
    if name == "ROUTES":
        return discover_routes(MODULE_IDS)
    raise AttributeError(name)
