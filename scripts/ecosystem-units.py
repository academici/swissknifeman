#!/usr/bin/env python3
"""Module split checks for the hub: manifests (unit.json) and the aicore schema profile; module listing.

Stdlib only, Python >= 3.9. The file list comes from git (tracked plus untracked-not-ignored files), never
from os.walk. The script reads files under --root and writes nothing; it does not run module CLIs.

Commands:
  check [--json]   all checks; exit 0 clean, 1 errors, 2 usage or environment problem
  list  [--json]   modules with id, kind, version, destination, stability, requires

Diagnostics are lines ``ECOSYSTEM_<CODE>: <path>: <message>`` on stderr. Checks are registered in CHECKS so
further checks (ownership map, schemas, boundaries) join without touching the command code.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

HUB_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = "configs/ecosystem-units.json"
UNIT_FILE = "unit.json"
AICORE_SCHEMA_URN_PREFIX = "urn:swissknifeman:aicore:"
AICORE_SCHEMAS = (("unit", "packages/aicore/schemas/unit/v1"),
                  ("check-result", "packages/aicore/schemas/check-result/v1"))
VERSION_READERS = ("json:version", "python:__version__")
SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)(-[0-9A-Za-z.-]+)?$")
CARET = re.compile(r"^\^(\d+)\.(\d+)(?:\.(\d+))?$")


class EnvironmentProblem(Exception):
    """Not a usage error of the user's command line but a missing prerequisite (exit 2)."""


@dataclass(frozen=True)
class Issue:
    code: str
    path: str
    message: str

    def text(self) -> str:
        return f"ECOSYSTEM_{self.code}: {self.path}: {self.message}"

    def as_json(self) -> dict:
        return {"code": f"ECOSYSTEM_{self.code}", "path": self.path, "message": self.message}


@dataclass
class Context:
    root: Path
    config: dict
    files: list
    _units: dict = field(default_factory=dict)


@dataclass
class Unit:
    folder: str
    doc: object  # parsed unit.json (any JSON value; validity is a separate check)


# --------------------------------------------------------------------------------------------- inputs

def list_files(root: Path) -> list:
    """Tracked and untracked-not-ignored files that exist, as sorted POSIX paths relative to root."""
    try:
        result = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--cached", "--others",
                                 "--exclude-standard"], capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise EnvironmentProblem(f"{root}: cannot list files with git: {exc}") from exc
    names = [n for n in result.stdout.decode("utf-8", "surrogateescape").split("\0") if n]
    return sorted({n for n in names if (root / n).is_file()})


def load_config(root: Path) -> dict:
    path = root / CONFIG_PATH
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EnvironmentProblem(f"{CONFIG_PATH}: cannot load: {exc}") from exc
    if not isinstance(config, dict):
        raise EnvironmentProblem(f"{CONFIG_PATH}: must be a JSON object")
    return config


def build_context(root: Path) -> Context:
    return Context(root=root, config=load_config(root), files=list_files(root))


def schema_validator():
    """Closed-profile validator of the orchestration module (the hub's copy, until the foundation owns one)."""
    lib = str(HUB_ROOT / "packages" / "orch" / "lib")
    if lib not in sys.path:
        sys.path.insert(0, lib)
    try:
        from orch import schema  # type: ignore
    except ImportError as exc:
        raise EnvironmentProblem(f"cannot import orch.schema from {lib}: {exc}") from exc
    return schema


# ------------------------------------------------------------------------------------ semver and ranges

def parse_version(text: str):
    """(major, minor, patch, release_flag); a pre-release sorts below its release (flag 0 < 1)."""
    match = SEMVER.match(text)
    if not match:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)), 0 if match.group(4) else 1)


def caret_bounds(text: str):
    """npm caret ``^X.Y[.Z]`` as (inclusive lower, exclusive upper) comparison keys, or None if malformed.

    X > 0: >=X.Y.Z <(X+1).0.0. X = 0: >=0.Y.Z <0.(Y+1).0; with an explicit patch on 0.0 the patch is pinned:
    ^0.0.Z is >=0.0.Z <0.0.(Z+1). A pre-release of the lower bound does not satisfy the range.
    """
    match = CARET.match(text)
    if not match:
        return None
    major, minor = int(match.group(1)), int(match.group(2))
    patch = int(match.group(3)) if match.group(3) is not None else 0
    if major > 0:
        upper = (major + 1, 0, 0, 0)
    elif minor > 0 or match.group(3) is None:
        upper = (0, minor + 1, 0, 0)
    else:
        upper = (0, 0, patch + 1, 0)
    return (major, minor, patch, 1), upper


