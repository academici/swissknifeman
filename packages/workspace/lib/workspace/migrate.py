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
import time
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
SECRET_REASON = "secret-pattern"  # reason of a local-only file kept out of git by ``--local-only-secrets``
SECRET_WARNING = "PS_SECRET_LOCAL_ONLY"
MAX_LISTED = 5
PLAN_LOCK_TIMEOUT_S = 30.0
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
        if parent.is_symlink():  # a symlinked container is never entered; ``plans/archive`` then stays a loose symlink
            continue
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


def _valid_rel(name: str) -> bool:
    """A folder name of a report: ``<id>`` or ``archive/<id>``, no empty, ``.`` or ``..`` part, no NUL."""
    parts = name.split("/")
    if not 1 <= len(parts) <= 2 or (len(parts) == 2 and parts[0] != ARCHIVE):
        return False
    return all(part not in ("", ".", "..") and "\0" not in part for part in parts)


def _report_name(row: Mapping[str, Any]) -> str:
    """The folder name of a report row, decoded; a name that could leave its plan folder is ``MIGRATION_REPORT_INVALID``."""
    name = decode_name(row["name"])
    if not _valid_rel(name):
        raise WorkspaceError("MIGRATION_REPORT_INVALID", f"the migration report names a folder that is not a plan "
                             f"folder name: {row['name']}")
    return name


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


def _identity(root: Path, ws: Path, yes: bool, plan: Plan, code: Optional[str] = None) -> Dict[str, Any]:
    """The project of the checkout without writing anything: the marker, else the remote rule of ``attach``."""
    try:
        marker = read_marker(root)
    except WorkspaceError as exc:
        plan.blockers.append({"code": exc.code, "message": exc.message})
        return {"project_id": None, "name": root.name, "origin": "invalid-marker", "marker_store": None}
    plan.marker = marker
    if marker is not None:
        workspace = layout.require_initialized(ws)["code"]
        if marker["workspace"] != workspace:
            plan.blockers.append({"code": "WORKSPACE_MISMATCH", "message": f"the marker names the workspace "
                                  f"{marker['workspace']!r}, this command works with {workspace!r} (--workspace)"})
            return {"project_id": marker["project_id"], "name": root.name, "origin": "other-workspace",
                    "marker_store": marker["plans_store"]}
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
    proposed = code or projects.slug(root.name)
    if read_project(ws, proposed) is not None:
        plan.blockers.append({"code": "PROJECT_CODE_TAKEN", "message": f"the workspace already has a project "
                              f"{proposed!r} with other remotes; choose another code with --code"})
    return {"project_id": None, "name": root.name, "origin": "new", "marker_store": None, "proposed_code": proposed}


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


def _keep_secrets_local(unit: Dict[str, Any]) -> None:
    """``--local-only-secrets``: a file that only has a ``PS-SECRET`` finding of its *content* is not a blocker but a local-only
    file of reason ``secret-pattern``. A file with a secret *name* (``.env``, ``*.pem``, ...) keeps blocking, and so does a
    finding whose path cannot be told from the real file (a name that is not UTF-8)."""
    base = f"{_kind_dir(unit['class'])}/{unit['stored_as']}"
    sizes = {f"{base}/{entry['path'][len(unit['prefix']):]}": entry["bytes"] for entry in unit["files"]}
    named = {item["path"] for item in unit["block"] if item["rule"] == "PS-SECRET"
             and safety.is_secret_name(item["path"].rsplit("/", 1)[-1])}
    moved = {item["path"] for item in unit["block"] if item["rule"] == "PS-SECRET" and item["path"] not in named
             and item["path"] in sizes}
    if not moved:
        return
    unit["block"] = [item for item in unit["block"] if not (item["rule"] == "PS-SECRET" and item["path"] in moved)]
    unit["warn"] = [item for item in unit["warn"] if item["path"] not in moved]  # the file stays on this machine
    unit["local_only"] = sorted(unit["local_only"] + [{"path": path, "bytes": sizes[path], "reason": SECRET_REASON}
                                                      for path in moved], key=lambda entry: entry["path"])


