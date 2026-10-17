"""``inspect``: classify the content of ``<project root>/plans`` and describe it as a manifest of digests.

Classes (contract ``workspace-contract#migration``):

- ``v4``: a folder whose ``plan.json`` has ``$schema`` ``urn:swissknifeman:task:plan:plan:v1`` (in ``plans/`` or in
  ``plans/archive/``); ``views/``, ``context/`` and ``.lock`` of the plan folder are derived and not part of the manifest;
- ``legacy``: any other folder of ``plans/`` or ``plans/archive/``, copied as it is;
- top-level files of ``plans/`` (and of ``plans/archive/``): they go to ``legacy-plans/_root``.

``__pycache__`` and ``.DS_Store`` are skipped everywhere. A symlink is never followed and never copied: it is listed in
``symlinks`` and stops the migration. Paths in the manifest are POSIX paths relative to ``plans/``; no file content is
read into a result, only hashed. The module is stdlib only and is shared by ``apply`` and ``verify``.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import time
from typing import Callable, Dict, List, Optional

PLAN_SCHEMA = "urn:swissknifeman:task:plan:plan:v1"
ARCHIVE = "archive"
ROOT_NAME = "_root"
IGNORED = frozenset({"__pycache__", ".DS_Store"})
V4_DERIVED = frozenset({"views", "context", ".lock"})
CHUNK = 1 << 20

Progress = Optional[Callable[[str], None]]


def stderr_progress(text: str) -> None:
    """Progress of a long call goes to stderr of the bridge, never into the answer."""
    print(f"workspace-planner: {text}", file=sys.stderr, flush=True)


class Ticker:
    """Rate limit for progress lines: at most one per ``every`` seconds."""

    def __init__(self, progress: Progress, every: float = 2.0):
        self.progress = progress
        self.every = every
        self.last = time.monotonic()

    def tick(self, text: str) -> None:
        if self.progress is None:
            return
        now = time.monotonic()
        if now - self.last >= self.every:
            self.last = now
            self.progress(text)


# ---------------------------------------------------------------------------------------------------- digests

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def digest_files(files: List[dict], prefix: str = "") -> str:
    """``sha256:<hex>`` over the sorted ``(path, sha256)`` pairs; ``prefix`` is cut from every path first, so that the
    same plan has the same digest in the checkout and in the workspace."""
    cut = len(prefix)
    lines = sorted(f"{entry['path'][cut:]}\0{entry['sha256']}\n" for entry in files)
    return "sha256:" + hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()


def digest_manifest(plans: List[dict], top_level: List[dict]) -> str:
    lines = [f"plan\0{plan['name']}\0{plan['class']}\0{plan['digest']}\n" for plan in plans]
    lines += [f"file\0{entry['path']}\0{entry['sha256']}\n" for entry in top_level]
    return "sha256:" + hashlib.sha256("".join(sorted(lines)).encode("utf-8")).hexdigest()


# ------------------------------------------------------------------------------------------------------ walk

class Scan:
    """Files and symlinks found under one folder; ``derived`` counts what the rules left out."""

    def __init__(self):
        self.files: List[dict] = []
        self.symlinks: List[str] = []
        self.derived = 0


def _walk(directory: Path, rel: str, scan: Scan, hash_files: bool, ticker: Ticker, skip_top: frozenset) -> None:
    """Collect the files of ``directory``; ``rel`` is its path relative to ``plans/``; ``skip_top`` names the derived
    entries of this level only."""
    try:
        entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
    except OSError as exc:
        raise OSError(f"cannot list {rel or '.'}: {exc.strerror or exc.__class__.__name__}") from None
    for entry in entries:
        name = entry.name
        child = f"{rel}/{name}" if rel else name
        if name in IGNORED or name in skip_top:
            scan.derived += 1
            continue
        if entry.is_symlink():
            scan.symlinks.append(child)
            continue
        if entry.is_dir(follow_symlinks=False):
            _walk(Path(entry.path), child, scan, hash_files, ticker, frozenset())
        elif entry.is_file(follow_symlinks=False):
            info = entry.stat(follow_symlinks=False)
            scan.files.append({"path": child, "bytes": info.st_size,
                               "sha256": sha256_file(Path(entry.path)) if hash_files else ""})
            ticker.tick(f"scanned {len(scan.files)} files")
        else:  # a socket, a device, a fifo: not migratable, treated as a symlink-like blocker
            scan.symlinks.append(child)


def classify_dir(directory: Path) -> str:
    """``v4`` when ``plan.json`` of ``directory`` carries the plan schema, else ``legacy``."""
    try:
        document = json.loads((directory / "plan.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return "legacy"
    return "v4" if isinstance(document, dict) and document.get("$schema") == PLAN_SCHEMA else "legacy"


def scan_unit(directory: Path, rel: str, cls: str, hash_files: bool = True, progress: Progress = None) -> Scan:
    """Scan one plan folder under the rules of its class; ``rel`` is the prefix of the paths in the result."""
    scan = Scan()
    _walk(directory, rel, scan, hash_files, Ticker(progress), V4_DERIVED if cls == "v4" else frozenset())
    scan.files.sort(key=lambda entry: entry["path"])
    return scan


def in_progress_items(directory: Path, name: str) -> List[str]:
    """``<plan>/<item>`` of every item of the plan folder whose status is ``in_progress``."""
    found = []
    phases = directory / "phases"
    try:
        phase_dirs = sorted(entry for entry in phases.iterdir() if entry.is_dir())
    except OSError:
        return found
    for phase in phase_dirs:
        for item in sorted(phase.glob("*.json")):
            if item.name == "phase.json":
                continue
            try:
                document = json.loads(item.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, ValueError):
                continue
            if isinstance(document, dict) and document.get("status") == "in_progress":
                found.append(f"{name}/{item.stem}")
    return found


def _unit_dirs(plans: Path):
    """``(name, directory)`` of the plan folders of ``plans/`` and ``plans/archive/`` and the loose files."""
    folders, loose = [], []
    for parent, prefix in ((plans, ""), (plans / ARCHIVE, ARCHIVE + "/")):
        if parent.is_symlink():  # never entered; ``plans/archive`` as a symlink is reported from the loose entries
            continue
        try:
            entries = sorted(os.scandir(parent), key=lambda entry: entry.name)
        except (FileNotFoundError, NotADirectoryError):
            continue  # no ``archive`` folder (or a file of that name, listed as a loose file)
        except OSError as exc:
            raise OSError(f"cannot list plans/{prefix}: {exc.strerror or exc.__class__.__name__}") from None
        for entry in entries:
            if entry.name in IGNORED or (prefix == "" and entry.name == ARCHIVE and entry.is_dir(follow_symlinks=False)):
                continue
            if entry.is_dir(follow_symlinks=False):
                folders.append((prefix + entry.name, Path(entry.path)))
            else:
                loose.append((prefix + entry.name, Path(entry.path)))
    return folders, loose


def inspect(project_root, progress: Progress = None, hash_files: bool = True) -> Dict[str, object]:
    """The manifest of ``<project_root>/plans`` (see the module docstring); ``present`` is false without a ``plans`` folder."""
    plans = Path(project_root) / "plans"
    result: Dict[str, object] = {"present": plans.is_dir() and not plans.is_symlink(), "plans": [], "top_level": [],
                                 "symlinks": [], "derived_skipped": 0, "digest": ""}
    if not result["present"]:
        result["digest"] = digest_manifest([], [])
        return result
    ticker = Ticker(progress)
    folders, loose = _unit_dirs(plans)
    entries: List[dict] = []
    symlinks: List[str] = []
    derived = 0
    for name, directory in folders:
        if directory.is_symlink():
            symlinks.append(name)
            continue
        cls = classify_dir(directory)
        scan = scan_unit(directory, name, cls, hash_files, progress)
        symlinks.extend(scan.symlinks)
        derived += scan.derived
        entry = {"name": name, "class": cls, "files": scan.files, "bytes": sum(f["bytes"] for f in scan.files),
                 "digest": digest_files(scan.files, name + "/"),
                 "in_progress": in_progress_items(directory, name) if cls == "v4" else []}
        entries.append(entry)
        ticker.tick(f"inspected {len(entries)} plan folders")
    top_level: List[dict] = []
    for name, path in loose:
        if path.is_symlink():
            symlinks.append(name)
            continue
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode):
            symlinks.append(name)
            continue
        top_level.append({"path": name, "bytes": info.st_size, "sha256": sha256_file(path) if hash_files else ""})
    result["plans"] = entries
    result["top_level"] = top_level
    result["symlinks"] = sorted(symlinks)
    result["derived_skipped"] = derived
    result["digest"] = digest_manifest(entries, top_level)
    return result


def units_of(manifest: dict) -> List[dict]:
    """The folders to move: every plan folder, then ``_root`` for the loose files (class ``legacy``). Each unit has
    ``name``, ``class``, ``files``, ``bytes``, ``digest`` and ``prefix`` (cut from a file path to get the path inside
    the unit)."""
    units = [{"name": plan["name"], "class": plan["class"], "files": plan["files"], "bytes": plan["bytes"],
              "digest": plan["digest"], "prefix": plan["name"] + "/"} for plan in manifest["plans"]]
    loose = manifest["top_level"]
    if loose:
        units.append({"name": ROOT_NAME, "class": "legacy", "files": loose, "bytes": sum(f["bytes"] for f in loose),
                      "digest": digest_files(loose), "prefix": ""})
    return units


def scan_digest(directory: Path, cls: str, progress: Progress = None) -> str:
    """The digest of a folder of the workspace under the rules of its class (paths relative to the folder)."""
    scan = scan_unit(directory, "", cls, True, progress)
    return digest_files(scan.files)
