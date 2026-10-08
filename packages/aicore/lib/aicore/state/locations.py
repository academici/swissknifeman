"""Standard locations of swissknifeman configuration and state.

Machine locations follow the XDG base directories; ``SKM_HOME`` (an absolute path) moves all
four of them under one directory and switches off every legacy-location lookup, so a sandbox
or a test never reads the real home directory. Project locations live in ``.swissknifeman/``
at the project root. Nothing here creates anything on disk except :func:`ensure_dir`.
stdlib only.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping, Optional, Union

APP = "swissknifeman"
PROJECT_DIRNAME = ".swissknifeman"

PathLike = Union[str, "os.PathLike[str]"]


@dataclass(frozen=True)
class Locations:
    """The four machine directories and whether they come from ``SKM_HOME``."""

    config: Path
    state: Path
    data: Path
    cache: Path
    isolated: bool


def _home(env: Mapping[str, str], home: Optional[PathLike]) -> Path:
    if home is not None:
        return Path(home)
    if env.get("HOME"):
        return Path(env["HOME"])
    return Path.home()


def _xdg(env: Mapping[str, str], name: str, default: Path) -> Path:
    value = env.get(name, "")
    # The XDG specification: a relative path in these variables is invalid and ignored.
    if value and os.path.isabs(value):
        return Path(value)
    return default


def machine_locations(env: Optional[Mapping[str, str]] = None,
                      home: Optional[PathLike] = None) -> Locations:
    """Resolve the machine config/state/data/cache directories (nothing is created)."""
    env = os.environ if env is None else env
    skm_home = env.get("SKM_HOME", "")
    if skm_home:
        if not os.path.isabs(skm_home):
            raise ValueError(f"SKM_HOME must be an absolute path, got {skm_home!r}")
        base = Path(skm_home)
        return Locations(base / "config", base / "state", base / "data", base / "cache", True)
    user = _home(env, home)
    return Locations(
        _xdg(env, "XDG_CONFIG_HOME", user / ".config") / APP,
        _xdg(env, "XDG_STATE_HOME", user / ".local" / "state") / APP,
        _xdg(env, "XDG_DATA_HOME", user / ".local" / "share") / APP,
        _xdg(env, "XDG_CACHE_HOME", user / ".cache") / APP,
        False,
    )


def _sub(base: Path, app: Optional[str]) -> Path:
    return base / app if app else base


def config_dir(*, env: Optional[Mapping[str, str]] = None, home: Optional[PathLike] = None) -> Path:
    return machine_locations(env, home).config


def state_dir(app: Optional[str] = None, *, env: Optional[Mapping[str, str]] = None,
              home: Optional[PathLike] = None) -> Path:
    return _sub(machine_locations(env, home).state, app)


def data_dir(app: Optional[str] = None, *, env: Optional[Mapping[str, str]] = None,
             home: Optional[PathLike] = None) -> Path:
    return _sub(machine_locations(env, home).data, app)


def cache_dir(app: Optional[str] = None, *, env: Optional[Mapping[str, str]] = None,
              home: Optional[PathLike] = None) -> Path:
    return _sub(machine_locations(env, home).cache, app)


def machine_config_file(*, env: Optional[Mapping[str, str]] = None,
                        home: Optional[PathLike] = None) -> Path:
    return config_dir(env=env, home=home) / "config.toml"


def ensure_dir(path: PathLike) -> Path:
    """Create *path* (and missing parents) with owner-only access for the directory itself."""
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    return target


def project_dir(root: PathLike) -> Path:
    return Path(root) / PROJECT_DIRNAME


def project_config_file(root: PathLike) -> Path:
    return project_dir(root) / "config.toml"


def project_state_dir(root: PathLike, app: Optional[str] = None) -> Path:
    return _sub(project_dir(root) / "state", app)


def project_backups_dir(root: PathLike) -> Path:
    return project_dir(root) / "backups"


def find_project_root(start: PathLike, *, env: Optional[Mapping[str, str]] = None,
                      home: Optional[PathLike] = None) -> Path:
    """Nearest ancestor of *start* (inclusive) holding ``.swissknifeman/`` or ``.git``.

    The user's home directory does not count through ``.swissknifeman/`` (the legacy machine
    state directory has that name); a ``.git`` there does. Without a match *start* itself is
    returned.
    """
    begin = Path(os.path.abspath(start))
    user = _home(os.environ if env is None else env, home)
    for candidate in (begin, *begin.parents):
        if (candidate / ".git").exists():
            return candidate
        if candidate != user and (candidate / PROJECT_DIRNAME).is_dir():
            return candidate
    return Path(start)


_WARNED: set = set()


def _warn_stderr(message: str) -> None:
    print(message, file=sys.stderr)


def resolve_with_legacy(new: PathLike, legacy: Union[PathLike, Iterable[PathLike]], *,
                        env: Optional[Mapping[str, str]] = None,
                        home: Optional[PathLike] = None,
                        warn: Optional[Callable[[str], None]] = None) -> Path:
    """Pick the location to use: *new* when present, else the first existing legacy path.

    A legacy path in use is reported once per process and per ``(new, legacy)`` pair; it is
    never copied or removed, so reads and writes keep going to one place until
    ``swissknifeman upgrade`` moves it. With ``SKM_HOME`` set the legacy paths are not
    looked at at all.
    """
    target = Path(new)
    if target.exists():
        return target
    if machine_locations(env, home).isolated:
        return target
    candidates = [legacy] if isinstance(legacy, (str, os.PathLike)) else list(legacy)
    for old in map(Path, candidates):
        if not old.exists():
            continue
        key = (str(target), str(old))
        if key not in _WARNED:
            _WARNED.add(key)
            (warn or _warn_stderr)(
                f"warning: {old} is a legacy location; swissknifeman now uses {target}. "
                "Move it there (swissknifeman upgrade will do it) to silence this warning.")
        return old
    return target