def _scan_units(plans: Path, units: List[Dict[str, Any]], limits: safety.Settings, local_only_secrets: bool = False) -> None:
    """Judge every file of every unit by the publish-safety rules as if it stood at its place in the workspace: sets
    ``block``, ``warn`` and ``local_only`` (paths relative to the project folder) on each unit. With ``local_only_secrets``
    the files with a secret-pattern finding become local-only files (see :func:`_keep_secrets_local`)."""
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
        if local_only_secrets:
            _keep_secrets_local(unit)


def _warnings(units: Sequence[Dict[str, Any]], allow_in_progress: bool) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[str]] = {}
    for unit in units:
        if unit["action"] in COPY:
            for item in unit["warn"]:
                grouped.setdefault(item["rule"].replace("-", "_"), []).append(item["path"])
        if unit["action"] in COPY + ("skipped-equal",):
            secret_paths = [item["path"] for item in unit["local_only"] if item["reason"] == SECRET_REASON]
            if secret_paths:
                grouped.setdefault(SECRET_WARNING, []).extend(secret_paths)
        if allow_in_progress and unit["in_progress"]:
            grouped.setdefault("MIGRATION_IN_PROGRESS", []).extend(unit["in_progress"])
    return [{"code": code, "count": len(paths), "paths": sorted(paths)[:MAX_LISTED]} for code, paths in sorted(grouped.items())]


