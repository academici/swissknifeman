"""argv of a catalog command (I4) and its working folder (I5); stdlib + aicore.

The argv is built only from the descriptor: ``argv[0]`` is a literal path inside the owner root (after
``realpath``), existing and executable; every ``{"input": name}`` part becomes exactly one element holding one
value, never glued to other text; a value starting with ``-`` is refused for a field without a flag; fields with a
flag follow the parts in input order (a true boolean adds the flag alone, any other value the flag and then the value
as its own element). ``dry_run.input`` sets that boolean field before building; ``dry_run.argv_append`` comes last.
Nothing runs through a shell.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple

from aicore.util.digest import sha256_tagged
from aicore.util.paths import is_within

from ..errors import GuiError


@dataclass(frozen=True)
class Built:
    argv: Tuple[str, ...]
    executable: str  # realpath of argv[0]
    digest: str  # sha256 of the program file, tagged
    cwd_kind: str  # "project" or "owner"


def _issue(name: str, code: str, message: str) -> Dict[str, str]:
    return {"pointer": f"/input/{name}", "code": code, "message": message}


def program(owner_root: os.PathLike, literal: str) -> Tuple[str, str]:
    """The realpath and digest of ``argv[0]``; ``PATH_ESCAPE`` outside the owner root, ``HANDLER_FAILED`` when it
    is not an executable file."""
    root = os.path.realpath(owner_root)
    if not isinstance(literal, str) or not literal or os.path.isabs(literal):
        raise GuiError("PATH_ESCAPE", "argv[0] must be a path relative to the owner root")
    target = os.path.realpath(os.path.join(root, literal))
    if not is_within(target, root):
        raise GuiError("PATH_ESCAPE", f"argv[0] {literal!r} leads outside the owner root")
    if not os.path.isfile(target) or not os.access(target, os.X_OK):
        raise GuiError("HANDLER_FAILED", f"argv[0] {literal!r} is not an executable file")
    with open(target, "rb") as handle:
        digest = sha256_tagged(handle.read())
    return target, digest


def _text(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def build(command: Mapping[str, Any], owner_root: os.PathLike, values: Mapping[str, Any], *,
          dry_run: bool = False) -> Built:
    """The argv of an ``exec.kind: argv`` command for already validated ``values`` (``gui.core.inputs``)."""
    execution = command["exec"]
    if execution.get("kind") != "argv":
        raise ValueError("build() takes an argv command")
    fields = {entry["name"]: entry for entry in command.get("input", ())}
    values = dict(values)
    dry = command.get("dry_run") or {}
    if dry_run:
        if not dry:
            raise GuiError("INPUT_INVALID", f"command {command['id']} has no dry run")
        if "input" in dry:
            values[dry["input"]] = True
    parts = execution["argv"]
    executable, digest = program(owner_root, parts[0])
    argv: List[str] = [executable]
    issues = []
    for part in parts[1:]:
        if isinstance(part, str):
            argv.append(part)
            continue
        name = part["input"]
        field = fields.get(name)
        if field is None or "flag" in field:
            raise GuiError("INPUT_INVALID", f"argv part {name!r} is not a positional input of the command")
        if name not in values or values[name] is None:
            issues.append(_issue(name, "required", "a positional input needs a value"))
            continue
        text = _text(values[name])
        if text.startswith("-"):
            issues.append(_issue(name, "leading_dash", "a value of a positional input must not start with '-'"))
            continue
        argv.append(text)
    for name, field in fields.items():
        flag = field.get("flag")
        if not flag or name not in values or values[name] is None:
            continue
        value = values[name]
        if field["type"] == "boolean":
            if value is True:
                argv.append(flag)
        else:
            argv.extend([flag, _text(value)])
    if issues:
        raise GuiError("INPUT_INVALID", f"{len(issues)} invalid value(s)", issues=issues)
    if dry_run:
        argv.extend(dry.get("argv_append", ()))
    return Built(argv=tuple(argv), executable=executable, digest=digest, cwd_kind=execution.get("cwd", "project"))


def cwd(built: Built, owner_root: os.PathLike, registry, project_id) -> Path:
    """The working folder: the trusted project root (through the registry) or the real owner root."""
    if built.cwd_kind == "owner":
        return Path(os.path.realpath(owner_root))
    if project_id is None:
        raise GuiError("INPUT_INVALID", "a command that runs in the project needs context.project_id",
                       issues=[{"pointer": "/context/project_id", "code": "required", "message": "required"}])
    return registry.resolve(project_id)
