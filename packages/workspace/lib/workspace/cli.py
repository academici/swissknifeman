"""workspace command line: ``python3 -m workspace.cli <command>`` (the ``bin/workspace`` wrapper runs it).

``--json`` prints one JSON object on stdout; a failure prints ``CODE: message`` on stderr and exits 1; wrong arguments exit 2.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, List, Optional, Sequence

from aicore.config import ConfigError
from aicore.state import ProjectContextRequired, resolve_project
from aicore.workspace import WorkspaceError

from . import __version__, doctor, events, layout, projects

USAGE = """usage: workspace <command> [options]

commands:
  init [--root DIR] [--json]        create the workspace layout, its git repository and the device file
  status [--fetch] [--json]         layout, git state, projects and their bindings on this machine
  doctor [--json]                   structural checks of the workspace and of the bindings
  doctor --publish-safety [--all] [--json]
                                    publish-safety rules on the files of the next commit (--all: every file);
                                    exit 1 when a rule blocks (PUBLISH_BLOCKED)
  project attach [--project DIR] [--name N] [--yes] [--json]
                                    attach a checkout to a project (writes the marker, never commits it)
  project list [--json]             projects of the workspace and their bindings on this machine
  project show PROJECT_ID [--json]  project record, binding and the plans the workspace holds
  project scan DIR... [--json]      bind the checkouts with a known marker found under DIR (depth 4)
  project rebind PROJECT_ID --path DIR [--json]
                                    replace the bound paths of a project by one checkout
  project detach PROJECT_ID [--path DIR] [--json]
                                    drop a binding of this machine; the workspace is not changed
  version                           print the version
  help                              show this text

exit codes: 0 ok, 1 failure (CODE: message on stderr), 2 usage error
"""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(2, f"workspace: usage: {message}\n")


def _build() -> argparse.ArgumentParser:
    parser = _Parser(prog="workspace", add_help=False)
    sub = parser.add_subparsers(dest="command", parser_class=_Parser)
    p = sub.add_parser("init")
    p.add_argument("--root", metavar="DIR", default=None)
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("status")
    p.add_argument("--fetch", action="store_true")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("doctor")
    p.add_argument("--publish-safety", action="store_true", dest="publish_safety")
    p.add_argument("--all", action="store_true")
    p.add_argument("--json", action="store_true")
    sub.add_parser("version")
    project = sub.add_parser("project")
    commands = project.add_subparsers(dest="project_command", parser_class=_Parser)
    commands.required = True
    p = commands.add_parser("attach")
    p.add_argument("--project", metavar="DIR", default=None)
    p.add_argument("--name", metavar="N", default=None)
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
    return parser


def _dump(doc: Any) -> None:
    print(json.dumps(doc, ensure_ascii=False, indent=2))


def _cmd_init(args: argparse.Namespace) -> int:
    result = layout.init(args.root)
    if result["created"]:
        events.emit("workspace.root.initialized", {"workspace_id": result["workspace_id"]}, subject=result["workspace_id"])
    if args.root is not None and layout.root_of(args.root) != layout.root_of(None):
        print(f"note: other commands use {layout.root_of(None)}; set SKM_WORKSPACE_ROOT={result['root']} to use this "
              f"workspace", file=sys.stderr)
    if args.json:
        _dump(result)
    elif result["already_initialized"]:
        print(f"workspace {result['workspace_id']} is already initialized at {result['root']}")
    else:
        print(f"created workspace {result['workspace_id']} at {result['root']} (device {result['device_id']})")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    doc = layout.status(None, fetch=args.fetch)
    if args.json:
        _dump(doc)
        return 0
    git = doc["git"] or {}
    print(f"workspace {doc['workspace_id']} at {doc['root']}")
    if doc["git"] is None:
        print("git: not a repository")
    else:
        remote = git["remote"] or "no remote"
        tracking = "" if git["ahead"] is None else f", ahead {git['ahead']}, behind {git['behind']}"
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


def _cmd_version(args: argparse.Namespace) -> int:
    print(__version__)
    return 0


def _project_root(value: Optional[str]) -> Path:
    context = resolve_project(Path.cwd(), explicit=value)
    if context is None:
        raise ProjectContextRequired(Path.cwd())
    return context.root


def _cmd_attach(args: argparse.Namespace) -> int:
    result = projects.attach(_project_root(args.project), name=args.name, yes=args.yes)
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


_COMMANDS = {"init": _cmd_init, "status": _cmd_status, "doctor": _cmd_doctor, "version": _cmd_version}
_PROJECT = {"attach": _cmd_attach, "list": _cmd_list, "show": _cmd_show, "scan": _cmd_scan, "rebind": _cmd_rebind,
            "detach": _cmd_detach}


def main(argv: Optional[Sequence[str]] = None) -> int:
    args: List[str] = list(sys.argv[1:] if argv is None else argv)
    if not args:
        sys.stderr.write(USAGE)
        return 2
    if args[0] in ("help", "-h", "--help"):
        sys.stdout.write(USAGE)
        return 0
    if args[0] == "--version":
        args = ["version"]
    if args[0] not in (*_COMMANDS, "project"):
        sys.stderr.write(f"workspace: unknown command {args[0]!r}\n{USAGE}")
        return 2
    try:
        namespace = _build().parse_args(args)
    except SystemExit as exc:  # argparse reports a usage error by exiting with 2
        return exc.code if isinstance(exc.code, int) else 2
    handler = _PROJECT[namespace.project_command] if namespace.command == "project" else _COMMANDS[namespace.command]
    try:
        return handler(namespace)
    except WorkspaceError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except ProjectContextRequired as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"INVALID_ARGUMENT: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
