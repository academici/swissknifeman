"""Standard locations of swissknifeman configuration and state.

The machine keeps everything in one folder, ``~/.local/share/swissknifeman`` (the machine home):
``config/``, ``state/``, ``cache/`` and ``workspaces/``, the data of the modules beside them
(``<home>/<module>``). The ``XDG_*`` variables no longer move the default. ``SKM_HOME`` (an absolute
path) is the machine home of a sandbox or a test and switches off every legacy-location lookup, so
it never reads the real home directory. A machine that still has the old XDG folders
(``~/.config/swissknifeman``, ``~/.local/state/swissknifeman``, ``~/.cache/swissknifeman``, ...)
keeps using each of them while the new folder of that kind does not exist yet; :mod:`.migrate`
(``aicore config migrate-home``) moves them. Project locations live in ``.swissknifeman/`` at the
project root, except for a checkout whose marker names a workspace project present on this machine: its config, state,
backups and stubs live in ``projects/<code>/local/`` of that workspace (:func:`project_local_dir`). Nothing here
creates anything on disk except :func:`ensure_dir`. stdlib only.
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, Mapping, Optional, Tuple, Union

APP = "swissknifeman"
PROJECT_DIRNAME = ".swissknifeman"

PathLike = Union[str, "os.PathLike[str]"]


@dataclass(frozen=True)
class Locations:
    """The machine directories, whether they come from ``SKM_HOME``, and which of them are still the old XDG ones.

    ``data`` is the machine home itself (module data is ``<home>/<module>``); ``legacy`` names the kinds
    (``config``, ``state``, ``cache``, ``workspaces``) that resolve to an old XDG folder.
    """

    config: Path
    state: Path
    data: Path
    cache: Path
    isolated: bool
    workspaces: Optional[Path] = None
    legacy: Tuple[str, ...] = ()
    home: Optional[Path] = None


# The machine folders of the layout before the machine home: kind -> (XDG variable, default below the user home).
LEGACY_XDG = {
    "config": ("XDG_CONFIG_HOME", (".config",)),
    "state": ("XDG_STATE_HOME", (".local", "state")),
    "data": ("XDG_DATA_HOME", (".local", "share")),
    "cache": ("XDG_CACHE_HOME", (".cache",)),
}


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


def machine_home(env: Optional[Mapping[str, str]] = None, home: Optional[PathLike] = None) -> Path:
    """The machine home: ``SKM_HOME`` (absolute), else ``~/.local/share/swissknifeman`` (nothing is created)."""
    env = os.environ if env is None else env
    skm_home = env.get("SKM_HOME", "")
    if skm_home:
        if not os.path.isabs(skm_home):
            raise ValueError(f"SKM_HOME must be an absolute path, got {skm_home!r}")
        return Path(skm_home)
    return _home(env, home) / ".local" / "share" / APP


def legacy_machine_dirs(env: Optional[Mapping[str, str]] = None,
                        home: Optional[PathLike] = None) -> Dict[str, Path]:
    """The ``config``, ``state``, ``data`` and ``cache`` folders of the XDG layout that was used before the machine home."""
    env = os.environ if env is None else env
    user = _home(env, home)
    return {kind: _xdg(env, variable, user.joinpath(*below)) / APP for kind, (variable, below) in LEGACY_XDG.items()}


def _present(path: Path) -> bool:
    """Whether ``path`` exists; a folder that cannot be read (``PermissionError``) counts as absent, as in the shell."""
    try:
        return path.exists()
    except OSError:
        return False


def machine_locations(env: Optional[Mapping[str, str]] = None,
                      home: Optional[PathLike] = None) -> Locations:
    """Resolve the machine config/state/cache/workspaces directories (nothing is created).

    Each of them is ``<machine home>/<kind>``; without ``SKM_HOME`` a kind falls back to its old XDG folder
    while the new one does not exist and the old one does (reported in ``Locations.legacy``).
    """
    env = os.environ if env is None else env
    base = machine_home(env, home)
    if env.get("SKM_HOME", ""):
        return Locations(base / "config", base / "state", base, base / "cache", True, base / "workspaces", (), base)
    old = legacy_machine_dirs(env, home)
    old["workspaces"] = old["data"] / "workspaces"
    chosen: Dict[str, Path] = {}
    used = []
    for kind in ("config", "state", "cache", "workspaces"):
        new = base / kind
        if not _present(new) and _present(old[kind]):
            chosen[kind] = old[kind]
            used.append(kind)
        else:
            chosen[kind] = new
    return Locations(chosen["config"], chosen["state"], base, chosen["cache"], False, chosen["workspaces"],
                     tuple(used), base)


def _sub(base: Path, app: Optional[str]) -> Path:
    return base / app if app else base


def config_dir(*, env: Optional[Mapping[str, str]] = None, home: Optional[PathLike] = None) -> Path:
    return machine_locations(env, home).config


def state_dir(app: Optional[str] = None, *, env: Optional[Mapping[str, str]] = None,
              home: Optional[PathLike] = None) -> Path:
    return _sub(machine_locations(env, home).state, app)


def data_dir(app: Optional[str] = None, *, env: Optional[Mapping[str, str]] = None,
             home: Optional[PathLike] = None) -> Path:
    """The machine home, or its ``app`` folder; until ``migrate-home`` ran, the data of a module that still lives in the
    old ``$XDG_DATA_HOME/swissknifeman/<app>`` is used while ``<machine home>/<app>`` does not exist."""
    where = machine_locations(env, home)
    target = _sub(where.data, app)
    if app and not where.isolated and not _present(target):
        old = legacy_machine_dirs(env, home)["data"] / app
        if _present(old):
            return old
    return target


def cache_dir(app: Optional[str] = None, *, env: Optional[Mapping[str, str]] = None,
              home: Optional[PathLike] = None) -> Path:
    return _sub(machine_locations(env, home).cache, app)


ENV_WORKSPACES_ROOT = "SKM_WORKSPACES_ROOT"
ENV_WORKSPACE = "SKM_WORKSPACE"
WORKSPACE_FILE = "workspace.json"
CODE_PATTERN = r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*"
CODE_MAX = 40
_CODE = re.compile(CODE_PATTERN)


def is_code(value: object) -> bool:
    """Whether ``value`` is a code of a workspace or a project: lowercase words of letters and digits joined by ``-``,
    starting with a letter, at most 40 characters. A code is also the name of a folder, so it is never a path."""
    return isinstance(value, str) and len(value) <= CODE_MAX and _CODE.fullmatch(value) is not None


class WorkspaceSelectionError(ValueError):
    """No workspace can be chosen: ``code`` is ``WORKSPACE_NOT_FOUND`` or ``WORKSPACE_AMBIGUOUS``."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def workspaces_root(env: Optional[Mapping[str, str]] = None, home: Optional[PathLike] = None) -> Path:
    """The folder that holds the workspaces (one git repository each): ``SKM_WORKSPACES_ROOT`` (an absolute path) or
    ``<machine home>/workspaces``. Nothing is created."""
    environment = os.environ if env is None else env
    value = environment.get(ENV_WORKSPACES_ROOT, "")
    if value:
        if not os.path.isabs(value):
            raise ValueError(f"{ENV_WORKSPACES_ROOT} must be an absolute path, got {value!r}")
        return Path(value)
    return machine_locations(environment, home).workspaces


