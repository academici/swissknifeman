"""``workspace migrate``: move the plans of a checkout into the workspace and take them back (contract ``migration``).

``discover`` lists the checkouts that hold plans, ``plan`` is the dry run (writes nothing), ``apply`` calls the port
``workspace:plans-migrator`` (the critical section lives in the bridge, never here) and then writes ``local-only.json``,
the report ``migrations/<op_id>.json`` and the binding, ``verify`` compares the workspace and the old folders with the last
report, ``rollback`` switches the marker back and removes what the migration put in, ``cleanup`` removes the old folders
whose copy in the workspace has the same digest. Nothing here commits: ``apply``, ``rollback`` and ``cleanup`` print the
commands that do.

The digest of a folder is ``sha256:`` over the sorted ``(path, sha256)`` pairs of its files, derived files left out
(``views/``, ``context/`` and ``.lock`` of a plan folder; ``__pycache__`` and ``.DS_Store`` everywhere); the bridge computes
it the same way, so a plan has one digest in the checkout and in the workspace.
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import re
import shlex
import shutil
import urllib.parse
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple, Union

from aicore.state import state_dir, workspace_state_dir
from aicore.util.io import atomic_write_text
from aicore.workspace import (WorkspaceError, bind, checkout_remotes, new_id, project_dir, read_device, read_marker,
                              read_project, utc_now, validate_document, write_marker)

from . import gitutil, layout, localonly, migrator_port, projects, safety

PathLike = Union[str, "os.PathLike[str]"]
Env = Optional[Mapping[str, str]]

PLAN_SCHEMA = "urn:swissknifeman:task:plan:plan:v1"
REPORT_SCHEMA = "urn:swissknifeman:aicore:workspace-migration:v1"
ARCHIVE = "archive"
ROOT_NAME = "_root"
IGNORED = frozenset({"__pycache__", ".DS_Store"})
V4_DERIVED = frozenset({"views", "context", ".lock"})
DISCOVER_DEPTH = 4
DISCOVER_SKIP = frozenset({"node_modules", ".git", "vendor"})
LAUNCHER = ".swissknifeman/launcher.py"
VIRTUAL = "projects/prj/"  # prefix of the paths given to the publish-safety rules (they judge paths below projects/)
COPY = ("copied", "imported-copy")
MAX_LISTED = 5
ON_CONFLICT = ("keep-workspace", "import-copy")
_HEAD = re.compile(r"^[0-9a-f]{40,64}$")
_CHUNK = 1 << 20


# --------------------------------------------------------------------------------------------------- digests

def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def digest_files(files: Sequence[Mapping[str, Any]], prefix: str = "") -> str:
    """``sha256:<hex>`` over the sorted ``(path, sha256)`` pairs; ``prefix`` is cut from every path first."""
    cut = len(prefix)
    lines = sorted(f"{entry['path'][cut:]}\0{entry['sha256']}\n" for entry in files)
    return "sha256:" + hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()


def _walk(directory: Path, rel: str, skip_top: frozenset, files: List[Dict[str, Any]], symlinks: List[str]) -> None:
    for entry in sorted(os.scandir(directory), key=lambda item: item.name):
        child = f"{rel}/{entry.name}" if rel else entry.name
        if entry.name in IGNORED or entry.name in skip_top:
            continue
        if entry.is_symlink():
            symlinks.append(child)
        elif entry.is_dir(follow_symlinks=False):
            _walk(Path(entry.path), child, frozenset(), files, symlinks)
        elif entry.is_file(follow_symlinks=False):
            files.append({"path": child, "bytes": entry.stat(follow_symlinks=False).st_size,
                          "sha256": _sha256(Path(entry.path))})
        else:
            symlinks.append(child)  # a socket, a device, a fifo


def scan_folder(directory: Path, cls: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    """``(files, symlinks)`` of a folder under the rules of its class; paths are relative to the folder."""
    files: List[Dict[str, Any]] = []
    symlinks: List[str] = []
    _walk(directory, "", V4_DERIVED if cls == "v4" else frozenset(), files, symlinks)
    return files, symlinks


def folder_digest(directory: Path, cls: str) -> Optional[str]:
    """The digest of a folder; ``None`` when there is none, a marker value for something that is not a real folder."""
    if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
        return "sha256:not-a-folder"
    if not directory.is_dir():
        return None
    return digest_files(scan_folder(directory, cls)[0])


def _classify(directory: Path) -> str:
    try:
        document = json.loads((directory / "plan.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return "legacy"
    return "v4" if isinstance(document, dict) and document.get("$schema") == PLAN_SCHEMA else "legacy"


def source_entries(plans: Path) -> Tuple[List[Tuple[str, Path]], List[Tuple[str, Path]]]:
    """``(folders, loose files)`` of ``plans/`` and ``plans/archive/`` as ``(name relative to plans/, path)``."""
    folders: List[Tuple[str, Path]] = []
    loose: List[Tuple[str, Path]] = []
    for parent, prefix in ((plans, ""), (plans / ARCHIVE, ARCHIVE + "/")):
        try:
            entries = sorted(os.scandir(parent), key=lambda item: item.name)
        except OSError:
            continue
        for entry in entries:
            if entry.name in IGNORED or (not prefix and entry.name == ARCHIVE and entry.is_dir(follow_symlinks=False)):
                continue
            (folders if entry.is_dir(follow_symlinks=False) else loose).append((prefix + entry.name, Path(entry.path)))
    return folders, loose


def _loose_digest(loose: Sequence[Tuple[str, Path]]) -> Optional[str]:
    files = [{"path": name, "sha256": _sha256(path)} for name, path in loose if path.is_file() and not path.is_symlink()]
    return digest_files(files) if files else None


# ------------------------------------------------------------------------------------------------ names, ids

def encode_name(name: str) -> str:
    """A folder name of the source as a report name: the schema forbids ``/`` (archived plans are ``archive/<id>``), a
    leading ``~`` and ``\\`` in a name, so these characters and ``%`` become ``%XX``."""
    text = name.replace("%", "%25").replace("/", "%2F").replace("\\", "%5C")
    return "%7E" + text[1:] if text.startswith("~") else text


def decode_name(text: str) -> str:
    return urllib.parse.unquote(text)


def device_short(device_id: str) -> str:
    """The suffix of an imported copy: the last 8 characters of the device id (its random part)."""
    return device_id[-8:]


def _kind_dir(cls: str) -> str:
    return "plans" if cls == "v4" else "legacy-plans"


def _real(path: PathLike) -> Path:
    return Path(os.path.realpath(os.path.abspath(os.path.expanduser(str(path)))))


def _head(root: Path) -> Optional[str]:
    try:
        done = gitutil.git(["rev-parse", "HEAD"], root)
    except WorkspaceError:
        return None
    value = done.stdout.strip() if done.returncode == 0 else ""
    return value if _HEAD.match(value) else None


# ---------------------------------------------------------------------------------------------------- locks

@contextlib.contextmanager
def _migration_lock(project_id: str, env: Env, home: Optional[PathLike]) -> Iterator[None]:
    """The lock of the bridge: ``<workspace state>/migrate-<project_id>.lock``; a second holder is ``MIGRATION_LOCKED``."""
    folder = workspace_state_dir(env, home)
    folder.mkdir(parents=True, exist_ok=True)
    handle = open(folder / f"migrate-{project_id}.lock", "a+")
    try:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise WorkspaceError("MIGRATION_LOCKED", "another migration of this project is running") from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
    finally:
        handle.close()


# --------------------------------------------------------------------------------------------------- discover

def _count_plans(plans: Path) -> Dict[str, int]:
    """Folders and sizes of ``plans/`` by structure only (file content is not read): a folder with a ``plan.json`` counts as
    a plan, any other as legacy."""
    counts = {"v4": 0, "legacy": 0, "files": 0, "bytes": 0}

    def size(directory: str) -> None:
        for entry in os.scandir(directory):
            if entry.is_symlink() or entry.name in IGNORED:
                continue
            if entry.is_dir(follow_symlinks=False):
                size(entry.path)
            elif entry.is_file(follow_symlinks=False):
                counts["files"] += 1
                counts["bytes"] += entry.stat(follow_symlinks=False).st_size

    folders, loose = source_entries(plans)
    for name, path in folders:
        counts["v4" if (path / "plan.json").is_file() else "legacy"] += 1
        with contextlib.suppress(OSError):
            size(str(path))
    for name, path in loose:
        with contextlib.suppress(OSError):
            counts["files"] += 1
            counts["bytes"] += path.lstat().st_size
    return counts


def _registry_paths(env: Env, home: Optional[PathLike]) -> List[Path]:
    """``local_path`` of every project of the maind registry (read as data; an unreadable file gives nothing)."""
    path = state_dir("maind", env=env, home=home) / "registry.json"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        rows = document["projects"]
    except (OSError, UnicodeError, ValueError, KeyError, TypeError):
        return []
    found: List[Path] = []
    for row in rows if isinstance(rows, list) else []:
        value = row.get("local_path") if isinstance(row, dict) else None
        if isinstance(value, str) and os.path.isabs(value):
            found.append(Path(value))
    return found


def _launcher_projects(base: Path) -> List[Path]:
    found: List[Path] = []
    for current, dirs, _files in os.walk(str(base)):
        depth = 0 if current == str(base) else len(Path(current).relative_to(base).parts)
        if os.path.isfile(os.path.join(current, LAUNCHER)):
            found.append(Path(current))
            dirs[:] = []
            continue
        dirs[:] = sorted(name for name in dirs if name not in DISCOVER_SKIP and depth < DISCOVER_DEPTH
                         and not os.path.islink(os.path.join(current, name)))
    return found


def discover(directories: Sequence[PathLike] = (), env: Env = None, home: Optional[PathLike] = None) -> Dict[str, Any]:
    """Checkouts that hold a ``plans/`` folder: launcher projects under ``directories`` (default ``~/projects``) and the
    ``local_path`` of the maind registry. Reads the structure and the sizes, never the content of a plan file."""
    environment = os.environ if env is None else env
    user = Path(str(home)) if home is not None else Path(environment.get("HOME") or Path.home())
    bases = [_real(item) for item in directories] if directories else [_real(user / "projects")]
    found: Dict[Path, set] = {}
    skipped: List[Dict[str, str]] = []
    for base in bases:
        if not base.is_dir():
            skipped.append({"path": str(base), "reason": "missing"})
            continue
        for path in _launcher_projects(base):
            found.setdefault(_real(path), set()).add("launcher")
    for path in _registry_paths(env, home):
        found.setdefault(_real(path), set()).add("registry")
    candidates = []
    for path in sorted(found):
        plans = path / "plans"
        if not path.is_dir() or not plans.is_dir() or plans.is_symlink():
            continue
        row: Dict[str, Any] = {"path": str(path), "name": path.name, "sources": sorted(found[path]), "marker": None}
        try:
            marker = read_marker(path)
            if marker is not None:
                row["marker"] = {"project_id": marker["project_id"], "plans_store": marker["plans_store"]}
        except WorkspaceError as exc:
            row["marker_error"] = exc.code
        row["plans"] = _count_plans(plans)
        candidates.append(row)
    return {"candidates": candidates, "skipped": skipped}


# ------------------------------------------------------------------------------------------------------ plan

class Plan:
    """The dry run of one migration: the public ``document`` and what ``apply`` needs to continue."""

    def __init__(self) -> None:
        self.document: Dict[str, Any] = {}
        self.manifest: Dict[str, Any] = {}
        self.units: List[Dict[str, Any]] = []
        self.root: Path = Path()
        self.ws: Path = Path()
        self.marker: Optional[Dict[str, Any]] = None
        self.project_id: Optional[str] = None
        self.blockers: List[Dict[str, Any]] = []


def _units_of(manifest: Mapping[str, Any]) -> List[Dict[str, Any]]:
    units = [{"name": plan["name"], "class": plan["class"], "files": plan["files"], "bytes": plan["bytes"],
              "digest": plan["digest"], "prefix": plan["name"] + "/", "in_progress": plan.get("in_progress", [])}
             for plan in manifest["plans"]]
    loose = manifest["top_level"]
    if loose:
        units.append({"name": ROOT_NAME, "class": "legacy", "files": loose, "bytes": sum(f["bytes"] for f in loose),
                      "digest": digest_files(loose), "prefix": "", "in_progress": []})
    return units


def _identity(root: Path, ws: Path, yes: bool, plan: Plan) -> Dict[str, Any]:
    """The project of the checkout without writing anything: the marker, else the remote rule of ``attach``."""
    try:
        marker = read_marker(root)
    except WorkspaceError as exc:
        plan.blockers.append({"code": exc.code, "message": exc.message})
        return {"project_id": None, "name": root.name, "origin": "invalid-marker", "marker_store": None}
    plan.marker = marker
    if marker is not None:
        record = read_project(ws, marker["project_id"])
        plan.project_id = marker["project_id"]
        return {"project_id": marker["project_id"], "name": record["name"] if record else root.name,
                "origin": "marker", "marker_store": marker["plans_store"], "in_workspace": record is not None}
    remotes = checkout_remotes(root)
    matches = [record for record in projects._known_projects(ws) if set(record["identity"]["remotes"]) & set(remotes)]
    if len(matches) > 1:
        listing = ", ".join(f"{item['project_id']} ({item['name']})" for item in matches)
        plan.blockers.append({"code": "PROJECT_AMBIGUOUS", "message": f"the remotes of {root.name} match several "
                              f"projects: {listing}; add the marker of the right one to the checkout"})
        return {"project_id": None, "name": root.name, "origin": "ambiguous", "marker_store": None}
    if len(matches) == 1:
        plan.project_id = matches[0]["project_id"]
        return {"project_id": matches[0]["project_id"], "name": matches[0]["name"], "origin": "remote-match",
                "marker_store": None, "needs_confirmation": not yes}
    return {"project_id": None, "name": root.name, "origin": "new", "marker_store": None}


def _workspace_digest(pdir: Optional[Path], relative: str, cls: str) -> Optional[str]:
    return None if pdir is None else folder_digest(pdir / relative, cls)


def _decide(units: List[Dict[str, Any]], pdir: Optional[Path], on_conflict: Optional[str], short: str) -> List[str]:
    """Set ``action`` and ``stored_as`` of every unit from the copy in the workspace (the rule of the bridge); returns the
    names of the plans that conflict."""
    conflicts: List[str] = []
    for unit in units:
        unit["stored_as"] = unit["name"]
        found = _workspace_digest(pdir, f"{_kind_dir(unit['class'])}/{unit['name']}", unit["class"])
        if found is None:
            unit["action"] = "copied"
        elif found == unit["digest"]:
            unit["action"] = "skipped-equal"
        elif on_conflict == "keep-workspace":
            unit["action"] = "kept-workspace"
        elif unit["class"] == "v4" and on_conflict is None:
            unit["action"] = "conflict"
            conflicts.append(unit["name"])
        else:  # import-copy for a plan, the device suffix for opaque folders (contract step 6)
            unit["stored_as"] = f"{unit['name']}~{short}"
            again = _workspace_digest(pdir, f"{_kind_dir(unit['class'])}/{unit['stored_as']}", unit["class"])
            if again is None:
                unit["action"] = "imported-copy"
            elif again == unit["digest"]:
                unit["action"] = "skipped-equal"
            else:
                unit["action"] = "conflict"
                conflicts.append(unit["name"])
    return conflicts


def _scan_units(plans: Path, units: List[Dict[str, Any]], limits: safety.Settings) -> None:
    """Judge every file of every unit by the publish-safety rules as if it stood at its place in the workspace: sets
    ``block``, ``warn`` and ``local_only`` (paths relative to the project folder) on each unit."""
    for unit in units:
        report = safety.Report()
        base = f"{VIRTUAL}{_kind_dir(unit['class'])}/{unit['stored_as']}"
        for entry in unit["files"]:
            version = safety._worktree_version(plans, entry["path"])
            if version is None:
                continue
            rel = f"{base}/{entry['path'][len(unit['prefix']):]}"
            report.files_checked += 1
            safety._scan_version(report, limits, rel, rel.split("/"), version)
        unit["block"] = [dict(item, path=item["path"][len(VIRTUAL):]) for item in report.block]
        unit["warn"] = [dict(item, path=item["path"][len(VIRTUAL):]) for item in report.warn]
        unit["local_only"] = [{"path": item["path"][len(VIRTUAL):], "bytes": item["bytes"], "reason": item["reason"]}
                              for item in sorted(report.local_only, key=lambda entry: entry["path"])]


def _warnings(units: Sequence[Dict[str, Any]], allow_in_progress: bool) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[str]] = {}
    for unit in units:
        if unit["action"] in COPY:
            for item in unit["warn"]:
                grouped.setdefault(item["rule"].replace("-", "_"), []).append(item["path"])
        if allow_in_progress and unit["in_progress"]:
            grouped.setdefault("MIGRATION_IN_PROGRESS", []).extend(unit["in_progress"])
    return [{"code": code, "count": len(paths), "paths": sorted(paths)[:MAX_LISTED]} for code, paths in sorted(grouped.items())]


def build_plan(project: PathLike, on_conflict: Optional[str] = None, allow_in_progress: bool = False, yes: bool = False,
               env: Env = None, home: Optional[PathLike] = None) -> Plan:
    """The dry run for the checkout ``project``: classes, digests, publish-safety, the comparison with the workspace and
    the blockers. Writes nothing (not even a device file or an id)."""
    if on_conflict not in (None, *ON_CONFLICT):
        raise ValueError(f"--on-conflict is {' or '.join(ON_CONFLICT)}")
    plan = Plan()
    plan.root = _real(project)
    if not plan.root.is_dir():
        raise WorkspaceError("BINDING_PATH_MISSING", f"{plan.root} is not a directory")
    plan.ws = layout.root_of(None, env, home)
    layout.require_initialized(plan.ws)
    identity = _identity(plan.root, plan.ws, yes, plan)
    manifest = migrator_port.call("inspect", {"project_root": str(plan.root)}, env, home)
    plan.manifest = manifest
    migrated = identity.get("marker_store") == "workspace"
    units = _units_of(manifest)
    device = read_device(env, home)
    short = device_short(device["device_id"]) if device else "device"
    pdir = project_dir(plan.ws, plan.project_id) if plan.project_id else None
    conflicts: List[str] = []
    limits = safety.load_settings(env, home)
    if not migrated:
        conflicts = _decide(units, pdir, on_conflict, short)
        _scan_units(plan.root / "plans", units, limits)
        if manifest["symlinks"]:
            plan.blockers.append({"code": "MIGRATION_BLOCKED_SYMLINK", "message": "the source holds symlinks or special "
                                  "files, which are never copied", "paths": manifest["symlinks"]})
        secrets = [dict(item, unit=unit["name"]) for unit in units if unit["action"] in COPY + ("conflict",)
                   for item in unit["block"] if item["rule"] == "PS-SECRET"]
        if secrets:
            plan.blockers.append({"code": "MIGRATION_BLOCKED_SECRET", "message": f"{len(secrets)} file(s) look like "
                                  "secrets; remove them from the plans or from the folder before migrating",
                                  "findings": [{key: item[key] for key in ("rule", "path", "detail")}
                                           for item in {entry["path"]: entry for entry in reversed(secrets)}.values()]})
        running = sorted(item for unit in units for item in unit["in_progress"])
        if running and not allow_in_progress:
            plan.blockers.append({"code": "MIGRATION_IN_PROGRESS", "message": f"{len(running)} item(s) are in progress; "
                                  "finish them or repeat with --allow-in-progress", "items": running})
    else:
        for unit in units:
            unit["action"] = "skipped-equal" if _workspace_digest(
                pdir, f"{_kind_dir(unit['class'])}/{unit['name']}", unit["class"]) == unit["digest"] else "conflict"
            unit.update(block=[], warn=[], local_only=[], stored_as=unit["name"])
    plan.units = units
    has_content = pdir is not None and any(
        child.name != ".gitkeep" for kind in ("plans", "legacy-plans") if (pdir / kind).is_dir()
        for child in (pdir / kind).iterdir())
    rows = []
    for unit in units:
        row = {"name": unit["name"], "class": unit["class"], "action": unit["action"], "files": len(unit["files"]),
               "bytes": unit["bytes"], "digest": unit["digest"]}
        if unit["stored_as"] != unit["name"]:
            row["stored_as"] = unit["stored_as"]
        rows.append(row)
    plan.document = {
        "project": identity,
        "mode": "import" if has_content else "initial",
        "source": {"checkout_name": plan.root.name, "head": _head(plan.root)},
        "already_migrated": migrated,
        "plans": rows,
        "conflicts": sorted(conflicts),
        "local_only": [item for unit in units if unit["action"] in COPY for item in unit["local_only"]],
        "warnings": _warnings(units, allow_in_progress),
        "blockers": plan.blockers,
        "manifest_digest": manifest["digest"],
        "ready": not plan.blockers and not conflicts,
    }
    return plan


# ----------------------------------------------------------------------------------------------------- apply

def _refusal(answer: Mapping[str, Any]) -> WorkspaceError:
    extra = []
    for key in ("locked", "changed", "symlinks", "conflicts", "paths"):
        values = answer.get(key)
        if values:
            extra.append(f"{key}: {', '.join(str(item) for item in values[:10])}")
    if answer.get("plans"):
        extra.append("plans: " + ", ".join(str(item.get("name")) for item in answer["plans"][:10]))
    detail = f" ({'; '.join(extra)})" if extra else ""
    return WorkspaceError(str(answer.get("code") or "MIGRATION_FAILED"),
                          f"{answer.get('message', 'the migration stopped')}{detail} [phase {answer.get('phase')}]")


_TIME = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")


def report_issues(document: Any) -> List[str]:
    """Issues of a migration report against ``workspace-migration/v1``. ``rolled_back_at`` (added to the contract with the
    rollback) is checked here by hand, so that a foundation that predates it still reads the report."""
    if not isinstance(document, dict):
        return ["not an object"]
    body = {key: value for key, value in document.items() if key != "rolled_back_at"}
    issues = validate_document("workspace-migration", body)
    if "rolled_back_at" in document and not (isinstance(document["rolled_back_at"], str)
                                             and _TIME.match(document["rolled_back_at"])):
        issues.append("rolled_back_at: not a UTC time")
    return issues


def _report_document(op_id: str, project_id: str, device_id: str, started: str, plan: Plan, answer: Mapping[str, Any],
                     local_only: int, codes: Sequence[str]) -> Dict[str, Any]:
    return {"$schema": REPORT_SCHEMA, "op_id": op_id, "project_id": project_id, "device_id": device_id,
            "started_at": started, "finished_at": utc_now(), "mode": answer.get("mode", plan.document["mode"]),
            "source": plan.document["source"],
            "plans": [{"name": encode_name(row["name"]), "class": row["class"], "action": row["action"],
                       "files": row["files"], "bytes": row["bytes"], "digest": row["digest"]}
                      for row in answer["plans"]],
            "local_only": local_only, "warnings": sorted(set(codes))}


def _record_local_only(ws: Path, project_id: str, device_id: str, plan: Plan, answer: Mapping[str, Any]) -> int:
    """Index the big files this migration brought in and rebuild the exclude block; returns how many it added."""
    by_name = {unit["name"]: unit for unit in plan.units}
    added: Dict[str, str] = {}
    for row in answer["plans"]:
        unit = by_name.get(row["name"])
        if unit is None or row["action"] not in COPY:
            continue
        stored = row.get("stored_as", row["name"])
        for item in unit["local_only"]:
            inner = item["path"][len(f"{_kind_dir(unit['class'])}/{unit['stored_as']}/"):]
            added[f"{_kind_dir(unit['class'])}/{stored}/{inner}"] = item["reason"]
    if not added:
        return 0
    mine = [{"path": item["path"], "reason": item["reason"]} for item in localonly.read(ws, project_id)["files"]
            if item["device_id"] == device_id and item["path"] not in added]
    entries = mine + [{"path": path, "reason": reason} for path, reason in sorted(added.items())]
    localonly.update(ws, project_id, entries, device_id)
    localonly.rebuild_exclude(ws, device_id)
    return len(added)


def apply(project: PathLike, on_conflict: Optional[str] = None, lock_timeout: int = 30,
          allow_in_progress: bool = False, yes: bool = False, env: Env = None,
          home: Optional[PathLike] = None) -> Dict[str, Any]:
    """Migrate the plans of a checkout into the workspace; returns the result for the command.

    The checks of ``plan`` run first: a blocker or an unresolved conflict is refused before the port is called. The port
    runs the critical section; afterwards the local-only index, the report, the binding are written (the caller emits the
    event and prints ``next``). A repeat after a full migration is ``noop`` and writes no report.
    """
    plan = build_plan(project, on_conflict, allow_in_progress, yes, env, home)
    if plan.blockers:
        first = plan.blockers[0]
        raise WorkspaceError(first["code"], first["message"])
    if plan.document["conflicts"]:
        raise WorkspaceError("MIGRATION_CONFLICT", f"{len(plan.document['conflicts'])} plan(s) differ from the "
                             f"workspace ({', '.join(plan.document['conflicts'][:10])}); repeat with "
                             f"--on-conflict keep-workspace or import-copy")
    root, ws = plan.root, plan.ws
    attached: Optional[Dict[str, Any]] = None
    if not plan.document["already_migrated"] and plan.units:
        if plan.marker is None or read_project(ws, plan.marker["project_id"]) is None:
            attached = projects.attach(root, yes=yes, env=env, home=home)
            plan.project_id = attached["project_id"]
            if attached["plans_store"] == "workspace":  # the plans folder holds only loose files: still to move
                write_marker(root, plan.project_id, "legacy")
    project_id = plan.project_id
    device = read_device(env, home) or layout._ensure_device(env, home)
    op_id = new_id("mig")
    started = utc_now()
    result: Dict[str, Any] = {"project_id": project_id, "op_id": op_id, "noop": False, "attached": attached}
    if project_id is None:  # nothing to migrate and no project yet
        result.update(noop=True, mode=plan.document["mode"], plans=[], op_id=None, next=[])
        return result
    answer = migrator_port.call("apply", {
        "project_root": str(root), "workspace_root": str(ws), "project_id": project_id, "op_id": op_id,
        "manifest": plan.manifest, "mode": plan.document["mode"], "on_conflict": on_conflict,
        "device_short": device_short(device["device_id"]), "lock_timeout_s": lock_timeout}, env, home)
    if answer.get("result") == "refused":
        raise _refusal(answer)
    bind(project_id, root, env, home)
    if answer.get("result") == "noop":
        result.update(noop=True, mode=answer.get("mode"), plans=answer["plans"], op_id=None, next=[])
        return result
    codes = [item["code"] for item in plan.document["warnings"]]
    notes: List[str] = []
    with gitutil.git_lock(env, home):
        try:
            recorded = _record_local_only(ws, project_id, device["device_id"], plan, answer)
        except (ValueError, WorkspaceError, OSError) as exc:
            recorded = 0
            codes.append("LOCAL_ONLY_NOT_RECORDED")
            notes.append(f"local-only files were not indexed: {getattr(exc, 'code', type(exc).__name__)}")
        document = _report_document(op_id, project_id, device["device_id"], started, plan, answer, recorded, codes)
        issues = report_issues(document)
        if issues:
            raise WorkspaceError("WORKSPACE_LAYOUT_INVALID", f"the migration report is invalid: {issues[0]}")
        report_path = project_dir(ws, project_id) / "migrations" / f"{op_id}.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(report_path, json.dumps(document, indent=2, ensure_ascii=False) + "\n")
    quoted = shlex.quote(str(root))
    result.update(mode=document["mode"], plans=answer["plans"], local_only=recorded, warnings=document["warnings"],
                  notes=notes, report=f"projects/{project_id}/migrations/{op_id}.json",
                  next=[f"git -C {quoted} add .swissknifeman/project.json && git -C {quoted} commit -m "
                        f"'chore: plans are stored in the portable workspace'",
                        "swissknifeman workspace sync"])
    return result


# -------------------------------------------------------------------------------------- reports of the project

def _project_of(root: Path) -> Tuple[Dict[str, Any], str]:
    marker = read_marker(root)
    if marker is None:
        raise WorkspaceError("PROJECT_UNKNOWN", f"{root} has no project marker; nothing was migrated from it")
    return marker, marker["project_id"]


def last_report(ws: Path, project_id: str, device_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """The newest valid migration report of a project (by start time, then id), of ``device_id`` when given; ``None``
    without any. A report names the checkout of one device: the reports of other devices say nothing about this one."""
    folder = project_dir(ws, project_id) / "migrations"
    found: List[Dict[str, Any]] = []
    try:
        names = sorted(child for child in folder.iterdir() if child.suffix == ".json")
    except OSError:
        return None
    for path in names:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            continue
        if isinstance(document, dict) and not report_issues(document) \
                and (device_id is None or document["device_id"] == device_id):
            found.append(document)
    return max(found, key=lambda item: (item["started_at"], item["op_id"])) if found else None


def _this_device(env: Env, home: Optional[PathLike]) -> Optional[str]:
    device = read_device(env, home)
    return device["device_id"] if device else None


def _copy_name(row: Mapping[str, Any], name: str, device_id: str) -> str:
    return f"{name}~{device_short(device_id)}" if row["action"] == "imported-copy" else name


def _workspace_state(pdir: Path, row: Mapping[str, Any], name: str, device_id: str) -> Optional[str]:
    return folder_digest(pdir / _kind_dir(row["class"]) / _copy_name(row, name, device_id), row["class"])


def _source_state(root: Path, row: Mapping[str, Any], name: str) -> Optional[str]:
    plans = root / "plans"
    if name == ROOT_NAME:
        return _loose_digest(source_entries(plans)[1])
    return folder_digest(plans / name, row["class"])


def verify(project: PathLike, env: Env = None, home: Optional[PathLike] = None) -> Dict[str, Any]:
    """Digest of the workspace copies and of the old folders against the last report of the project."""
    root = _real(project)
    ws = layout.root_of(None, env, home)
    layout.require_initialized(ws)
    _marker, project_id = _project_of(root)
    report = last_report(ws, project_id, _this_device(env, home))
    if report is None:
        raise WorkspaceError("MIGRATION_NOT_APPLIED", f"project {project_id} has no migration report of this device")
    pdir = project_dir(ws, project_id)
    undone = "rolled_back_at" in report  # the copies were removed on purpose: only the old folders can still be compared
    rows = []
    for row in report["plans"]:
        name = decode_name(row["name"])
        compared = row["action"] != "kept-workspace" and not undone
        in_workspace = _workspace_state(pdir, row, name, report["device_id"]) if compared else None
        old = _source_state(root, row, name)
        if compared and in_workspace != row["digest"]:
            state = "changed-in-workspace"
        elif old is None:
            state = "legacy-removed"
        elif old != row["digest"]:
            state = "changed-in-legacy"
        else:
            state = "equal"
        rows.append({"name": name, "class": row["class"], "action": row["action"], "state": state})
    return {"project_id": project_id, "op_id": report["op_id"], "rolled_back": undone,
            "all_equal": all(item["state"] == "equal" for item in rows), "plans": rows}


# --------------------------------------------------------------------------------------------------- rollback

def _workspace_extras(pdir: Path, known: Sequence[str]) -> List[str]:
    """Plan folders of ``plans/`` that no row of the report accounts for."""
    plans = pdir / "plans"
    found: List[str] = []
    for parent, prefix in ((plans, ""), (plans / ARCHIVE, ARCHIVE + "/")):
        try:
            children = sorted(child for child in parent.iterdir() if child.is_dir())
        except OSError:
            continue
        found.extend(prefix + child.name for child in children if not (not prefix and child.name == ARCHIVE))
    return [name for name in found if name not in known]


def rollback(project: PathLike, env: Env = None, home: Optional[PathLike] = None) -> Dict[str, Any]:
    """Undo the last migration: marker back to ``legacy``, the folders it put into the workspace removed.

    Refused (``MIGRATION_DIVERGED`` with the list) when a plan of the report changed in the workspace or the old folder
    is gone or changed; nothing is touched then. A folder that was already in the workspace (``skipped-equal``,
    ``kept-workspace``) stays.
    """
    root = _real(project)
    ws = layout.root_of(None, env, home)
    layout.require_initialized(ws)
    marker, project_id = _project_of(root)
    report = last_report(ws, project_id, _this_device(env, home))
    if marker["plans_store"] != "workspace" or report is None or "rolled_back_at" in report:
        raise WorkspaceError("MIGRATION_NOT_APPLIED", f"project {project_id} has no applied migration to roll back")
    pdir = project_dir(ws, project_id)
    device_id = report["device_id"]
    diverged: List[str] = []
    stored: List[str] = []
    for row in report["plans"]:
        name = decode_name(row["name"])
        if row["action"] != "kept-workspace":
            if _workspace_state(pdir, row, name, device_id) != row["digest"]:
                diverged.append(f"{name} (changed-in-workspace)")
            elif row["class"] == "v4":
                stored.append(_copy_name(row, name, device_id))
        old = _source_state(root, row, name)
        if old is None:
            diverged.append(f"{name} (legacy-removed)")
        elif old != row["digest"]:
            diverged.append(f"{name} (changed-in-legacy)")
    if report["mode"] == "initial":
        diverged.extend(f"{name} (added-in-workspace)" for name in _workspace_extras(pdir, stored))
    if diverged:
        raise WorkspaceError("MIGRATION_DIVERGED", f"{len(diverged)} plan(s) differ from the report {report['op_id']}: "
                             f"{', '.join(diverged[:10])}{' ...' if len(diverged) > 10 else ''}")
    removed: List[str] = []
    with _migration_lock(project_id, env, home), gitutil.git_lock(env, home):
        write_marker(root, project_id, "legacy")
        staging = ws / ".staging" / f"rollback-{report['op_id']}"
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)
        moved: List[str] = []
        for row in report["plans"]:
            if row["action"] not in COPY:
                continue
            relative = f"{_kind_dir(row['class'])}/{_copy_name(row, decode_name(row['name']), device_id)}"
            target = pdir / relative
            if target.is_dir():
                destination = staging / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.rename(target, destination)
                moved.append(relative)
        shutil.rmtree(staging)
        removed = moved
        for kind in ("plans", "legacy-plans"):
            with contextlib.suppress(OSError):
                (pdir / kind / ARCHIVE).rmdir()
        if moved:
            _drop_local_only(ws, project_id, device_id, moved)
        report = dict(report, rolled_back_at=utc_now())
        issues = report_issues(report)
        if issues:
            raise WorkspaceError("WORKSPACE_LAYOUT_INVALID", f"the migration report is invalid: {issues[0]}")
        atomic_write_text(pdir / "migrations" / f"{report['op_id']}.json",
                          json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    quoted = shlex.quote(str(root))
    return {"project_id": project_id, "op_id": report["op_id"], "rolled_back": True, "removed": sorted(removed),
            "next": [f"git -C {quoted} add .swissknifeman/project.json && git -C {quoted} commit -m "
                     f"'chore: plans are stored in the checkout again'", "swissknifeman workspace sync"]}


def _drop_local_only(ws: Path, project_id: str, device_id: str, removed: Sequence[str]) -> None:
    gone = tuple(f"{item}/" for item in removed)
    entries = [{"path": item["path"], "reason": item["reason"]} for item in localonly.read(ws, project_id)["files"]
               if item["device_id"] == device_id and not item["path"].startswith(gone)]
    localonly.update(ws, project_id, entries, device_id)
    localonly.rebuild_exclude(ws, device_id)


# ---------------------------------------------------------------------------------------------------- cleanup

def _plans_tracked(root: Path) -> Optional[bool]:
    """Whether the git index of the checkout lists a path below ``plans/``, read from ``.git/index`` (versions 2 and 3)
    without running git; ``None`` when that cannot be told."""
    git_dir = root / ".git"
    if not git_dir.exists():
        return False
    if git_dir.is_dir() and not (git_dir / "index").exists():
        return False  # a repository that has not added anything yet
    try:
        data = (git_dir / "index").read_bytes()
        version, count = int.from_bytes(data[4:8], "big"), int.from_bytes(data[8:12], "big")
        if data[:4] != b"DIRC" or version not in (2, 3):
            return None
        position = 12
        for _ in range(count):
            flags = int.from_bytes(data[position + 60:position + 62], "big")
            fixed = 62 + (2 if version == 3 and flags & 0x4000 else 0)
            end = data.index(b"\0", position + fixed)
            if data[position + fixed:end].startswith(b"plans/"):
                return True
            position += (fixed + (end - position - fixed) + 8) & ~7
    except (OSError, ValueError, IndexError):
        return None
    return False


def cleanup(project: PathLike, confirm: str, env: Env = None, home: Optional[PathLike] = None) -> Dict[str, Any]:
    """Remove the old folders whose copy in the workspace has the same digest; others are kept with the reason.

    ``confirm`` must be the project id of the marker (``CLEANUP_CONFIRM_MISMATCH``). Runs no git command; the commit that
    stops tracking ``plans/`` is printed as ``next``.
    """
    root = _real(project)
    ws = layout.root_of(None, env, home)
    layout.require_initialized(ws)
    marker, project_id = _project_of(root)
    if confirm != project_id:
        raise WorkspaceError("CLEANUP_CONFIRM_MISMATCH", f"--confirm {confirm} is not the project id of this checkout")
    if marker["plans_store"] != "workspace":
        raise WorkspaceError("MIGRATION_NOT_APPLIED", f"project {project_id} still keeps its plans in the checkout; "
                             "run migrate apply first")
    pdir = project_dir(ws, project_id)
    device = read_device(env, home)
    shorts = {device_short(device["device_id"])} if device else set()
    plans = root / "plans"
    tracked = _plans_tracked(root)
    folders, loose = source_entries(plans)
    removed: List[str] = []
    kept: List[Dict[str, str]] = []

    def copies(cls: str, name: str) -> List[Optional[str]]:
        return [folder_digest(pdir / _kind_dir(cls) / candidate, cls) for candidate in
                [name, *(f"{name}~{short}" for short in sorted(shorts))]]

    for name, path in folders:
        if path.is_symlink():
            kept.append({"name": name, "reason": "symlink"})
            continue
        cls = _classify(path)
        files, symlinks = scan_folder(path, cls)
        if symlinks:
            kept.append({"name": name, "reason": "symlink-inside"})
            continue
        found = copies(cls, name)
        mine = digest_files(files)
        if mine in found:
            shutil.rmtree(path)
            removed.append(name)
        elif all(item is None for item in found):
            kept.append({"name": name, "reason": "workspace-copy-missing"})
        else:
            kept.append({"name": name, "reason": "workspace-copy-differs"})
    plain = [(name, path) for name, path in loose if path.is_file() and not path.is_symlink()]
    kept.extend({"name": name, "reason": "symlink"} for name, path in loose if path.is_symlink())
    if plain:
        mine = _loose_digest(plain)
        found = copies("legacy", ROOT_NAME)
        if mine in found:
            for name, path in plain:
                path.unlink()
                removed.append(name)
        else:
            reason = "workspace-copy-missing" if all(item is None for item in found) else "workspace-copy-differs"
            kept.extend({"name": name, "reason": reason} for name, _path in plain)
    plans_removed = _remove_if_empty(plans)
    doc: Dict[str, Any] = {"project_id": project_id, "removed": sorted(removed), "kept": kept,
                           "plans_removed": plans_removed, "next": []}
    if removed and tracked is not False:
        command = (f"git -C {shlex.quote(str(root))} rm -r --cached plans && git -C {shlex.quote(str(root))} commit -m "
                   "\"chore(skm): планы перенесены в portable workspace\"")
        doc["next"].append(command if tracked else f"if plans/ was tracked by git: {command}")
    return doc


def _remove_if_empty(plans: Path) -> bool:
    """Remove ``plans/archive`` and then ``plans`` when nothing but ignorable files is left in them; whether ``plans`` is gone."""
    for folder in (plans / ARCHIVE, plans):
        try:
            names = os.listdir(folder)
        except OSError:
            continue
        if all(name in IGNORED for name in names):
            shutil.rmtree(folder)
    return not plans.exists()
