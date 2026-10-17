"""``workspace sync``: commit, pull, resolve and push of the workspace repository (contract ``workspace-contract#sync``).

The steps, all under ``git.lock``:

1. ``commit``: publish-safety over the changed files (a block stops everything, nothing is committed), local-only files go to
   ``local-only.json`` and ``.git/info/exclude``, ``git add -A`` of the layout paths, one commit with a ``Workspace-Device``
   trailer.
2. ``pull``: ``git fetch origin``, then a dry merge with ``git merge-tree --write-tree``. A clean result is merged (fast-forward
   where possible); a conflict changes neither the working tree nor ``HEAD`` and is reported per path with its project, plan
   and ref (``WORKSPACE_CONFLICT``).
3. ``resolve``: ``--resolve PATH=local|remote`` collects decisions in ``sync.json``; when every conflicting path is decided and
   ``origin/<branch>`` and ``HEAD`` are as they were at the pull, the merge is made with the decided sides, else
   ``WORKSPACE_CONFLICT_STALE``. No side is ever chosen by this module.
4. ``push``: ``git push origin HEAD:<branch>`` without force; a rejected push is ``WORKSPACE_BEHIND``.
5. ``sync.json`` (machine state) and ``audit.jsonl`` (one line per operation) record the outcome; the events
   ``workspace.sync.*`` are journaled after the lock is released.

Every git call is an argument list through :mod:`workspace.gitutil`; the forms ``push --force``, ``reset --hard``, ``clean``,
``checkout .`` and ``rebase`` do not occur here.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Set, Tuple, Union

from aicore.state import ensure_dir, workspace_state_dir
from aicore.util.io import atomic_write_text
from aicore.workspace import WorkspaceError, project_dir, utc_now

from . import events, gitutil, layout, localonly, safety

PathLike = Union[str, "os.PathLike[str]"]
Env = Optional[Mapping[str, str]]

STATE_FILE = "sync.json"
AUDIT_FILE = "audit.jsonl"
SIDES = {"local": "--ours", "remote": "--theirs"}
ADD_PATHS = ("projects", "workspace.json", ".gitignore", ".gitattributes", "README.md")
CHUNK = 100  # paths per git call that takes paths as arguments
NEXT_PULL = "swissknifeman workspace sync --pull"


class SyncError(WorkspaceError):
    """A refusal of ``sync`` with the report of what had been done until then (``report``)."""

    def __init__(self, code: str, message: str, report: Optional[Dict[str, Any]] = None):
        super().__init__(code, message)
        self.report: Dict[str, Any] = report if report is not None else {}


# ------------------------------------------------------------------------------------------------ machine state


def state_path(env: Env = None, home: Optional[PathLike] = None) -> Path:
    return workspace_state_dir(env, home) / STATE_FILE


def read_state(env: Env = None, home: Optional[PathLike] = None) -> Dict[str, Any]:
    """``sync.json`` of this machine; an empty document when it is missing or unreadable."""
    try:
        document = json.loads(state_path(env, home).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return {}
    return document if isinstance(document, dict) else {}


def _write_state(env: Env, home: Optional[PathLike], **fields: Any) -> Dict[str, Any]:
    document = read_state(env, home)
    document.update(fields)
    ensure_dir(workspace_state_dir(env, home))
    atomic_write_text(state_path(env, home), json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    return document


def _audit(env: Env, home: Optional[PathLike], record: Mapping[str, Any]) -> None:
    folder = ensure_dir(workspace_state_dir(env, home))
    line = json.dumps(dict(record), ensure_ascii=False, sort_keys=True)
    with open(folder / AUDIT_FILE, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")


# ----------------------------------------------------------------------------------------------- git helpers


def _out(target: Path, *args: str) -> str:
    return gitutil.git(list(args), target).stdout.strip()


def _head(target: Path) -> str:
    return _out(target, "rev-parse", "HEAD")


def _ref(target: Path, name: str) -> Optional[str]:
    done = gitutil.git(["rev-parse", "--verify", "-q", f"{name}^{{commit}}"], target)
    return done.stdout.strip() if done.returncode == 0 and done.stdout.strip() else None


def _merge_in_progress(target: Path) -> bool:
    return gitutil.git(["rev-parse", "-q", "--verify", "MERGE_HEAD"], target).returncode == 0


def _must(done: "Any", what: str, code: str = "WORKSPACE_SYNC_FAILED") -> str:
    if done.returncode != 0:
        detail = gitutil.redact_remote_text(done.stderr.strip() or done.stdout.strip() or f"exit {done.returncode}")
        raise SyncError(code, f"git {what} failed: {detail}")
    return done.stdout


def _in_chunks(items: Sequence[str]) -> List[List[str]]:
    return [list(items[start:start + CHUNK]) for start in range(0, len(items), CHUNK)]


# ------------------------------------------------------------------------------------------------- conflicts


def conflict_row(path: str) -> Dict[str, Any]:
    """``{path, project_id, plan, ref}`` of a conflicting path: ``phases/P2/P2.3.json`` is ref ``P2.3``,
    ``decisions/D4.json`` is ``D4``, ``plan.json`` is ``plan``; paths outside a plan have no plan and no ref."""
    parts = path.split("/")
    project_id: Optional[str] = None
    plan: Optional[str] = None
    ref: Optional[str] = None
    if len(parts) >= 2 and parts[0] == "projects" and parts[1].startswith("prj_"):
        project_id = parts[1]
        if len(parts) >= 5 and parts[2] == "plans":
            index = 4 if parts[3] == "archive" and len(parts) >= 6 else 3
            plan = parts[index]
            rest = parts[index + 1:]
            if rest:
                name = rest[-1]
                ref = "plan" if rest == ["plan.json"] else (name.rsplit(".", 1)[0] if "." in name else name)
    return {"path": path, "project_id": project_id, "plan": plan, "ref": ref}


def _parse_merge_tree(output: str) -> List[str]:
    """The conflicting paths of ``git merge-tree --write-tree --name-only -z --messages``: the tree id, then the
    NUL-terminated names up to an empty field (the informational messages follow)."""
    fields = output.split("\0")
    names: List[str] = []
    for field in fields[1:]:
        if not field:
            break
        names.append(field)
    return sorted(set(names))


def parse_resolutions(items: Sequence[str]) -> Dict[str, str]:
    """``["PATH=local", "PATH2=remote"]`` as ``{path: side}``; a bad form or two sides for one path is a ``ValueError``."""
    decisions: Dict[str, str] = {}
    for item in items:
        path, separator, side = item.rpartition("=")
        path = path[2:] if path.startswith("./") else path
        if not separator or not path or side not in SIDES:
            raise ValueError(f"--resolve takes PATH=local or PATH=remote, not {item!r}")
        if decisions.get(path, side) != side:
            raise ValueError(f"--resolve names two sides for {path}")
        decisions[path] = side
    return decisions


# ----------------------------------------------------------------------------------------------- the context


class _Run:
    """What one ``sync`` call knows and has done; ``report`` is the document the call returns."""

    def __init__(self, target: Path, env: Env, home: Optional[PathLike], branch: str, remote: Optional[str],
                 device_id: str, workspace_id: str, steps: List[str],
                 announce: Optional[Callable[[Dict[str, Any]], None]]):
        self.target, self.env, self.home = target, env, home
        self.branch, self.remote, self.device_id, self.workspace_id = branch, remote, device_id, workspace_id
        self.announce = announce
        self.operation = "sync"
        self.events: List[Tuple[str, Dict[str, Any]]] = []
        self.report: Dict[str, Any] = {"branch": branch, "remote": remote, "device_id": device_id, "steps": steps}

    def audit(self, operation: str, result: str, **fields: Any) -> None:
        record: Dict[str, Any] = {"at": utc_now(), "op": operation, "result": result, "device_id": self.device_id,
                                  "branch": self.branch, "remote": self.remote}
        record.update(fields)
        _audit(self.env, self.home, record)


# ------------------------------------------------------------------------------------------------- 1. commit


def _subject(paths: Sequence[str]) -> Tuple[str, str]:
    """``(subject, body)`` of the sync commit: ``skm(plan): <plan-id> sync <N> files`` when every file is in one plan,
    else ``skm(workspace): sync <N> files``; the body lists the projects and plans."""
    plans: Dict[str, Set[str]] = {}
    others: List[str] = []
    for path in paths:
        row = conflict_row(path)
        if row["project_id"] and row["plan"]:
            plans.setdefault(row["project_id"], set()).add(row["plan"])
        elif row["project_id"]:
            plans.setdefault(row["project_id"], set())
        else:
            others.append(path)
    pairs = [(project, plan) for project, names in plans.items() for plan in names]
    count = len(paths)
    if len(pairs) == 1 and not others and pairs[0][1]:
        subject = f"skm(plan): {pairs[0][1]} sync {count} files"
    else:
        subject = f"skm(workspace): sync {count} files"
    lines = []
    for project in sorted(plans):
        names = sorted(plans[project])
        lines.append(f"project {project}" + (f": {', '.join(names)}" if names else ""))
    if others:
        lines.append("workspace: " + ", ".join(sorted(others)[:20]))
    return subject, "\n".join(lines)


def _record_local_only(run: _Run, report: "safety.Report") -> None:
    """Index the local-only files of the scan per project (keeping the entries of this device that still exist) and rebuild
    the exclude block."""
    grouped = localonly.entries_by_project(report)
    for project_id, entries in sorted(grouped.items()):
        folder = project_dir(run.target, project_id)
        keep = [{"path": item["path"], "reason": item["reason"]} for item in localonly.read(run.target, project_id)["files"]
                if item["device_id"] == run.device_id and (folder / item["path"]).is_file()]
        listed = {item["path"] for item in entries}
        merged = [item for item in keep if item["path"] not in listed] + entries
        localonly.update(run.target, project_id, merged, run.device_id)
    localonly.rebuild_exclude(run.target, run.device_id)


def _unindexed(report: "safety.Report") -> List[Dict[str, Any]]:
    """Local-only findings that have no ``local-only.json`` to go to (outside ``projects/<id>/``, or the index itself)."""
    found = []
    for item in report.local_only:
        parts = item["path"].split("/")
        inside = len(parts) >= 3 and parts[0] == "projects" and parts[2] != localonly.INDEX_FILE
        if not inside:
            found.append({"rule": "PS-LOCAL-ONLY-UNINDEXED", "path": safety._display(item["path"]),
                          "detail": f"a {item['reason']}-limited file that no local-only.json can hold ({item['bytes']} bytes)"})
    return found


def _blocked(run: _Run, block: Sequence[Dict[str, Any]], warn: Sequence[Dict[str, Any]], checked: int) -> SyncError:
    run.report["commit"] = {"status": "blocked", "block": list(block), "warn": list(warn), "files_checked": checked}
    return SyncError("PUBLISH_BLOCKED", f"{len(block)} finding(s) forbid publishing the workspace; nothing was committed; "
                     f"fix them and run `workspace doctor --publish-safety`", run.report)


def _step_commit(run: _Run) -> None:
    run.operation = "commit"
    target = run.target
    settings = safety.load_settings(run.env, run.home)
    paths = safety.changed_paths(target)
    first = safety.scan(target, paths, settings)
    if first.block:
        raise _blocked(run, first.block, first.warn, first.files_checked)
    final = first
    untracked: List[str] = []
    if first.local_only:
        orphans = _unindexed(first)
        if orphans:
            raise _blocked(run, orphans, first.warn, first.files_checked)
        _record_local_only(run, first)
        final = safety.scan(target, safety.changed_paths(target), settings)
        if final.block:
            raise _blocked(run, final.block, final.warn, final.files_checked)
        tracked = safety.tracked_paths(target)
        untracked = sorted(item["path"] for item in first.local_only if item["path"] in tracked)
        for chunk in _in_chunks(untracked):
            _must(gitutil.git(["rm", "--cached", "-q", "--", *chunk], target), "rm --cached")
    warn = list(first.warn)
    warn.extend(item for item in final.warn if item not in warn)
    present = [name for name in ADD_PATHS
               if (target / name).exists() or (target / name).is_symlink()
               or gitutil.git(["ls-files", "--error-unmatch", "--", name], target).returncode == 0]
    _must(gitutil.git(["add", "-A", "--", *present], target), "add")
    staged = _executable_fix(target, paths)
    names = [item for item in _must(gitutil.git(["diff", "--cached", "--name-only", "-z"], target),
                                    "diff --cached").split("\0") if item]
    local_only = [dict(item, path=safety._display(item["path"])) for item in sorted(first.local_only,
                                                                                    key=lambda entry: entry["path"])]
    result: Dict[str, Any] = {"status": "nothing", "sha": None, "files": 0, "warn": warn, "local_only": local_only,
                              "untracked": [safety._display(path) for path in untracked],
                              "executable_cleared": [safety._display(path) for path in staged]}
    if not names:
        run.report["commit"] = result
        run.audit("commit", "nothing")
        return
    subject, body = _subject(names)
    message = ["-m", subject]
    if body:
        message += ["-m", body]
    message += ["-m", f"Workspace-Device: {run.device_id}"]
    _must(gitutil.git([*gitutil.identity_args(target), "commit", "-q", *message], target), "commit")
    sha = _head(target)
    result.update(status="committed", sha=sha, files=len(names), subject=subject)
    run.report["commit"] = result
    now = utc_now()
    _write_state(run.env, run.home, last_commit_at=now, last_result="ok")
    run.audit("commit", "ok", sha=sha, files=len(names))
    run.events.append(("workspace.sync.committed", {"sha": sha, "files": len(names)}))


def _executable_fix(target: Path, paths: Sequence[str]) -> List[str]:
    """Clear the execute bit in the index of the files this sync takes (rule PS-EXECUTABLE); returns the paths."""
    wanted = set(paths)
    out = _must(gitutil.git(["ls-files", "-s", "-z"], target), "ls-files")
    executable = []
    for record in out.split("\0"):
        if record:
            meta, _, path = record.partition("\t")
            if meta.split(" ")[0] == "100755" and path in wanted:
                executable.append(path)
    for chunk in _in_chunks(executable):
        _must(gitutil.git(["update-index", "--chmod=-x", "--", *chunk], target), "update-index")
    return sorted(executable)


# -------------------------------------------------------------------------------------------------- 2. pull


def _step_pull(run: _Run) -> None:
    run.operation = "pull"
    target, branch = run.target, run.branch
    gitutil.fetch(target, "origin", run.env)
    theirs = _ref(target, f"refs/remotes/origin/{branch}")
    head = _head(target)
    if theirs is None:
        run.report["pull"] = {"status": "no-remote-branch", "merged": False, "head": head}
        _finish_pull(run, head, False, "no-remote-branch")
        return
    if gitutil.git(["merge-base", "--is-ancestor", theirs, "HEAD"], target).returncode == 0:
        run.report["pull"] = {"status": "up-to-date", "merged": False, "head": head}
        _finish_pull(run, head, False, "up-to-date")
        return
    if gitutil.git(["merge-base", "HEAD", theirs], target).returncode != 0:
        raise SyncError("WORKSPACE_UNRELATED_HISTORIES", f"this workspace and origin/{branch} share no history; use "
                        f"`workspace clone` on a machine without a workspace", run.report)
    dry = gitutil.git(["merge-tree", "--write-tree", "--name-only", "-z", "--messages", "HEAD", theirs], target)
    if dry.returncode == 1:
        _report_conflict(run, theirs, head, _parse_merge_tree(dry.stdout))
    if dry.returncode != 0:
        detail = gitutil.redact_remote_text(dry.stderr.strip() or f"exit {dry.returncode}")
        raise SyncError("WORKSPACE_MERGE_FAILED", f"git merge-tree failed: {detail}", run.report)
    fast_forward = gitutil.git(["merge-base", "--is-ancestor", "HEAD", theirs], target).returncode == 0
    done = gitutil.git([*gitutil.identity_args(target), "merge", "--no-edit", "-m", f"skm(workspace): merge origin/{branch}",
                        theirs], target)
    if done.returncode != 0:
        _abort_merge(target)
        detail = gitutil.redact_remote_text(done.stderr.strip() or done.stdout.strip() or f"exit {done.returncode}")
        raise SyncError("WORKSPACE_MERGE_FAILED", f"git merge failed: {detail}", run.report)
    head = _head(target)
    run.report["pull"] = {"status": "fast-forward" if fast_forward else "merged", "merged": True, "head": head}
    _finish_pull(run, head, True, run.report["pull"]["status"])


def _finish_pull(run: _Run, head: str, merged: bool, status: str) -> None:
    _write_state(run.env, run.home, last_pull_at=utc_now(), last_result="ok", last_conflicts=None, pending_resolutions={})
    run.audit("pull", "ok", head=head, merged=merged, status=status)
    run.events.append(("workspace.sync.pulled", {"head": head, "merged": merged}))


def _abort_merge(target: Path) -> None:
    if _merge_in_progress(target):
        gitutil.git(["merge", "--abort"], target)


def _report_conflict(run: _Run, theirs: str, head: str, paths: Sequence[str]) -> None:
    rows = [conflict_row(path) for path in paths]
    _write_state(run.env, run.home, last_conflicts={"origin_head": theirs, "local_head": head, "at": utc_now(),
                                                     "conflicts": rows}, pending_resolutions={}, last_result="WORKSPACE_CONFLICT")
    run.audit("pull", "WORKSPACE_CONFLICT", head=head, origin_head=theirs, paths=list(paths))
    run.events.append(("workspace.sync.conflict", {"paths": list(paths)}))
    run.report["pull"] = {"status": "conflict", "merged": False, "head": head, "origin_head": theirs}
    run.report["conflicts"] = rows
    raise SyncError("WORKSPACE_CONFLICT", f"{len(rows)} file(s) changed on both sides; nothing was merged and the working "
                    f"tree is unchanged; decide each with `workspace sync --resolve PATH=local|remote`", run.report)


# ----------------------------------------------------------------------------------------------- 3. resolve


def _step_resolve(run: _Run, decisions: Mapping[str, str], reset: bool) -> None:
    run.operation = "resolve"
    state = read_state(run.env, run.home)
    last = state.get("last_conflicts") if isinstance(state.get("last_conflicts"), dict) else None
    rows = list(last["conflicts"]) if last else []
    known = [row["path"] for row in rows]
    pending: Dict[str, str] = {} if reset else dict(state.get("pending_resolutions") or {})
    if reset:
        _write_state(run.env, run.home, pending_resolutions={})
        run.audit("resolve", "reset")
        run.report["resolution"] = {"decided": 0, "remaining": sorted(known), "reset": True}
    if not decisions:
        return
    if last is None:
        raise SyncError("RESOLUTION_INCOMPLETE", f"no conflicts of a pull are waiting; run `{NEXT_PULL}` first", run.report)
    unknown = sorted(path for path in decisions if path not in known)
    if unknown:
        raise SyncError("RESOLUTION_INCOMPLETE", f"not a conflicting path of the last pull: {', '.join(unknown)}; "
                        f"conflicts: {', '.join(sorted(known))}", run.report)
    pending.update(decisions)
    _write_state(run.env, run.home, pending_resolutions=pending)
    remaining = sorted(path for path in known if path not in pending)
    run.report["resolution"] = {"decided": len(pending), "remaining": remaining}
    if remaining:
        run.audit("resolve", "partial", decided=len(pending), remaining=remaining)
        return
    _merge_resolved(run, last, pending)


def _stale(run: _Run, why: str) -> SyncError:
    _write_state(run.env, run.home, pending_resolutions={}, last_conflicts=None, last_result="WORKSPACE_CONFLICT_STALE")
    run.audit("resolve", "WORKSPACE_CONFLICT_STALE", why=why)
    return SyncError("WORKSPACE_CONFLICT_STALE", f"{why}; the decisions were dropped; run `{NEXT_PULL}` and decide again",
                     run.report)


def _merge_resolved(run: _Run, last: Mapping[str, Any], pending: Mapping[str, str]) -> None:
    target, branch = run.target, run.branch
    gitutil.fetch(target, "origin", run.env)
    theirs = _ref(target, f"refs/remotes/origin/{branch}")
    if theirs != last["origin_head"]:
        raise _stale(run, f"origin/{branch} moved since the conflicts were found")
    if _head(target) != last["local_head"]:
        raise _stale(run, "this workspace has new commits since the conflicts were found")
    started = gitutil.git([*gitutil.identity_args(target), "merge", "--no-commit", "--no-ff", theirs], target)
    try:
        if not _merge_in_progress(target):
            detail = gitutil.redact_remote_text(started.stderr.strip() or started.stdout.strip() or "no merge started")
            raise SyncError("WORKSPACE_MERGE_FAILED", f"git merge failed: {detail}", run.report)
        unmerged = [item for item in _must(gitutil.git(["diff", "--name-only", "--diff-filter=U", "-z"], target),
                                           "diff").split("\0") if item]
        extra = sorted(set(unmerged) - set(pending))
        if extra:
            _abort_merge(target)
            raise _stale(run, f"the merge conflicts in files that were not decided: {', '.join(extra)}")
        for path in sorted(set(unmerged)):
            _apply_side(target, path, pending[path])
        if _must(gitutil.git(["ls-files", "-u", "-z"], target), "ls-files").strip("\0"):
            raise SyncError("WORKSPACE_MERGE_FAILED", "files are still unmerged after the decisions", run.report)
        count = len(pending)
        _must(gitutil.git([*gitutil.identity_args(target), "commit", "-q", "-m",
                           f"skm(workspace): merge origin/{branch} (resolved {count})", "-m",
                           f"Workspace-Device: {run.device_id}"], target), "commit", "WORKSPACE_MERGE_FAILED")
    except BaseException:
        _abort_merge(target)
        raise
    head = _head(target)
    run.report["resolution"] = {"decided": len(pending), "remaining": [], "merged": True, "head": head}
    run.report["pull"] = {"status": "resolved", "merged": True, "head": head, "origin_head": theirs}
    _write_state(run.env, run.home, last_pull_at=utc_now(), last_result="ok", last_conflicts=None, pending_resolutions={})
    run.audit("resolve", "ok", head=head, resolved=sorted(pending), sides={path: pending[path] for path in sorted(pending)})
    run.events.append(("workspace.sync.pulled", {"head": head, "merged": True}))


def _apply_side(target: Path, path: str, side: str) -> None:
    """Take ``local`` (ours) or ``remote`` (theirs) for an unmerged path; a side that deleted the file deletes it."""
    stages = {record.partition("\t")[0].split(" ")[2] for record in
              _must(gitutil.git(["ls-files", "-u", "-z", "--", path], target), "ls-files").split("\0") if record}
    wanted = "2" if side == "local" else "3"
    if wanted in stages:
        _must(gitutil.git(["checkout", SIDES[side], "--", path], target), "checkout")
        _must(gitutil.git(["add", "--", path], target), "add")
    else:
        _must(gitutil.git(["rm", "-q", "--", path], target), "rm")


# --------------------------------------------------------------------------------------------------- 4. push


def _step_push(run: _Run) -> None:
    run.operation = "push"
    target, branch = run.target, run.branch
    head = _head(target)
    info = {"remote": run.remote, "branch": branch}
    run.report["push"] = {"status": "pending", "head": head, **info}
    if run.announce is not None:
        run.announce(dict(info))
    if _ref(target, f"refs/remotes/origin/{branch}") == head:
        run.report["push"]["status"] = "up-to-date"
        run.audit("push", "ok", head=head, status="up-to-date")
        _write_state(run.env, run.home, last_push_at=utc_now(), last_result="ok")
        return
    done = gitutil.git(["push", "origin", f"HEAD:{branch}"], target, env=gitutil.network_env(run.env))
    if done.returncode != 0:
        detail = gitutil.redact_remote_text(done.stderr.strip() or done.stdout.strip() or f"exit {done.returncode}")
        if "[rejected]" in detail or "non-fast-forward" in detail or "fetch first" in detail:
            run.report["push"]["status"] = "behind"
            raise SyncError("WORKSPACE_BEHIND", f"the remote branch {branch} has commits this workspace lacks; run "
                            f"`{NEXT_PULL}` and push again", run.report)
        run.report["push"]["status"] = "failed"
        raise SyncError("REMOTE_UNREACHABLE", f"git push failed: {detail}", run.report)
    run.report["push"]["status"] = "pushed"
    _write_state(run.env, run.home, last_push_at=utc_now(), last_result="ok")
    run.audit("push", "ok", head=head, status="pushed")
    run.events.append(("workspace.sync.pushed", {"head": head}))


# ---------------------------------------------------------------------------------------------------- sync


def plan_steps(commit: bool, pull: bool, push: bool, resolving: bool) -> Tuple[bool, bool, bool]:
    """``(commit, pull, push)`` to run. No flag: commit and pull. ``push`` needs steps 1 and 2 first, so it implies both
    (``--resolve`` replaces the pull: its merge is the pull, and a commit runs only when asked for)."""
    if resolving and pull:
        raise ValueError("--resolve works on the conflicts of the last pull and cannot be combined with --pull")
    if not (commit or pull or push or resolving):
        return True, True, False
    if push:
        return (commit or not resolving), not resolving, True
    return commit, pull, False


def sync(commit: bool = False, pull: bool = False, push: bool = False, resolve: Sequence[str] = (),
         resolve_reset: bool = False, root: Optional[PathLike] = None, env: Env = None, home: Optional[PathLike] = None,
         announce: Optional[Callable[[Dict[str, Any]], None]] = None) -> Dict[str, Any]:
    """Run the steps of ``sync`` (see the module text) and return the report. A refusal is a :class:`SyncError` whose
    ``report`` holds what was done before it. ``announce`` is called with ``{remote, branch}`` right before a push."""
    decisions = parse_resolutions(resolve)
    resolving = bool(decisions) or resolve_reset
    do_commit, do_pull, do_push = plan_steps(commit, pull, push, resolving)
    target = layout.root_of(root, env, home)
    document = layout.require_initialized(target)
    if not (target / ".git").exists():
        raise WorkspaceError("WORKSPACE_LAYOUT_INVALID", f"{target} is not a git repository")
    gitutil.require_version()
    steps = [name for name, on in (("commit", do_commit), ("pull", do_pull), ("resolve", resolving), ("push", do_push)) if on]
    run: Optional[_Run] = None
    try:
        with gitutil.git_lock(env, home):
            branch = _out(target, "symbolic-ref", "--short", "-q", "HEAD")
            if not branch:
                raise WorkspaceError("WORKSPACE_LAYOUT_INVALID", "the workspace repository has no branch checked out")
            remote = gitutil.remote_of(target)
            if remote is None and (do_pull or resolving or do_push):
                raise WorkspaceError("REMOTE_NOT_SET", "this workspace has no remote; run `workspace connect --remote URL`")
            device = layout._ensure_device(env, home)
            run = _Run(target, env, home, branch, remote, device["device_id"], document["workspace_id"], steps, announce)
            try:
                if _merge_in_progress(target):
                    raise SyncError("WORKSPACE_MERGE_IN_PROGRESS", "a merge is unfinished in the workspace repository; finish "
                                    "it or run `git merge --abort` there", run.report)
                if do_commit:
                    _step_commit(run)
                if do_pull:
                    _step_pull(run)
                if resolving:
                    _step_resolve(run, decisions, resolve_reset)
                    if do_push and run.report.get("resolution", {}).get("remaining"):
                        do_push = False
                if do_push:
                    _step_push(run)
            except WorkspaceError as exc:
                if not isinstance(exc, SyncError):
                    exc = SyncError(exc.code, exc.message, run.report)
                run.report["error"] = {"code": exc.code, "message": exc.message}
                if exc.code != "WORKSPACE_CONFLICT":
                    _fail(run, exc.code)
                raise exc from None
            run.report["result"] = "ok"
    finally:
        if run is not None:
            _emit(run)
    return run.report


def _fail(run: _Run, code: str) -> None:
    """Record a refusal in ``sync.json`` and ``audit.jsonl`` (a conflict and a stale decision record themselves)."""
    try:
        if code != "WORKSPACE_CONFLICT_STALE":
            _write_state(run.env, run.home, last_result=code)
            run.audit(run.operation, code)
    except OSError:
        pass


def _emit(run: _Run) -> None:
    for event_type, data in run.events:
        events.emit(event_type, data, subject=run.workspace_id, env=run.env, home=run.home)
