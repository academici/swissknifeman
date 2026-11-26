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
EXIT_TAMPERED = 3  # SIDECAR_TAMPERED: the frozen sidecar differs from its digest


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
    p = sub.add_parser("schemas", help="the gui contracts as self-contained JSON Schemas (for type generators)")
    schemas_sub = p.add_subparsers(dest="schemas_command", parser_class=_Parser, metavar="<action>", required=True)
    q = schemas_sub.add_parser("bundle", help="write <contract>.schema.json per contract of unit.json, refs inlined")
    q.add_argument("--out", metavar="DIR", required=True, help="output folder (created)")
    p = sub.add_parser("state", help="check or rebuild the state database gui.db")
    state_sub = p.add_subparsers(dest="state_command", parser_class=_Parser, metavar="<action>", required=True)
    q = state_sub.add_parser("check", help="integrity, foreign keys, schema version and row counts (read-only)")
    q.add_argument("--json", action="store_true", help="print the report as JSON")
    q = state_sub.add_parser("rebuild", help="backup, build a fresh gui.db, copy every row, verify, swap atomically")
    q.add_argument("--json", action="store_true", help="print the report as JSON")
    q.add_argument("--dry-run", action="store_true", help="print the plan and write nothing")
    p = sub.add_parser("serve", help="run the loopback backend in the foreground and print a one-time browser URL")
    p.add_argument("--port", type=int, default=None, metavar="N", help="TCP port on 127.0.0.1 (default: [gui] port)")
    p.add_argument("--project", metavar="DIR", default=None, help="register this project (default: the current one)")
    p.add_argument("--no-browser", action="store_true", help="do not start the browser")
    p.add_argument("--detached", action="store_true", help=argparse.SUPPRESS)  # started by gui open: no URL
    p.add_argument("--sidecar", action="store_true",
                   help="run as the sidecar of the desktop shell: handshake line on stdin, GUI_READY on stdout")
    p = sub.add_parser("open", help="open the GUI in the browser, starting the backend when none runs")
    p.add_argument("--project", metavar="DIR", default=None, help="register this project (default: the current one)")
    p.add_argument("--no-browser", action="store_true", help="only print the URL")
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


def _schemas(args: argparse.Namespace) -> int:
    from . import contracts

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    unit = json.loads((contracts.SCHEMAS.parent / "unit.json").read_text(encoding="utf-8"))
    for entry in unit["provides"]["contracts"]:
        name = entry["id"].rpartition(":")[2]
        document = contracts.bundle(name, entry["version"])
        (out / f"{name}.schema.json").write_text(json.dumps(document, indent=2, sort_keys=True,
                                                            ensure_ascii=False) + "\n", encoding="utf-8")
        print(out / f"{name}.schema.json")
    return 0


def _fail(code: str, message: str) -> int:
    print(f"{code}: {message}", file=sys.stderr)
    return EXIT_FAILURE


def _state(args: argparse.Namespace) -> int:
    from .backend import BackendError, InstanceLock, gui_state_dir
    from .core import state_admin
    from .storage import db

    folder = gui_state_dir()
    if args.state_command == "check":
        report = state_admin.check(folder / db.DB_NAME)
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
        else:
            print(f"{'ok' if report['ok'] else 'FAILED'}: {report['path']} (schema {report['schema_version']}, "
                  f"known {report['known_version']})")
            for table, count in report["tables"].items():
                print(f"  {table}: {count}")
            for problem in report["problems"]:
                print(f"  problem: {problem}")
        return 0 if report["ok"] else EXIT_FAILURE
    try:
        lock = InstanceLock(folder).acquire()  # the backend must not run: it holds the database open
    except BackendError as error:
        return _fail(error.code, error.message)
    try:
        report = state_admin.rebuild(folder, dry_run=args.dry_run)
    except state_admin.StateError as error:
        return _fail(error.code, error.message)
    finally:
        lock.release()
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        verb = "would rebuild" if args.dry_run else "rebuilt"
        print(f"{verb}: {report['path']} (schema {report['from_version']} -> {report['to_version']})")
        for table, entry in report["tables"].items():
            print(f"  {table}: {entry['rows']} row(s)")
        print(f"backup: {report['backup']}" + (" (planned)" if args.dry_run else ""))
    return 0


def _project_dir(args: argparse.Namespace) -> Optional[Path]:
    from .backend import project_marker_root

    if args.project:
        return Path(args.project).expanduser().resolve()
    if getattr(args, "detached", False):  # `gui open` registers its project itself; cwd is the state folder
        return None
    return project_marker_root(Path.cwd())


def _browse(url: str, settings, no_browser: bool) -> None:
    print(f"GUI_URL {url}", flush=True)
    if settings.open_browser and not no_browser:
        import webbrowser

        webbrowser.open(url)


