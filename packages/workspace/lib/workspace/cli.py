"""workspace command line: ``python3 -m workspace.cli <command>`` (the ``bin/workspace`` wrapper runs it).

``--json`` prints one JSON object on stdout; a failure prints ``CODE: message`` on stderr and exits 1; wrong arguments exit 2.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, List, Optional, Sequence

from aicore.config import ConfigError
from aicore.state import (ProjectContextRequired, WorkspaceSelectionError, is_code, list_workspaces, resolve_project,
                          selected_workspace, workspaces_root)
from aicore.workspace import WorkspaceError, read_marker

from . import __version__, doctor, events, layout, migrate, projects, remote, sync

USAGE = """usage: workspace <command> [options]

A machine can hold several workspaces (one git repository each) under workspaces/<code>/. The command works with the one
named by --workspace CODE (anywhere in the arguments), else SKM_WORKSPACE, else the workspace of the project you are in,
else the only workspace of the machine.

commands:
  init --code CODE [--root DIR] [--json]
                                    create the workspace CODE (workspaces/CODE): layout, git repository, device file
  list [--json]                     the workspaces of this machine
  status [--fetch] [--json]         layout, git state, projects and their bindings on this machine
  doctor [--json]                   structural checks of the workspace and of the bindings
  doctor --publish-safety [--all] [--json]
                                    publish-safety rules on the files of the next commit (--all: every file);
                                    exit 1 when a rule blocks (PUBLISH_BLOCKED)
  project attach [--project DIR] [--name N] [--code CODE] [--yes] [--json]
                                    attach a checkout to a project (writes the marker, never commits it)
  project list [--json]             projects of the workspace and their bindings on this machine
  project show PROJECT_ID [--json]  project (code) record, binding and the plans the workspace holds
  project scan DIR... [--json]      bind the checkouts with a known marker found under DIR (depth 4)
  project rebind PROJECT_ID --path DIR [--json]
                                    replace the bound paths of a project by one checkout
  project detach PROJECT_ID [--path DIR] [--json]
                                    drop a binding of this machine; the workspace is not changed
  migrate discover [DIR...] [--json]
                                    checkouts with plans: launcher projects under DIR (default ~/projects) and the maind registry
  migrate plan --project DIR [--on-conflict keep-workspace|import-copy] [--allow-in-progress] [--local-only-secrets]
               [--code CODE] [--yes] [--json]
                                    dry run: classes, digests, publish-safety, comparison with the workspace; writes nothing
  migrate apply --project DIR [--on-conflict ...] [--lock-timeout S] [--allow-in-progress] [--local-only-secrets]
                [--code CODE] [--yes] [--json]
                                    move the plans into the workspace through the plans-migrator port; prints, never commits;
                                    --local-only-secrets keeps files with a secret pattern on this machine (not in git)
  migrate verify --project DIR [--json]
                                    digests of the workspace copies and of the old folders against the last report
  migrate rollback --project DIR [--json]
                                    marker back to legacy and the folders the migration brought in removed
  migrate cleanup --project DIR --confirm PROJECT_ID [--json]
                                    remove the old plans folders whose copy in the workspace is equal
  connect --remote URL [--branch B] [--json]
                                    classify the remote (empty or the same workspace) and add it as origin; never pushes
  clone URL [--code CODE] [--root DIR] [--json]
                                    make a workspace of this machine from a remote (the code comes from the remote's
                                    workspace.json; the folder must be absent or empty)
  sync [--commit] [--pull] [--push] [--resolve PATH=local|remote ...] [--resolve-reset] [--json]
                                    commit (publish-safety first), pull (dry merge, typed conflicts), resolve, push; no flag:
                                    commit and pull; --push needs and runs both; a conflict is never decided for you
  version                           print the version
  help                              show this text