def satisfies(version: str, range_text: str) -> bool:
    key = parse_version(version)
    bounds = caret_bounds(range_text)
    if key is None or bounds is None:
        return False
    return bounds[0] <= key < bounds[1]


def read_version(root: Path, source: dict) -> str:
    """Version string from a ``version_sources`` entry; raises ValueError with a readable reason."""
    path, how = source.get("path"), source.get("read")
    if not isinstance(path, str) or how not in VERSION_READERS:
        raise ValueError(f"version source must have a path and a read mode of {', '.join(VERSION_READERS)}")
    try:
        text = (root / path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc.strerror or exc}") from exc
    if how == "json:version":
        try:
            value = json.loads(text).get("version")
        except (ValueError, AttributeError) as exc:
            raise ValueError(f"{path} is not a JSON object with a version") from exc
    else:
        value = None
        try:
            for node in ast.parse(text).body:
                if isinstance(node, ast.Assign) and any(
                        isinstance(t, ast.Name) and t.id == "__version__" for t in node.targets):
                    value = ast.literal_eval(node.value)
        except (SyntaxError, ValueError) as exc:
            raise ValueError(f"cannot read __version__ from {path}: {exc}") from exc
    if not isinstance(value, str):
        raise ValueError(f"{path} has no string version")
    return value


# ----------------------------------------------------------------------------------------------- units

def module_folders(ctx: Context) -> list:
    """Folders under packages/ that hold files, minus the retired ones."""
    retired = set(ctx.config.get("retired") or ())
    folders = {p.split("/")[1] for p in ctx.files if p.startswith("packages/") and p.count("/") >= 2}
    return sorted(folders - retired)


def load_units(ctx: Context) -> dict:
    """folder -> Unit for every module folder whose unit.json exists and parses; cached per context."""
    if not ctx._units:
        for folder in module_folders(ctx):
            path = ctx.root / "packages" / folder / UNIT_FILE
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            ctx._units[folder] = Unit(folder, doc)
    return ctx._units


def unit_registry(ctx: Context, schema):
    return schema.load_registry(ctx.root / AICORE_SCHEMAS[0][1], urn_prefix=AICORE_SCHEMA_URN_PREFIX,
                                kinds=(AICORE_SCHEMAS[0][0],))


def lib_packages(ctx: Context, folder: str) -> list:
    prefix = f"packages/{folder}/lib/"
    names = set()
    for path in ctx.files:
        if path.startswith(prefix):
            top = path[len(prefix):].split("/")[0]
            if top.endswith(".py"):
                top = top[:-3]
            if top and top != "__pycache__" and not top.endswith(".egg-info"):
                names.add(top)
    return sorted(names)


def safe_relpath(value: str) -> bool:
    return not (value.startswith("/") or any(part in ("", ".", "..") for part in value.split("/")))


def check_manifests(ctx: Context) -> list:
    issues: list = []
    schema = schema_validator()
    try:
        registry = unit_registry(ctx, schema)
    except schema.SchemaProfileError as exc:
        return [Issue("SCHEMA_PROFILE", AICORE_SCHEMAS[0][1], str(exc))]
    config_versions = ctx.config.get("version_sources") or {}
    foundation_id = (ctx.config.get("foundation") or {}).get("id")
    folders = module_folders(ctx)
    valid: dict = {}  # folder -> doc, only units that passed schema validation

    for folder in folders:
        manifest = f"packages/{folder}/{UNIT_FILE}"
        path = ctx.root / manifest
        if not path.is_file():
            issues.append(Issue("UNIT_MISSING", manifest, f"module folder packages/{folder}/ has no {UNIT_FILE}"))
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            issues.append(Issue("UNIT_INVALID", manifest, f"cannot parse JSON: {exc}"))
            continue
        problems = schema.validate(doc, "unit", registry)
        for problem in problems:
            issues.append(Issue("UNIT_INVALID", manifest, f"{problem.code}: {problem.message}"))
        if problems:
            continue
        valid[folder] = doc
        if doc["id"] != folder:
            issues.append(Issue("UNIT_ID", manifest, f"id {doc['id']!r} must equal the folder name {folder!r}"))
        if (ctx.root / "packages" / folder / "lib").is_dir():
            found = lib_packages(ctx, folder)
            if found != [folder]:
                issues.append(Issue("UNIT_LIB", manifest, f"lib/ must hold exactly one top package named "
                                                          f"{folder!r}, found {found or 'none'}"))
        issues.extend(_check_version(ctx, folder, manifest, doc, config_versions, foundation_id))
        issues.extend(_check_paths(ctx, folder, manifest, doc))

    for folder, doc in valid.items():
        issues.extend(_check_requires(f"packages/{folder}/{UNIT_FILE}", doc, valid, foundation_id))
    return issues


