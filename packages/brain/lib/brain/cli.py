"""brain command line: ``python3 -m brain <command>`` (the ``bin/brain`` wrapper runs it)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from aicore.config import ConfigError
from aicore.state import find_project_root

from . import __version__, catalog, docs, doctor, errors, settings, vault
from .errors import BrainError

USAGE = """usage: brain <command> [options]

commands:
  vault [--json] [--project DIR]    print the vault path and where it was found
  project [--project DIR] [--json]  print the vault folder of a project
  docs integrate --project DIR [--dry-run]
                                    apply the project's document sync settings (pull and script)
  docs pull --project DIR [--dry-run]
                                    copy vault documents into the project
  docs push --project DIR [--dry-run] [--force]
                                    copy project documents into the vault (--force replaces changed files)
  docs script --project DIR         write .claude/sync-brain.sh
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
    p = sub.add_parser("docs")
    docs_sub = p.add_subparsers(dest="docs_command", parser_class=_Parser)
    docs_sub.required = True
    for name in ("integrate", "pull", "push", "script"):
        q = docs_sub.add_parser(name)
        q.add_argument("--project", metavar="DIR", required=True)
        if name != "script":
            q.add_argument("--dry-run", action="store_true")
        if name == "push":
            q.add_argument("--force", action="store_true")
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


def _docs_context(args: argparse.Namespace):
    root = _project_root(args.project)
    config = settings.load(root)
    info = vault.resolve_vault(config)
    _emit_warnings(config.warnings, info.warnings)
    return root, config, info, docs.DocsSync.from_settings(root, config, info)


def _relative(paths: Sequence[Path], base: Optional[Path]) -> List[str]:
    return [str(p.relative_to(base)) if base is not None else str(p) for p in paths]


def _docs_integrate(args: argparse.Namespace) -> int:
    root, config, info, sync = _docs_context(args)
    if not config.docs_enabled or sync.vault is None:
        if config.docs_enabled and info.path is not None:
            print(f"brain: warning: {errors.VAULT_MISSING}: vault directory {info.path} does not exist", file=sys.stderr)
        print("  doc-sync is off")
        return 0
    prefix = "[dry-run] would " if args.dry_run else ""
    script = root / docs.SCRIPT_RELATIVE
    if config.docs_direction in ("pull", "bidirectional"):
        copied = sync.pull(dry_run=args.dry_run)
        if args.dry_run:
            print(f"  [dry-run] would pull files from the vault by patterns ({', '.join(sync.patterns)}): {len(copied)}")
        else:
            print(f"  pull: copied files from the vault to the project: {len(copied)}")
    if args.dry_run:
        print(f"  {prefix}generate {docs.SCRIPT_RELATIVE} (vault={sync.vault}, direction={sync.direction})")
        return 0
    written = sync.write_script()
    print(f"  generated {written} (manual sync: bash {written.name} [pull|push])")
    return 0


def _docs_pull(args: argparse.Namespace) -> int:
    root, config, info, sync = _docs_context(args)
    vault.require(info)
    copied = sync.pull(dry_run=args.dry_run)
    if args.dry_run:
        for name in _relative(copied, root):
            print(f"[dry-run] would copy {name}")
    print(f"{'would copy' if args.dry_run else 'copied'} {len(copied)} files from the vault to the project")
    return 0


def _docs_push(args: argparse.Namespace) -> int:
    root, config, info, sync = _docs_context(args)
    vault_root = vault.require(info)
    copied = sync.push(dry_run=args.dry_run, force=args.force)
    for name in _relative(copied, vault_root):
        print(f"{'[dry-run] would copy' if args.dry_run else 'copied'} {name}")
    print(f"{'would copy' if args.dry_run else 'copied'} {len(copied)} files from the project to the vault")
    if sync.conflicts:
        names = ", ".join(_relative(sync.conflicts, vault_root))
        raise BrainError(errors.DOCS_CONFLICT,
                         f"{len(sync.conflicts)} files differ in the vault and were left alone: {names} "
                         "(use --force to replace them)")
    return 0


def _docs_script(args: argparse.Namespace) -> int:
    root, config, info, sync = _docs_context(args)
    print(sync.write_script())
    return 0


_DOCS_COMMANDS = {"integrate": _docs_integrate, "pull": _docs_pull, "push": _docs_push, "script": _docs_script}


def _cmd_docs(args: argparse.Namespace) -> int:
    return _DOCS_COMMANDS[args.docs_command](args)


_COMMANDS = {"vault": _cmd_vault, "project": _cmd_project, "doctor": _cmd_doctor, "version": _cmd_version,
             "docs": _cmd_docs}


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
