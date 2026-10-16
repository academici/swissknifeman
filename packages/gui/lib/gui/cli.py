"""gui command line: ``python3 -m gui.cli <command>`` (the ``bin/gui`` wrapper runs it).

This module must stay importable on the hub Python (3.9) so that an old interpreter gets a clean
``PYTHON_TOO_OLD`` failure instead of a syntax error.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from . import MIN_PYTHON, __version__

PYTHON_TOO_OLD = "PYTHON_TOO_OLD"

EXIT_FAILURE = 1
EXIT_USAGE = 2


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"gui: usage: {message}\n")


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="gui", description="Local control plane of Swiss Knife Man (desktop and browser mode).")
    parser.add_argument("--version", action="version", version=f"gui {__version__}")
    sub = parser.add_subparsers(dest="command", parser_class=_Parser, metavar="<command>")
    p = sub.add_parser("contributions", help="print the resolved catalog of GUI contributions (catalog/v1)")
    p.add_argument("--json", action="store_true", help="print the catalog/v1 document")
    p.add_argument("--project", metavar="DIR", default=None, help="project whose extensions count (default: none)")
    p = sub.add_parser("check", help="check one contribution: its rules and the conformance of its handler")
    p.add_argument("path", metavar="PATH", help="a gui.json file or a unit or extension folder that declares one")
    p.add_argument("--json", action="store_true", help="print a list of check-result/v1 documents")
    p = sub.add_parser("deps", help="third-party Python packages of the backend (requirements.lock)")
    deps_sub = p.add_subparsers(dest="deps_command", parser_class=_Parser, metavar="<action>", required=True)
    q = deps_sub.add_parser("ensure", help="install the locked wheels once (pip when it works, else from PyPI)")
    q.add_argument("--json", action="store_true", help="print {path, lock_digest, installed}")
    q.add_argument("--offline", action="store_true", help="never download: fail unless already installed")
    deps_sub.add_parser("path", help="print the install folder of the lock")
    return parser


def _contributions(args: argparse.Namespace) -> int:
    from .catalog import resolve, sources

    project = Path(args.project).expanduser().resolve() if args.project else None
    catalog = resolve.resolve(sources.collect(project))
    if args.json:
        print(json.dumps(catalog, indent=2, ensure_ascii=False))
        return 0
    rows = [(entry["owner"], entry["source"], *(str(len(entry["document"].get(name, ())))
                                                 for name in ("routes", "queries", "commands")), entry["file"])
            for entry in catalog["contributions"]]
    header = ("owner", "source", "routes", "queries", "commands", "file")
    widths = [max(len(row[index]) for row in [header, *rows]) for index in range(len(header) - 1)]
    for row in [header, *rows]:
        print("  ".join(cell.ljust(width) for cell, width in zip(row, widths)) + "  " + row[-1])
    if catalog["rejected"]:
        print("rejected:")
        for entry in catalog["rejected"]:
            print(f"  {entry['code']} {entry['owner'] or '-'} {entry['file']}: {entry['message']}")
    print(f"digest: {catalog['digest']}")
    return 0


def _check(args: argparse.Namespace) -> int:
    from .catalog import resolve

    results = resolve.check(Path(args.path))
    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        for result in results:
            print(f"{result['status']} {result['check_id']}: {result['observed']}")
    return EXIT_FAILURE if any(result["status"] == "fail" for result in results) else 0


def _deps(args: argparse.Namespace) -> int:
    from . import deps

    try:
        if args.deps_command == "path":
            print(deps.site_dir())
            return 0
        present = deps.is_complete(deps.site_dir())
        folder = deps.ensure(offline=args.offline)
    except deps.GuiDepsError as error:
        print(str(error), file=sys.stderr)
        return EXIT_FAILURE
    if args.json:
        print(json.dumps({"path": str(folder), "lock_digest": deps.lock_digest(), "installed": not present}))
    else:
        print(f"{'present' if present else 'installed'}: {folder}")
    return 0


def check_python(version_info: Optional[Sequence[int]] = None) -> Optional[str]:
    """The ``PYTHON_TOO_OLD`` message when the interpreter is older than ``MIN_PYTHON``, else ``None``."""
    current: Tuple[int, ...] = tuple(version_info if version_info is not None else sys.version_info)[:2]
    if current >= MIN_PYTHON:
        return None
    need = ".".join(str(part) for part in MIN_PYTHON)
    have = ".".join(str(part) for part in current)
    return f"{PYTHON_TOO_OLD}: gui requires Python >= {need}, found {have}"


def main(argv: Optional[List[str]] = None) -> int:
    problem = check_python()
    if problem:
        print(problem, file=sys.stderr)
        return EXIT_FAILURE
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "contributions":
        return _contributions(args)
    if args.command == "deps":
        return _deps(args)
    return _check(args)


if __name__ == "__main__":
    sys.exit(main())
