"""What the workspace repository tracks: the allowlist and the ignore list.

The repository carries only what a plan needs on another machine. Tracked: ``workspace.json``, ``README.md``,
``.gitignore``, ``.gitattributes`` and, per project, ``project.json``, ``plans/``, ``tasks/``, ``decisions/`` and the records the
workspace itself keeps (``legacy-plans/``, ``migrations/``, ``local-only.json``). Never tracked: ``projects/<code>/local/``
(the project-local config with ``repo.path``, state, backups, stubs), run files and orchestration artifacts, model and
provider settings of a project, and build output. The ignore list lives in a block of the workspace ``.gitignore`` between
``# skm:policy begin`` and ``# skm:policy end``; :func:`apply` rewrites that block and nothing else, :func:`audit` reads what
git tracks and reports what the policy forbids. Nothing here takes ``git.lock``: a caller that changes the repository holds it.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

from aicore.util.io import atomic_write_text
from aicore.workspace import LOCAL_DIRNAME, WorkspaceError

from . import gitutil
from .pathtypes import PathLike


BEGIN = "# skm:policy begin (managed by swissknifeman workspace: do not edit between the markers)"
END = "# skm:policy end"
TRACKED_TOP_LEVEL = (".gitignore", ".gitattributes", "README.md", "workspace.json")
TRACKED_PROJECT_ENTRIES = ("project.json", "plans", "tasks", "decisions", "legacy-plans", "migrations", "local-only.json")

# (comment, patterns): root-anchored gitignore lines.
IGNORE_POLICY = (
    ("machine-local folder of a project: config.toml with repo.path, state, backups, stubs",
     ("/projects/*/local/",)),
    ("run files and orchestration artifacts",
     ("/projects/*/runs/", "/projects/*/plans/*/runs/", "/projects/*/plans/*/artifacts/**/*.jsonl", "**/orch/",
      "**/orch-artifacts/")),
    ("model and provider settings of a project",
     ("**/.swissknifeman/", "**/.claude/", "**/.codex/", "**/.cursor/", "**/.grok/", "**/.antigravity/",
      "**/*.local.toml", "**/*.local.json")),
    ("build output",
     ("/projects/*/dist/", "/projects/*/build/", "/projects/*/plans/*/dist/", "/projects/*/plans/*/build/",
      "**/node_modules/", "**/__pycache__/", "*.pyc")),
)
PATTERNS = tuple(pattern for _comment, group in IGNORE_POLICY for pattern in group)
_PROBE = f"projects/probe/{LOCAL_DIRNAME}/config.toml"


def block() -> str:
    """The managed block of ``.gitignore`` (ends with a newline)."""
    lines = [BEGIN]
    for comment, group in IGNORE_POLICY:
        lines.append(f"# {comment}")
        lines.extend(group)
    lines.append(END)
    return "\n".join(lines) + "\n"


def _replace_block(text: str) -> str:
    lines = text.splitlines()
    kept: List[str] = []
    inside = False
    placed = False
    new = block().splitlines()
    for line in lines:
        if line.strip() == BEGIN:
            if inside:
                raise WorkspaceError("WORKSPACE_LAYOUT_INVALID", ".gitignore has a second begin line of the policy block")
            inside = True
            if not placed:
                kept.extend(new)
                placed = True
        elif line.strip() == END and inside:
            inside = False
        elif not inside:
            kept.append(line)
    if inside:
        raise WorkspaceError("WORKSPACE_LAYOUT_INVALID", ".gitignore has a policy begin line without an end line")
    if not placed:
        kept.extend(new)
    return "\n".join(kept) + "\n"


def apply(ws_root: PathLike) -> List[str]:
    """Bring the policy block of ``.gitignore`` up to date (the file is created when missing, every line outside the block is
    kept) and return the patterns that were not in the file before. Writes only when the text changes."""
    path = Path(ws_root) / ".gitignore"
    try:
        old = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        old = ""
    present = {line.strip() for line in old.splitlines()}
    added = [pattern for pattern in PATTERNS if pattern not in present]
    text = _replace_block(old)
    if text != old:
        atomic_write_text(path, text)
    return added


def missing(ws_root: PathLike) -> List[str]:
    """The patterns of the ignore list that ``.gitignore`` does not hold as a line."""
    try:
        present = {line.strip() for line in (Path(ws_root) / ".gitignore").read_text(encoding="utf-8").splitlines()}
    except (OSError, UnicodeError):
        present = set()
    return [pattern for pattern in PATTERNS if pattern not in present]


def local_ignored(ws_root: PathLike) -> bool:
    """Whether git ignores a file in ``projects/<code>/local/`` because of the ``.gitignore`` of the workspace (neither a
    global excludes file nor ``.git/info/exclude`` counts: they protect no other machine)."""
    done = gitutil.git(["-c", f"core.excludesFile={os.devnull}", "check-ignore", "--no-index", "-v", "--", _PROBE],
                       ws_root)
    return done.returncode == 0 and done.stdout.split(":", 1)[0] == ".gitignore"


def _allowed(path: str) -> bool:
    parts = path.split("/")
    if len(parts) == 1:
        return parts[0] in TRACKED_TOP_LEVEL
    if parts[0] != "projects":
        return False
    return (len(parts) == 2 and parts[1] == ".gitkeep") or (len(parts) >= 3 and parts[2] in TRACKED_PROJECT_ENTRIES)


def audit(ws_root: PathLike) -> Dict[str, Any]:
    """What git tracks against the policy: ``{tracked, local, ignored, outside}`` where ``local`` are tracked files below a
    ``local/`` folder, ``ignored`` other tracked files that the ignore list names, ``outside`` tracked files that the allowlist
    does not name (all sorted)."""
    root = Path(ws_root)
    listed = gitutil.require(gitutil.git(["ls-files", "-z"], root), "ls-files")
    tracked = sorted(item for item in listed.split("\0") if item)
    local = [path for path in tracked
             if path.split("/")[0] == "projects" and len(path.split("/")) > 3 and path.split("/")[2] == LOCAL_DIRNAME]
    in_local = set(local)
    rest = [path for path in tracked if path not in in_local]
    ignored: List[str] = []
    if rest:
        done = gitutil.git(["-c", f"core.excludesFile={os.devnull}", "check-ignore", "--no-index", "-z", "--stdin"], root,
                           input="\0".join(rest) + "\0")
        if done.returncode == 0:
            hits = {item for item in done.stdout.split("\0") if item}
            ignored = [path for path in rest if path in hits]
    listed_ignored = set(ignored)
    return {"tracked": tracked, "local": local, "ignored": ignored,
            "outside": [path for path in rest if path not in listed_ignored and not _allowed(path)]}