def list_workspaces(env: Optional[Mapping[str, str]] = None, home: Optional[PathLike] = None) -> list:
    """Codes of the workspaces of this machine (folders of :func:`workspaces_root` that hold ``workspace.json``)."""
    root = workspaces_root(env, home)
    try:
        return sorted(child.name for child in root.iterdir() if is_code(child.name) and (child / WORKSPACE_FILE).is_file())
    except OSError:
        return []


def selected_workspace(env: Optional[Mapping[str, str]] = None, home: Optional[PathLike] = None) -> str:
    """The code of the workspace this process works with: ``SKM_WORKSPACE``, else the only workspace of the machine.
    ``WORKSPACE_NOT_FOUND`` when the machine has none, ``WORKSPACE_AMBIGUOUS`` when there are several and none is chosen."""
    environment = os.environ if env is None else env
    value = environment.get(ENV_WORKSPACE, "")
    if value:
        if not is_code(value):
            raise ValueError(f"{ENV_WORKSPACE} must be a workspace code, got {value!r}")
        return value
    codes = list_workspaces(environment, home)
    if len(codes) == 1:
        return codes[0]
    if not codes:
        raise WorkspaceSelectionError("WORKSPACE_NOT_FOUND", f"no workspace in {workspaces_root(environment, home)}; "
                                      f"run `swissknifeman workspace init --code CODE` or `workspace clone URL`")
    raise WorkspaceSelectionError("WORKSPACE_AMBIGUOUS", f"several workspaces ({', '.join(codes)}); choose one with "
                                  f"--workspace CODE or {ENV_WORKSPACE}")