def build_plan(project: PathLike, on_conflict: Optional[str] = None, allow_in_progress: bool = False, yes: bool = False,
               env: Env = None, home: Optional[PathLike] = None, local_only_secrets: bool = False,
               code: Optional[str] = None) -> Plan:
    """The dry run for the checkout ``project``: classes, digests, publish-safety, the comparison with the workspace and
    the blockers. Writes nothing (not even a device file or an id).

    ``local_only_secrets``: a file whose content matches a secret pattern is no blocker; it is migrated like a big file
    (local-only, reason ``secret-pattern``) and counted in the warning ``PS_SECRET_LOCAL_ONLY``. Secret file names and
    symlinks keep blocking."""
    if on_conflict not in (None, *ON_CONFLICT):
        raise ValueError(f"--on-conflict is {' or '.join(ON_CONFLICT)}")
    plan = Plan()
    plan.root = _real(project)
    if not plan.root.is_dir():
        raise WorkspaceError("BINDING_PATH_MISSING", f"{plan.root} is not a directory")
    plan.ws = layout.root_of(None, env, home)
    layout.require_initialized(plan.ws)
    identity = _identity(plan.root, plan.ws, yes, plan, code)
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
        _scan_units(plan.root / "plans", units, limits, local_only_secrets)
        if manifest["symlinks"]:
            plan.blockers.append({"code": "MIGRATION_BLOCKED_SYMLINK", "message": "the source holds symlinks or special "
                                  "files, which are never copied", "paths": manifest["symlinks"]})
        secrets = [dict(item, unit=unit["name"]) for unit in units if unit["action"] in COPY + ("conflict",)
                   for item in unit["block"] if item["rule"] == "PS-SECRET"]
        if secrets:
            plan.blockers.append({"code": "MIGRATION_BLOCKED_SECRET", "message": f"{len(secrets)} file(s) look like "
                                  "secrets; remove them from the plans or from the folder before migrating, or repeat "
                                  "with --local-only-secrets to keep the files with a secret pattern on this machine",
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
    stored_as: List[Any] = []
    if isinstance(body.get("plans"), list):  # ``stored_as`` (where a suffixed copy lives) is checked here by hand as well
        rows = [dict(row) if isinstance(row, dict) else row for row in body["plans"]]
        stored_as = [row.pop("stored_as") for row in rows if isinstance(row, dict) and "stored_as" in row]
        body = dict(body, plans=rows)
    issues = validate_document("workspace-migration", body)
    issues.extend("plans.stored_as: not a folder name" for value in stored_as
                  if not isinstance(value, str) or not _valid_rel(decode_name(value)))
    if "rolled_back_at" in document and not (isinstance(document["rolled_back_at"], str)
                                             and _TIME.match(document["rolled_back_at"])):
        issues.append("rolled_back_at: not a UTC time")
    return issues


def _report_row(row: Mapping[str, Any]) -> Dict[str, Any]:
    document = {"name": encode_name(row["name"]), "class": row["class"], "action": row["action"],
                "files": row["files"], "bytes": row["bytes"], "digest": row["digest"]}
    if row.get("stored_as") and row["stored_as"] != row["name"]:
        document["stored_as"] = encode_name(row["stored_as"])
    return document


def _report_document(op_id: str, project_id: str, device_id: str, started: str, plan: Plan, answer: Mapping[str, Any],
                     local_only: int, codes: Sequence[str]) -> Dict[str, Any]:
    return {"$schema": REPORT_SCHEMA, "op_id": op_id, "project_id": project_id, "device_id": device_id,
            "started_at": started, "finished_at": utc_now(), "mode": answer.get("mode", plan.document["mode"]),
            "source": plan.document["source"],
            "plans": [_report_row(row) for row in answer["plans"]],
            "local_only": local_only, "warnings": sorted(set(codes))}


def _record_local_only(ws: Path, project_id: str, device_id: str, plan: Plan, answer: Mapping[str, Any]) -> int:
    """Index the local-only files (big ones, and secret-pattern ones) this migration brought in and rebuild the exclude block;
    returns how many it added."""
    by_name = {unit["name"]: unit for unit in plan.units}
    pdir = project_dir(ws, project_id)
    added: Dict[str, str] = {}
    for row in answer["plans"]:
        unit = by_name.get(row["name"])
        if unit is None or row["action"] not in COPY + ("skipped-equal",):
            continue
        stored = row.get("stored_as", row["name"])
        for item in unit["local_only"]:
            # a repeat after a stop between the rename and the index finds the folder equal (``skipped-equal``): the secret-pattern
            # files, which no later scan repairs, are indexed now; big files are found again by the next ``sync``
            if row["action"] == "skipped-equal" and item["reason"] != SECRET_REASON:
                continue
            inner = item["path"][len(f"{_kind_dir(unit['class'])}/{unit['stored_as']}/"):]
            path = f"{_kind_dir(unit['class'])}/{stored}/{inner}"
            if row["action"] == "skipped-equal" and not (pdir / path).is_file():
                continue
            added[path] = item["reason"]
    if not added:
        return 0
    mine = [{"path": item["path"], "reason": item["reason"]} for item in localonly.read(ws, project_id)["files"]
            if item["device_id"] == device_id and item["path"] not in added]
    entries = mine + [{"path": path, "reason": reason} for path, reason in sorted(added.items())]
    localonly.update(ws, project_id, entries, device_id)
    localonly.rebuild_exclude(ws, device_id)
    return len(added)


def _intent_path(project_id: str, op_id: str, env: Env, home: Optional[PathLike]) -> Path:
    """One intent file per operation: a second apply never overwrites or removes the intent of the first."""
    return workspace_state_dir(env, home) / f"migrate-{project_id}.{op_id}.intent.json"


def _write_intent(path: Path, op_id: str, started: str, device_id: str, plan: Plan) -> None:
    """What the report and the local-only index need, kept on this device until they are written. It is ``confirmed`` only
    when the answer of the bridge (its real decisions) has been added by ``_confirm_intent``."""
    document = {"op_id": op_id, "started_at": started, "device_id": device_id, "mode": plan.document["mode"],
                "source": plan.document["source"], "codes": [item["code"] for item in plan.document["warnings"]],
                "plans": [dict(row) for row in plan.document["plans"]], "confirmed": False,
                "units": [{key: unit[key] for key in ("name", "class", "stored_as", "local_only")} for unit in plan.units]}
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(document, indent=2, ensure_ascii=False) + "\n")


def _confirm_intent(path: Path, answer: Mapping[str, Any]) -> None:
    """Replace the plan-time rows by the rows the bridge answered (its actions and ``stored_as``), right after it returns."""
    with contextlib.suppress(OSError, UnicodeError, ValueError, KeyError, TypeError):
        document = json.loads(path.read_text(encoding="utf-8"))
        document.update(plans=[dict(row) for row in answer["plans"]], mode=answer.get("mode", document["mode"]),
                        confirmed=True)
        atomic_write_text(path, json.dumps(document, indent=2, ensure_ascii=False) + "\n")


def _read_intent(project_id: str, device_id: str, ws: Path, answer: Mapping[str, Any], env: Env, home: Optional[PathLike]):
    """``(path, op_id, started, plan, answer, codes)`` of the newest confirmed intent of this device whose report is
    missing and whose folders are the ones the bridge found, or ``None``. An unconfirmed intent holds only the plan-time
    decisions, which the bridge may have changed, so it is never used."""
    found = []
    for path in workspace_state_dir(env, home).glob(f"migrate-{project_id}.*.intent.json"):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            if (document["confirmed"] is True and document["device_id"] == device_id and isinstance(document["plans"], list)
                    and {(row["name"], row["digest"]) for row in document["plans"]}
                    == {(row["name"], row["digest"]) for row in answer["plans"]}
                    and not (project_dir(ws, project_id) / "migrations" / f"{document['op_id']}.json").exists()):
                found.append((document["started_at"], document["op_id"], path, document))
        except (OSError, UnicodeError, ValueError, KeyError, TypeError):
            continue
    if not found:
        return None
    _started, _op, path, document = max(found, key=lambda item: item[:2])
    plan = Plan()
    plan.units = document["units"]
    plan.document = {"mode": document["mode"], "source": document["source"]}
    return (path, document["op_id"], document["started_at"], plan,
            {"mode": document["mode"], "plans": document["plans"]}, list(document["codes"]))


def apply(project: PathLike, on_conflict: Optional[str] = None, lock_timeout: int = 30,
          allow_in_progress: bool = False, yes: bool = False, env: Env = None,
          home: Optional[PathLike] = None, local_only_secrets: bool = False,
          code: Optional[str] = None) -> Dict[str, Any]:
    """Migrate the plans of a checkout into the workspace; returns the result for the command. ``code`` is the project code
    of a project the workspace does not know yet (default: made from the folder name).

    The checks of ``plan`` run first: a blocker or an unresolved conflict is refused before the port is called. The port
    runs the critical section; afterwards the local-only index, the report, the binding are written (the caller emits the
    event and prints ``next``). A repeat after a full migration is ``noop`` and writes no report. ``local_only_secrets``
    is the flag of :func:`build_plan`; the port copies the files as it copies every other file.
    """
    plan = build_plan(project, on_conflict, allow_in_progress, yes, env, home, local_only_secrets, code)
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
            attached = projects.attach(root, yes=yes, env=env, home=home, code=code)
            plan.project_id = attached["project_id"]
            if attached["plans_store"] == "workspace":  # the plans folder holds only loose files: still to move
                write_marker(root, attached["workspace"], plan.project_id, "legacy")
    project_id = plan.project_id
    device = read_device(env, home) or layout._ensure_device(env, home)
    op_id = new_id("mig")
    started = utc_now()
    result: Dict[str, Any] = {"project_id": project_id, "op_id": op_id, "noop": False, "attached": attached}
    if project_id is None:  # nothing to migrate and no project yet
        result.update(noop=True, mode=plan.document["mode"], plans=[], op_id=None, next=[])
        return result
    intent_path = _intent_path(project_id, op_id, env, home)  # this call's own file; it is the only one it removes
    written = not plan.document["already_migrated"]
    if written:
        _write_intent(intent_path, op_id, started, device["device_id"], plan)
    finished = [intent_path]
    answer = migrator_port.call("apply", {
        "project_root": str(root), "workspace_root": str(ws), "project_id": project_id, "op_id": op_id,
        "manifest": plan.manifest, "mode": plan.document["mode"], "on_conflict": on_conflict,
        "device_short": device_short(device["device_id"]), "lock_timeout_s": lock_timeout}, env, home)
    if answer.get("result") == "refused":
        with contextlib.suppress(OSError):
            intent_path.unlink()
        raise _refusal(answer)
    if written and answer.get("result") != "noop":
        _confirm_intent(intent_path, answer)
    bind(project_id, root, env, home)
    codes = [item["code"] for item in plan.document["warnings"]]
    if answer.get("result") == "noop":
        pending = _read_intent(project_id, device["device_id"], ws, answer, env, home)
        if pending is None:
            with contextlib.suppress(OSError):
                intent_path.unlink()
            result.update(noop=True, mode=answer.get("mode"), plans=answer["plans"], op_id=None, next=[])
            return result
        # an earlier call switched the marker and stopped before the report: write the metadata it still owes
        recovered, op_id, started, plan, answer, codes = pending
        finished.append(recovered)
        result["op_id"] = op_id
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
    for path in finished:
        with contextlib.suppress(OSError):
            path.unlink()
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
    """The name of the row's folder in the workspace: ``stored_as`` of the report when it has one."""
    stored = row.get("stored_as")
    if stored is not None:
        decoded = decode_name(stored)
        if not _valid_rel(decoded) or not (decoded == name or decoded.startswith(f"{name}~")):
            raise WorkspaceError("MIGRATION_REPORT_INVALID", f"the migration report places {row['name']} at {stored}")
        return decoded
    if row["action"] != "imported-copy":
        return name
    short = device_short(device_id)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", short):
        raise WorkspaceError("MIGRATION_REPORT_INVALID", "the migration report names an invalid device")
    return f"{name}~{short}"


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
        name = _report_name(row)
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


def _lock_folders(stack: contextlib.ExitStack, folders: Sequence[Path], timeout: float = PLAN_LOCK_TIMEOUT_S) -> None:
    """The ``PlanLock`` of the planner (``flock`` on ``<plan>/.lock``) of every folder, in the order of the sorted paths, so
    that a running planner command finishes before the folder is removed; ``MIGRATION_LOCKED`` after ``timeout`` seconds."""
    for folder in sorted(folders, key=str):
        handle = open(folder / ".lock", "a+")
        stack.callback(handle.close)
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise WorkspaceError("MIGRATION_LOCKED", f"plan {folder.name} is held by another process") from None
                time.sleep(0.05)


def rollback(project: PathLike, env: Env = None, home: Optional[PathLike] = None) -> Dict[str, Any]:
    """Undo the last migration: marker back to ``legacy``, the folders it put into the workspace removed.

    Refused (``MIGRATION_DIVERGED`` with the list) when a plan of the report changed in the workspace or the old folder
    is gone or changed; nothing is touched then. A folder that was already in the workspace (``skipped-equal``,
    ``kept-workspace``) stays. Everything runs under the migration lock and the lock of every plan that is removed; a
    failure before the marker is switched puts the folders back, a failure after it is finished by a repeated call (the
    marker is ``legacy``, the copies are gone, the report is not yet marked).
    """
    root = _real(project)
    ws = layout.root_of(None, env, home)
    layout.require_initialized(ws)
    _marker, project_id = _project_of(root)
    pdir = project_dir(ws, project_id)
    with _migration_lock(project_id, env, home), gitutil.git_lock(env, home), contextlib.ExitStack() as plan_locks:
        marker, current = _project_of(root)
        report = last_report(ws, project_id, _this_device(env, home))
        if current != project_id or report is None or "rolled_back_at" in report:
            raise WorkspaceError("MIGRATION_NOT_APPLIED", f"project {project_id} has no applied migration to roll back")
        device_id = report["device_id"]
        names = [(row, _report_name(row)) for row in report["plans"]]
        targets = [(row, f"{_kind_dir(row['class'])}/{_copy_name(row, name, device_id)}")
                   for row, name in names if row["action"] in COPY]
        # a legacy marker with every copy gone is the rest of a rollback that stopped after the marker was switched
        finishing = marker["plans_store"] == "legacy" and not any(
            os.path.lexists(pdir / relative) for _row, relative in targets)
        if marker["plans_store"] != "workspace" and not finishing:
            raise WorkspaceError("MIGRATION_NOT_APPLIED", f"project {project_id} has no applied migration to roll back")
        def check() -> None:
            if finishing:
                return
            diverged: List[str] = []
            stored: List[str] = []
            for row, name in names:
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
                raise WorkspaceError("MIGRATION_DIVERGED", f"{len(diverged)} plan(s) differ from the report "
                                     f"{report['op_id']}: {', '.join(diverged[:10])}{' ...' if len(diverged) > 10 else ''}")

        check()  # nothing is touched when it fails; the locks come after it and the check is repeated under them
        _lock_folders(plan_locks, [pdir / relative for row, relative in targets
                                   if row["class"] == "v4" and (pdir / relative / "plan.json").is_file()
                                   and not (pdir / relative).is_symlink()])
        check()
        done = dict(report, rolled_back_at=utc_now())
        issues = report_issues(done)
        if issues:
            raise WorkspaceError("WORKSPACE_LAYOUT_INVALID", f"the migration report is invalid: {issues[0]}")
        staging = ws / ".staging" / f"rollback-{report['op_id']}"
        if staging.exists():
            shutil.rmtree(staging)
        moved: List[Tuple[Path, Path]] = []
        removed: List[str] = []
        before = [{"path": item["path"], "reason": item["reason"]} for item in localonly.read(ws, project_id)["files"]
                  if item["device_id"] == device_id]
        try:
            staging.mkdir(parents=True)
            for _row, relative in targets:
                target = pdir / relative
                if target.is_dir() and not target.is_symlink():
                    destination = staging / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    os.rename(target, destination)
                    moved.append((target, destination))
                    removed.append(relative)
            if removed:
                _drop_local_only(ws, project_id, device_id, removed)
            if marker["plans_store"] != "legacy":
                write_marker(root, marker["workspace"], project_id, "legacy")
        except BaseException:
            stuck: List[str] = []
            for target, destination in reversed(moved):
                try:
                    if target.is_dir() and not target.is_symlink() and set(os.listdir(target)) <= {".lock"}:
                        shutil.rmtree(target)  # what a planner's PlanLock made at the old path while the folder was away
                    os.rename(destination, target)
                except OSError:
                    stuck.append(str(target.relative_to(pdir)))
            with contextlib.suppress(Exception):
                localonly.update(ws, project_id, before, device_id)
                localonly.rebuild_exclude(ws, device_id)
            if stuck:  # the staging folder holds the only copy of these: keep it
                raise WorkspaceError("MIGRATION_FAILED", f"the rollback stopped and could not put back {', '.join(stuck)}; "
                                     f"the copies are kept in {staging}") from None
            shutil.rmtree(staging, ignore_errors=True)
            raise
        for kind in ("plans", "legacy-plans"):
            with contextlib.suppress(OSError):
                (pdir / kind / ARCHIVE).rmdir()
        atomic_write_text(pdir / "migrations" / f"{report['op_id']}.json",
                          json.dumps(done, indent=2, ensure_ascii=False) + "\n")
        shutil.rmtree(staging, ignore_errors=True)
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
    with _migration_lock(project_id, env, home):  # a rollback in between would leave no copy of what is removed here
        if _project_of(root)[0]["plans_store"] != "workspace":
            raise WorkspaceError("MIGRATION_NOT_APPLIED", f"project {project_id} still keeps its plans in the checkout; "
                                 "run migrate apply first")
        return _cleanup_locked(root, ws, project_id, env, home)


def _cleanup_locked(root: Path, ws: Path, project_id: str, env: Env, home: Optional[PathLike]) -> Dict[str, Any]:
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
        if folder.is_symlink():
            continue
        try:
            names = os.listdir(folder)
        except OSError:
            continue
        if all(name in IGNORED for name in names):
            shutil.rmtree(folder)
    return not plans.exists()