def _check_version(ctx, folder, manifest, doc, sources, foundation_id) -> list:
    source = sources.get(folder)
    if source is None:
        if doc["id"] == foundation_id:
            return []  # the foundation's unit.json is its own version source
        return [Issue("UNIT_VERSION", manifest, f"no entry for {folder!r} in {CONFIG_PATH} version_sources")]
    try:
        expected = read_version(ctx.root, source)
    except ValueError as exc:
        return [Issue("UNIT_VERSION", manifest, str(exc))]
    if doc["version"] != expected:
        return [Issue("UNIT_VERSION", manifest, f"version {doc['version']!r} differs from {source['path']} "
                                                f"({expected!r}); fix {UNIT_FILE}")]
    return []


def _check_requires(manifest, doc, valid, foundation_id) -> list:
    issues = []
    by_id = {d["id"]: d for d in valid.values()}
    seen = set()
    for index, req in enumerate(doc["requires"]):
        name = req["unit"]
        where = f"requires[{index}] {name!r}"
        if name in seen:
            issues.append(Issue("UNIT_REQUIRES", manifest, f"{where}: listed twice"))
        seen.add(name)
        target = by_id.get(name)
        if name == doc["id"]:
            issues.append(Issue("UNIT_REQUIRES", manifest, f"{where}: a unit cannot require itself"))
        elif target is None:
            issues.append(Issue("UNIT_REQUIRES", manifest, f"{where}: no such unit"))
        elif doc["kind"] == "foundation":
            issues.append(Issue("UNIT_REQUIRES", manifest, f"{where}: the foundation requires nothing"))
        elif target["kind"] != "foundation":
            issues.append(Issue("UNIT_REQUIRES", manifest, f"{where}: a {doc['kind']} may require only the "
                                                           f"foundation, {name!r} is a {target['kind']}"))
        elif not satisfies(target["version"], req["range"]):
            issues.append(Issue("UNIT_RANGE", manifest, f"{where}: version {target['version']} of {name!r} "
                                                        f"does not satisfy {req['range']}"))
    return issues


def _check_paths(ctx, folder, manifest, doc) -> list:
    issues = []
    base = ctx.root / "packages" / folder
    provides = doc["provides"]

    def probe(kind, rel, label, executable=False, directory=False):
        if not safe_relpath(rel):
            issues.append(Issue("UNIT_PATH", manifest, f"{label}: {rel!r} must stay inside the module"))
            return None
        target = base / rel
        exists = target.is_dir() if directory else target.is_file()
        if not exists:
            issues.append(Issue("UNIT_PATH", manifest, f"{label}: {rel!r} does not exist"))
            return None
        if executable and not (rel.endswith(".py") or os.access(target, os.X_OK)):
            issues.append(Issue("UNIT_PATH", manifest, f"{label}: {rel!r} is not executable"))
            return None
        return target

    for rel in provides.get("cli", ()):
        probe("cli", rel, "provides.cli", executable=True)
    for plugin in provides.get("plugins", ()):
        target = probe("plugin", plugin["manifest"], f"provides.plugins[{plugin['name']}]")
        if target is not None:
            try:
                name = json.loads(target.read_text(encoding="utf-8")).get("name")
            except (OSError, ValueError, AttributeError):
                name = None
            if name != plugin["name"]:
                issues.append(Issue("UNIT_PATH", manifest, f"provides.plugins: {plugin['manifest']!r} names "
                                                           f"{name!r}, expected {plugin['name']!r}"))
    for contract in provides.get("contracts", ()):
        probe("contract", contract["path"], f"provides.contracts[{contract['id']}]", directory=True)
    for check in provides.get("doctor", ()):
        probe("doctor", check["probe"][0], f"provides.doctor[{check['id']}]")
    if "config" in provides:
        probe("config", provides["config"], "provides.config")
    return issues