def workspace_root(env: Optional[Mapping[str, str]] = None, home: Optional[PathLike] = None,
                   code: Optional[str] = None) -> Path:
    """The root (the one git root) of a workspace: ``workspaces_root()/<code>``; without ``code`` the selected workspace
    (:func:`selected_workspace`). Nothing is created."""
    chosen = code if code is not None else selected_workspace(env, home)
    if not is_code(chosen):
        raise ValueError(f"invalid workspace code {chosen!r}")
    return workspaces_root(env, home) / chosen


def workspace_state_dir(env: Optional[Mapping[str, str]] = None, home: Optional[PathLike] = None,
                        code: Optional[str] = None) -> Path:
    """Machine files of a workspace (bindings, sync state, audit, locks); never in the workspace git tree. The same
    ``code`` rule as :func:`workspace_root`."""
    chosen = code if code is not None else selected_workspace(env, home)
    if not is_code(chosen):
        raise ValueError(f"invalid workspace code {chosen!r}")
    return state_dir("workspaces", env=env, home=home) / chosen


def device_file(env: Optional[Mapping[str, str]] = None, home: Optional[PathLike] = None) -> Path:
    """The device file of this machine, shared by every workspace (``state/workspaces/device.json``)."""
    return state_dir("workspaces", env=env, home=home) / "device.json"


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


PROJECT_MARKER_FILE = "project.json"
LOCAL_DIRNAME = "local"


def _marker_codes(root: PathLike) -> Optional[Tuple[str, str]]:
    """``(workspace code, project code)`` of the marker ``<root>/.swissknifeman/project.json``. A missing, unreadable or
    malformed marker names nothing (``None``): the contract check and its refusal belong to ``aicore.workspace``, a path
    lookup never fails because of it."""
    try:
        with open(project_dir(root) / PROJECT_MARKER_FILE, encoding="utf-8") as handle:
            document = json.load(handle)
    except (OSError, UnicodeError, ValueError):
        return None
    if not isinstance(document, dict):
        return None
    workspace, project = document.get("workspace"), document.get("project_id")
    return (workspace, project) if is_code(workspace) and is_code(project) else None


def project_local_dir(root: PathLike, *, env: Optional[Mapping[str, str]] = None,
                      home: Optional[PathLike] = None) -> Optional[Path]:
    """``<workspace>/projects/<code>/local``: the machine-local folder of the project (contract ``project-local-config/v1``),
    found through the marker of the checkout at ``root`` (workspace code and project code). ``None`` (the project keeps its
    ``.swissknifeman/`` folder, as before) when the checkout has no marker, the marker is unusable, or the workspace it names
    has no folder for the project on this machine. Nothing is created and ``local/`` itself need not exist yet."""
    codes = _marker_codes(root)
    if codes is None:
        return None
    try:
        folder = workspaces_root(env, home) / codes[0] / "projects" / codes[1]
    except ValueError:
        return None
    return folder / LOCAL_DIRNAME if folder.is_dir() else None


def project_config_file(root: PathLike, *, env: Optional[Mapping[str, str]] = None,
                        home: Optional[PathLike] = None) -> Path:
    """The project layer of the configuration: ``local/config.toml`` of the project in its workspace, else
    ``<root>/.swissknifeman/config.toml``."""
    local = project_local_dir(root, env=env, home=home)
    return (local if local is not None else project_dir(root)) / "config.toml"


def project_state_dir(root: PathLike, app: Optional[str] = None, *, env: Optional[Mapping[str, str]] = None,
                      home: Optional[PathLike] = None) -> Path:
    local = project_local_dir(root, env=env, home=home)
    return _sub((local if local is not None else project_dir(root)) / "state", app)


def project_backups_dir(root: PathLike, *, env: Optional[Mapping[str, str]] = None,
                        home: Optional[PathLike] = None) -> Path:
    local = project_local_dir(root, env=env, home=home)
    return (local if local is not None else project_dir(root)) / "backups"


def project_stubs_dir(root: PathLike, *, env: Optional[Mapping[str, str]] = None,
                      home: Optional[PathLike] = None) -> Path:
    """The project stubs: ``local/stubs`` of the project in its workspace, else ``<root>/.swissknifeman/stubs``."""
    local = project_local_dir(root, env=env, home=home)
    return (local if local is not None else project_dir(root)) / "stubs"


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
