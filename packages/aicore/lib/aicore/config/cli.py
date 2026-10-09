"""``aicore config``: show, explain, set, unset, init, example and paths.

Exit codes: 0 success, 1 configuration error or refusal, 2 usage error.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import sys
from pathlib import Path
from typing import Any, List, Mapping, Optional, Sequence, TextIO

from ..state import (backup, ensure_dir, find_project_root, machine_config_file, machine_locations,
                     project_backups_dir, project_config_file, project_state_dir)
from ..util import io as _io
from . import ConfigError, edit_layer_file, load_module_schema, parse_value, resolve, toml_edit
from .example import render_sections, render_unit
from .model import CONFIG_FILE_VERSION, _where
from .units import UnitInfo, discover, load_unit

class _Parser(argparse.ArgumentParser):
    """argparse with the documented exit code 2 and messages on the stream given to ``main``."""

    def error(self, message: str):  # type: ignore[override]
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: error: {message}\n")


class _Refusal(Exception):
    """A failure to report on stderr with exit code 1."""


def _common() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", metavar="DIR", help="project root (default: the nearest .swissknifeman or .git)")
    common.add_argument("--config", metavar="FILE", help="invocation layer: a config file applied on top")
    common.add_argument("--json", action="store_true", help="machine-readable output")
    return common


def _layer_options(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--machine", action="store_true", help="the machine config file")
    group.add_argument("--project", action="store_true", help="the project config file (see --root)")


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="aicore config", description="Layered configuration of swissknifeman modules.")
    commands = parser.add_subparsers(dest="command", required=True, parser_class=_Parser, metavar="COMMAND")
    common = _common()

    show = commands.add_parser("show", parents=[common], help="effective values with the layer of each")
    show.add_argument("module")

    explain = commands.add_parser("explain", parents=[common], help="where each value comes from and what it overrides")
    explain.add_argument("module")
    explain.add_argument("key", nargs="?", help="a key or table (dotted); default: every set key")

    for name, text in (("set", "write one key into a layer file"), ("unset", "remove one key from a layer file")):
        sub = commands.add_parser(name, parents=[common], help=text)
        sub.add_argument("target", metavar="MODULE.KEY")
        if name == "set":
            sub.add_argument("value")
        _layer_options(sub)

    init = commands.add_parser("init", parents=[common], help="create a layer file from the module examples")
    _layer_options(init)
    init.add_argument("--module", action="append", metavar="ID", help="module to include (repeatable; default: all)")
    init.add_argument("--force", action="store_true", help="replace an existing file (a backup is kept)")

    example = commands.add_parser("example", parents=[common], help="print, write or check config.example.toml")
    example.add_argument("unit_dir")
    mode = example.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="write <unit-dir>/config.example.toml")
    mode.add_argument("--check", action="store_true", help="exit 1 with a diff if the file differs")

    commands.add_parser("paths", parents=[common], help="where configuration and state live")
    return parser


class _Context:
    def __init__(self, args: argparse.Namespace, env: Mapping[str, str], cwd: Path, out: TextIO, err: TextIO):
        self.args = args
        self.env = env
        self.out = out
        self.err = err
        root = getattr(args, "root", None)
        self.root = Path(os.path.abspath(root)) if root else find_project_root(cwd, env=env)

    def say(self, text: str = "") -> None:
        print(text, file=self.out)

    def emit_json(self, doc: Any) -> None:
        print(json.dumps(doc, indent=2, ensure_ascii=False), file=self.out)

    def module(self, module_id: str) -> UnitInfo:
        known = discover(self.env)
        if module_id not in known:
            names = ", ".join(sorted(known)) or "none"
            raise _Refusal(f"unknown module {module_id!r} (modules with a config schema: {names}); "
                           "set SKM_UNITS_PATH to look elsewhere")
        return known[module_id]

    def resolved(self, module_id: str):
        info = self.module(module_id)
        return resolve(module_id, schema=info.schema_path, project=self.root,
                       config_file=self.args.config, env=self.env)

    def layer(self) -> str:
        return "project" if self.args.project else "machine"

    def layer_file(self) -> Path:
        return project_config_file(self.root) if self.args.project else machine_config_file(env=self.env)


def _toml(value: Any) -> str:
    return toml_edit.render_value(value)


def _cmd_show(ctx: _Context) -> int:
    config = ctx.resolved(ctx.args.module)
    if ctx.args.json:
        ctx.emit_json({"module": config.module, "values": config.as_dict()})
        return 0
    for entry in config.explain():
        ctx.say(f"{entry.key} = {_toml(entry.value)}  # {_where(entry.layer, entry.file, entry.line, entry.source)}")
    return 0


def _cmd_explain(ctx: _Context) -> int:
    config = ctx.resolved(ctx.args.module)
    if ctx.args.json:
        ctx.emit_json(config.explain_json(ctx.args.key))
    else:
        text = config.explain_text(ctx.args.key)
        if text:
            ctx.say(text)
    return 0


def _split_target(target: str) -> List[str]:
    module_id, dot, key = target.partition(".")
    if not module_id or not dot or not key:
        raise _UsageError(f"expected MODULE.KEY, got {target!r}")
    return [module_id, key]


class _UsageError(Exception):
    """A usage failure to report with exit code 2."""


def _edit(ctx: _Context, *, remove: bool) -> int:
    module_id, key = _split_target(ctx.args.target)
    info = ctx.module(module_id)
    schema = load_module_schema(info.schema_path, module_id)
    value = None if remove else parse_value(schema, key, ctx.args.value)
    path = ctx.layer_file()
    result = edit_layer_file(path, module_id, key, value, schema=schema, layer=ctx.layer(), remove=remove,
                             project=ctx.root if ctx.args.project else None, env=ctx.env)
    if ctx.args.json:
        ctx.emit_json({"module": module_id, "key": key, "layer": ctx.layer(), "file": str(path),
                       "changed": result.changed, "backup": str(result.backup) if result.backup else None})
        return 0
    verb = "removed" if remove else "set"
    if result.changed:
        ctx.say(f"{verb} {module_id}.{key} in {path}" + (f" (backup: {result.backup})" if result.backup else ""))
    else:
        ctx.say(f"{module_id}.{key} already {'unset' if remove else 'has this value'} in {path}")
    return 0


def _cmd_init(ctx: _Context) -> int:
    known = discover(ctx.env)
    wanted = ctx.args.module or sorted(known)
    if not wanted:
        raise _Refusal("no module with a config schema was found; set SKM_UNITS_PATH")
    sections = []
    for module_id in wanted:
        if module_id not in known:
            ctx.module(module_id)  # raises the unknown-module refusal
        info = known[module_id]
        sections.append(render_sections(load_module_schema(info.schema_path, module_id)))
    path = ctx.layer_file()
    target = Path(os.path.realpath(path))
    existed = target.exists()
    if existed and not ctx.args.force:
        raise _Refusal(f"{path} already exists; use --force to replace it (a backup is kept)")
    text = (f"schema_version = {CONFIG_FILE_VERSION}\n\n"
            "# Uncomment the keys you change; `swissknifeman config explain <module>` shows their origin.\n\n"
            + "\n".join(sections))
    saved = backup(path, project=ctx.root if ctx.args.project else None, env=ctx.env) if existed else None
    ensure_dir(target.parent)
    _io.atomic_write_text(target, text)
    if ctx.args.json:
        ctx.emit_json({"layer": ctx.layer(), "file": str(path), "modules": list(wanted),
                       "backup": str(saved) if saved else None})
    else:
        ctx.say(f"wrote {path} for {', '.join(wanted)}" + (f" (backup: {saved})" if saved else ""))
    return 0


def _cmd_example(ctx: _Context) -> int:
    unit_dir = Path(ctx.args.unit_dir)
    info = load_unit(unit_dir)
    if info is None:
        raise _Refusal(f"{unit_dir}: no unit.json with provides.config")
    text = render_unit(info)
    target = unit_dir / "config.example.toml"
    if ctx.args.write:
        _io.atomic_write_text(target, text)
        ctx.say(f"wrote {target}")
        return 0
    if ctx.args.check:
        try:
            current = target.read_text(encoding="utf-8")
        except OSError:
            current = ""
        if current == text:
            return 0
        diff = difflib.unified_diff(current.splitlines(keepends=True), text.splitlines(keepends=True),
                                    fromfile=str(target), tofile="generated")
        ctx.out.write("".join(diff))
        print(f"{target} differs from the schema; run `aicore config example {unit_dir} --write`", file=ctx.err)
        return 1
    ctx.out.write(text)
    return 0


def _cmd_paths(ctx: _Context) -> int:
    where = machine_locations(ctx.env)
    doc = {
        "config": str(where.config), "state": str(where.state), "data": str(where.data),
        "cache": str(where.cache), "isolated": where.isolated,
        "machine_config_file": str(machine_config_file(env=ctx.env)),
        "project": {"root": str(ctx.root), "config_file": str(project_config_file(ctx.root)),
                    "state": str(project_state_dir(ctx.root)), "backups": str(project_backups_dir(ctx.root))},
    }
    if ctx.args.json:
        ctx.emit_json(doc)
        return 0
    for name, value in doc.items():
        if name == "project":
            for sub, path in value.items():
                ctx.say(f"project.{sub}: {path}")
        else:
            ctx.say(f"{name}: {str(value).lower() if isinstance(value, bool) else value}")
    return 0


_COMMANDS = {
    "show": _cmd_show, "explain": _cmd_explain, "set": lambda ctx: _edit(ctx, remove=False),
    "unset": lambda ctx: _edit(ctx, remove=True), "init": _cmd_init, "example": _cmd_example, "paths": _cmd_paths,
}


def main(argv: Optional[Sequence[str]] = None, *, env: Optional[Mapping[str, str]] = None,
         cwd: Optional[Path] = None, out: Optional[TextIO] = None, err: Optional[TextIO] = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    out = out or sys.stdout
    err = err or sys.stderr
    try:
        args = build_parser().parse_args(args_list)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    ctx = _Context(args, os.environ if env is None else env, cwd or Path.cwd(), out, err)
    try:
        return _COMMANDS[args.command](ctx)
    except _UsageError as exc:
        print(f"aicore config {args.command}: error: {exc}", file=err)
        return 2
    except (ConfigError, toml_edit.TomlEditError, _Refusal, ValueError, OSError) as exc:
        print(f"aicore config {args.command}: {exc}", file=err)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
