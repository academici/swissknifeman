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


ENV_WORKSPACE_ROOT = "SKM_WORKSPACE_ROOT"


def workspace_root(env: Optional[Mapping[str, str]] = None, home: Optional[PathLike] = None) -> Path:
    """The root of the portable workspace (its one git root): ``SKM_WORKSPACE_ROOT`` (an absolute path) or
    ``data_dir()/workspace``. Nothing is created."""
    environment = os.environ if env is None else env
    value = environment.get(ENV_WORKSPACE_ROOT, "")
    if value:
        if not os.path.isabs(value):
            raise ValueError(f"{ENV_WORKSPACE_ROOT} must be an absolute path, got {value!r}")
        return Path(value)
    return data_dir(env=environment, home=home) / "workspace"


def workspace_state_dir(env: Optional[Mapping[str, str]] = None, home: Optional[PathLike] = None) -> Path:
    """Machine files of the workspace (bindings, device, sync state, audit, locks); never in the workspace git tree."""
    return state_dir("workspace", env=env, home=home)


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


ENV_PROJECT_ROOT = "SKM_PROJECT_ROOT"
DEFAULT_MARKERS = (".git", PROJECT_DIRNAME)


# The project-local launcher (``<project>/.swissknifeman/launcher.py``) hands its project over in these variables. The
# context binds only the process the launcher replaced itself with (the exec chain keeps the process id): a child
# process inherits the variables but not the authority, so a worktree agent of a run is never pinned to the parent tree.
LAUNCHER_NAME = "launcher.py"
ENV_LAUNCHER_ACTIVE = "SKM_LAUNCHER_ACTIVE"
ENV_LAUNCHER_PROTOCOL = "SKM_LAUNCHER_PROTOCOL"
ENV_LAUNCHER_PATH = "SKM_LAUNCHER_PATH"
ENV_LAUNCHER_ROOT = "SKM_LAUNCHER_PROJECT_ROOT"
ENV_LAUNCHER_PID = "SKM_LAUNCHER_PID"
ENV_INVOCATION_CWD = "SKM_INVOCATION_CWD"
LAUNCHER_ENV = (ENV_LAUNCHER_ACTIVE, ENV_LAUNCHER_PROTOCOL, ENV_LAUNCHER_PATH, ENV_LAUNCHER_ROOT, ENV_LAUNCHER_PID,
                ENV_INVOCATION_CWD)


def launcher_root(env: Optional[Mapping[str, str]] = None, pid: Optional[int] = None) -> Optional[Path]:
    """The project root the launcher bound to this process, or ``None``: the launcher variables are absent, or they were
    inherited from another process (``SKM_LAUNCHER_PID`` is not ``pid``, by default this process)."""
    environment = os.environ if env is None else env
    if environment.get(ENV_LAUNCHER_ACTIVE) != "1" or not environment.get(ENV_LAUNCHER_ROOT):
        return None
    if environment.get(ENV_LAUNCHER_PID) != str(os.getpid() if pid is None else pid):
        return None
    return Path(environment[ENV_LAUNCHER_ROOT])


def same_path(first: PathLike, second: PathLike) -> bool:
    """Whether two paths name the same place after ``~``, ``..`` and symlinks are resolved (a string prefix is not)."""
    return os.path.realpath(os.path.expanduser(str(first))) == os.path.realpath(os.path.expanduser(str(second)))


@dataclass(frozen=True)
class ProjectContext:
    """The project of a command and how it was found: ``resolution`` is ``launcher``, ``flag``, ``environment``, ``marker``
    or ``git``; ``marker`` is the entry that matched (``None`` when the project was named, not searched for)."""

    root: Path
    resolution: str
    marker: Optional[str] = None


class ProjectContextRequired(LookupError):
    """``PROJECT_CONTEXT_REQUIRED``: a command that needs a project found none above its start."""

    code = "PROJECT_CONTEXT_REQUIRED"

    def __init__(self, start: PathLike, reason: Optional[str] = None):
        super().__init__("PROJECT_CONTEXT_REQUIRED: " + (reason or f"no project found above {start} (no .git or "
                         f".swissknifeman); go into the project or pass --project DIR"))


