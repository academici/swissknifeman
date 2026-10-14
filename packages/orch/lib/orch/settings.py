"""Layered ``[orch]`` configuration and the choice of the execution engine (docs/configuration.md).

``load`` resolves the section through ``aicore.config`` (defaults -> machine file -> project file -> environment ->
``--config`` file -> flags); orch never reads ``config.toml`` itself. ``affecting`` and ``digest`` name the values
that change what preparation produces, so a launch-plan can record the configuration it was built from.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import os
from pathlib import Path
import tempfile

from aicore.config import ResolvedConfig, resolve
from aicore.config.units import foundation_root
from aicore.util import digest as _digest

from orch.port import BINDINGS

ORCH_ROOT = Path(__file__).resolve().parents[2]
ENGINE_REASONS = {
    "flag": "ENGINE_FROM_FLAG",
    "role": "ENGINE_FROM_ROLE",
    "config": "ENGINE_FROM_CONFIG",
}


class SettingsError(ValueError):
    """``ENGINE_UNKNOWN``: a requested engine is not one of the bindings; ``PROFILES_DIR_RELATIVE``: a relative pack folder."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Settings:
    """The effective ``[orch]`` configuration. ``profiles_dirs`` are absolute paths with ``~`` expanded."""

    engine: str
    engine_by_role: Mapping[str, str]
    default_profile: str
    work_source: str
    capabilities_stale: str
    profiles_dirs: tuple
    events_enabled: bool
    resolved: ResolvedConfig | None = None
    conductor: Mapping[str, object] = field(default_factory=dict)
    aicore: ResolvedConfig | None = None  # the ``aicore`` module: ``providers.available`` is read from it (routing)

    def explain_text(self, key: str | None = None) -> str:
        """Where each value comes from (empty when the settings were built by hand)."""
        return "" if self.resolved is None else self.resolved.explain_text(key)


def _dirs(resolved: ResolvedConfig) -> tuple:
    """``profiles.dirs`` as absolute paths. ``~`` is expanded; a relative entry is refused (``PROFILES_DIR_RELATIVE``),
    because the folder of the file that wrote it cannot be told once a higher layer appends to the array."""
    found = []
    for text in resolved.get("profiles.dirs"):
        path = Path(os.path.expanduser(text))
        if not path.is_absolute():
            raise SettingsError("PROFILES_DIR_RELATIVE", f"profiles.dirs entry {text!r} must be absolute or start with ~")
        found.append(path)
    return tuple(found)


def _conductor(resolved: ResolvedConfig) -> dict:
    """``[orch.conductor]`` as plain data: the global layer of the run options and the role command lines."""
    return {
        "provider": resolved.get("conductor.provider"),
        "reviewer": resolved.get("conductor.reviewer"),
        "registrar": resolved.get("conductor.registrar"),
        "rules": list(resolved.get("conductor.rules") or []),
        "on_blocked": resolved.get("conductor.on_blocked"),
        "questions": resolved.get("conductor.questions"),
        "limits": {key: resolved.get(f"conductor.limits.{key}")
                   for key in ("tokens_max", "stage_timeout_s", "stage_idle_timeout_s", "check_timeout_s")},
        "argv": {role: list(argv) for role, argv in (resolved.get("conductor.argv") or {}).items()},
    }


def load(*, project: str | Path | None = None, config_file: str | Path | None = None,
         env: Mapping[str, str] | None = None, home: str | Path | None = None,
         flags: Mapping[str, object] | None = None) -> Settings:
    """Resolve ``[orch]`` for a project (``None``: no project layer). Raises ``aicore.config.ConfigError``."""
    resolved = resolve("orch", unit_root=ORCH_ROOT, project=project, config_file=config_file, env=env, home=home,
                       flags=flags)
    foundation = resolve("aicore", schema=foundation_root() / "configs" / "config.schema.json", project=project,
                         config_file=config_file, env=env, home=home)
    return Settings(
        engine=resolved.get("engine"),
        engine_by_role=dict(resolved.get("engine_by_role") or {}),
        default_profile=resolved.get("default_profile"),
        work_source=resolved.get("work_source"),
        capabilities_stale=resolved.get("capabilities.stale"),
        profiles_dirs=_dirs(resolved),
        events_enabled=resolved.get("events.enabled"),
        resolved=resolved,
        conductor=_conductor(resolved),
        aicore=foundation,
    )


def defaults() -> Settings:
    """The settings of the schema defaults alone: no machine, project or environment layer is read."""
    with tempfile.TemporaryDirectory(prefix="orch-defaults-") as home:
        return load(project=None, env={}, home=home)


def affecting(settings: Settings) -> dict:
    """The values that change what preparation produces (the other keys do not enter the digest)."""
    return {
        "engine": settings.engine,
        "engine_by_role": dict(sorted(settings.engine_by_role.items())),
        "default_profile": settings.default_profile,
        "capabilities.stale": settings.capabilities_stale,
    }


def digest(settings: Settings) -> str:
    """SHA-256 hex of the canonical JSON of :func:`affecting`."""
    return _digest.sha256_hex(_digest.canonical_json_bytes(affecting(settings)))


def config_digest(settings: Settings) -> str:
    """Tagged digest of the effective ``[orch]`` and ``[aicore.providers]`` (``None`` for a part that was not resolved):
    two runs with the same digest ran under the same configuration."""
    providers = settings.aicore.get("providers") if settings.aicore is not None else None
    return _digest.digest_json({"orch": settings.resolved.as_dict() if settings.resolved is not None else None,
                                "aicore.providers": providers})


def config_layers(settings: Settings) -> list:
    """The configuration layers behind the digest: ``[{layer, file, present}]``, lowest first."""
    if settings.resolved is None:
        return []
    return [{"layer": layer.name, "file": layer.file, "present": layer.present} for layer in settings.resolved.layers]


def select_engine(settings: Settings, role: str, *, flag: str | None = None, stage_id: str = "*") -> tuple:
    """``(binding, decision)``: the flag, else ``engine_by_role[role]``, else ``engine``.

    ``decision`` is an element of ``launch-plan.decisions`` of kind ``binding``; the sources that were overridden
    are listed after the chosen one. No other engine is ever substituted: whether the chosen engine can honour a
    stage is decided by preparation, which refuses when it cannot.
    """
    sources = []
    if flag is not None:
        sources.append(("flag", flag))
    if role in settings.engine_by_role:
        sources.append(("role", settings.engine_by_role[role]))
    sources.append(("config", settings.engine))
    for _, name in sources:
        if name not in BINDINGS:
            raise SettingsError("ENGINE_UNKNOWN", f"unknown engine {name!r}; one of {', '.join(BINDINGS)}")
    (first, chosen), rest = sources[0], sources[1:]
    considered = [{"candidate": chosen, "accepted": True, "reason_codes": [ENGINE_REASONS[first]]}]
    considered += [{"candidate": name, "accepted": False, "reason_codes": ["ENGINE_OVERRIDDEN"]}
                   for _, name in rest if name != chosen]
    return chosen, {"stage_id": stage_id, "kind": "binding", "chosen": chosen, "considered": considered}
