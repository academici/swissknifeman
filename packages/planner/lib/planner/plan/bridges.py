"""Named bridges: discovery and dispatch of ``bridges/<name>/bridge.json`` entrypoints.

The core knows no partner by name. A bridge is found by scanning the bridge roots: the directories of the
``bridges.roots`` setting (a relative path is taken from the project root, a leading ``~`` is expanded), then the
built-in ``<planner>/bridges`` when it exists. The first root that holds a name wins. A manifest is validated against
the ``bridge`` schema kind, and a verb runs the declared script with the bridge's own arguments. The bridge's output
and exit code pass through unchanged.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys

from . import schema, settings, store
from .model import PlanError

PLANNER_ROOT = Path(__file__).resolve().parents[3]
VERB = re.compile(r"^[a-z][a-z0-9-]*\Z")


def default_root() -> Path:
    """The built-in root shipped with the planner (absent when no bridge ships with it)."""
    return PLANNER_ROOT / "bridges"


def project_root(project: str | Path | None = None) -> Path | None:
    """``project`` as given, else the project of the nearest ``plans/`` at or above the working directory."""
    if project is not None:
        return Path(project).resolve()
    return settings.project_root_of(store.find_plans_root())


def roots(project: str | Path | None = None) -> list[Path]:
    """Bridge roots in order: ``bridges.roots`` of the configuration, then the built-in root when it is a directory."""
    base = project_root(project)
    found: list[Path] = []
    for entry in settings.for_project(base).get("bridges.roots") or ():
        path = Path(entry).expanduser()
        found.append(path if path.is_absolute() else (base or Path.cwd()) / path)
    builtin = default_root()
    if builtin.is_dir():
        found.append(builtin)
    unique: list[Path] = []
    for path in found:
        path = path.resolve()
        if path not in unique:
            unique.append(path)
    return unique


def _invalid(path: Path, message: str, issues=()) -> PlanError:
    return PlanError("BRIDGE_INVALID", f"{path}: {message}", list(issues))


def load(directory: Path) -> dict:
    """Read and validate one ``bridge.json``; entrypoints must be existing files inside the bridge."""
    path = directory / "bridge.json"
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise _invalid(path, f"cannot load manifest: {exc}") from exc
    issues = schema.validate(manifest, "bridge")
    if issues:
        raise _invalid(path, "; ".join(i.message for i in issues[:3]), issues)
    if manifest["name"] != directory.name:
        raise _invalid(path, f"name {manifest['name']!r} must equal the directory name {directory.name!r}")
    entrypoints = manifest["entrypoints"]
    if not entrypoints:
        raise _invalid(path, "entrypoints must declare at least one verb")
    base = directory.resolve()
    for verb, target in entrypoints.items():
        if not VERB.match(verb):
            raise _invalid(path, f"verb {verb!r} does not match ^[a-z][a-z0-9-]*$")
        if not isinstance(target, str) or not target or Path(target).is_absolute() or ".." in Path(target).parts:
            raise _invalid(path, f"entrypoint {verb!r} must be a relative path inside the bridge")
        entry = (base / target).resolve()
        if not entry.is_relative_to(base) or not entry.is_file():
            raise _invalid(path, f"entrypoint {verb!r} is not a file inside the bridge: {target}")
    return manifest


def _scan_root(base: Path, skip: frozenset = frozenset()) -> list[tuple[Path, dict]]:
    """Bridges of one root; a directory named in ``skip`` is not read (its name is the bridge name)."""
    if not base.is_dir():
        return []
    return [(manifest_path.parent, load(manifest_path.parent)) for manifest_path in sorted(base.glob("*/bridge.json"))
            if manifest_path.parent.name not in skip]


def scan(root: Path | None = None) -> list[tuple[Path, dict]]:
    """Every bridge in name order; a missing root means no bridges.

    An explicit ``root`` is scanned alone. Otherwise every root of ``roots()`` is scanned in order and a repeated name
    keeps its first bridge, with a ``BRIDGE_SHADOWED`` warning on stderr for the others.
    """
    if root is not None:
        return _scan_root(Path(root))
    chosen: dict[str, Path] = {}
    found: list[tuple[Path, dict]] = []
    for base in roots():
        shadowed = frozenset(chosen)
        if base.is_dir():
            for manifest_path in sorted(base.glob("*/bridge.json")):
                if manifest_path.parent.name in shadowed:
                    print(f"BRIDGE_SHADOWED: {manifest_path.parent.name} in {manifest_path.parent} is shadowed by "
                          f"{chosen[manifest_path.parent.name]}", file=sys.stderr)
        for directory, manifest in _scan_root(base, shadowed):
            chosen[manifest["name"]] = directory
            found.append((directory, manifest))
    return sorted(found, key=lambda pair: pair[1]["name"])


def _display_path(directory: Path) -> str:
    """Path of a bridge relative to the project root when it is inside it, absolute otherwise."""
    base = project_root()
    try:
        return directory.resolve().relative_to(base).as_posix() if base is not None else directory.resolve().as_posix()
    except ValueError:
        return directory.resolve().as_posix()


def listing(root: Path | None = None) -> dict:
    rows = []
    for directory, manifest in scan(root):
        rows.append({"name": manifest["name"], "partner": manifest["partner"], "direction": manifest["direction"],
                     "contract": manifest["contract"], "verbs": sorted(manifest["entrypoints"]),
                     "path": _display_path(directory)})
    return {"bridges": rows}


def environment() -> dict[str, str]:
    env = dict(os.environ)
    lib = str(PLANNER_ROOT / "lib")
    env["PLANNER_ROOT"] = str(PLANNER_ROOT)
    env["PLANNER_PLAN_PY"] = str(PLANNER_ROOT / "scripts" / "plan.py")
    env["TASK_ROOT"] = env["PLANNER_ROOT"]  # Compatibility alias: remove in the next minor release.
    env["TASK_PLAN_PY"] = env["PLANNER_PLAN_PY"]  # Compatibility alias: remove in the next minor release.
    env["PYTHONPATH"] = lib + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    from planner import integration
    aicore_root = integration.status()["root"]
    if aicore_root:
        env["AICORE_ROOT"] = aicore_root
    return env


def run(name: str, verb: str | None, args: list[str], root: Path | None = None) -> int:
    """Run ``verb`` of bridge ``name`` with ``args``; return the bridge's exit code."""
    found = next(((d, m) for d, m in scan(root) if m["name"] == name), None)
    if found is None:
        raise PlanError("BRIDGE_UNKNOWN", f"no bridge named {name!r}; see `plan.py bridge list`")
    directory, manifest = found
    available = ", ".join(sorted(manifest["entrypoints"]))
    if verb is None or verb not in manifest["entrypoints"]:
        raise PlanError("BRIDGE_VERB_UNKNOWN", f"bridge {name!r} has no verb {verb!r}; available: {available}")
    entry = directory.resolve() / manifest["entrypoints"][verb]
    sys.stdout.flush()
    sys.stderr.flush()
    return subprocess.run([sys.executable, str(entry), *args], env=environment(), check=False).returncode
