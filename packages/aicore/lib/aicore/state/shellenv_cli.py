"""``aicore shell-env``: the managed shell-profile snippet that exports ``SKM_HOME``, ``SKM_WORKSPACES``, ``SKM_WORKSPACE``.

    show      [--profile FILE] [--json]            the variables, what the snippet would export and its state
    install   [--profile FILE] [--dry-run] [--json]   add the snippet to the shell profile or bring it up to date
    uninstall [--profile FILE] [--dry-run] [--json]   remove the snippet (nothing else in the file changes)
    doctor    [--profile FILE] [--json]            check the snippet and the variables of this shell

The profile is ``~/.bashrc`` for bash and ``~/.zshrc`` for zsh (``$SHELL``); ``--profile`` names another file. Exit codes:
0 done, 1 refused or a check failed, 2 usage. Text mode prints ``CODE: message`` on stderr; ``--json`` prints one document.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, TextIO

from . import envtable, shellenv

USAGE = __doc__.split("\n\n")[1]
COMMANDS = ("show", "install", "uninstall", "doctor")


class _Usage(Exception):
    pass


def _options(args: Sequence[str], flags: Sequence[str]) -> Dict[str, Any]:
    found: Dict[str, Any] = {name: False for name in flags}
    found["--profile"] = None
    items = list(args)
    while items:
        item = items.pop(0)
        if item == "--profile":
            if not items:
                raise _Usage("--profile needs a file")
            found["--profile"] = items.pop(0)
        elif item in found and item != "--profile":
            found[item] = True
        else:
            raise _Usage(f"unknown argument {item!r}")
    return found


def _emit(document: Dict[str, Any], as_json: bool, out: TextIO, lines: List[str]) -> None:
    if as_json:
        out.write(json.dumps(document, indent=2, ensure_ascii=False) + "\n")
    else:
        out.write("\n".join(lines) + "\n")


def main(argv: Optional[Sequence[str]] = None, *, env: Optional[Mapping[str, str]] = None, cwd: Optional[Path] = None,
         out: Optional[TextIO] = None, err: Optional[TextIO] = None) -> int:
    import sys
    args = list(sys.argv[1:] if argv is None else argv)
    out = out or sys.stdout
    err = err or sys.stderr
    environment = os.environ if env is None else env
    if not args or args[0] in ("-h", "--help", "help"):
        (out if args else err).write(USAGE + "\n")
        return 0 if args else 2
    command, rest = args[0], args[1:]
    try:
        if command not in COMMANDS:
            raise _Usage(f"unknown command {command!r}")
        options = _options(rest, ["--json", "--dry-run"] if command in ("install", "uninstall") else ["--json"])
        as_json = options["--json"]
        explicit = options["--profile"]
        if command == "doctor":
            checks = shellenv.doctor_checks("aicore", environment, None, explicit)
            if as_json:
                out.write(json.dumps(checks, indent=2, ensure_ascii=False) + "\n")
            else:
                out.write("".join(f"{item['status']} {item['check_id']}: {item['observed']}\n" for item in checks))
            return 1 if any(item["status"] == "fail" for item in checks) else 0
        values, notes = shellenv.planned_values(environment)
        profile = shellenv.profile_path(environment, None, explicit)
        if command == "show":
            state = shellenv.inspect(profile, values)
            document = {"variables": [{"name": item.name, "meaning": item.meaning, "value": values.get(item.name),
                                       "current": environment.get(item.name)} for item in envtable.TABLE],
                        "profile": state, "notes": notes}
            lines = [f"{item.name}={values.get(item.name, '(not exported)')}  {item.meaning}" for item in envtable.TABLE]
            lines.append(f"profile: {state.get('profile') or 'unsupported shell'} ({state['state']})")
            lines.extend(f"note: {note}" for note in notes)
            _emit(document, as_json, out, lines)
            return 0
        if profile is None:
            raise shellenv.ShellEnvError("SHELL_UNSUPPORTED", f"no profile for the shell {environment.get('SHELL', '?')!r}; "
                                         f"use --profile FILE or export {', '.join(envtable.NAMES)} yourself")
        dry = options["--dry-run"]
        if command == "install":
            result = shellenv.install(profile, values, dry_run=dry)
        else:
            result = shellenv.uninstall(profile, dry_run=dry)
        result.update(dry_run=dry, variables=sorted(values) if command == "install" else [], notes=notes if command == "install" else [])
        lines = [f"{result['action']}: {result['profile']}" + (" (dry run)" if dry else "")]
        lines.extend(f"note: {note}" for note in result["notes"])
        _emit(result, as_json, out, lines)
        return 0
    except _Usage as exc:
        err.write(f"usage: {exc}\n{USAGE}\n")
        return 2
    except shellenv.ShellEnvError as exc:
        if "--json" in args:
            out.write(json.dumps({"error": exc.code, "message": exc.message}) + "\n")
        else:
            err.write(f"{exc.code}: {exc.message}\n")
        return 1
