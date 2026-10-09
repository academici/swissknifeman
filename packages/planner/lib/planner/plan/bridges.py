"""Named bridges: discovery and dispatch of ``bridges/<name>/bridge.json`` entrypoints.

The core knows no partner by name. A bridge is found by scanning the bridges root; its manifest is
validated against the ``bridge`` schema kind, and a verb runs the declared script with the bridge's own
arguments. The bridge's output and exit code pass through unchanged.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys

from . import schema
from .model import PlanError

PLANNER_ROOT = Path(__file__).resolve().parents[3]
VERB = re.compile(r"^[a-z][a-z0-9-]*\Z")


def default_root() -> Path:
    return PLANNER_ROOT / "bridges"


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


def scan(root: Path | None = None) -> list[tuple[Path, dict]]:
    """Every bridge under ``root`` in name order; a missing root means no bridges."""
    base = Path(root) if root is not None else default_root()
    if not base.is_dir():
        return []
    return [(manifest_path.parent, load(manifest_path.parent))
            for manifest_path in sorted(base.glob("*/bridge.json"))]


def listing(root: Path | None = None) -> dict:
    rows = []
    for directory, manifest in scan(root):
        rows.append({"name": manifest["name"], "partner": manifest["partner"], "direction": manifest["direction"],
                     "contract": manifest["contract"], "verbs": sorted(manifest["entrypoints"]),
                     "path": f"bridges/{directory.name}"})
    return {"bridges": rows}


def environment() -> dict[str, str]:
    env = dict(os.environ)
    lib = str(PLANNER_ROOT / "lib")
    env["PLANNER_ROOT"] = str(PLANNER_ROOT)
    env["PLANNER_PLAN_PY"] = str(PLANNER_ROOT / "scripts" / "plan.py")
    env["TASK_ROOT"] = env["PLANNER_ROOT"]  # Compatibility alias: remove in the next minor release.
    env["TASK_PLAN_PY"] = env["PLANNER_PLAN_PY"]  # Compatibility alias: remove in the next minor release.
    env["PYTHONPATH"] = lib + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
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
