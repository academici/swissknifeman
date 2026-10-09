"""brain command line: ``python3 -m brain <command>`` (the ``bin/brain`` wrapper runs it)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from aicore.config import ConfigError
from aicore.state import find_project_root

from . import __version__, catalog, doctor, errors, settings, vault
from .errors import BrainError

USAGE = """usage: brain <command> [options]

commands:
  vault [--json] [--project DIR]    print the vault path and where it was found
  project [--project DIR] [--json]  print the vault folder of a project
  doctor [--json]                   check the vault, the configuration and the notes folder
  version                           print the version and the library path
  help                              show this text

exit codes: 0 ok, 1 failure (code on stderr), 2 usage error
"""


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(2, f"brain: usage: {message}\n")


def _build() -> argparse.ArgumentParser:
    parser = _Parser(prog="brain", add_help=False)
    sub = parser.add_subparsers(dest="command", parser_class=_Parser)
    for name in ("vault", "project"):
        p = sub.add_parser(name)
        p.add_argument("--project", metavar="DIR", default=None)
        p.add_argument("--json", action="store_true")
    p = sub.add_parser("doctor")
    p.add_argument("--project", metavar="DIR", default=None)
    p.add_argument("--json", action="store_true")
    sub.add_parser("version")
    return parser


def _project_root(value: Optional[str]) -> Path:
    return Path(value).expanduser().resolve() if value else find_project_root(Path.cwd())


def _emit_warnings(*groups: Sequence[str]) -> None:
    seen: List[str] = []
    for message in (m for group in groups for m in group):
        if message not in seen:
            seen.append(message)
            print(f"brain: warning: {message}", file=sys.stderr)


def _dump(doc: Any) -> None:
    print(json.dumps(doc, ensure_ascii=False, indent=2))


def _cmd_vault(args: argparse.Namespace) -> int:
    root = _project_root(args.project)
    config = settings.load(root)
    info = vault.resolve_vault(config)
    _emit_warnings(config.warnings, info.warnings)
    if args.json:
        _dump(info.to_dict())
    elif info.path is not None:
        print(f"{info.path}  (source: {info.source})")
    vault.require(info)
    return 0


def _cmd_project(args: argparse.Namespace) -> int:
    root = _project_root(args.project)
    config = settings.load(root)
    info = vault.resolve_vault(config)
    _emit_warnings(config.warnings, info.warnings)
    vault_root = vault.require(info)
    problems: List[str] = []
    found = catalog.find_project(vault_root, root, projects_dir=config.projects_dir, warnings=problems)
    _emit_warnings(problems)
    doc: Dict[str, Any] = {"project": str(root), "vault": str(vault_root),
                           "folder": None if found is None else str(found.folder),
                           "name": None if found is None else found.name,
                           "via": None if found is None else found.via}
    if args.json:
        _dump(doc)
    elif found is not None:
        print(f"{found.folder}  ({found.name}, via {found.via})")
    if found is None:
        raise BrainError(errors.PROJECT_NOT_IN_VAULT, f"{root} has no folder in the vault {vault_root}")
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    root = _project_root(args.project)
    results = doctor.run_checks(root)
    if args.json:
        _dump(results)
    else:
        for item in results:
            print(f"[{item['status']}] {item['check_id']}: {item['observed']}")
            for line in item.get("evidence", []):
                print(f"    {line}")
            if "remediation" in item:
                print(f"    fix: {item['remediation']}")
    return 1 if any(item["status"] == "fail" for item in results) else 0


def _cmd_version(args: argparse.Namespace) -> int:
    print(f"brain {__version__} ({Path(__file__).resolve().parent})")
    return 0


_COMMANDS = {"vault": _cmd_vault, "project": _cmd_project, "doctor": _cmd_doctor, "version": _cmd_version}


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        sys.stderr.write(USAGE)
        return 2
    if args[0] in ("help", "-h", "--help"):
        sys.stdout.write(USAGE)
        return 0
    if args[0] not in _COMMANDS:
        sys.stderr.write(f"brain: unknown command {args[0]!r}\n{USAGE}")
        return 2
    namespace = _build().parse_args(args)
    try:
        return _COMMANDS[namespace.command](namespace)
    except BrainError as exc:
        print(f"brain: {exc.code}: {exc.message}", file=sys.stderr)
        return 1
    except ConfigError as exc:
        print(f"brain: {exc}", file=sys.stderr)
        return 1
