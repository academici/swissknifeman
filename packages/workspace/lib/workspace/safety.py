"""Publish-safety: rules that decide whether the files of the next workspace commit may leave the machine.

Levels: ``block`` (a commit and a push are refused, ``PUBLISH_BLOCKED``), ``warn`` (reported) and ``local-only`` (the file
stays out of git and is indexed by :mod:`workspace.localonly`). The report never holds a secret value: a finding names
the rule, the path, the line and the mask. Home-directory paths in plan data only warn; block is for secrets, absolute
paths in the portable manifests, symlinks and entries outside the layout.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple, Union

from aicore.config import ConfigError, resolve
from aicore.util.redact import MASK, PATTERNS
from aicore.workspace import WorkspaceError

from . import gitutil

SCHEMA = "urn:swissknifeman:workspace:publish-report:v1"
DEFAULT_MAX_TRACKED = 5242880
DEFAULT_MAX_BINARY = 1048576
BINARY_PROBE = 8000
TOP_LEVEL = frozenset({".gitignore", ".gitattributes", "workspace.json", "README.md", "projects"})
PROJECT_ENTRIES = frozenset({"project.json", "plans", "legacy-plans", "migrations", "local-only.json"})
KEEP_FILE = "projects/.gitkeep"  # keeps the empty projects folder in git (written by init)
SECRET_NAMES = (".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "credentials.*", "secrets.*")
PATTERN_NAMES = ("token", "named-secret")
_PROJECT_ID = re.compile(r"prj_[0-9A-HJKMNP-TV-Z]{26}")
_HOME_PATH = re.compile(r"/home/[^/\s\"']+/|/Users/[^/\s\"']+/|[A-Za-z]:\\\\?Users\\\\?")
_ABSOLUTE = re.compile(r"^(?:[/~]|[A-Za-z]:[\\/])")
# Matches of the redaction patterns that are not secrets: a lower-case hyphenated word that starts with ``sk-`` (the tail of
# a slug such as ``task-development-workflow``; real keys carry digits or capitals) and the value of a ``name = value`` pair
# that is a placeholder (``<NAME>``, ``$NAME``, ``${NAME}``, ``{name}``) or a secret reference (``env://NAME``). The whole
# value must have that shape: a secret that merely starts with ``<`` or ``$`` is still a secret.
_SLUG = re.compile(r"sk-[a-z]+(?:-[a-z]+)*")
_PLACEHOLDER = re.compile(r"<[A-Za-z][A-Za-z0-9_.-]*>|\$\{[A-Za-z_][A-Za-z0-9_]*\}|\$[A-Za-z_][A-Za-z0-9_]*"
                          r"|\{[A-Za-z][A-Za-z0-9_.-]*\}|env://[A-Za-z0-9_][A-Za-z0-9_./-]*")

PathLike = Union[str, "os.PathLike[str]"]
Env = Optional[Mapping[str, str]]


@dataclass(frozen=True)
class Settings:
    """The ``[workspace.publish]`` limits."""

    max_tracked_bytes: int = DEFAULT_MAX_TRACKED
    max_binary_tracked_bytes: int = DEFAULT_MAX_BINARY


def load_settings(env: Env = None, home: Optional[PathLike] = None) -> Settings:
    """The limits of the configuration (defaults and machine layers); the defaults when it cannot be read."""
    try:
        config = resolve("workspace", unit_root=gitutil.UNIT_ROOT, env=env, home=home, warn=lambda message: None)
        return Settings(int(config.get("publish.max_tracked_bytes")), int(config.get("publish.max_binary_tracked_bytes")))
    except (ConfigError, TypeError, ValueError):
        return Settings()


@dataclass
class Report:
    """The result of a scan; :meth:`to_dict` is the ``publish-report/v1`` document."""

    files_checked: int = 0
    block: List[Dict[str, Any]] = field(default_factory=list)
    warn: List[Dict[str, Any]] = field(default_factory=list)
    local_only: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        return "block" if self.block else "warn" if self.warn else "ok"

    def to_dict(self) -> Dict[str, Any]:
        return {"$schema": SCHEMA, "files_checked": self.files_checked, "block": self.block, "warn": self.warn,
                "local_only": [dict(item, path=_display(item["path"])) for item in
                              sorted(self.local_only, key=lambda item: item["path"])], "verdict": self.verdict}


def _finding(rule: str, path: str, detail: str, line: Optional[int] = None) -> Dict[str, Any]:
    item: Dict[str, Any] = {"rule": rule, "path": _display(path), "detail": detail}
    if line is not None:
        item["line"] = line
    return item


def changed_paths(ws_root: PathLike) -> List[str]:
    """Paths the next commit would take: ``git status --porcelain=v2 -z --untracked-files=all`` (ignored and excluded files
    are not listed), sorted, relative to ``ws_root``."""
    root = Path(ws_root)
    out = gitutil.require(gitutil.git(["status", "--porcelain=v2", "-z", "--untracked-files=all"], root), "status")
    records = out.split("\0")
    found: Set[str] = set()
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            continue
        kind = record[0]
        if kind == "1":
            found.add(record.split(" ", 8)[8])
        elif kind == "2":
            found.add(record.split(" ", 9)[9])
            index += 1  # the original path of a rename follows as its own record
        elif kind == "u":
            found.add(record.split(" ", 10)[10])
        elif kind == "?":
            found.add(record[2:])
    return sorted(found)


def all_paths(ws_root: PathLike) -> List[str]:
    """Every tracked file and every untracked file that is not ignored or excluded, sorted."""
    root = Path(ws_root)
    tracked = gitutil.require(gitutil.git(["ls-files", "-z"], root), "ls-files").split("\0")
    others = gitutil.require(gitutil.git(["ls-files", "-z", "--others", "--exclude-standard"], root), "ls-files").split("\0")
    return sorted({item for item in tracked + others if item})


def tracked_paths(ws_root: PathLike) -> Set[str]:
    return {item for item in gitutil.require(gitutil.git(["ls-files", "-z"], Path(ws_root)), "ls-files").split("\0") if item}


def is_manifest(parts: Sequence[str]) -> bool:
    """The portable documents that must hold no absolute path."""
    if len(parts) == 1:
        return parts[0] == "workspace.json"
    if len(parts) == 3 and parts[0] == "projects":
        return parts[2] in ("project.json", "local-only.json")
    return len(parts) == 4 and parts[0] == "projects" and parts[2] == "migrations" and parts[3].endswith(".json")


def is_secret_name(name: str) -> bool:
    """Whether a file name (not a path) is a secret file name (``.env``, ``*.pem``, ``*.key``, ...)."""
    return any(fnmatch.fnmatchcase(name.lower(), pattern) for pattern in SECRET_NAMES)


def _layout_findings(rel: str, parts: Sequence[str]) -> List[Dict[str, Any]]:
    found = []
    if parts[0] not in TOP_LEVEL:
        found.append(_finding("PS-TOP-LEVEL", rel, f"{parts[0]!r} is not part of the workspace layout"))
    elif parts[0] == "projects" and rel != KEEP_FILE:
        if len(parts) < 3 or not _PROJECT_ID.fullmatch(parts[1]):
            found.append(_finding("PS-PROJECT-LEVEL", rel, "projects/ holds only folders named by a project id (prj_ and "
                                  "26 characters)"))
        elif parts[2] not in PROJECT_ENTRIES:
            found.append(_finding("PS-PROJECT-LEVEL", rel, f"{parts[2]!r} is not part of a project folder"))
    return found


def _absolute_pointers(node: Any, pointer: str = "") -> List[str]:
    found: List[str] = []
    if isinstance(node, str):
        if _ABSOLUTE.match(node) or _HOME_PATH.search(node):
            found.append(pointer or "/")
    elif isinstance(node, dict):
        for key, value in node.items():
            found.extend(_absolute_pointers(value, f"{pointer}/{key}"))
    elif isinstance(node, list):
        for number, value in enumerate(node):
            found.extend(_absolute_pointers(value, f"{pointer}/{number}"))
    return found


def _not_a_secret(index: int, match: "re.Match[str]") -> bool:
    text = match.group(0)
    if index == 0:
        start = match.start()
        if text.startswith("sk-") and start > 0 and match.string[start - 1].isalnum():
            return True  # the tail of a word such as ``task-0204-...``, not a key
        return _SLUG.fullmatch(text) is not None
    return _PLACEHOLDER.fullmatch(text[len(match.group(1)):]) is not None


def _secret_finding(rel: str, text: str) -> Optional[Dict[str, Any]]:
    """A ``PS-SECRET`` finding for the first line that matches a redaction pattern; the value is never copied."""
    first: Optional[int] = None
    matches = 0
    name = ""
    for number, line in enumerate(text.splitlines(), start=1):
        for index, pattern in enumerate(PATTERNS):
            hits = sum(1 for match in pattern.finditer(line) if not _not_a_secret(index, match))
            if hits:
                matches += hits
                if first is None:
                    first, name = number, PATTERN_NAMES[index] if index < len(PATTERN_NAMES) else f"pattern-{index}"
    if first is None:
        return None
    return _finding("PS-SECRET", rel, f"{matches} match(es) of the {name} secret pattern, the first at line {first}: {MASK}",
                    first)


def _add(found: List[Dict[str, Any]], items: Iterable[Dict[str, Any]]) -> None:
    for item in items:
        if item not in found:
            found.append(item)


@dataclass(frozen=True)
class _Version:
    """One form of a file that a commit could publish: the working-tree file or the blob in the index."""

    kind: str  # "link" | "file" | "other"
    size: int
    executable: bool
    head: Callable[[], bytes]
    body: Callable[[], bytes]


def _index_entries(root: Path) -> Dict[str, List[Tuple[str, str]]]:
    """``git ls-files -s -z``: path -> ``[(mode, object id)]`` of what the index holds (a conflict has several stages)."""
    out = gitutil.require(gitutil.git(["ls-files", "-s", "-z"], root), "ls-files")
    entries: Dict[str, List[Tuple[str, str]]] = {}
    for record in out.split("\0"):
        if record:
            meta, _, path = record.partition("\t")
            mode, oid, _stage = meta.split(" ")
            entries.setdefault(path, []).append((mode, oid))
    return entries


def _worktree_version(root: Path, rel: str) -> Optional[_Version]:
    full = root / rel
    try:
        info = os.lstat(full)
    except OSError:
        return None
    if stat.S_ISDIR(info.st_mode):
        return None

    def head() -> bytes:
        with open(full, "rb") as handle:
            return handle.read(BINARY_PROBE)

    kind = "link" if stat.S_ISLNK(info.st_mode) else "file" if stat.S_ISREG(info.st_mode) else "other"
    return _Version(kind, info.st_size, bool(info.st_mode & 0o111), head, full.read_bytes)


def _blob_version(root: Path, mode: str, oid: str) -> _Version:
    cache: List[bytes] = []

    def body() -> bytes:
        if not cache:
            done = gitutil.git_bytes(["cat-file", "blob", oid], root)
            if done.returncode != 0:
                raise OSError(f"git cat-file {oid} failed")
            cache.append(done.stdout)
        return cache[0]

    size_done = gitutil.git(["cat-file", "-s", oid], root)
    size = int(size_done.stdout.strip() or 0) if size_done.returncode == 0 else 0
    kind = "link" if mode == "120000" else "file" if mode in ("100644", "100755") else "other"
    return _Version(kind, size, mode == "100755", lambda: body()[:BINARY_PROBE], body)


def _versions(root: Path, rel: str, entries: Sequence[Tuple[str, str]]) -> List[_Version]:
    """What a commit could publish for ``rel``: the staged blob(s), which is what ``git commit`` takes, and the working-tree
    file, which ``git add`` would take."""
    found = [_blob_version(root, mode, oid) for mode, oid in dict.fromkeys(entries)]
    current = _worktree_version(root, rel)
    if current is not None:
        found.append(current)
    return found


def _scan_version(report: Report, limits: Settings, rel: str, parts: Sequence[str], version: _Version) -> None:
    if version.kind == "link":
        _add(report.block, [_finding("PS-SYMLINK", rel, "symbolic links are not published")])
        return
    if version.kind != "file":
        return
    if is_secret_name(parts[-1]):
        _add(report.block, [_finding("PS-SECRET", rel, f"the file name is a secret file name: {MASK}")])
    size = version.size
    binary = False
    if size <= limits.max_tracked_bytes:
        try:
            binary = b"\0" in version.head()
        except OSError:
            return
    reason = "size" if size > limits.max_tracked_bytes else \
        "binary" if binary and size > limits.max_binary_tracked_bytes else None
    if reason is not None:
        item = {"path": rel, "bytes": size, "reason": reason}
        if item not in report.local_only:
            report.local_only.append(item)
        return
    if version.executable:
        _add(report.warn, [_finding("PS-EXECUTABLE", rel, "the execute bit is set; clear it in the index with "
                                    "git update-index --chmod=-x")])
    if binary:
        return
    try:
        text = version.body().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return
    secret = _secret_finding(rel, text)
    if secret is not None:
        _add(report.block, [secret])
    if is_manifest(parts):
        try:
            pointers = _absolute_pointers(json.loads(text))
        except ValueError:
            pointers = []
        for pointer in pointers:
            _add(report.block, [_finding("PS-MANIFEST-PATH", rel, f"an absolute path at {pointer} of a portable document")])
    elif parts[0] == "projects":
        count = len(_HOME_PATH.findall(text))
        if count:
            _add(report.warn, [_finding("PS-HOME-PATH", rel, f"{count} home-directory path(s) in plan data")])


def _display(rel: str) -> str:
    """``rel`` as printable text: the bytes of a name that is not UTF-8 become ``\\xNN`` instead of lone surrogates."""
    return os.fsencode(rel).decode("utf-8", "backslashreplace")


def scan(ws_root: PathLike, paths: Iterable[str], settings: Optional[Settings] = None,
         tracked: Optional[Set[str]] = None) -> Report:
    """Apply the PS-* rules to ``paths`` (relative to ``ws_root``). A path that is neither in the index nor in the working
    tree is skipped.

    A file is judged in both forms a commit can publish: the blob in the git index (the staged content, which can differ
    from the file on disk) and the working-tree file (what ``git add`` would take).

    ``tracked`` is the set of files git already tracks (computed when a local-only file needs it); a tracked file that is
    local-only is a ``PS-TRACKED-LOCAL-ONLY`` warning.
    """
    root = Path(ws_root)
    limits = settings or Settings()
    report = Report()
    staged = _index_entries(root) if (root / ".git").exists() else {}
    for rel in sorted(set(paths)):
        parts = rel.split("/")
        versions = _versions(root, rel, staged.get(rel, ()))
        if not versions:
            continue
        report.files_checked += 1
        _add(report.block, _layout_findings(rel, parts))
        for version in versions:
            _scan_version(report, limits, rel, parts, version)
    if report.local_only:
        known = tracked if tracked is not None else tracked_paths(root)
        for item in report.local_only:
            if item["path"] in known:
                report.warn.append(_finding("PS-TRACKED-LOCAL-ONLY", item["path"],
                                            f"git already tracks this {item['reason']}-limited file; it stays in the index "
                                            "until sync removes it explicitly"))
    return report


def check(ws_root: PathLike, every_file: bool = False, env: Env = None, home: Optional[PathLike] = None) -> Report:
    """The report for the next commit (default) or for every file (``every_file``)."""
    root = Path(ws_root)
    if not (root / ".git").exists():
        raise WorkspaceError("WORKSPACE_LAYOUT_INVALID", f"{root} is not a git repository")
    paths = all_paths(root) if every_file else changed_paths(root)
    return scan(root, paths, load_settings(env, home))