def _serve_sidecar(args: argparse.Namespace) -> int:
    """``gui serve --sidecar`` (decision D28): the secret comes on stdin, never in argv, env, disk or log."""
    import os
    import signal

    from . import deps, sidecar
    from .backend import GUI_PROTOCOL, BackendError, BackendState, InstanceLock, Sessions, gui_state_dir
    from .core.projects import ProjectRegistry
    from .errors import GuiError
    from .settings import load
    from .storage import db

    if args.detached or args.port is not None:
        print("gui: usage: --sidecar cannot be combined with --detached or --port (the port is in the handshake)",
              file=sys.stderr)
        return EXIT_USAGE
    sidecar.scrub_process_environment()  # the bundler's PYTHONHOME/LD_LIBRARY_PATH must not reach the children
    problem = sidecar.check_digest()  # before the handshake is read and before any socket exists
    if problem:
        print(problem, file=sys.stderr, flush=True)
        return EXIT_TAMPERED
    stdin = sidecar.stdin_stream()
    try:
        handshake = sidecar.read_handshake(stdin)
    except sidecar.HandshakeError as error:
        print(str(error), file=sys.stderr, flush=True)
        return EXIT_USAGE
    if not getattr(sys, "frozen", False):  # the frozen backend carries its packages
        try:
            deps.activate()
        except deps.GuiDepsError as error:
            return _fail(error.code, error.message)
    folder = gui_state_dir()
    try:
        lock = InstanceLock(folder).acquire()
    except BackendError as error:
        return _fail(error.code, error.message)
    state = None
    try:
        settings = load()
        conn = db.open_db(folder / db.DB_NAME)
        if args.project:
            ProjectRegistry(conn).add(Path(args.project).expanduser().resolve(), source="open")
        from .http import server

        sock = server.bind(handshake.port)
        state = BackendState(settings=settings, conn=conn, env=os.environ, port=sock.getsockname()[1],
                             sessions=Sessions(handshake.secret), state_folder=folder, mode="desktop",
                             shell_version=handshake.shell_version)
        from . import __version__

        # The handler is in place before the watchdog can fire; uvicorn then stops gracefully like on SIGTERM.
        signal.signal(signal.SIGTERM, server._stop)
        try:
            sys.stdout.write(sidecar.ready_line(state.port, state.epoch, os.getpid(), __version__, GUI_PROTOCOL)
                             + "\n")
            sys.stdout.flush()
            sidecar.watch_stdin(stdin, lambda: os.kill(os.getpid(), signal.SIGTERM))
            server.serve(state, sock)
        except server._Stopped:  # EOF or SIGTERM before uvicorn took over the signals
            pass
    except GuiError as error:
        return _fail(error.code, error.message)
    finally:
        if state is not None:
            state.conn.close()
        lock.release()
    return 0


def _serve(args: argparse.Namespace) -> int:
    import os

    if args.sidecar:
        return _serve_sidecar(args)

    from . import deps
    from .backend import BackendError, BackendState, InstanceLock, gui_state_dir, remove_runtime, write_runtime
    from .core.projects import ProjectRegistry
    from .errors import GuiError
    from .settings import load
    from .storage import db

    try:
        deps.activate()
    except deps.GuiDepsError as error:
        return _fail(error.code, error.message)
    folder = gui_state_dir()
    try:
        lock = InstanceLock(folder).acquire()
    except BackendError as error:
        return _fail(error.code, error.message)
    state = None
    try:
        settings = load()
        conn = db.open_db(folder / db.DB_NAME)
        project = _project_dir(args)
        if project is not None:
            ProjectRegistry(conn).add(project, source="open")
        from .http import server

        sock = server.bind(settings.port if args.port is None else args.port)
        state = BackendState(settings=settings, conn=conn, env=os.environ, port=sock.getsockname()[1],
                             state_folder=folder)
        write_runtime(folder, state.runtime_info())
        if args.detached:
            print(f"GUI_READY 127.0.0.1:{state.port}", flush=True)
        else:
            _browse(state.url(state.sessions.new_token()), settings, args.no_browser)
        server.serve(state, sock)
    except GuiError as error:
        return _fail(error.code, error.message)
    finally:
        if state is not None:
            remove_runtime(folder, state.epoch)
            state.conn.close()
        lock.release()
    return 0


def _open(args: argparse.Namespace) -> int:
    from .backend import BackendError, alive, gui_state_dir, read_runtime, request, start_detached
    from .settings import load

    folder = gui_state_dir()
    settings = load()
    try:
        info = read_runtime(folder)
        if not alive(info):
            info = start_detached(folder)
        project = _project_dir(args)
        if project is not None:
            status, answer = request(info, "POST", "/v1/projects", {"path": str(project)})
            if status != 201:
                error = (answer or {}).get("error", {}) if isinstance(answer, dict) else {}
                return _fail(error.get("code", "BACKEND_START_FAILED"), error.get("message", f"HTTP {status}"))
        status, answer = request(info, "POST", "/v1/session/tokens", {})
    except BackendError as error:
        return _fail(error.code, error.message)
    except OSError as error:
        return _fail("BACKEND_START_FAILED", f"the backend does not answer: {error}")
    if status != 201 or not isinstance(answer, dict) or not isinstance(answer.get("url"), str):
        return _fail("BACKEND_START_FAILED", f"the backend refused a session token (HTTP {status})")
    _browse(answer["url"], settings, args.no_browser)
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
    if args.command == "schemas":
        return _schemas(args)
    if args.command == "state":
        return _state(args)
    if args.command in ("serve", "open"):
        from aicore.config import ConfigError

        try:
            return _serve(args) if args.command == "serve" else _open(args)
        except ConfigError as error:
            return _fail(error.code, str(error))
    return _check(args)


if __name__ == "__main__":
    sys.exit(main())