exit codes: 0 ok, 1 failure (CODE: message on stderr), 2 usage error
with --json a refusal also prints {"error": {"code", "message"}} on stdout (contract schemas/command error)
"""

_ERROR_CODE = re.compile(r"[A-Z][A-Z0-9_]*")


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(2, f"workspace: usage: {message}\n")


def _build() -> argparse.ArgumentParser:
    parser = _Parser(prog="workspace", add_help=False)
    sub = parser.add_subparsers(dest="command", parser_class=_Parser)
    p = sub.add_parser("init")
    p.add_argument("--code", metavar="CODE", required=True)
    p.add_argument("--root", metavar="DIR", default=None)
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("list")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("status")
    p.add_argument("--fetch", action="store_true")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("doctor")
    p.add_argument("--publish-safety", action="store_true", dest="publish_safety")
    p.add_argument("--all", action="store_true")
    p.add_argument("--json", action="store_true")
    sub.add_parser("version")
    p = sub.add_parser("connect")
    p.add_argument("--remote", metavar="URL", required=True)
    p.add_argument("--branch", metavar="B", default=None)
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("clone")
    p.add_argument("url", metavar="URL")
    p.add_argument("--code", metavar="CODE", default=None)
    p.add_argument("--root", metavar="DIR", default=None)
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("sync")
    p.add_argument("--commit", action="store_true")
    p.add_argument("--pull", action="store_true")
    p.add_argument("--push", action="store_true")
    p.add_argument("--resolve", action="append", default=[], metavar="PATH=local|remote")
    p.add_argument("--resolve-reset", action="store_true", dest="resolve_reset")
    p.add_argument("--json", action="store_true")
    project = sub.add_parser("project")
    commands = project.add_subparsers(dest="project_command", parser_class=_Parser)
    commands.required = True
    p = commands.add_parser("attach")
    p.add_argument("--project", metavar="DIR", default=None)
    p.add_argument("--name", metavar="N", default=None)
    p.add_argument("--code", metavar="CODE", default=None)
    p.add_argument("--yes", action="store_true")
    p.add_argument("--json", action="store_true")
    p = commands.add_parser("list")
    p.add_argument("--json", action="store_true")
    p = commands.add_parser("show")
    p.add_argument("project_id")
    p.add_argument("--json", action="store_true")
    p = commands.add_parser("scan")
    p.add_argument("directories", nargs="+", metavar="DIR")
    p.add_argument("--json", action="store_true")
    p = commands.add_parser("rebind")
    p.add_argument("project_id")
    p.add_argument("--path", metavar="DIR", required=True)
    p.add_argument("--json", action="store_true")
    p = commands.add_parser("detach")
    p.add_argument("project_id")
    p.add_argument("--path", metavar="DIR", default=None)
    p.add_argument("--json", action="store_true")
    migrator = sub.add_parser("migrate")
    steps = migrator.add_subparsers(dest="migrate_command", parser_class=_Parser)
    steps.required = True
    p = steps.add_parser("discover")
    p.add_argument("directories", nargs="*", metavar="DIR")
    p.add_argument("--json", action="store_true")
    for name in ("plan", "apply"):
        p = steps.add_parser(name)
        p.add_argument("--project", metavar="DIR", default=None)
        p.add_argument("--on-conflict", dest="on_conflict", choices=migrate.ON_CONFLICT, default=None)
        p.add_argument("--allow-in-progress", dest="allow_in_progress", action="store_true")
        p.add_argument("--local-only-secrets", dest="local_only_secrets", action="store_true")
        p.add_argument("--code", metavar="CODE", default=None)
        p.add_argument("--yes", action="store_true")
        p.add_argument("--json", action="store_true")
        if name == "apply":
            p.add_argument("--lock-timeout", dest="lock_timeout", type=int, default=30, metavar="S")
    for name in ("verify", "rollback", "cleanup"):
        p = steps.add_parser(name)
        p.add_argument("--project", metavar="DIR", default=None)
        p.add_argument("--json", action="store_true")
        if name == "cleanup":
            p.add_argument("--confirm", metavar="PROJECT_ID", required=True)
    return parser


def _dump(doc: Any) -> None:
    print(json.dumps(doc, ensure_ascii=False, indent=2))


def _cmd_init(args: argparse.Namespace) -> int:
    result = layout.init(args.code, args.root)
    if result["created"]:
        events.emit("workspace.root.initialized", {"code": result["code"], "workspace_id": result["workspace_id"]},
                    subject=result["workspace_id"])
    if args.root is not None and layout.root_of(args.root) != layout.root_of(None):
        print(f"note: {result['root']} is outside {workspaces_root()}; commands find this workspace only there",
              file=sys.stderr)
    if args.json:
        _dump(result)
    elif result["already_initialized"]:
        print(f"workspace {result['code']} ({result['workspace_id']}) is already initialized at {result['root']}")
    else:
        print(f"created workspace {result['code']} ({result['workspace_id']}) at {result['root']} "
              f"(device {result['device_id']})")
    return 0


def _cmd_list_workspaces(args: argparse.Namespace) -> int:
    rows = layout.list_rows()
    if args.json:
        _dump({"workspaces": rows})
        return 0
    for row in rows:
        print(f"{row['code']}  {row['remote'] or 'no remote'}  {row['projects']} project(s)  {row['root']}")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    doc = layout.status(None, fetch=args.fetch)
    if args.json:
        _dump(doc)
        return 0
    git = doc["git"] or {}
    print(f"workspace {doc['code']} ({doc['workspace_id']}) at {doc['root']}")
    if doc["git"] is None:
        print("git: not a repository")
    else:
        remote = git["remote"] or "no remote"
        tracking = "" if git["ahead"] is None else f", ahead {git['ahead']}, behind {git['behind']}"
        tracking += " (diverged)" if git["diverged"] else ""
        print(f"git: branch {git['branch']}, {git['dirty']} changed, {remote}{tracking}")
    for row in doc["projects"]:
        where = ", ".join(row["paths"]) if row["bound"] else "not bound here"
        print(f"project {row['project_id']} {row['name']}: {row['plans']} plans, store {row['plans_store'] or '-'}, {where}")
    if doc["last_sync"]:
        print(f"last sync: {json.dumps(doc['last_sync'], ensure_ascii=False)}")
    return 0


def _publish_text(report: Any) -> None:
    print(f"publish-safety: {report.verdict} ({report.files_checked} files checked)")
    for label, items in (("block", report.block), ("warn", report.warn)):
        for item in items:
            where = item["path"] + (f":{item['line']}" if "line" in item else "")
            print(f"[{label}] {item['rule']} {where}: {item['detail']}")
    for item in sorted(report.local_only, key=lambda entry: entry["path"]):
        print(f"[local-only] {item['path']} ({item['reason']}, {item['bytes']} bytes)")


def _cmd_publish_safety(args: argparse.Namespace) -> int:
    report = doctor.publish_safety(every_file=args.all)
    if args.json:
        _dump(report.to_dict())
    else:
        _publish_text(report)
    if report.block:
        print(f"PUBLISH_BLOCKED: {len(report.block)} finding(s) forbid publishing the workspace; fix them and run "
              f"`workspace doctor --publish-safety` again", file=sys.stderr)
        return 1
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    if args.publish_safety:
        return _cmd_publish_safety(args)
    if args.all:
        print("workspace: usage: --all needs --publish-safety", file=sys.stderr)
        return 2
    checks = doctor.run_checks()
    if args.json:
        _dump({"checks": checks})
    else:
        for item in checks:
            print(f"[{item['status']}] {item['check_id']}: {item['observed']}")
            for line in item.get("evidence", []):
                print(f"    {line}")
            if "remediation" in item:
                print(f"    fix: {item['remediation']}")
    return 1 if any(item["status"] == "fail" for item in checks) else 0


def _cmd_connect(args: argparse.Namespace) -> int:
    doc = remote.connect(args.remote, args.branch)
    if args.json:
        _dump(doc)
        return 0
    print(f"connected {doc['remote']} as origin (branch {doc['branch']}, remote is {doc['classification']})")
    print(f"next: {doc['next']}")
    return 0


def _cmd_clone(args: argparse.Namespace) -> int:
    doc = remote.clone(args.url, args.root, code=args.code)
    if args.root is not None:
        print(f"note: {doc['root']} was chosen with --root; commands find a workspace only in {workspaces_root()}",
              file=sys.stderr)
    if args.json:
        _dump(doc)
        return 0
    print(f"cloned workspace {doc['code']} ({doc['workspace_id']}) from {doc['remote']} to {doc['root']} "
          f"(device {doc['device_id']})")
    print(f"next: {doc['next']}")
    return 0


def _sync_text(doc: Any) -> None:
    commit = doc.get("commit")
    if commit is not None:
        if commit["status"] == "committed":
            print(f"commit {commit['sha'][:12]}: {commit['subject']}")
        elif commit["status"] == "nothing":
            print("commit: nothing to commit")
        else:
            for label in ("block", "warn"):
                for item in commit.get(label, []):
                    where = item["path"] + (f":{item['line']}" if "line" in item else "")
                    print(f"[{label}] {item['rule']} {where}: {item['detail']}")
        for item in commit.get("warn", []):
            if commit["status"] != "blocked":
                where = item["path"] + (f":{item['line']}" if "line" in item else "")
                print(f"[warn] {item['rule']} {where}: {item['detail']}")
        for path in commit.get("untracked", []):
            print(f"[warn] {path} is local-only now: removed from the git index, kept on disk")
        for item in commit.get("local_only", []):
            print(f"[local-only] {item['path']} ({item['reason']}, {item['bytes']} bytes)")
    pull = doc.get("pull")
    if pull is not None:
        print(f"pull: {pull['status']} (HEAD {pull['head'][:12]})")
    for row in doc.get("conflicts", []):
        where = " ".join(f"{key} {row[key]}" for key in ("project_id", "plan", "ref") if row.get(key))
        print(f"conflict {row['path']}" + (f"  ({where})" if where else ""))
    resolution = doc.get("resolution")
    if resolution is not None:
        print(f"resolve: {resolution['decided']} decided, {len(resolution['remaining'])} remaining"
              + (f": {', '.join(resolution['remaining'])}" if resolution["remaining"] else ""))
    push = doc.get("push")
    if push is not None:
        print(f"push: {push['status']} ({push['remote']} {push['branch']}, HEAD {push['head'][:12]})")


def _cmd_sync(args: argparse.Namespace) -> int:
    def announce(info: Any) -> None:
        if not args.json:
            print(f"pushing to {info['remote']} branch {info['branch']}", flush=True)

    try:
        doc = sync.sync(commit=args.commit, pull=args.pull, push=args.push, resolve=args.resolve,
                        resolve_reset=args.resolve_reset, announce=announce)
    except sync.SyncError as exc:
        if args.json:
            _dump(exc.report)
        else:
            _sync_text(exc.report)
        print(str(exc), file=sys.stderr)
        return 1
    if args.json:
        _dump(doc)
    else:
        _sync_text(doc)
    return 0


def _cmd_version(args: argparse.Namespace) -> int:
    print(__version__)
    return 0


def _project_root(value: Optional[str]) -> Path:
    context = resolve_project(Path.cwd(), explicit=value)
    if context is None:
        raise ProjectContextRequired(Path.cwd())
    return context.root


def _cmd_attach(args: argparse.Namespace) -> int:
    result = projects.attach(_project_root(args.project), name=args.name, yes=args.yes, code=args.code)
    events.emit("workspace.project.attached", {"project_id": result["project_id"], "created": result["created"]},
                subject=result["project_id"])
    if args.json:
        _dump(result)
        return 0
    print(f"attached {result['name']} as {result['project_id']} (plans store: {result['plans_store']})")
    if result["marker_written"]:
        print("marker written to the checkout")
    if "next" in result:
        print(f"next: {result['next']}")
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    rows = projects.list_projects()
    if args.json:
        _dump({"projects": rows})
        return 0
    for row in rows:
        where = ", ".join(row["paths"]) if row["bound"] else "not bound here"
        print(f"{row['project_id']}  {row['name']}  [{row['status']}]  {where}")
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    doc = projects.show(args.project_id)
    if args.json:
        _dump(doc)
        return 0
    record, plans = doc["project"], doc["plans"]
    print(f"{record['project_id']}  {record['name']}  [{record['status']}]")
    print("remotes: " + (", ".join(record["identity"]["remotes"]) or "-"))
    print("bound: " + (", ".join(doc["binding"]["paths"]) if doc["binding"] else "not bound here"))
    print(f"plans: {len(plans['plans'])}, archived: {len(plans['archived'])}, legacy: {len(plans['legacy'])}, "
          f"migrations: {len(plans['migrations'])}")
    return 0


def _cmd_scan(args: argparse.Namespace) -> int:
    doc = projects.scan(args.directories)
    if args.json:
        _dump(doc)
        return 0
    for item in doc["bound"]:
        print(f"bound {item['project_id']} {item['path']}")
    for item in doc["unknown"]:
        print(f"unknown {item['project_id']} {item['path']}")
    for item in doc["skipped"]:
        print(f"skipped {item['path']} ({item['reason']})")
    return 0


def _cmd_rebind(args: argparse.Namespace) -> int:
    doc = projects.rebind(args.project_id, args.path)
    if args.json:
        _dump(doc)
    else:
        print(f"{doc['project_id']} is bound to {doc['binding']['primary']}")
    return 0


def _cmd_detach(args: argparse.Namespace) -> int:
    doc = projects.detach(args.project_id, args.path)
    if args.json:
        _dump(doc)
    elif doc["removed"]:
        print(f"detached {doc['project_id']}" + (f" ({args.path})" if args.path else ""))
    else:
        print(f"{doc['project_id']} had no such binding")
    return 0


def _mib(size: int) -> str:
    return f"{size / 1048576:.1f} MiB"


def _cmd_discover(args: argparse.Namespace) -> int:
    doc = migrate.discover(args.directories)
    if args.json:
        _dump(doc)
        return 0
    for row in doc["candidates"]:
        marker = row["marker"]
        state = f"{marker['project_id']} store {marker['plans_store']}" if marker else row.get("marker_error", "no marker")
        counts = row["plans"]
        print(f"{row['path']}  [{', '.join(row['sources'])}]  {counts['v4']} plans, {counts['legacy']} legacy, "
              f"{counts['files']} files, {_mib(counts['bytes'])}  ({state})")
    for item in doc["skipped"]:
        print(f"skipped {item['path']} ({item['reason']})")
    return 0


def _cmd_migrate_plan(args: argparse.Namespace) -> int:
    plan = migrate.build_plan(_project_root(args.project), args.on_conflict, args.allow_in_progress, args.yes,
                              local_only_secrets=args.local_only_secrets, code=args.code)
    doc = plan.document
    if args.json:
        _dump(doc)
    else:
        project = doc["project"]
        print(f"project {project['project_id'] or '(new)'} {project['name']}: mode {doc['mode']}"
              + (", already migrated" if doc["already_migrated"] else ""))
        for row in doc["plans"]:
            suffix = f" as {row['stored_as']}" if "stored_as" in row else ""
            print(f"  {row['action']:<14} {row['class']:<6} {row['name']}{suffix}  ({row['files']} files, {_mib(row['bytes'])})")
        for item in doc["warnings"]:
            print(f"warn {item['code']}: {item['count']} (e.g. {', '.join(item['paths'][:3])})")
        if doc["local_only"]:
            print(f"local-only: {len(doc['local_only'])} file(s), {_mib(sum(item['bytes'] for item in doc['local_only']))}")
        if doc["conflicts"]:
            print(f"conflicts: {', '.join(doc['conflicts'])}; apply needs --on-conflict keep-workspace|import-copy")
        for blocker in doc["blockers"]:
            print(f"BLOCKED {blocker['code']}: {blocker['message']}")
    if doc["blockers"]:
        print(f"{doc['blockers'][0]['code']}: {doc['blockers'][0]['message']}", file=sys.stderr)
        return 1
    return 0


def _print_next(doc: Any) -> None:
    for line in doc.get("next", []):
        print(f"next: {line}")


def _cmd_migrate_apply(args: argparse.Namespace) -> int:
    doc = migrate.apply(_project_root(args.project), args.on_conflict, args.lock_timeout, args.allow_in_progress, args.yes,
                        local_only_secrets=args.local_only_secrets, code=args.code)
    attached = doc.pop("attached", None)
    if attached is not None:
        events.emit("workspace.project.attached", {"project_id": attached["project_id"], "created": attached["created"]},
                    subject=attached["project_id"])
    if not doc["noop"]:
        events.emit("workspace.migration.applied", {"project_id": doc["project_id"], "op_id": doc["op_id"],
                                                    "mode": doc["mode"], "plans": len(doc["plans"]),
                                                    "local_only": doc["local_only"]}, subject=doc["project_id"])
    if args.json:
        _dump(doc)
        return 0
    if doc["noop"]:
        print("nothing to do: the plans are already in the workspace")
        return 0
    print(f"migrated {len(doc['plans'])} folder(s) of {doc['project_id']} ({doc['mode']}), {doc['local_only']} local-only; "
          f"report {doc['report']}")
    for line in doc["notes"]:
        print(f"note: {line}")
    _print_next(doc)
    return 0


def _cmd_migrate_verify(args: argparse.Namespace) -> int:
    doc = migrate.verify(_project_root(args.project))
    if args.json:
        _dump(doc)
        return 0
    for row in doc["plans"]:
        print(f"{row['state']:<21} {row['class']:<6} {row['name']}")
    return 0


def _cmd_migrate_rollback(args: argparse.Namespace) -> int:
    doc = migrate.rollback(_project_root(args.project))
    events.emit("workspace.migration.rolled-back", {"project_id": doc["project_id"], "op_id": doc["op_id"]},
                subject=doc["project_id"])
    if args.json:
        _dump(doc)
        return 0
    print(f"rolled back {doc['op_id']}: the marker of {doc['project_id']} is legacy, {len(doc['removed'])} folder(s) removed")
    _print_next(doc)
    return 0


def _cmd_migrate_cleanup(args: argparse.Namespace) -> int:
    doc = migrate.cleanup(_project_root(args.project), args.confirm)
    if args.json:
        _dump(doc)
        return 0
    for name in doc["removed"]:
        print(f"removed {name}")
    for item in doc["kept"]:
        print(f"kept {item['name']} ({item['reason']})")
    if doc["plans_removed"]:
        print("removed the empty plans folder")
    _print_next(doc)
    return 0


_COMMANDS = {"init": _cmd_init, "list": _cmd_list_workspaces, "status": _cmd_status, "doctor": _cmd_doctor, "version": _cmd_version,
             "connect": _cmd_connect, "clone": _cmd_clone, "sync": _cmd_sync}
_PROJECT = {"attach": _cmd_attach, "list": _cmd_list, "show": _cmd_show, "scan": _cmd_scan, "rebind": _cmd_rebind,
            "detach": _cmd_detach}
_MIGRATE = {"discover": _cmd_discover, "plan": _cmd_migrate_plan, "apply": _cmd_migrate_apply,
            "verify": _cmd_migrate_verify, "rollback": _cmd_migrate_rollback, "cleanup": _cmd_migrate_cleanup}


def _take_workspace_option(args: List[str]) -> Optional[str]:
    """Remove ``--workspace CODE`` / ``--workspace=CODE`` from ``args`` and return the code (``None`` when absent)."""
    found: Optional[str] = None
    index = 0
    while index < len(args):
        value = args[index]
        if value == "--workspace" and index + 1 < len(args):
            found = args[index + 1]
            del args[index:index + 2]
            continue
        if value.startswith("--workspace="):
            found = value.split("=", 1)[1]
            del args[index]
            continue
        index += 1
    return found


def _workspace_of_cwd() -> Optional[str]:
    """The workspace the project you are in belongs to (its marker), else ``None``."""
    try:
        context = resolve_project(Path.cwd())
        marker = read_marker(context.root) if context is not None else None
    except Exception:  # a damaged marker is reported by the command that needs the project
        return None
    return marker["workspace"] if marker else None


# commands that choose or create a workspace themselves, or need none
_WITHOUT_SELECTION = frozenset({"init", "list", "clone", "version"})


def _select_workspace(command: str, option: Optional[str]) -> None:
    """Make ``SKM_WORKSPACE`` name the workspace of this run (``--workspace``, the environment, the project you are in,
    the only workspace of the machine). ``init`` names it with ``--code``; ``clone`` reads it from the remote."""
    if command in _WITHOUT_SELECTION:
        if option is not None:
            os.environ["SKM_WORKSPACE"] = option
        return
    if option is not None:
        if not is_code(option):
            raise WorkspaceError("WORKSPACE_CODE_INVALID", f"--workspace {option!r} is not a workspace code")
        os.environ["SKM_WORKSPACE"] = option
        return
    if os.environ.get("SKM_WORKSPACE"):
        return
    chosen = _workspace_of_cwd()
    if chosen is not None:
        os.environ["SKM_WORKSPACE"] = chosen
        return
    os.environ["SKM_WORKSPACE"] = selected_workspace()  # the only workspace, else WORKSPACE_NOT_FOUND / _AMBIGUOUS


def _error_document(exc: BaseException, code: Optional[str] = None) -> dict:
    """The failure as the ``error`` contract of ``schemas/command``: a stable ``code`` and the message after ``CODE: ``."""
    text = str(exc)
    if code is None:
        code = getattr(exc, "code", None)
        if not (isinstance(code, str) and _ERROR_CODE.fullmatch(code)):
            found = re.match(r"([A-Z][A-Z0-9_]*): ", text)
            code = found.group(1) if found else "ERROR"
    prefix = f"{code}: "
    message = text[len(prefix):] if text.startswith(prefix) else text
    return {"error": {"code": code, "message": message or code}}


def _fail(namespace: argparse.Namespace, exc: BaseException, code: Optional[str] = None) -> None:
    """Print a refusal as ``CODE: message`` on stderr; with ``--json`` also the ``error`` document on stdout."""
    document = _error_document(exc, code)
    print(f"{document['error']['code']}: {document['error']['message']}" if code else str(exc), file=sys.stderr)
    if getattr(namespace, "json", False):
        _dump(document)


def main(argv: Optional[Sequence[str]] = None) -> int:
    saved = os.environ.get("SKM_WORKSPACE")
    try:
        return _main(argv)
    finally:
        if saved is None:
            os.environ.pop("SKM_WORKSPACE", None)
        else:
            os.environ["SKM_WORKSPACE"] = saved


def _main(argv: Optional[Sequence[str]] = None) -> int:
    args: List[str] = list(sys.argv[1:] if argv is None else argv)
    option = _take_workspace_option(args)
    if not args:
        sys.stderr.write(USAGE)
        return 2
    if args[0] in ("help", "-h", "--help"):
        sys.stdout.write(USAGE)
        return 0
    if args[0] == "--version":
        args = ["version"]
    if args[0] not in (*_COMMANDS, "project", "migrate"):
        sys.stderr.write(f"workspace: unknown command {args[0]!r}\n{USAGE}")
        return 2
    try:
        namespace = _build().parse_args(args)
    except SystemExit as exc:  # argparse reports a usage error by exiting with 2
        return exc.code if isinstance(exc.code, int) else 2
    if namespace.command == "project":
        handler = _PROJECT[namespace.project_command]
    elif namespace.command == "migrate":
        handler = _MIGRATE[namespace.migrate_command]
    else:
        handler = _COMMANDS[namespace.command]
    try:
        _select_workspace(namespace.command, option)
        return handler(namespace)
    except (WorkspaceError, WorkspaceSelectionError, ProjectContextRequired, ConfigError) as exc:
        _fail(namespace, exc)
        return 1
    except ValueError as exc:
        _fail(namespace, exc, "INVALID_ARGUMENT")
        return 2


if __name__ == "__main__":
    sys.exit(main())
