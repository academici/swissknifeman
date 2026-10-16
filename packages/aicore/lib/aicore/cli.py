"""``aicore <group>``: the command line of the foundation; picks a group and hands the rest over."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Mapping, Optional, Sequence, TextIO

# group -> (module, function, summary line of the usage text)
GROUPS = {
    "config": ("aicore.config.cli", "main",
               "layered module configuration: show, explain, set, unset, init, example, paths"),
    "schema": ("aicore.util.schemacompat", "main", "contract tools: compat"),
    "events": ("aicore.ext.cli", "main", "project event journal: emit, list, deliver, replay, status"),
    "ext": ("aicore.ext.cli", "ext_main", "extensions: plugins, overlays, conformance, status"),
    "marketplace": ("aicore.content.marketplace", "main", "hub marketplace from unit.json: build [--check]"),
    "release": ("aicore.release.bundle", "main", "release bundle: compat manifest, schema package, attestation, checksums"),
    "project": ("aicore.project.cli", "main", "project-local launcher: init, sync, verify, context, doctor, exec"),
}

_HELP = ("-h", "--help", "help")


def usage() -> str:
    lines = [f"  {name:<8} {summary}" for name, (_module, _function, summary) in GROUPS.items()]
    return ("usage: aicore <group> [args]\n\ngroups:\n" + "\n".join(lines)
            + "\n\nRun `aicore <group> --help` for the commands.\n")


def main(argv: Optional[Sequence[str]] = None, *, env: Optional[Mapping[str, str]] = None,
         cwd: Optional[Path] = None, out: Optional[TextIO] = None, err: Optional[TextIO] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    out = out or sys.stdout
    err = err or sys.stderr
    if not args:
        err.write(usage())
        return 2
    if args[0] in _HELP:
        out.write(usage())
        return 0
    group = GROUPS.get(args[0])
    if group is None:
        err.write(f"aicore: unknown group {args[0]!r}\n{usage()}")
        return 2
    module, function, _summary = group
    handler = getattr(importlib.import_module(module), function)  # lazy: only the chosen group is imported
    return handler(args[1:], env=env, cwd=cwd, out=out, err=err)
