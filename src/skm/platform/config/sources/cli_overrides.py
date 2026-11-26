"""Invocation sources in env → files → ordered --set order (settings §B.11.2)."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.outcomes import Diagnostic
from skm.platform.config.keys import Level
from skm.platform.config.layers import Contribution, Layer, LayerRef
from skm.platform.config.registry import SettingsRegistry
from skm.platform.config.sources.document import parse_document
from skm.platform.config.sources.env import env_layers
from skm.platform.config.sources.text_values import parse_text_value

__all__ = ["InvocationOverrides", "cli_layers", "invocation_layers"]


@dataclass(frozen=True, slots=True)
class InvocationOverrides:
    config_files: tuple[Path, ...] = ()
    sets: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "config_files", tuple(Path(path) for path in self.config_files))
        object.__setattr__(self, "sets", tuple(self.sets))


def cli_layers(registry: SettingsRegistry, overrides: InvocationOverrides) -> tuple[Layer, ...]:
    layers: list[Layer] = []
    for path in overrides.config_files:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            raise ValidationFailed(
                ErrorCode.CONFIG_INVALID, "Cannot read invocation file", details={"source": str(path)}
            ) from None
        document = parse_document(text, "json" if path.suffix.lower() == ".json" else "toml", registry)
        if document.problems:
            problem = document.problems[0]
            raise ValidationFailed(
                ErrorCode(problem.code),
                problem.message,
                details={"key": problem.key, "reason": problem.reason},
            )
        if document.locks:
            raise ValidationFailed(
                ErrorCode.CONFIG_INVALID,
                "Invocation files cannot lock keys",
                details={"reason": "invocation_lock"},
            )
        ref = LayerRef(Level.INVOCATION, label=f"--config {path}", source=f"config-file:{path}")
        layers.append(
            Layer(
                ref,
                {key: Contribution(ref, entry.op, entry.value) for key, entry in document.entries.items()},
            )
        )
    for assignment in overrides.sets:
        key, separator, text = assignment.partition("=")
        append = key.endswith("+")
        key = key.removesuffix("+") if append else key
        if not separator or not key:
            raise ValidationFailed(
                ErrorCode.CONFIG_INVALID, "Expected KEY=VALUE or KEY+=VALUE", details={"reason": "set_syntax"}
            )
        spec = registry.spec(key)
        ref = LayerRef(Level.INVOCATION, label="--set", source="cli")
        layers.append(
            Layer(ref, {key: Contribution(ref, "append" if append else "set", parse_text_value(spec, text))})
        )
    return tuple(layers)


def invocation_layers(
    registry: SettingsRegistry,
    environ: Mapping[str, str],
    overrides: InvocationOverrides | None = None,
    *,
    warn: Callable[[Diagnostic], None] | None = None,
) -> tuple[Layer, ...]:
    return (
        *env_layers(registry, environ, warn=warn),
        *cli_layers(registry, overrides or InvocationOverrides()),
    )
