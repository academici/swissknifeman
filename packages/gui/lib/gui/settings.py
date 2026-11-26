"""Layered ``[gui]`` configuration (``configs/config.schema.json``).

``load`` resolves the section through ``aicore.config`` (defaults -> machine file -> project file -> environment ->
``--config`` file -> flags); gui never reads ``config.toml`` itself. stdlib + aicore.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Union

from aicore.config import ResolvedConfig, resolve

GUI_ROOT = Path(__file__).resolve().parents[2]

PathLike = Union[str, Path]


@dataclass(frozen=True)
class Runs:
    max_global: int
    max_per_project: int
    max_per_owner: int
    chunk_bytes: int
    log_max_bytes: int
    idle_timeout_s: int
    cancel_grace_s: int


@dataclass(frozen=True)
class Events:
    ring_frames: int
    queue_frames: int
    heartbeat_s: int
    journal_poll_s: int


@dataclass(frozen=True)
class Retention:
    log_days: int
    log_total_mb: int


@dataclass(frozen=True)
class Query:
    max_output_bytes: int


@dataclass(frozen=True)
class Config:
    lock_timeout_s: float
    preview_ttl_s: int


@dataclass(frozen=True)
class Plugins:
    drain_timeout_s: int
    quarantine_failures: int
    quarantine_window_s: int
    history_limit: int


@dataclass(frozen=True)
class Terminal:
    enabled: bool
    max_sessions: int
    idle_timeout_s: int
    max_session_s: int
    credit_bytes: int
    output_chunk_bytes: int


@dataclass(frozen=True)
class Settings:
    """The effective ``[gui]`` configuration; ``resolved`` explains where each value comes from."""

    port: int
    open_browser: bool
    runs: Runs
    events: Events
    retention: Retention
    query: Query
    config: Config
    plugins: Plugins
    terminal: Terminal
    resolved: Optional[ResolvedConfig] = None


def _group(resolved: ResolvedConfig, cls: type, prefix: str):
    return cls(**{name: resolved.get(f"{prefix}.{name}") for name in cls.__dataclass_fields__})


def _terminal(resolved: ResolvedConfig) -> Terminal:
    group = _group(resolved, Terminal, "terminal")
    return Terminal(**{**group.__dict__, "enabled": bool(group.enabled)})


def load(env: Optional[Mapping[str, str]] = None, project: Optional[PathLike] = None, *,
         config_file: Optional[PathLike] = None, home: Optional[PathLike] = None,
         flags: Optional[Mapping[str, object]] = None) -> Settings:
    """Resolve ``[gui]`` (``project=None``: no project layer). Raises ``aicore.config.ConfigError``."""
    resolved = resolve("gui", unit_root=GUI_ROOT, project=project, config_file=config_file, env=env, home=home,
                       flags=flags)
    return Settings(port=resolved.get("port"), open_browser=bool(resolved.get("open_browser")),
                    runs=_group(resolved, Runs, "runs"), events=_group(resolved, Events, "events"),
                    retention=_group(resolved, Retention, "retention"), query=_group(resolved, Query, "query"),
                    config=_group(resolved, Config, "config"), plugins=_group(resolved, Plugins, "plugins"),
                    terminal=_terminal(resolved),
                    resolved=resolved)
