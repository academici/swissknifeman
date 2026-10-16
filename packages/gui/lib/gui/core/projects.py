"""Registry of the projects the gui trusts (decision D12), kept in ``gui.db``.

A project gets in only by an explicit act of the owner (``gui open --project``/cwd or a confirmed
``POST /v1/projects``), so every entry is trusted; the maind fleet is shown by the gui-hub bridge only as data.
``resolve`` is the one way to a working folder inside a project (I5): the root must still be the same real
directory and the path must stay inside it after ``realpath``. stdlib + aicore.
"""
from __future__ import annotations

import hashlib
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Union

from aicore.state.locations import find_project_root
from aicore.util.paths import is_within

from ..errors import GuiError
from ..storage.db import audit, now

CONTRACT = "urn:swissknifeman:gui:project:v1"
SOURCES = ("open", "user")
_SLUG = re.compile(r"[^a-z0-9]+")
_ID = re.compile(r"^[a-z0-9-]{1,40}-[0-9a-f]{8}$")


@dataclass(frozen=True)
class Project:
    id: str
    name: str
    root: str
    trusted: bool
    source: str
    added_at: str

    def document(self, *, standalone: bool = True) -> dict:
        """The ``project`` kind of project/v1; ``standalone=False`` gives the entry of a ``project_list``."""
        body = {"id": self.id, "name": self.name, "root": self.root, "trusted": self.trusted, "source": self.source,
                "added_at": self.added_at}
        return {"$schema": CONTRACT, "kind": "project", **body} if standalone else body


def slug(name: str) -> str:
    """Lower case, runs of other characters to ``-``, at most 40 characters; ``project`` when nothing is left."""
    text = _SLUG.sub("-", name.lower()).strip("-")[:40].strip("-")
    return text or "project"


def project_id(root: str) -> str:
    return f"{slug(os.path.basename(root))}-{hashlib.sha256(root.encode('utf-8')).hexdigest()[:8]}"


def list_document(projects: List[Project]) -> dict:
    return {"$schema": CONTRACT, "kind": "project_list",
            "projects": [project.document(standalone=False) for project in projects]}


def _row(row: sqlite3.Row) -> Project:
    return Project(id=row["id"], name=row["name"], root=row["root"], trusted=bool(row["trusted"]),
                   source=row["source"], added_at=row["added_at"])


class ProjectRegistry:
    """Trusted projects over an open ``gui.db`` connection (migration 1)."""

    def __init__(self, conn: sqlite3.Connection, *, actor: str = "gui") -> None:
        self.conn = conn
        self.actor = actor

    def add(self, path: Union[str, Path], *, source: str, correlation_id: Optional[str] = None) -> Project:
        """Register the project that holds ``path`` (its root by the SKM markers, else ``path``); idempotent."""
        if source not in SOURCES:
            raise ValueError(f"source must be one of {SOURCES}, got {source!r}")
        start = Path(os.path.abspath(os.path.expanduser(str(path))))
        if not start.is_dir():
            raise GuiError("NOT_FOUND", f"project folder {start} does not exist")
        # Only the markers decide: SKM_PROJECT_ROOT or a launcher binding of this process must not replace the path.
        markers_only = {name: os.environ[name] for name in ("HOME",) if name in os.environ}
        root = os.path.realpath(find_project_root(start, env=markers_only))
        if not os.path.isdir(root):
            raise GuiError("NOT_FOUND", f"project folder {root} does not exist")
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            row = self.conn.execute("SELECT * FROM projects WHERE root = ?", (root,)).fetchone()
            if row is None:
                project = Project(id=project_id(root), name=os.path.basename(root) or root, root=root, trusted=True,
                                  source=source, added_at=now())
                self.conn.execute("INSERT INTO projects (id, root, name, trusted, source, added_at) "
                                  "VALUES (?, ?, ?, 1, ?, ?)",
                                  (project.id, project.root, project.name, project.source, project.added_at))
                audit(self.conn, actor=self.actor, action="project.add", target=project.id, decision="allowed",
                      details={"root": root, "source": source}, correlation_id=correlation_id)
            else:
                project = _row(row)
            self.conn.execute("COMMIT")
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        return project

    def get(self, project_id_: str) -> Project:
        row = self.conn.execute("SELECT * FROM projects WHERE id = ?", (project_id_,)).fetchone()
        if row is None:
            raise GuiError("NOT_FOUND", f"no project {project_id_!r}")
        return _row(row)

    def list(self) -> List[Project]:
        return [_row(row) for row in self.conn.execute("SELECT * FROM projects ORDER BY name, id")]

    def remove(self, project_id_: str, *, correlation_id: Optional[str] = None) -> None:
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            removed = self.conn.execute("DELETE FROM projects WHERE id = ?", (project_id_,)).rowcount
            if not removed:
                raise GuiError("NOT_FOUND", f"no project {project_id_!r}")
            audit(self.conn, actor=self.actor, action="project.remove", target=project_id_, decision="allowed",
                  correlation_id=correlation_id)
            self.conn.execute("COMMIT")
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise

    def resolve(self, project_id_: str, relpath: Optional[str] = None) -> Path:
        """The real path of the project root or of ``relpath`` inside it.

        ``NOT_FOUND`` when the project is unknown or its root is gone or replaced (it no longer resolves to itself,
        e.g. turned into a symlink); ``PATH_ESCAPE`` when ``relpath`` is absolute or leads outside after ``realpath``.
        """
        project = self.get(project_id_)
        root = project.root
        if not os.path.isdir(root) or os.path.realpath(root) != root:
            raise GuiError("NOT_FOUND", f"the root of project {project.id} is missing or moved: {root}")
        if relpath is None or relpath in ("", "."):
            return Path(root)
        if os.path.isabs(relpath) or "\x00" in relpath:
            raise GuiError("PATH_ESCAPE", f"{relpath!r} is not a path relative to project {project.id}")
        candidate = os.path.realpath(os.path.join(root, relpath))
        if not is_within(candidate, root):
            raise GuiError("PATH_ESCAPE", f"{relpath!r} leads outside project {project.id}")
        return Path(candidate)


def valid_id(text: str) -> bool:
    return bool(_ID.match(text))
