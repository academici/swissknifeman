"""Read-only host layer reader for Codex ``doctor`` checks (integrations §5.6)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final, Literal, cast

from skm.kernel.errors import ValidationFailed
from skm.modules.integrations.domain.contracts import ClientLayer
from skm.modules.integrations.ports import CheckoutFs, UserHomeReader
from skm.platform.config.sources.document import decode_document

from .permissions import CODEX_MACHINE_LOCAL_KEYS

__all__ = [
    "CODEX_LAYER_SPECS",
    "effective_hooks_enabled",
    "project_machine_local_keys",
    "read_codex_layers",
]

type _HomeLogical = Literal["codex.user_config"]

CODEX_LAYER_SPECS: Final[tuple[tuple[str, str, str, str], ...]] = (
    ("user", "home", "codex.user_config", "~/.codex/config.toml"),
    ("project", "checkout", ".codex/config.toml", ".codex/config.toml"),
)


def _parse_layer_bytes(layer_id: str, display_path: str, raw: bytes | None) -> ClientLayer:
    if raw is None:
        return {
            "layer": layer_id,
            "path": display_path,
            "exists": False,
            "valid": True,
            "data": None,
            "error": None,
        }

    try:
        text = raw.decode("utf-8")
        parsed = decode_document(text, "toml")
    except (UnicodeDecodeError, ValueError, TypeError, ValidationFailed):
        return {
            "layer": layer_id,
            "path": display_path,
            "exists": True,
            "valid": False,
            "data": None,
            "error": "invalid_toml",
        }

    return {
        "layer": layer_id,
        "path": display_path,
        "exists": True,
        "valid": True,
        "data": parsed,
        "error": None,
    }


def read_codex_layers(fs: CheckoutFs, home: UserHomeReader) -> tuple[ClientLayer, ...]:
    """Read user (``~/.codex/config.toml``) and project (``.codex/config.toml``) layers without mutation."""
    layers: list[ClientLayer] = []
    for layer_id, origin, selector, display_path in CODEX_LAYER_SPECS:
        raw = home.read(cast("_HomeLogical", selector)) if origin == "home" else fs.read(selector)
        layers.append(_parse_layer_bytes(layer_id, display_path, raw))
    return tuple(layers)


def project_machine_local_keys(layers: Sequence[ClientLayer]) -> tuple[str, ...]:
    """Return machine-local keys set in the ``project`` Codex layer."""
    for layer in layers:
        if layer.get("layer") == "project" and layer.get("valid") is True:
            data = layer.get("data")
            if isinstance(data, Mapping):
                return tuple(key for key in CODEX_MACHINE_LOCAL_KEYS if key in data)
    return ()


def effective_hooks_enabled(layers: Sequence[ClientLayer]) -> bool | None:
    """Resolve effective ``features.hooks`` across ``user`` -> ``project`` layers."""
    result: bool | None = None
    for layer in layers:
        if layer.get("valid") is not True:
            continue
        data = layer.get("data")
        if not isinstance(data, Mapping):
            continue
        features = data.get("features")
        if isinstance(features, Mapping):
            hooks_flag = cast("Mapping[str, object]", features).get("hooks")
            if isinstance(hooks_flag, bool):
                result = hooks_flag
    return result