class ProjectContextConflict(ProjectContextRequired):
    """``PROJECT_CONTEXT_CONFLICT``: the launcher bound the command to one project and a second source names another.
    A subclass of :class:`ProjectContextRequired`, so every handler that prints that refusal prints this one too."""

    code = "PROJECT_CONTEXT_CONFLICT"

    def __init__(self, launcher: PathLike, other: PathLike, source: str = "--project"):
        LookupError.__init__(self, f"PROJECT_CONTEXT_CONFLICT: launcher project is {launcher}, but {source} names "
                                   f"{other}; drop {source} (the launcher binds the project)")
        self.launcher_root = Path(launcher)
        self.other_root = Path(other)
        self.source = source


def _marker_found(candidate: Path, marker: Union[str, tuple]) -> bool:
    """Whether ``candidate`` holds the marker: a name (any entry; ``.swissknifeman`` only as a directory) or
    ``(name, kind)`` with kind ``file``, ``dir`` or ``any``."""
    name, kind = (marker, "dir" if marker == PROJECT_DIRNAME else "any") if isinstance(marker, str) else marker
    path = candidate / name
    return path.is_file() if kind == "file" else path.is_dir() if kind == "dir" else path.exists()


def resolve_project(start: PathLike, *, explicit: Optional[PathLike] = None,
                    env: Optional[Mapping[str, str]] = None, home: Optional[PathLike] = None,
                    markers: Iterable[Union[str, tuple]] = DEFAULT_MARKERS,
                    stop_at_home: bool = False) -> Optional[ProjectContext]:
    """The project of a command: the launcher-bound root (:func:`launcher_root`; a ``--project`` that names another folder
    is ``PROJECT_CONTEXT_CONFLICT``, never an override), else ``explicit`` (the ``--project`` flag), else
    ``SKM_PROJECT_ROOT``, else the nearest ancestor of ``start`` (inclusive) that holds one of ``markers`` (checked in the
    order given; a marker is a name, or ``(name, "file"|"dir"|"any")``; ``.git`` may be a file), else ``None``.

    A named project that is not a directory is refused (``ProjectContextRequired``), never replaced by a search. The user's
    home directory does not count through ``.swissknifeman`` (the legacy machine state directory has that name); with
    ``stop_at_home`` the search ends at the home directory (it is checked, nothing above it is).
    """
    environment = os.environ if env is None else env
    bound = launcher_root(environment)
    if bound is not None:
        if not bound.is_dir():
            raise ProjectContextRequired(bound, f"{ENV_LAUNCHER_ROOT} {bound} is not a directory; run the launcher "
                                                f"of an existing project")
        if explicit is not None and str(explicit) != "" and not same_path(explicit, bound):
            raise ProjectContextConflict(bound, os.path.abspath(os.path.expanduser(str(explicit))))
        return ProjectContext(bound, "launcher")
    named, resolution, label = None, "", ""
    if explicit is not None and str(explicit) != "":
        named, resolution, label = explicit, "flag", "--project"
    elif environment.get(ENV_PROJECT_ROOT, ""):
        named, resolution, label = environment[ENV_PROJECT_ROOT], "environment", ENV_PROJECT_ROOT
    if named is not None:
        root = Path(os.path.abspath(os.path.expanduser(named)))
        if not root.is_dir():
            raise ProjectContextRequired(root, f"{label} {root} is not a directory; name the project folder or "
                                               f"go into the project")
        return ProjectContext(root, resolution)
    begin = Path(os.path.abspath(start))
    user = _home(environment, home)
    for candidate in (begin, *begin.parents):
        for marker in markers:
            name = marker if isinstance(marker, str) else marker[0]
            if name == PROJECT_DIRNAME and candidate == user:
                continue
            if _marker_found(candidate, marker):
                return ProjectContext(candidate, "git" if name == ".git" else "marker", name)
        if stop_at_home and candidate == user:
            break
    return None


def find_project_root(start: PathLike, *, env: Optional[Mapping[str, str]] = None,
                      home: Optional[PathLike] = None) -> Path:
    """The root of :func:`resolve_project` for ``start``; without a project, ``start`` itself. It never raises: a
    ``SKM_PROJECT_ROOT`` or launcher root that is not a directory is ignored and the markers decide."""
    try:
        context = resolve_project(start, env=env, home=home)
    except ProjectContextRequired:
        environment = dict(os.environ if env is None else env)
        for name in (ENV_PROJECT_ROOT, *LAUNCHER_ENV):
            environment.pop(name, None)
        context = resolve_project(start, env=environment, home=home)
    return context.root if context else Path(start)


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
