"""workspace doctor: structural checks as ``check-result/v1`` documents. The checks read; they never repair.

``workspace.layout`` (folders and files), ``workspace.documents`` (every JSON document against its contract),
``workspace.git-policy`` (the tracking policy of the repository: ``policy.py``), ``workspace.bindings`` (checkouts of this machine), ``workspace.legacy-plans`` (plans left beside a workspace store) and
``workspace.git`` (git version), ``workspace.plans-migrator`` (the plugin of the migration is found) and
``workspace.env-snippet`` / ``workspace.env-variables`` (the shell-profile snippet and the ``SKM_*`` variables, from
``aicore.state.shellenv``). A machine without a
workspace is normal before the first ``init``: that is a warning.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from aicore.state import shellenv as shell_env
from aicore.workspace import (is_code, WorkspaceError, legacy_plans_present, read_bindings, read_marker, read_workspace,
                              validate_document)

from . import gitutil, layout, migrator_port, policy, safety
from .pathtypes import PathLike

RESULT_SCHEMA = "urn:swissknifeman:aicore:check-result:v1"
PROJECT_ENTRIES = (*policy.TRACKED_PROJECT_ENTRIES, "local")

Env = Optional[Mapping[str, str]]


def _result(check_id: str, status: str, observed: str, category: str, *, evidence: Optional[List[str]] = None,
            remediation: Optional[str] = None) -> Dict[str, Any]:
    doc: Dict[str, Any] = {"$schema": RESULT_SCHEMA, "check_id": check_id, "status": status, "category": category,
                           "observed": observed}
    if evidence:
        doc["evidence"] = evidence
    if remediation:
        doc["remediation"] = remediation
    return doc


def _layout(target: Path, initialized: bool) -> Dict[str, Any]:
    check = "workspace.layout"
    if not initialized:
        return _result(check, "warn", "WORKSPACE_NOT_INITIALIZED: there is no workspace on this machine", "state",
                       evidence=[f"root: {target}"], remediation="Run: swissknifeman workspace init")
    problems: List[str] = []
    notes: List[str] = []
    if not (target / ".git").exists():
        problems.append("WORKSPACE_LAYOUT_INVALID: the workspace folder is not a git repository (.git is missing)")
    for child in sorted(target.iterdir()):
        if child.name not in layout.TOP_LEVEL:
            notes.append(f"WORKSPACE_LAYOUT_INVALID: unknown top-level entry {child.name!r}")
    projects = target / "projects"
    if not projects.is_dir():
        notes.append("WORKSPACE_LAYOUT_INVALID: the projects folder is missing (git does not keep empty folders)")
    else:
        for child in sorted(projects.iterdir()):
            if child.name == ".gitkeep":
                continue
            if not (child.is_dir() and is_code(child.name)):
                notes.append(f"WORKSPACE_LAYOUT_INVALID: projects/{child.name} is not a project folder")
                continue
            for entry in sorted(child.iterdir()):
                if entry.name not in PROJECT_ENTRIES:
                    notes.append(f"WORKSPACE_LAYOUT_INVALID: unknown entry projects/{child.name}/{entry.name}")
    if problems:
        return _result(check, "fail", problems[0], "state", evidence=problems + notes,
                       remediation="Restore the folder from its git remote or initialize a new workspace.")
    if notes:
        return _result(check, "warn", f"{len(notes)} entries do not belong to the workspace layout", "state",
                       evidence=notes, remediation="Move foreign files out of the workspace; it keeps only its layout.")
    return _result(check, "ok", f"workspace layout at {target}", "state")


def _documents(target: Path) -> Dict[str, Any]:
    check = "workspace.documents"
    failures: List[str] = []
    count = 0

    def examine(path: Path, kind: str) -> None:
        nonlocal count
        count += 1
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            failures.append(f"WORKSPACE_LAYOUT_INVALID: {path.relative_to(target).as_posix()} is not readable JSON")
            return
        issues = validate_document(kind, document)
        if issues:
            failures.append(f"WORKSPACE_LAYOUT_INVALID: {path.relative_to(target).as_posix()}: {issues[0]}")
        elif kind == "workspace-project" and document["project_id"] != path.parent.name:
            failures.append(f"WORKSPACE_LAYOUT_INVALID: {path.relative_to(target).as_posix()} names the project "
                            f"{document['project_id']}, not its folder")
        elif kind == "workspace-migration" and document["project_id"] != path.parent.parent.name:
            failures.append(f"WORKSPACE_LAYOUT_INVALID: {path.relative_to(target).as_posix()} belongs to another project")

    examine(target / "workspace.json", "workspace")
    for project_id in layout.project_ids(target):
        folder = target / "projects" / project_id
        if (folder / "project.json").is_file():
            examine(folder / "project.json", "workspace-project")
        else:
            failures.append(f"WORKSPACE_LAYOUT_INVALID: projects/{project_id}/project.json is missing")
        if (folder / "local-only.json").is_file():
            examine(folder / "local-only.json", "workspace-local-only")
        if (folder / "migrations").is_dir():
            for report in sorted((folder / "migrations").glob("*.json")):
                examine(report, "workspace-migration")
    if failures:
        return _result(check, "fail", f"{len(failures)} documents do not match their contract", "content",
                       evidence=failures, remediation="Restore the named files from git (git -C <workspace> checkout -- <file>) "
                       "or from another machine.")
    return _result(check, "ok", f"{count} workspace documents match their contracts", "content")


def _shown(paths: List[str], limit: int = 20) -> List[str]:
    return paths[:limit] + ([f"... and {len(paths) - limit} more"] if len(paths) > limit else [])


def _git_policy(target: Path, initialized: bool) -> Dict[str, Any]:
    """The ignore list is complete and effective, and git tracks nothing the policy forbids."""
    check = "workspace.git-policy"
    if not initialized or not (target / ".git").exists():
        return _result(check, "skip", "there is no workspace repository to read", "state")
    try:
        found = policy.audit(target)
        absent = policy.missing(target)
        effective = policy.local_ignored(target)
    except WorkspaceError as exc:
        return _result(check, "fail", str(exc)[:400], "state", remediation="Restore the repository from its git remote.")
    if found["local"]:
        return _result(check, "fail", f"POLICY_LOCAL_TRACKED: {len(found['local'])} files of a local/ folder are tracked",
                       "state", evidence=_shown(found["local"]),
                       remediation=f"Untrack them: git -C {target} rm -r --cached -- projects/<code>/local")
    notes: List[str] = []
    if absent:
        notes.append(f"POLICY_IGNORE_MISSING: .gitignore lacks {len(absent)} lines of the ignore list: " + ", ".join(absent[:5])
                     + (" ..." if len(absent) > 5 else ""))
    elif not effective:
        notes.append("POLICY_LOCAL_NOT_IGNORED: a later line of .gitignore (or a negation) lets git see projects/<code>/local/")
    notes.extend(f"POLICY_TRACKED_IGNORED: {path} is tracked but the ignore list names it" for path in found["ignored"])
    notes.extend(f"POLICY_TRACKED_OUTSIDE_ALLOWLIST: {path} is not something the workspace tracks"
                 for path in found["outside"])
    if notes:
        return _result(check, "warn", f"{len(notes)} deviations from the tracking policy of the workspace", "state",
                       evidence=_shown(notes),
                       remediation="Run: swissknifeman workspace sync --commit (it brings the ignore list of .gitignore up to "
                       "date); untrack other files with git rm --cached or move them out of the workspace.")
    return _result(check, "ok", f"{len(found['tracked'])} tracked files follow the policy; local/ is ignored", "state")


def _bindings(target: Optional[Path], env: Env, home: Optional[PathLike]) -> Dict[str, Any]:
    check = "workspace.bindings"
    try:
        bindings = read_bindings(env, home)["projects"]
    except WorkspaceError as exc:
        return _result(check, "fail", str(exc), "state",
                       remediation="Remove the damaged bindings.json of this machine and run: swissknifeman workspace project scan DIR")
    known = set(layout.project_ids(target)) if target is not None else set()
    notes: List[str] = []
    for project_id, entry in sorted(bindings.items()):
        if target is not None and project_id not in known:
            notes.append(f"PROJECT_UNKNOWN: {project_id} is bound but not in the workspace")
        for path in entry["paths"]:
            if not os.path.isdir(path):
                notes.append(f"BINDING_PATH_MISSING: {project_id}: {path} does not exist")
                continue
            try:
                marker = read_marker(path)
            except WorkspaceError as exc:
                notes.append(f"BINDING_MARKER_MISMATCH: {project_id}: {path}: {exc.message}")
                continue
            if marker is None or marker["project_id"] != project_id:
                found = "has no marker" if marker is None else f"has the marker of {marker['project_id']}"
                notes.append(f"BINDING_MARKER_MISMATCH: {project_id}: {path} {found}")
    if notes:
        return _result(check, "warn", f"{len(notes)} problems in the bindings of this machine", "state", evidence=notes,
                       remediation="Fix with: swissknifeman workspace project rebind <project_id> --path DIR, "
                       "or drop the binding: swissknifeman workspace project detach <project_id>")
    return _result(check, "ok", f"{len(bindings)} projects bound on this machine", "state")


def _legacy_plans(env: Env, home: Optional[PathLike]) -> Dict[str, Any]:
    check = "workspace.legacy-plans"
    try:
        bindings = read_bindings(env, home)["projects"]
    except WorkspaceError:
        return _result(check, "skip", "the bindings cannot be read", "state")
    notes: List[str] = []
    for project_id, entry in sorted(bindings.items()):
        for path in entry["paths"]:
            try:
                marker = read_marker(path) if os.path.isdir(path) else None
            except WorkspaceError:
                continue
            if marker and marker["project_id"] == project_id and marker["plans_store"] == "workspace" \
                    and legacy_plans_present(path, env, home):
                notes.append(f"LEGACY_PLANS_PRESENT: {project_id}: {path}/plans still holds plans; the workspace copy is used")
    if notes:
        return _result(check, "warn", f"{len(notes)} checkouts still hold plans beside the workspace store", "state",
                       evidence=notes, remediation="Compare and remove the old copy once the workspace copy is verified.")
    return _result(check, "ok", "no plans are left beside a workspace store", "state")


def _git() -> Dict[str, Any]:
    check = "workspace.git"
    version = gitutil.git_version()
    if version is None:
        return _result(check, "fail", "WORKSPACE_GIT_TOO_OLD: git is not installed", "environment",
                       remediation="Install git 2.38 or newer.")
    text = ".".join(str(part) for part in version)
    if version < gitutil.MIN_GIT_WORKSPACE:
        return _result(check, "warn", f"WORKSPACE_GIT_TOO_OLD: git {text} is older than {layout.GIT_MIN_TEXT}",
                       "environment", remediation="Update git to 2.38 or newer before using sync.")
    return _result(check, "ok", f"git {text}", "environment")


def _migrator(env: Env, home: Optional[PathLike]) -> Dict[str, Any]:
    check = "workspace.plans-migrator"
    try:
        found = migrator_port.registration(env, home)
    except WorkspaceError as exc:
        return _result(check, "warn", str(exc), "environment",
                       remediation="Register the bridge: swissknifeman config set aicore plugins.workspace-planner.manifest "
                       "<hub>/bridges/workspace-planner/extension.json (needed by workspace migrate only)")
    return _result(check, "ok", f"plans migrator {found.id} {found.manifest.version if found.manifest else '?'} provides {migrator_port.POINT}",
                   "environment")


def publish_safety(root: Optional[PathLike] = None, every_file: bool = False, env: Env = None,
                   home: Optional[PathLike] = None) -> "safety.Report":
    """The publish-safety report of the workspace at ``root``: the files of the next commit, or every file."""
    target = layout.root_of(root, env, home)
    layout.require_initialized(target)
    return safety.check(target, every_file, env, home)


def run_checks(root: Optional[PathLike] = None, env: Env = None, home: Optional[PathLike] = None) -> List[Dict[str, Any]]:
    """The doctor checks of the workspace at ``root`` (default: ``workspace_root()``) and of this machine."""
    target = layout.root_of(root, env, home)
    initialized = False
    skipped = None
    try:
        initialized = target.is_dir() and read_workspace(target) is not None
    except WorkspaceError as exc:
        skipped = str(exc)
    results = [_layout(target, initialized or skipped is not None)]
    if skipped is not None:
        results[0] = _result("workspace.layout", "fail", skipped, "state",
                             remediation="Restore workspace.json from git or initialize a new workspace.")
    results.append(_documents(target) if initialized else
                   _result("workspace.documents", "skip", "there is no workspace to read", "content"))
    results.append(_git_policy(target, initialized))
    results.append(_bindings(target if initialized else None, env, home))
    results.append(_legacy_plans(env, home))
    results.append(_git())
    results.append(_migrator(env, home))
    results.extend(shell_env.doctor_checks("workspace", env, home))
    return results
