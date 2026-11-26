"""Platform settings sections and their pure callbacks (settings §B.8.3).

Bootstrap combines these mappings with module-owned settings declarations. This
module imports no modules and does not duplicate bootstrap credentials or pool
capacity validation.
"""

from collections.abc import Mapping
from typing import cast

from skm.kernel.json_types import JsonValue
from skm.platform.config.generated.settings import (
    ApiSettings,
    BackgroundSettings,
    EcosystemsSettings,
    EventsSettings,
    LoggingSettings,
    ModulesSettings,
    PluginsSettings,
    StorageSettings,
    UiSettings,
)
from skm.platform.config.registry import SectionValidatorFn

__all__ = ["SECTION_URNS", "VALIDATORS", "VIEWS"]

VIEWS: Mapping[str, type] = {
    "modules": ModulesSettings,
    "plugins": PluginsSettings,
    "logging": LoggingSettings,
    "storage": StorageSettings,
    "events": EventsSettings,
    "background": BackgroundSettings,
    "api": ApiSettings,
    "ui": UiSettings,
    "ecosystems": EcosystemsSettings,
}
SECTION_URNS = tuple(f"urn:skm:settings:{section}:v1" for section in VIEWS)


def _subsets(values: Mapping[str, JsonValue]) -> str | None:
    """required ⊆ allowed and control_plane_allowed ⊆ allowed."""
    allowed = values["plugins.allowed"]
    if allowed is None:
        return None
    allowed_ids = set(cast("list[str]", allowed))
    for key in ("plugins.required", "plugins.control_plane_allowed"):
        subset = values[key]
        if subset is not None and not set(cast("list[str]", subset)) <= allowed_ids:
            return f"{key} must be a subset of plugins.allowed"
    return None


VALIDATORS: Mapping[str, SectionValidatorFn] = {"plugins.subsets": _subsets}
