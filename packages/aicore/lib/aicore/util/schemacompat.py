"""Backward-compatibility check of contract schemas (stdlib only).

``compare`` walks two versions of a schema in parallel and reports every change by the rules in ``RULES``:
a change is *breaking* when a document valid by the old schema may be invalid by the new one. The rules are
conservative: a change whose compatibility cannot be proven (a different ``pattern``, a different ``oneOf``)
counts as breaking. Annotations (``title``, ``description``, ``default``, ``x-skm-*``) are not compared.

``main`` is the ``aicore schema compat`` command: it compares the contracts of the working tree with the same
contracts at a git reference, inside one major version, and grades each breaking change by the ``stability`` of
the contract in ``unit.json``.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Mapping, NamedTuple, Optional, Sequence, Set, TextIO, Tuple

from .schema import RefError, Registry, SchemaProfileError, _compile, _equal, load_contract

# rule -> whether the change breaks documents that were valid by the old schema
RULES: Dict[str, bool] = {
    "property-removed": True,
    "property-added": False,
    "required-added": True,
    "required-removed": False,
    "enum-narrowed": True,
    "enum-widened": False,
    "enum-added": True,
    "type-changed": True,
    "type-widened": False,
    "const-changed": True,
    "pattern-changed": True,
    "pattern-removed": False,
    "bound-tightened": True,
    "bound-relaxed": False,
    "additional-closed": True,
    "pattern-property-removed": True,
    "pattern-property-added": False,
    "property-names-changed": True,
    "unique-added": True,
    "oneof-changed": True,
    "ref-changed": False,
}

# Stabilities whose breaking changes are refused; the others (development, alpha) only warn.
WARN_ONLY_STABILITY = frozenset({"development", "alpha"})
DEFAULT_REF = "HEAD"
GIT_TIMEOUT = 30

# (keyword, value when absent, direction): a "min" bound is tightened by growing, a "max" bound by shrinking
_BOUNDS = (("minLength", 0, "min"), ("minItems", 0, "min"), ("minimum", None, "min"), ("maximum", None, "max"))
_SCHEMA_FILE = re.compile(r"[a-z][a-z0-9-]*/v[1-9][0-9]*/[a-z][a-z0-9-]*\.schema\.json")


class Change(NamedTuple):
    path: str  # JSON pointer into the schema, "" is the root
    rule: str  # a key of RULES
    breaking: bool
    message: str


def compare(old: Registry, old_id: str, new: Registry, new_id: str) -> List[Change]:
    """Changes from the schema ``old_id`` of ``old`` to the schema ``new_id`` of ``new``."""
    return _Comparer(old, new).run(old_id, new_id)


class _Comparer:
    def __init__(self, old: Registry, new: Registry):
        self.old = old
        self.new = new
        self.changes: List[Change] = []
        self._visited: Set[Tuple[Any, Any]] = set()  # pairs of $ref targets that were already compared

    def run(self, old_id: str, new_id: str) -> List[Change]:
        old_root, old_owner = self.old.resolve(old_id, old_id)
        new_root, new_owner = self.new.resolve(new_id, new_id)
        self._walk(old_root, old_owner, new_root, new_owner, "")
        return self.changes

    def _add(self, path: str, rule: str, message: str) -> None:
        self.changes.append(Change(path, rule, RULES[rule], message))

    def _walk(self, old: dict, old_base: str, new: dict, new_base: str, path: str) -> None:
        old, old_base, old_target = _expand(self.old, old, old_base)
        new, new_base, new_target = _expand(self.new, new, new_base)
        if old_target is not None or new_target is not None:
            pair = (old_target or id(old), new_target or id(new))
            if pair in self._visited:
                return
            self._visited.add(pair)
        if old_target is not None and new_target is not None and old_target[0] != new_target[0]:
            self._add(path, "ref-changed", f"$ref target moved from {old_target[0]} to {new_target[0]}")
        self._type(old, new, path)
        self._enum(old, new, path)
        self._const_pattern(old, new, path)
        self._bounds(old, new, path)
        if new.get("uniqueItems") is True and old.get("uniqueItems") is not True:
            self._add(path, "unique-added", "uniqueItems is now required")
        self._objects(old, old_base, new, new_base, path)
        if "items" in old or "items" in new:
            self._walk(old.get("items", {}), old_base, new.get("items", {}), new_base, f"{path}/items")
        self._one_of(old, old_base, new, new_base, path)

    def _type(self, old: dict, new: dict, path: str) -> None:
        old_types, new_types = _types(old), _types(new)
        if old_types == new_types:
            return
        if new_types is None:
            self._add(path, "type-widened", "type restriction removed")
        elif old_types is None or not all(_covered(t, new_types) for t in old_types):
            self._add(path, "type-changed", f"type {_show_types(old_types)} is now {_show_types(new_types)}")
        else:
            self._add(path, "type-widened", f"type {_show_types(old_types)} is now {_show_types(new_types)}")

    def _enum(self, old: dict, new: dict, path: str) -> None:
        old_enum, new_enum = old.get("enum"), new.get("enum")
        if new_enum is None and old_enum is not None:
            self._add(path, "enum-widened", "enum removed")
        elif old_enum is None and new_enum is not None:
            self._add(path, "enum-added", "enum now restricts the values")
        elif old_enum is not None and new_enum is not None:
            dropped = [v for v in old_enum if not _contains(new_enum, v)]
            gained = [v for v in new_enum if not _contains(old_enum, v)]
            if dropped:
                self._add(path, "enum-narrowed", "enum lost " + _show(dropped))
            if gained:
                self._add(path, "enum-widened", "enum gained " + _show(gained))

    def _const_pattern(self, old: dict, new: dict, path: str) -> None:
        if "const" in new and ("const" not in old or not _equal(old["const"], new["const"])):
            self._add(path, "const-changed", f"const is now {_show(new['const'])}")
        old_pattern, new_pattern = old.get("pattern"), new.get("pattern")
        if new_pattern is not None and new_pattern != old_pattern:
            self._add(path, "pattern-changed", f"pattern is now {new_pattern!r}")  # regex equality is not proven
        elif new_pattern is None and old_pattern is not None:
            self._add(path, "pattern-removed", "pattern removed")

    def _bounds(self, old: dict, new: dict, path: str) -> None:
        for keyword, default, direction in _BOUNDS:
            old_value, new_value = old.get(keyword, default), new.get(keyword, default)
            if old_value == new_value:
                continue
            grows = direction == "min"
            if new_value is not None and (old_value is None or (new_value > old_value) == grows):
                self._add(path, "bound-tightened", f"{keyword} is now {new_value} (was {_bound(old_value)})")
            else:
                self._add(path, "bound-relaxed", f"{keyword} is now {_bound(new_value)} (was {old_value})")

    def _objects(self, old: dict, old_base: str, new: dict, new_base: str, path: str) -> None:
        old_props, new_props = old.get("properties", {}), new.get("properties", {})
        new_patterns = new.get("patternProperties", {})
        closed = new.get("additionalProperties") is False
        if closed and old.get("additionalProperties") is not False:
            self._add(path, "additional-closed", "additionalProperties is now false")
        for name in old_props:
            if name not in new_props and closed and not any(_compile(p).search(name) for p in new_patterns):
                self._add(f"{path}/properties/{_escape(name)}", "property-removed",
                          f"property {name!r} removed from a closed object")
        for name, child in new_props.items():
            if name in old_props:
                self._walk(old_props[name], old_base, child, new_base, f"{path}/properties/{_escape(name)}")
            else:
                self._add(f"{path}/properties/{_escape(name)}", "property-added", f"property {name!r} added")
        old_required, new_required = old.get("required", ()), new.get("required", ())
        for name in new_required:
            if name not in old_required:
                self._add(path, "required-added", f"property {name!r} is now required")
        for name in old_required:
            if name not in new_required:
                self._add(path, "required-removed", f"property {name!r} is no longer required")
        old_patterns = old.get("patternProperties", {})
        for pattern in old_patterns:
            if pattern not in new_patterns:
                self._add(f"{path}/patternProperties/{_escape(pattern)}", "pattern-property-removed",
                          f"patternProperties key {pattern!r} removed")
        for pattern, child in new_patterns.items():
            if pattern in old_patterns:
                self._walk(old_patterns[pattern], old_base, child, new_base,
                           f"{path}/patternProperties/{_escape(pattern)}")
            else:
                self._add(f"{path}/patternProperties/{_escape(pattern)}", "pattern-property-added",
                          f"patternProperties key {pattern!r} added")
        if "propertyNames" in new and ("propertyNames" not in old
                                       or not _equal(old["propertyNames"], new["propertyNames"])):
            self._add(path, "property-names-changed", "propertyNames is now " + _show(new["propertyNames"]))

    def _one_of(self, old: dict, old_base: str, new: dict, new_base: str, path: str) -> None:
        old_branches, new_branches = old.get("oneOf"), new.get("oneOf")
        if old_branches is None and new_branches is None:
            return
        if old_branches is None or new_branches is None or len(old_branches) != len(new_branches):
            self._add(f"{path}/oneOf", "oneof-changed",
                      f"oneOf has {len(old_branches or ())} branches, now {len(new_branches or ())}")
            return
        outer = self.changes
        for index, (before, after) in enumerate(zip(old_branches, new_branches)):
            self.changes = []
            self._walk(before, old_base, after, new_base, f"{path}/oneOf/{index}")
            inner, self.changes = self.changes, outer
            if inner:
                rules = ", ".join(sorted({change.rule for change in inner}))
                self._add(f"{path}/oneOf/{index}", "oneof-changed", f"oneOf branch {index} changed ({rules})")


def _expand(registry: Registry, node: dict, base: str,
            seen: Optional[Set[Tuple[str, str]]] = None) -> Tuple[dict, str, Optional[Tuple[str, str]]]:
    """Resolve ``$ref`` chains: the merged body, the owner of its children and the final target ``(owner, ref)``.

    Keywords next to a ``$ref`` win over the target's: no contract of the repository combines them with
    anything but annotations.
    """
    ref = node.get("$ref")
    if ref is None:
        return node, base, None
    target, owner = registry.resolve(ref, base)
    key = (owner, ref.partition("#")[2])
    seen = set() if seen is None else seen
    if key in seen:
        raise RefError(f"$ref {ref!r} refers to itself")
    seen.add(key)
    body, owner, final = _expand(registry, target, owner, seen)
    merged = dict(body)
    merged.update((k, v) for k, v in node.items() if k != "$ref")
    return merged, owner, final or key


def _types(node: dict) -> Optional[Set[str]]:
    value = node.get("type")
    if value is None:
        return None
    return {value} if isinstance(value, str) else set(value)


def _covered(name: str, types: Set[str]) -> bool:
    return name in types or (name == "integer" and "number" in types)


def _show_types(types: Optional[Set[str]]) -> str:
    return "any" if types is None else "/".join(sorted(types))


def _contains(values: Sequence[Any], value: Any) -> bool:
    return any(_equal(value, other) for other in values)


def _show(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _bound(value: Any) -> str:
    return "unbounded" if value is None else str(value)


def _escape(key: str) -> str:
    return key.replace("~", "~0").replace("/", "~1")


# ---- command line -----------------------------------------------------------------------------------------------

USAGE = ("usage: aicore schema <command> [args]\n\ncommands:\n"
         "  compat   compare the contracts with a git reference and report incompatible changes\n\n"
         "Run `aicore schema compat --help` for the options.\n")


class _Exit(Exception):
    def __init__(self, code: int):
        super().__init__(code)
        self.code = code


class _Refusal(Exception):
    def __init__(self, code: str, message: str, exit_code: int = 2):
        super().__init__(message)
        self.code = code
        self.exit_code = exit_code


class _Parser(argparse.ArgumentParser):
    """argparse that writes to the streams given to ``main`` and reports usage errors as ``CODE: message``."""

    out: TextIO = sys.stdout
    err: TextIO = sys.stderr

    def _print_message(self, message, file=None):  # type: ignore[override]
        if message:
            (self.err if file is sys.stderr else self.out).write(message)

    def error(self, message: str):  # type: ignore[override]
        self.err.write(f"SCHEMA_COMPAT_USAGE: {message}\n")
        raise _Exit(2)

    def exit(self, status=0, message=None):  # type: ignore[override]
        if message:
            self.err.write(message)
        raise _Exit(status)


def build_parser(out: TextIO, err: TextIO) -> argparse.ArgumentParser:
    parser = _Parser(prog="aicore schema compat", description="Compare the contract schemas of the working tree "
                     "with a git reference inside one major version.")
    parser.out, parser.err = out, err
    parser.add_argument("--base", metavar="REF", default=DEFAULT_REF, help="git reference to compare with (default: HEAD)")
    parser.add_argument("--root", metavar="DIR", help="directory of the contract schemas "
                        "(default: packages/aicore/schemas of the repository, else the schemas of this module)")
    parser.add_argument("--unit", metavar="FILE", help="unit.json that grades the contracts (default: <root>/../unit.json)")
    parser.add_argument("--contract", metavar="NAME", help="compare one contract only")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    return parser


def main(argv: Optional[Sequence[str]] = None, *, env: Optional[Mapping[str, str]] = None,
         cwd: Optional[Path] = None, out: Optional[TextIO] = None, err: Optional[TextIO] = None) -> int:
    """``aicore schema <command>``; exit 0 compatible or warnings only, 1 breaking change, 2 usage or git error."""
    args = list(sys.argv[1:] if argv is None else argv)
    out = out or sys.stdout
    err = err or sys.stderr
    if not args:
        err.write(USAGE)
        return 2
    if args[0] in ("-h", "--help", "help"):
        out.write(USAGE)
        return 0
    if args[0] != "compat":
        err.write(f"SCHEMA_COMPAT_USAGE: unknown command {args[0]!r}\n{USAGE}")
        return 2
    parser = build_parser(out, err)
    try:
        options = parser.parse_args(args[1:])
        report = _compat(options, Path(cwd) if cwd else Path.cwd(), env)
    except _Exit as stop:
        return stop.code
    except _Refusal as refusal:
        err.write(f"{refusal.code}: {refusal}\n")
        return refusal.exit_code
    if options.json:
        out.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    else:
        out.write(render_text(report))
    return 1 if _errors(report) else 0


def _compat(options: argparse.Namespace, cwd: Path, env: Optional[Mapping[str, str]]) -> dict:
    repo = _git_toplevel(cwd, env)
    root = _schema_root(options.root, repo, cwd)
    try:
        relroot = root.relative_to(repo).as_posix()
    except ValueError:
        raise _Refusal("SCHEMA_COMPAT_ROOT", f"{root} is outside the repository {repo}")
    unit_path = Path(options.unit).resolve() if options.unit else root.parent / "unit.json"
    stabilities, module_stability = _read_stabilities(unit_path)
    current = _contracts(root)
    if options.contract is not None:
        current = {key: value for key, value in current.items() if key[0] == options.contract}
        if not current:
            raise _Refusal("SCHEMA_COMPAT_UNKNOWN_CONTRACT", f"no contract {options.contract!r} in {root}")
    base_files = _base_files(repo, relroot, options.base, env)
    contracts = []
    with tempfile.TemporaryDirectory(prefix="skm-compat-") as scratch:
        base_root = Path(scratch)
        for relpath in base_files:
            target = base_root / relpath
            target.parent.mkdir(parents=True, exist_ok=True)
            location = relpath if relroot == "." else f"{relroot}/{relpath}"
            target.write_bytes(_git(repo, ["show", f"{options.base}:{location}"], env).stdout)
        base_contracts = _contracts(base_root)
        for (name, version), directory in sorted(current.items(), key=lambda item: (item[0][0], _major(item[0][1]))):
            stability = stabilities.get((name, version), module_stability)
            entry = {"contract": name, "version": version, "stability": stability, "status": "compared",
                     "changes": []}
            if (name, version) not in base_contracts:
                previous = [v for (n, v) in base_contracts if n == name and _major(v) < _major(version)]
                entry["status"] = "major" if previous else "new"
            else:
                entry["changes"] = _grade(_compare_dirs(base_contracts[(name, version)], directory, name, version),
                                          stability)
            contracts.append(entry)
    return {"base": options.base, "contracts": contracts}


def _compare_dirs(base_dir: Path, current_dir: Path, name: str, version: str) -> List[Change]:
    label = f"{name}/{version}"
    try:
        old, kind = load_contract(base_dir)
    except SchemaProfileError as exc:
        raise _Refusal("SCHEMA_COMPAT_BASE_INVALID", f"{label} at the base: {exc}", 1)
    try:
        new, _ = load_contract(current_dir)
    except SchemaProfileError as exc:
        raise _Refusal("SCHEMA_COMPAT_INVALID", f"{label}: {exc}", 1)
    try:
        return compare(old, old.for_kind(kind)[1], new, new.for_kind(kind)[1])
    except RefError as exc:
        raise _Refusal("SCHEMA_COMPAT_INVALID", f"{label}: {exc}", 1)


def _grade(changes: Sequence[Change], stability: str) -> List[dict]:
    graded = []
    for change in changes:
        if not change.breaking:
            severity = "info"
        elif stability in WARN_ONLY_STABILITY:
            severity = "warning"
        else:
            severity = "error"
        graded.append({"path": change.path, "rule": change.rule, "breaking": change.breaking,
                       "severity": severity, "message": change.message})
    return graded


def _errors(report: dict) -> bool:
    return any(change["severity"] == "error" for entry in report["contracts"] for change in entry["changes"])


def render_text(report: dict) -> str:
    lines = []
    counts = {"error": 0, "warning": 0, "info": 0}
    for entry in report["contracts"]:
        label = f"{entry['contract']}/{entry['version']}"
        if entry["status"] != "compared":
            lines.append(f"{label}: {entry['status']} (not compared)")
        for change in entry["changes"]:
            counts[change["severity"]] += 1
            lines.append(f"{label} {change['path'] or '/'}: {change['rule']} ({change['severity']}) "
                         f"{change['message']}")
    lines.append(f"compat: {len(report['contracts'])} contracts against {report['base']}: "
                 f"{counts['error']} errors, {counts['warning']} warnings, {counts['info']} notes")
    return "\n".join(lines) + "\n"


def _major(version: str) -> int:
    return int(version[1:])


def _schema_root(option: Optional[str], repo: Path, cwd: Path) -> Path:
    if option:
        root = Path(option)
        root = (root if root.is_absolute() else cwd / root).resolve()
    else:
        root = repo / "packages" / "aicore" / "schemas"
        if not root.is_dir():
            root = Path(__file__).resolve().parents[3] / "schemas"
    if not root.is_dir():
        raise _Refusal("SCHEMA_COMPAT_ROOT", f"{root} is not a directory")
    return root


def _contracts(root: Path) -> Dict[Tuple[str, str], Path]:
    """``(contract, version) -> directory`` for every ``<contract>/v<N>/<contract>.schema.json`` below ``root``."""
    found = {}
    for path in sorted(root.glob("*/v*/*.schema.json")):
        relpath = path.relative_to(root).as_posix()
        if _SCHEMA_FILE.fullmatch(relpath) and path.stem[: -len(".schema")] == path.parent.parent.name:
            found[(path.parent.parent.name, path.parent.name)] = path.parent
    return found


def _read_stabilities(unit_path: Path) -> Tuple[Dict[Tuple[str, str], str], str]:
    try:
        unit = json.loads(unit_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise _Refusal("SCHEMA_COMPAT_UNIT", f"cannot read {unit_path}: {exc}")
    stabilities = {}
    for contract in (unit.get("provides") or {}).get("contracts") or ():
        name = str(contract.get("id", "")).rpartition(":")[2]
        stabilities[(name, contract.get("version"))] = contract.get("stability", "development")
    return stabilities, unit.get("stability", "development")  # an unlisted contract follows its module


def _git(repo: Path, arguments: Sequence[str], env: Optional[Mapping[str, str]]) -> "subprocess.CompletedProcess[bytes]":
    try:
        result = subprocess.run(["git", "-C", str(repo)] + list(arguments), capture_output=True,
                                timeout=GIT_TIMEOUT, env=dict(env) if env is not None else None)
    except FileNotFoundError:
        raise _Refusal("SCHEMA_COMPAT_NO_GIT", "git is not installed")
    except subprocess.TimeoutExpired:
        raise _Refusal("SCHEMA_COMPAT_GIT_FAILED", f"git {arguments[0]} did not finish in {GIT_TIMEOUT}s")
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise _Refusal("SCHEMA_COMPAT_GIT_FAILED", f"git {' '.join(arguments[:2])} failed: {detail}")
    return result


def _git_toplevel(cwd: Path, env: Optional[Mapping[str, str]]) -> Path:
    try:
        result = _git(cwd, ["rev-parse", "--show-toplevel"], env)
    except _Refusal as refusal:
        if refusal.code == "SCHEMA_COMPAT_GIT_FAILED":
            raise _Refusal("SCHEMA_COMPAT_NO_GIT", f"{cwd} is not inside a git repository")
        raise
    return Path(result.stdout.decode("utf-8").strip()).resolve()


def _base_files(repo: Path, relroot: str, ref: str, env: Optional[Mapping[str, str]]) -> List[str]:
    """Paths (relative to the schema root) of the schema files that the reference holds."""
    if ref.startswith("-"):
        raise _Refusal("SCHEMA_COMPAT_USAGE", f"invalid git reference {ref!r}")
    try:
        _git(repo, ["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], env)
    except _Refusal as refusal:
        if refusal.code == "SCHEMA_COMPAT_GIT_FAILED":
            raise _Refusal("SCHEMA_COMPAT_BAD_REF", f"{ref!r} is not a commit of {repo}")
        raise
    listing = _git(repo, ["ls-tree", "-r", "--name-only", ref, "--", relroot], env).stdout.decode("utf-8")
    prefix = "" if relroot == "." else relroot + "/"
    names = [line[len(prefix):] for line in listing.splitlines() if line.startswith(prefix)]
    return [name for name in names if _SCHEMA_FILE.fullmatch(name)]
