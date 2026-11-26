"""Whether a checkout is wired into its workspace: the check behind ``project doctor`` (``project.workspace``).

A checkout is integrated when its marker names a workspace that exists on this machine, the workspace holds the project
under the marker's code, this machine binds exactly this checkout to that code, and (as a rule, a warning otherwise) the
folder of the checkout is called like the project. A checkout without a marker is not part of any workspace: ``skip``.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Union

from aicore.state.locations import workspace_root, workspace_state_dir  # noqa: F401  (workspace_state_dir: readers of bindings)

from . import WorkspaceError
from .bindings import read_bindings
from .documents import read_marker, read_project, read_workspace

PathLike = Union[str, "os.PathLike[str]"]
Env = Optional[Mapping[str, str]]


def _finding(status: str, observed: str, remedy: str = "") -> Dict[str, Any]:
    return {"status": status, "observed": observed, "remedy": remedy}


def check_project(project_root: PathLike, env: Env = None, home: Optional[PathLike] = None) -> List[Dict[str, Any]]:
    """The findings (``status`` ``ok|warn|fail|skip``, ``observed``, ``remedy``) for the checkout at ``project_root``."""
    root = Path(project_root)
    try:
        marker = read_marker(root)
    except WorkspaceError as exc:
        return [_finding("fail", str(exc)[:400], "fix or remove .swissknifeman/project.json, then `workspace project attach`")]
    if marker is None:
        return [_finding("skip", "no .swissknifeman/project.json: the checkout is not part of a workspace",
                         "`swissknifeman workspace project attach` to wire it")]
    code, project = marker["workspace"], marker["project_id"]
    findings: List[Dict[str, Any]] = []
    ws = workspace_root(env, home, code=code)
    try:
        document = read_workspace(ws)
    except WorkspaceError as exc:
        return [_finding("fail", str(exc)[:400], "run `swissknifeman workspace doctor`")]
    if document is None:
        return [_finding("fail", f"the marker names the workspace {code!r}, which is not on this machine ({ws})",
                         "`swissknifeman workspace clone <url>` (or `workspace init --code %s`)" % code)]
    if document["code"] != code:
        return [_finding("fail", f"{ws} holds the workspace {document['code']!r}, not {code!r}",
                         "rename the folder or fix the marker")]
    try:
        record = read_project(ws, project)
    except WorkspaceError as exc:
        return [_finding("fail", str(exc)[:400], "run `swissknifeman workspace doctor`")]
    if record is None:
        findings.append(_finding("fail", f"the workspace {code!r} has no project {project!r}",
                                 "`swissknifeman workspace sync --pull`, or `workspace project attach` on a machine that has it"))
    else:
        findings.append(_finding("ok", f"project {project!r} is in the workspace {code!r}"))
    scoped = dict(os.environ if env is None else env)
    scoped["SKM_WORKSPACE"] = code
    try:
        entry = read_bindings(scoped, home)["projects"].get(project)
    except WorkspaceError as exc:
        findings.append(_finding("fail", str(exc)[:400], "run `swissknifeman workspace doctor`"))
        entry = None
    real = os.path.realpath(str(root))
    if entry is None:
        findings.append(_finding("fail", f"this machine does not bind {project!r} to any checkout",
                                 "`swissknifeman workspace project scan <dir>` or `workspace project rebind %s --path .`" % project))
    elif real not in entry["paths"]:
        findings.append(_finding("fail", f"{project!r} is bound to {', '.join(entry['paths'])}, not to this checkout",
                                 "`swissknifeman workspace project rebind %s --path %s`" % (project, real)))
    else:
        findings.append(_finding("ok", f"this checkout is bound to {project!r}"))
    if root.name != project:
        findings.append(_finding("warn", f"the folder is called {root.name!r}, the project code is {project!r}",
                                 "rename the folder or keep the difference on purpose"))
    return findings
