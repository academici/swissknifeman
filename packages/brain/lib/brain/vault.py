"""Vault lookup: the ladder that finds the Obsidian vault of this machine."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

from . import errors, settings as _settings
from .errors import BrainError

ENV_VAULT = "MAIND_BRAIN_VAULT"
DEFAULT_CANDIDATE = ("Vaults", "Brain")
SET_HINT = "aicore config set brain.vault_path <dir> --machine"


@dataclass(frozen=True)
class VaultInfo:
    """Where the vault is. ``source``: config, legacy-project, env-legacy, default or none."""

    path: Optional[Path]
    source: str
    exists: bool
    obsidian: bool
    warnings: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {"path": None if self.path is None else str(self.path), "source": self.source,
                "exists": self.exists, "obsidian": self.obsidian, "warnings": list(self.warnings)}


def _info(path: Path, source: str, warnings: Tuple[str, ...]) -> VaultInfo:
    exists = path.is_dir()
    return VaultInfo(path, source, exists, exists and (path / ".obsidian").is_dir(), warnings)


def resolve_vault(config: _settings.BrainSettings, *, env: Optional[Mapping[str, str]] = None,
                  home: Optional[Any] = None) -> VaultInfo:
    """Walk the ladder: configuration, legacy project block, ``MAIND_BRAIN_VAULT``, ``~/Vaults/Brain``.

    A path named by a rung that is set but absent on disk stops the walk (``exists`` False): it is never
    replaced by a lower rung. The default candidate counts only with an ``.obsidian`` folder, so the
    lookup cannot stumble on an arbitrary directory.
    """
    environment = os.environ if env is None else env
    home_path = _settings.home_dir(environment, home)

    if config.vault_path:
        path = Path(os.path.abspath(_settings.expand(config.vault_path, home_path)))
        return _info(path, config.vault_source, (() if config.vault_source == "config" else (_settings.LEGACY_VAULT_WARNING,)))
    value = environment.get(ENV_VAULT, "").strip()
    if value:
        path = Path(os.path.abspath(_settings.expand(value, home_path)))
        warning = _settings.warning(errors.BRAIN_LEGACY_ENV,
                                    f"{ENV_VAULT} is deprecated; set brain.vault_path in the machine configuration")
        return _info(path, "env-legacy", (warning,))
    candidate = home_path.joinpath(*DEFAULT_CANDIDATE)
    if (candidate / ".obsidian").is_dir():
        return _info(candidate, "default", ())
    return VaultInfo(None, "none", False, False, ())


def require(info: VaultInfo) -> Path:
    """The vault root, or the :class:`BrainError` that says why there is none."""
    if info.path is None:
        raise BrainError(errors.VAULT_NOT_FOUND, f"no vault found; set it with: {SET_HINT}")
    if not info.exists:
        raise BrainError(errors.VAULT_MISSING, f"vault directory {info.path} does not exist (source: {info.source})")
    return info.path