def check_aicore_schemas(ctx: Context) -> list:
    """The aicore schemas must load under the closed profile (draft 2020-12, no free-form keywords)."""
    if not (ctx.root / "packages" / "aicore").is_dir():
        return []
    schema = schema_validator()
    issues = []
    for kind, rel in AICORE_SCHEMAS:
        if not (ctx.root / rel).is_dir():
            issues.append(Issue("SCHEMA_PROFILE", rel, "schema directory is missing"))
            continue
        try:
            registry = schema.load_registry(ctx.root / rel, urn_prefix=AICORE_SCHEMA_URN_PREFIX, kinds=(kind,))
            registry.for_kind(kind)
        except schema.SchemaProfileError as exc:
            issues.append(Issue("SCHEMA_PROFILE", rel, str(exc)))
    return issues


def check_config(ctx: Context) -> list:
    """Shape of configs/ecosystem-units.json (only the keys the implemented checks rely on)."""
    config, issues = ctx.config, []

    def bad(message):
        issues.append(Issue("CONFIG", CONFIG_PATH, message))

    if config.get("schema_version") != "ecosystem-units/v1":
        bad("schema_version must be 'ecosystem-units/v1'")
    targets = config.get("targets")
    if not (isinstance(targets, list) and targets and all(isinstance(t, str) and t for t in targets)):
        bad("targets must be a non-empty list of strings")
        targets = []
    aliases = config.get("module_aliases")
    if not (isinstance(aliases, dict) and all(isinstance(v, str) and v in targets for v in aliases.values())):
        bad("module_aliases must map folder ids to ids listed in targets")
    retired = config.get("retired")
    if not (isinstance(retired, list) and all(isinstance(r, str) for r in retired)):
        bad("retired must be a list of folder names")
    foundation = config.get("foundation")
    if not (isinstance(foundation, dict) and isinstance(foundation.get("id"), str)
            and isinstance(foundation.get("aliases"), list)):
        bad("foundation must be {id, aliases[]}")
    sources = config.get("version_sources")
    if not isinstance(sources, dict):
        bad("version_sources must be an object")
    else:
        for folder, source in sorted(sources.items()):
            if not (isinstance(source, dict) and isinstance(source.get("path"), str)
                    and source.get("read") in VERSION_READERS):
                bad(f"version_sources[{folder!r}] must be {{path, read}} with read in {', '.join(VERSION_READERS)}")
    return issues


CHECKS = (("config", check_config), ("manifests", check_manifests), ("aicore-schemas", check_aicore_schemas))


# ---------------------------------------------------------------------------------------------- commands

def cmd_check(ctx: Context, args) -> int:
    issues: list = []
    for _name, run in CHECKS:
        issues.extend(run(ctx))
    if args.json:
        print(json.dumps({"ok": not issues, "errors": [i.as_json() for i in issues],
                          "violations": [], "improvements": []}, indent=2))
    for issue in issues:
        print(issue.text(), file=sys.stderr)
    return 1 if issues else 0


def cmd_list(ctx: Context, args) -> int:
    rows = []
    for folder, unit in sorted(load_units(ctx).items()):
        doc = unit.doc if isinstance(unit.doc, dict) else {}
        requires = [r.get("unit") for r in doc.get("requires", ()) if isinstance(r, dict)]
        rows.append({"id": doc.get("id", folder), "kind": doc.get("kind"), "version": doc.get("version"),
                     "destination": doc.get("destination"), "stability": doc.get("stability"),
                     "requires": requires})
    if args.json:
        print(json.dumps({"modules": rows}, indent=2))
        return 0
    header = ("id", "kind", "version", "destination", "stability", "requires")
    table = [header] + [tuple(str(row[k] if k != "requires" else ",".join(row[k]) or "-") for k in header)
                        for row in rows]
    widths = [max(len(r[i]) for r in table) for i in range(len(header))]
    for r in table:
        print("  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ecosystem-units.py", description=__doc__.split("\n\n")[0])
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--root", type=Path, default=HUB_ROOT, help="repository root (default: this repository)")
    shared.add_argument("--json", action="store_true", help="machine-readable output on stdout")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", parents=[shared], help="run all checks")
    sub.add_parser("list", parents=[shared], help="list modules")
    return parser


COMMANDS = {"check": cmd_check, "list": cmd_list}


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        ctx = build_context(args.root.resolve())
        return COMMANDS[args.command](ctx, args)
    except EnvironmentProblem as exc:
        print(f"ecosystem-units: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
