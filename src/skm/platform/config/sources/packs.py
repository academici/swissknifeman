"""Active pack fragments in deterministic priority/id order (settings §B.4)."""

import logging
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from skm.kernel.json_types import JsonValue
from skm.kernel.outcomes import Diagnostic, Severity
from skm.platform.config.keys import Chain, Level, MergeStrategy, freeze_json
from skm.platform.config.layers import Contribution, Layer, LayerRef
from skm.platform.config.registry import SettingsRegistry

__all__ = ["PackFragment", "pack_layers"]


@dataclass(frozen=True, slots=True)
class PackFragment:
    pack_id: str
    priority: int
    values: Mapping[str, JsonValue]
    unset: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "values", MappingProxyType({k: freeze_json(v, k) for k, v in self.values.items()})
        )
        object.__setattr__(self, "unset", frozenset(self.unset))


def pack_layers(
    source: Iterable[PackFragment],
    registry: SettingsRegistry,
    chain: Chain,
    *,
    warn: Callable[[Diagnostic], None] | None = None,
) -> tuple[Layer, ...]:
    """The pack source supplies active fragments and their effective (settings or manifest) priority."""
    layers: list[Layer] = []
    seen: set[str] = set()
    for fragment in sorted(source, key=lambda item: (item.priority, item.pack_id)):
        if fragment.pack_id in seen:
            raise ValueError("a pack must supply a single fragment per chain")
        seen.add(fragment.pack_id)
        ref = LayerRef(Level.PACK, pack_id=fragment.pack_id, pack_priority=fragment.priority)
        contributions: dict[str, Contribution] = {}
        for key in sorted(fragment.values.keys() | fragment.unset):
            code = _rejection(fragment, registry, key, chain)
            if code == "other_chain":
                continue
            if code is not None:
                diagnostic = Diagnostic(
                    code,
                    "Pack contribution ignored",
                    Severity.WARNING,
                    target=key,
                    details={"pack_id": fragment.pack_id},
                )
                if warn is not None:
                    warn(diagnostic)
                else:
                    logging.getLogger(__name__).warning("%s: %s (%s)", code, key, fragment.pack_id)
                continue
            op = "unset" if key in fragment.unset else "set"
            contributions[key] = Contribution(ref, op, None if op == "unset" else fragment.values[key])
        layers.append(Layer(ref, contributions))
    return tuple(layers)


def _rejection(fragment: PackFragment, registry: SettingsRegistry, key: str, chain: Chain) -> str | None:
    spec = registry.find(key)
    if spec is None:
        return "CONFIG_UNKNOWN_KEY"
    if spec.chain is not chain:
        return "other_chain"
    if not spec.pack:
        return "CONFIG_PACK_NOT_ALLOWED"
    if key in fragment.unset:
        return "CONFIG_INVALID" if key in fragment.values or spec.monotonic else None
    value = fragment.values[key]
    if spec.merge is MergeStrategy.DEEP_MERGE and isinstance(value, dict):
        # Required members may be inherited. Validate the original keys too: removing tombstones
        # before validation would hide forbidden property names and unknown properties.
        markers = _markers(value)
        issues = registry.value_issues(key, value)
        invalid = any(
            issue.code != "required"
            and not any(issue.pointer == path or issue.pointer.startswith(path + "/") for path in markers)
            for issue in issues
        )
        return "CONFIG_INVALID" if invalid else None
    return "CONFIG_INVALID" if registry.value_issues(key, value) else None


def _markers(value: JsonValue, prefix: str = "") -> tuple[str, ...]:
    if isinstance(value, dict) and set(value) == {"$unset"} and value["$unset"] is True:
        return (prefix,)
    if not isinstance(value, dict):
        return ()
    return tuple(
        path
        for name, child in value.items()
        for path in _markers(child, prefix + "/" + name.replace("~", "~0").replace("/", "~1"))
    )
