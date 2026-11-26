"""Environment invocation layers. Protected contributions remain visible to fold/explain."""

import logging
from collections.abc import Callable, Mapping
from threading import Lock

from skm.kernel.outcomes import Diagnostic, Severity
from skm.platform.config.keys import Level
from skm.platform.config.layers import Contribution, Layer, LayerRef
from skm.platform.config.registry import SettingsRegistry
from skm.platform.config.sources.text_values import parse_text_value

__all__ = ["env_layers"]

_WARNED: set[str] = set()
_WARN_LOCK = Lock()


def env_layers(
    registry: SettingsRegistry,
    environ: Mapping[str, str],
    *,
    warn: Callable[[Diagnostic], None] | None = None,
) -> tuple[Layer, ...]:
    layers: list[Layer] = []
    for name in sorted(environ):
        if not name.startswith("SKM__"):
            continue
        key = name.removeprefix("SKM__").replace("__", ".").lower()
        spec = registry.find(key)
        if spec is None:
            with _WARN_LOCK:
                first = name not in _WARNED
                _WARNED.add(name)
            if first:
                diagnostic = Diagnostic(
                    "CONFIG_UNKNOWN_KEY",
                    "Unknown invocation environment key",
                    Severity.WARNING,
                    target=key,
                    details={"variable": name},
                )
                if warn is not None:
                    warn(diagnostic)
                else:
                    logging.getLogger(__name__).warning("%s: %s", diagnostic.code, name)
            continue
        ref = LayerRef(Level.INVOCATION, label=f"env:{name}", source="env")
        layers.append(Layer(ref, {key: Contribution(ref, "set", parse_text_value(spec, environ[name]))}))
    return tuple(layers)
