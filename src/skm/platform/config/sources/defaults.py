"""Schema-owned defaults, restricted to one chain (settings §B.4)."""

from typing import cast

from skm.kernel.json_types import JsonValue
from skm.platform.config.keys import MISSING, Chain, Level
from skm.platform.config.layers import Contribution, Layer, LayerRef
from skm.platform.config.registry import SettingsRegistry

__all__ = ["defaults_layer"]


def defaults_layer(registry: SettingsRegistry, chain: Chain) -> Layer:
    ref = LayerRef(Level.DEFAULT)
    return Layer(
        ref,
        {
            spec.key: Contribution(ref, "default", cast("JsonValue", spec.default))
            for spec in registry.keys(chain=chain)
            if spec.default is not MISSING
        },
    )
