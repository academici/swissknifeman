#!/usr/bin/env python3
"""swissknifeman umbrella CLI: one entry over the independent CLIs of the modules.

Modules are found by their ``unit.json`` (``ext.units.discover_units`` of the foundation); a module with ``provides.cli`` is a
command group of its own id. Aliases of former groups and legacy verbs are data in ``configs/umbrella.json``.
This file holds no module logic and no module ids. stdlib and the foundation module only.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "umbrella.json"
DEFAULT_UNITS_PATH = ("packages", "bridges")
UNITS_SCHEMA = "umbrella-units/v1"
HELP_FLAGS = ("-h", "--help", "help")
VERSION_WORDS = ("-V", "--version", "version")

BUILTINS = (
    ("units [list|show <id>] [--json]", "modules found by unit.json"),
    ("doctor", "diagnostics of every module that declares provides.doctor (fan-out)"),
    ("help, -h, --help", "this text"),
    ("-V, --version, version", "umbrella version (git describe)"),
)


def units_env(env: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
    """The environment for unit discovery: the hub folders unless ``SKM_UNITS_PATH`` is set."""
    result = dict(os.environ if env is None else env)
    if not result.get("SKM_UNITS_PATH"):
        result["SKM_UNITS_PATH"] = os.pathsep.join(str(ROOT / name) for name in DEFAULT_UNITS_PATH)
    return result


def load_units(env: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
    """All modules by id, sorted by id."""
    from aicore.ext.units import discover_units  # PYTHONPATH comes from bin/swissknifeman

    found = discover_units(units_env(env))
    return {key: found[key] for key in sorted(found)}


def load_config(path: Path = CONFIG) -> Dict[str, Any]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"UMBRELLA_CONFIG_INVALID: {path}: {exc.__class__.__name__}", file=sys.stderr)
        return {"aliases": {}}
    return doc if isinstance(doc, dict) else {"aliases": {}}


def _provides(unit: Any) -> Mapping[str, Any]:
    value = unit.doc.get("provides")
    return value if isinstance(value, dict) else {}


def _strings(value: Any) -> List[str]:
    return [item for item in value if isinstance(item, str) and item] if isinstance(value, list) else []


def cli_of(unit: Any) -> Optional[Path]:
    """The first ``provides.cli`` entry of a module as a path, or None."""
    entries = _strings(_provides(unit).get("cli"))
    return unit.root / entries[0] if entries else None


def group_units(units: Mapping[str, Any]) -> Dict[str, Any]:
    """Modules that are command groups: a CLI and not a bridge (bridge scripts are helpers, not commands)."""
    return {key: unit for key, unit in units.items()
            if unit.doc.get("kind") != "bridge" and cli_of(unit) is not None}


def _command(path: Path) -> List[str]:
    """argv head to run a CLI file; a file that is not executable runs through the interpreter."""
    if os.access(path, os.X_OK) or path.suffix != ".py":
        return [str(path)]
    return [sys.executable, str(path)]


def _when(when: Mapping[str, Any], args: Sequence[str]) -> bool:
    first = args[0] if args else ""
    if "first_in" in when and first not in when["first_in"]:
        return False
    if when.get("first_empty_or_flag") and first and not first.startswith("-"):
        return False
    return True


def resolve_alias(config: Mapping[str, Any], name: str, args: Sequence[str]) -> Optional[Dict[str, Any]]:
    """The first matching route of an alias: ``{unit|script, argv_prefix, args}`` or None."""
    alias = (config.get("aliases") or {}).get(name)
    if not isinstance(alias, dict):
        return None
    for route in alias.get("routes") or ():
        if not _when(route.get("when") or {}, args):
            continue
        rest = list(args[1:] if route.get("drop_first") else args)
        return {"unit": route.get("unit"), "script": route.get("script"),
                "argv_prefix": list(route.get("argv_prefix") or ()), "args": rest}
    return None


def _missing(path: Path) -> int:
    print(f"ERROR: launcher not found: {path}", file=sys.stderr)
    print("Repository is corrupted or incomplete - restart ./install.sh.", file=sys.stderr)
    return 1


def _exec(head: Sequence[str], rest: Sequence[str]) -> int:
    argv = list(head) + list(rest)
    sys.stdout.flush()
    os.execv(argv[0], argv)
    return 1  # not reached


def route(argv: Sequence[str], units: Optional[Mapping[str, Any]] = None,
          config: Optional[Mapping[str, Any]] = None) -> int:
    """Resolve the first word: built-in command, alias, module id; anything else is unknown."""
    cmd = argv[0] if argv else "help"
    rest = list(argv[1:])
    if cmd in HELP_FLAGS:
        print(help_text(units, config))
        return 0
    if cmd in VERSION_WORDS:
        print(f"swissknifeman {version()}")
        return 0
    if cmd == "units":
        return units_command(rest, units)
    if cmd == "doctor":
        return doctor_command(units, config)
    config = load_config() if config is None else config
    target = resolve_alias(config, cmd, rest)
    units = load_units() if units is None else units
    if target is not None:
        if target["script"]:
            path = ROOT / target["script"]
            return _exec(_command(path), target["argv_prefix"] + target["args"]) if path.exists() else _missing(path)
        unit = units.get(target["unit"])
        path = cli_of(unit) if unit is not None else None
        if path is None or not path.exists():
            return _missing(path or ROOT / "packages" / str(target["unit"]))
        return _exec(_command(path), target["argv_prefix"] + target["args"])
    unit = group_units(units).get(cmd)
    if unit is not None:
        path = cli_of(unit)
        return _exec(_command(path), rest) if path.exists() else _missing(path)
    print(f"Unknown command: {cmd}", file=sys.stderr)
    print(help_text(units, config), file=sys.stderr)
    return 1


def version() -> str:
    """``git describe --tags`` of the hub, else the version named in the config fallback file."""
    try:
        out = subprocess.run(["git", "describe", "--tags"], cwd=ROOT, capture_output=True, text=True, timeout=10)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    spec = load_config().get("version") or {}
    try:
        doc = json.loads((ROOT / spec["fallback_file"]).read_text(encoding="utf-8"))
        return str(doc[spec["fallback_key"]])
    except (KeyError, OSError, ValueError, TypeError):
        return "unknown"


def help_text(units: Optional[Mapping[str, Any]] = None, config: Optional[Mapping[str, Any]] = None) -> str:
    units = load_units() if units is None else units
    config = load_config() if config is None else config
    aliases = config.get("aliases") or {}
    lines = ["swissknifeman — umbrella over the module CLIs (finds modules by unit.json; holds no module logic).",
             "", "Usage: swissknifeman <command> [args]", "", "Built-in:"]
    width = max(len(name) for name, _ in BUILTINS)
    lines += [f"  {name.ljust(width)}  {text}" for name, text in BUILTINS]
    described = [(name, str(item.get("description"))) for name, item in aliases.items()
                 if isinstance(item, dict) and item.get("description")]
    plain = [name for name, item in aliases.items() if isinstance(item, dict) and not item.get("description")]
    if described:
        lines += ["", "Aliases (configs/umbrella.json):"]
        width = max(len(name) for name, _ in described)
        lines += [f"  {name.ljust(width)}  {text}" for name, text in sorted(described)]
    if plain:
        lines.append("  other aliases: " + " ".join(sorted(plain)))
    groups = group_units(units)
    if groups:
        lines += ["", "Modules (provides.cli in unit.json):"]
        width = max(len(key) for key in groups)
        lines += [f"  {key.ljust(width)}  {groups[key].doc.get('title', '')}" for key in groups]
    return "\n".join(lines)


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def unit_row(unit: Any) -> Dict[str, Any]:
    provides = _provides(unit)
    plugins = provides.get("plugins")
    doctor = provides.get("doctor")
    return {
        "id": unit.id,
        "kind": str(unit.doc.get("kind", "")),
        "version": str(unit.doc.get("version", "")),
        "stability": str(unit.doc.get("stability", "")),
        "destination": str(unit.doc.get("destination", "")),
        "root": _rel(unit.root),
        "cli": _strings(provides.get("cli")),
        "plugins": [item["name"] for item in plugins
                    if isinstance(item, dict) and isinstance(item.get("name"), str)] if isinstance(plugins, list) else [],
        "doctor": len(doctor) if isinstance(doctor, list) else 0,
        "install": bool(provides.get("install")),
    }


def units_command(args: Sequence[str], units: Optional[Mapping[str, Any]] = None) -> int:
    as_json = "--json" in args
    words = [arg for arg in args if arg != "--json"]
    units = load_units() if units is None else units
    action = words[0] if words else "list"
    if action == "show":
        if len(words) != 2:
            print("usage: swissknifeman units show <id> [--json]", file=sys.stderr)
            return 2
        unit = units.get(words[1])
        if unit is None:
            print(f"UNIT_UNKNOWN: no module {words[1]!r}; known: {', '.join(units) or 'none'}", file=sys.stderr)
            return 2
        print(json.dumps(unit.doc, indent=2, ensure_ascii=False))
        return 0
    if action != "list" or len(words) > 1:
        print("usage: swissknifeman units [list|show <id>] [--json]", file=sys.stderr)
        return 2
    rows = [unit_row(unit) for unit in units.values()]
    if as_json:
        print(json.dumps({"schema": UNITS_SCHEMA, "units": rows}, indent=2, ensure_ascii=False))
        return 0
    for row in rows:
        print(" ".join([row["id"], row["kind"], row["version"], row["stability"], row["destination"],
                        row["cli"][0] if row["cli"] else "-"]))
    return 0


def doctor_command(units: Optional[Mapping[str, Any]] = None, config: Optional[Mapping[str, Any]] = None) -> int:
    """Run ``<cli> doctor`` of the modules listed in the config ``doctor.fanout``, in that order; exit is the last failure."""
    units = load_units() if units is None else units
    config = load_config() if config is None else config
    rc = 0
    for key in _strings((config.get("doctor") or {}).get("fanout")):
        unit = units.get(key)
        path = cli_of(unit) if unit is not None else None
        print(f"== {key} ==", flush=True)
        if path is None or not path.exists():
            print(f"ERROR: package launcher not found: {path or key}", file=sys.stderr)
            rc = 1
        else:
            code = subprocess.run(_command(path) + ["doctor"], check=False).returncode
            rc = code or rc
        print()
    return rc


def main(argv: Optional[Sequence[str]] = None) -> int:
    return route(list(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())
