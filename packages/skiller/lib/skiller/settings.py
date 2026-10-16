"""skiller settings: the ``[skiller]`` and ``[skiller.sync]`` configuration and the legacy files it still honours.

Values come from ``aicore.config`` (schema ``configs/config.schema.json``: defaults, project file,
environment, ``--config``). Two legacy files fill the same sections when the project file leaves a
section unset: ``<project>/.swissknife.json`` (selection keys, :data:`SKILLER_KEYS`) and
``<project>/.swissknifeman/config.json`` (vendor mode, :data:`SYNC_KEYS`). A legacy file is read as one
section: as soon as ``.swissknifeman/config.toml`` sets any key of a section, the legacy file is ignored
for that section (never merged key by key), and a warning says so. Keys of ``.swissknife.json`` that belong
to other modules (``providers``, ``memory_brain``, ``policy_profile``) are not read here.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Tuple, Union

from aicore.config import ConfigError, ExtraLayer, ResolvedConfig, edit_layer_file, resolve
from aicore.state import project_config_file
from aicore.util.term import die

UNIT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = UNIT_ROOT / "configs" / "config.schema.json"
LEGACY_SELECTION_FILE = ".swissknife.json"
LEGACY_SYNC_FILE = ".swissknifeman/config.json"
PROJECT_FILE = ".swissknifeman/config.toml"

# Keys of .swissknife.json that belong to skiller, and keys of .swissknifeman/config.json (vendor mode).
SKILLER_KEYS = ("project_type", "buckets", "plugins", "exclude", "presets", "agent", "skills_path")
SYNC_KEYS = ("agent", "skills_path", "presets", "include", "buckets", "exclude", "gitignore_managed")

LEGACY_CONFIG = "SKILLER_LEGACY_CONFIG"
LEGACY_IGNORED = "SKILLER_LEGACY_IGNORED"

PathLike = Union[str, "os.PathLike[str]"]
_EMITTED: set = set()


@dataclass(frozen=True)
class SkillerSettings:
    """The effective ``[skiller]`` section of one project.

    ``values`` is the whole section as a nested dict (``values["sync"]`` is ``[skiller.sync]``); a key that no
    layer set holds the default of the schema. ``explicit`` / ``sync_explicit`` name the keys some layer set.
    ``source`` and ``sync_source`` say where the selection keys and the vendor keys come from: ``"config"``
    (``config.toml``, environment, ``--config``), ``"legacy"`` (a legacy file) or ``"none"``.
    """

    values: Mapping[str, Any]
    sync_configured: bool
    source: str
    sync_source: str
    explicit: FrozenSet[str] = frozenset()
    sync_explicit: FrozenSet[str] = frozenset()
    warnings: Tuple[str, ...] = ()
    legacy: Optional[Mapping[str, Any]] = field(default=None, repr=False)
    legacy_sync: Optional[Mapping[str, Any]] = field(default=None, repr=False)

    def selection(self) -> Dict[str, Any]:
        """The explicitly set selection keys (what ``.swissknife.json`` held before)."""
        return {key: self.values[key] for key in SKILLER_KEYS if key in self.explicit}

    def sync(self) -> Dict[str, Any]:
        """The explicitly set keys of ``[skiller.sync]``."""
        section = self.values["sync"]
        return {key: section[key] for key in SYNC_KEYS if key in self.sync_explicit}


def warning(code: str, message: str) -> str:
    return f"{code}: {message}"


def _emit(message: str, file: Path) -> None:
    """Print a warning to stderr once per process and file."""
    mark = (message, str(file))
    if mark not in _EMITTED:
        _EMITTED.add(mark)
        print(f"WARN: {message}", file=sys.stderr)


def _read_json(path: Path, strict: bool) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        if strict:
            die(f"{path}: invalid JSON: {exc}")
        return None
    if not isinstance(data, dict):
        if strict:
            die(f"{path}: root should be JSON-object")
        return None
    return data


def _profile_names(env: Any) -> List[str]:
    return sorted(p.stem for p in (env.root / "profiles").glob("*.json"))


def _set_in_project(config: ResolvedConfig, key: str) -> bool:
    """Whether ``.swissknifeman/config.toml`` gave a value to ``key`` (even if a higher layer overrides it)."""
    entry = config.explain(key)[0]
    return entry.layer == "project" or any(item.layer == "project" for item in entry.overridden)


def _explicit(config: ResolvedConfig, keys: Tuple[str, ...], prefix: str = "") -> FrozenSet[str]:
    return frozenset(key for key in keys if config.explain(prefix + key)[0].layer != "defaults")


def _check_final_values(env: Any, config: ResolvedConfig) -> None:
    """``project_type`` and ``agent`` must name a profile and a delivery agent whatever layer set them."""
    from aicore.delivery.materialize import AGENT_DEFAULTS
    for key, valid, label in (("project_type", _profile_names(env), "project_type"),
                              ("agent", list(AGENT_DEFAULTS), "agent")):
        entry = config.explain(key)[0]
        value = entry.value
        if not value or entry.layer.startswith("legacy-") or value in valid:
            continue
        where = entry.file or entry.layer
        if entry.line:
            where = f"{where}:{entry.line}"
        die(f"{where}: unknown {label} '{value}' (available: {', '.join(valid)})")


def load(target: PathLike, *, env: Any = None, strict: bool = True) -> SkillerSettings:
    """Resolve the skiller settings of the project at ``target``.

    ``env`` is the skiller :class:`~skiller.common.Env` (its ``root`` holds the profiles, its ``home`` the
    machine file); without it the module's own root and the process home are used. An invalid
    configuration layer raises :class:`aicore.config.ConfigError`. With ``strict`` an invalid legacy file
    ends the process with the message it always had; without it a legacy file that cannot be read is
    ignored, and no check or warning is printed (for readers that only look for a path).
    """
    from .skillset import validate_skillset_config
    from .config import validate_config
    target = Path(target)
    if env is None:
        from .common import Env
        env = Env(UNIT_ROOT)
    home = env.home

    def resolve_with(extra: Tuple[ExtraLayer, ...]) -> ResolvedConfig:
        return resolve("skiller", unit_root=UNIT_ROOT, project=target, extra_layers=extra, home=home,
                       warn=lambda message: None)

    legacy_file, sync_file = target / LEGACY_SELECTION_FILE, target / LEGACY_SYNC_FILE
    legacy = _read_json(legacy_file, strict)
    if legacy is not None and strict:
        validate_config(env, legacy, legacy_file)
    legacy_sync = _read_json(sync_file, strict)
    if legacy_sync is not None and strict:
        validate_skillset_config(legacy_sync, sync_file)

    base = config = resolve_with(())
    warnings: List[str] = []
    extra: List[ExtraLayer] = []

    legacy_keys = [key for key in SKILLER_KEYS if legacy is not None and key in legacy]
    toml_top = any(_set_in_project(base, key) for key in SKILLER_KEYS)
    legacy_used = False
    if legacy_keys:
        if toml_top:
            warnings.append(warning(LEGACY_IGNORED, f"{LEGACY_SELECTION_FILE} keys {', '.join(legacy_keys)} are "
                                    f"ignored because [skiller] is set in {PROJECT_FILE}"))
        else:
            legacy_used = True
            extra.append(ExtraLayer("legacy-swissknife", {key: legacy[key] for key in legacy_keys},
                                    file=LEGACY_SELECTION_FILE))
            warnings.append(warning(LEGACY_CONFIG, f"{LEGACY_SELECTION_FILE} is deprecated for skiller "
                                    f"settings; move them to [skiller] in {PROJECT_FILE}"))

    sync_keys = [key for key in SYNC_KEYS if legacy_sync is not None and key in legacy_sync]
    toml_sync = any(_set_in_project(base, "sync." + key) for key in SYNC_KEYS)
    legacy_sync_used = False
    if legacy_sync is not None:
        if toml_sync:
            if sync_keys:
                warnings.append(warning(LEGACY_IGNORED, f"{LEGACY_SYNC_FILE} keys {', '.join(sync_keys)} are "
                                        f"ignored because [skiller.sync] is set in {PROJECT_FILE}"))
        else:
            legacy_sync_used = True
            if sync_keys:
                extra.append(ExtraLayer("legacy-skillset", {"sync": {key: legacy_sync[key] for key in sync_keys}},
                                        file=LEGACY_SYNC_FILE))
            warnings.append(warning(LEGACY_CONFIG, f"{LEGACY_SYNC_FILE} is deprecated; move its settings to "
                                    f"[skiller.sync] in {PROJECT_FILE}"))
    if extra:
        config = resolve_with(tuple(extra))
    if strict:
        _check_final_values(env, config)
        for message in warnings:
            _emit(message, sync_file if LEGACY_SYNC_FILE in message else legacy_file)

    explicit = _explicit(config, SKILLER_KEYS)
    sync_explicit = _explicit(config, SYNC_KEYS, "sync.")
    if toml_top:
        source = "config"
    elif legacy_used:
        source = "legacy"
    else:
        source = "config" if explicit else "none"
    if toml_sync:
        sync_source = "config"
    elif legacy_sync_used:
        sync_source = "legacy"
    else:
        sync_source = "config" if sync_explicit else "none"
    return SkillerSettings(
        values=config.as_dict(), sync_configured=sync_source != "none", source=source, sync_source=sync_source,
        explicit=explicit, sync_explicit=sync_explicit, warnings=tuple(warnings),
        legacy=legacy, legacy_sync=legacy_sync if legacy_sync_used else None)


def configured_skills_paths(target: PathLike, *, env: Any = None) -> List[str]:
    """The ``skills_path`` values a project configures (vendor mode first, then the selection key); never fails."""
    try:
        values = load(target, env=env, strict=False).values
    except (ConfigError, OSError, ValueError):
        return []
    paths = [values["sync"]["skills_path"], values["skills_path"]]
    return [path for path in dict.fromkeys(paths) if path]


def write_key(target: PathLike, key: Union[str, Tuple[str, ...]], value: Any) -> Optional[Path]:
    """Set one key of ``[skiller]`` in ``<project>/.swissknifeman/config.toml`` and return its backup (or None).

    The edit keeps comments, backs the old file up through ``aicore.state`` and replaces it atomically; a
    missing file is created with ``schema_version``.
    """
    result = edit_layer_file(project_config_file(target), "skiller", key, value, schema=SCHEMA_PATH,
                             layer="project", project=target)
    return result.backup
