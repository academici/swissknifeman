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
    ("doctor [--unit ID] [--category C] [--json] [--timeout S]", "read-only checks of the modules (provides.doctor)"),
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
        return doctor_command(rest, units)
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


DOCTOR_SCHEMA = "umbrella-doctor/v1"
DEFAULT_TIMEOUT = 120.0
CATEGORIES = ("environment", "config", "state", "content", "integration")
DOCTOR_USAGE = "usage: swissknifeman doctor [--unit ID]... [--category C]... [--json] [--timeout S]"


def _doctor_args(args: Sequence[str]) -> Any:
    """Parse the doctor options: ``(unit ids, categories, as_json, timeout)`` or an error message."""
    ids: List[str] = []
    cats: List[str] = []
    as_json = False
    timeout = DEFAULT_TIMEOUT
    rest = list(args)
    while rest:
        arg = rest.pop(0)
        name, eq, inline = arg.partition("=")
        if arg == "--json":
            as_json = True
        elif name in ("--unit", "--category", "--timeout"):
            if eq:
                value = inline
            elif rest:
                value = rest.pop(0)
            else:
                return f"{arg} needs a value"
            if name == "--unit":
                ids.append(value)
            elif name == "--category":
                if value not in CATEGORIES:
                    return f"unknown category {value!r}; known: {', '.join(CATEGORIES)}"
                cats.append(value)
            else:
                try:
                    timeout = float(value)
                except ValueError:
                    return f"--timeout needs a number of seconds, got {value!r}"
                if not timeout > 0:
                    return "--timeout must be positive"
        else:
            return f"unknown argument {arg!r}"
    return ids, cats, as_json, timeout


def _declared(unit: Any) -> List[Dict[str, Any]]:
    entries = _provides(unit).get("doctor")
    return [item for item in entries if isinstance(item, dict) and isinstance(item.get("id"), str)
            and _strings(item.get("probe"))] if isinstance(entries, list) else []


def _synthetic(schema_id: str, unit_id: str, check_id: str, category: str, observed: str,
               remediation: str) -> Dict[str, Any]:
    return {"$schema": schema_id, "check_id": check_id, "status": "fail",
            "category": category, "observed": observed, "remediation": remediation, "unit": unit_id}


def _run_probe(argv: Sequence[str], cwd: Path, timeout: float) -> Any:
    """Run one probe read-only from the module root: ``(stdout, None)`` or ``(None, reason)``."""
    head = cwd / argv[0]
    command = (_command(head) if head.exists() else [argv[0]]) + list(argv[1:])
    try:
        proc = subprocess.Popen(command, cwd=str(cwd), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, start_new_session=True)
    except OSError as exc:
        return None, f"probe could not start: {exc.__class__.__name__}: {exc}"
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, 9)
        except OSError:
            proc.kill()
        proc.communicate()
        return None, f"probe timed out after {timeout:g} s"
    if not out.strip():
        return None, f"probe printed nothing (exit {proc.returncode}): {err.strip()[:300]}"
    return out, None


def _check_registry() -> Any:
    import aicore as foundation
    from aicore.util.schema import load_contract

    folder = Path(foundation.__file__).resolve().parents[2] / "schemas" / "check-result" / "v1"
    registry, kind = load_contract(folder)
    schema = json.loads((folder / f"{kind}.schema.json").read_text(encoding="utf-8"))
    return registry, kind, schema["properties"]["$schema"]["const"]


def _parse_results(out: str, registry: Any, kind: str) -> Any:
    """Documents of a probe output as ``(list, None)`` or ``(None, reason)``; every document must satisfy check-result/v1."""
    from aicore.util.schema import validate

    try:
        data = json.loads(out)
    except ValueError:
        return None, f"probe output is not JSON: {out.strip()[:300]}"
    docs = data if isinstance(data, list) else [data]
    for doc in docs:
        issues = validate(doc, kind, registry) if isinstance(doc, dict) else ["not an object"]
        if issues:
            return None, f"probe output violates check-result/v1: {str(issues[0])[:300]}"
    return docs, None


def collect_doctor(units: Mapping[str, Any], unit_ids: Sequence[str], categories: Sequence[str],
                   timeout: float) -> Dict[str, Any]:
    """Run the unique probes of the selected modules once each; build the ``umbrella-doctor/v1`` document."""
    registry, kind, schema_id = _check_registry()
    results: List[Dict[str, Any]] = []
    without: List[str] = []
    for unit in units.values():
        if unit_ids and unit.id not in unit_ids:
            continue
        declared = _declared(unit)
        if not declared:
            without.append(unit.id)
            continue
        wanted = [item for item in declared if not categories or item.get("category") in categories]
        probes: Dict[tuple, List[Dict[str, Any]]] = {}
        for item in wanted:
            probes.setdefault(tuple(_strings(item["probe"])), []).append(item)
        for argv, items in probes.items():
            ids = {item["id"] for item in items}
            out, reason = _run_probe(argv, unit.root, timeout)
            docs, reason = _parse_results(out, registry, kind) if out is not None else (None, reason)
            if docs is None:
                results.append(_synthetic(schema_id, unit.id, f"{unit.id}.doctor", "environment", str(reason),
                                          "run in the module folder: " + " ".join(argv)))
                continue
            seen = set()
            for doc in docs:
                check = doc["check_id"]
                if not (check in {d["id"] for d in declared} or check.startswith(unit.id + ".")):
                    continue
                if categories and doc["category"] not in categories:
                    continue
                seen.add(check)
                results.append({**doc, "unit": unit.id})
            for item in items:
                if item["id"] not in seen:
                    results.append(_synthetic(schema_id, unit.id, item["id"], str(item.get("category") or "environment"),
                                              "probe printed no result for this check",
                                              "run in the module folder: " + " ".join(argv)))
    return {"schema": DOCTOR_SCHEMA, "results": results, "units_without_doctor": without}


def doctor_command(args: Sequence[str], units: Optional[Mapping[str, Any]] = None) -> int:
    """Aggregate ``provides.doctor`` of the modules; read-only; exit 1 on any fail, 2 on a usage error."""
    parsed = _doctor_args(args)
    if isinstance(parsed, str):
        print(f"{parsed}\n{DOCTOR_USAGE}", file=sys.stderr)
        return 2
    unit_ids, categories, as_json, timeout = parsed
    units = load_units() if units is None else units
    unknown = [item for item in unit_ids if item not in units]
    if unknown:
        print(f"UNIT_UNKNOWN: no module {unknown[0]!r}; known: {', '.join(units) or 'none'}", file=sys.stderr)
        return 2
    doc = collect_doctor(units, unit_ids, categories, timeout)
    results = doc["results"]
    failed = any(item["status"] == "fail" for item in results)
    if as_json:
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        return 1 if failed else 0
    for item in results:
        print(f"{item['status']} {item['check_id']}: {item['observed']}")
    for unit_id in doc["units_without_doctor"]:
        print(f"info {unit_id}: no doctor checks declared")
    counts = {name: sum(1 for item in results if item["status"] == name) for name in ("ok", "warn", "fail", "skip")}
    print(f"{counts['ok']} ok, {counts['warn']} warn, {counts['fail']} fail"
          + (f", {counts['skip']} skip" if counts["skip"] else ""))
    fixes = [item for item in results if item["status"] in ("warn", "fail") and item.get("remediation")]
    if fixes:
        print("\nRemediation:")
        for item in fixes:
            print(f"  {item['check_id']}: {item['remediation']}")
    return 1 if failed else 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    return route(list(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())
