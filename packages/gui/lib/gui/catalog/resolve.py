"""Resolver of GUI contributions: the one place that decides which ``gui.json`` the GUI trusts.

Each contribution goes through the rules in ``RULES`` order (path, read, schema, then the rules beyond the schema);
the first failing rule names the rejection code. Accepted contributions are then compared with each other: two
sources that claim the same owner, local id or route path are all rejected (``CONTRIB_CONFLICT``), so the order of
the sources never decides a winner. The catalog (``catalog/v1``) is sorted and carries no timestamps.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from aicore.config.units import foundation_root
from aicore.ext.conformance import run_conformance
from aicore.ext.errors import ExtError
from aicore.ext.plugins import load_manifest
from aicore.util.digest import digest_json
from aicore.util.paths import is_within, resolve_path

from .. import contracts
from .sources import Collected, Source, declared

CATALOG = "urn:swissknifeman:gui:catalog:v1"
HOST_PROTOCOL = ("1", "1")  # min, max

INVALID = "CONTRIB_INVALID"
UNREADABLE = "CONTRIB_UNREADABLE"
OWNER_MISMATCH = "CONTRIB_OWNER_MISMATCH"
ID_PREFIX = "CONTRIB_ID_PREFIX"
CONFLICT = "CONTRIB_CONFLICT"
INCOMPATIBLE = "CONTRIB_INCOMPATIBLE"
HANDLER_MISSING = "CONTRIB_HANDLER_MISSING"
PATH_ESCAPE = "CONTRIB_PATH_ESCAPE"
REF_UNKNOWN = "CONTRIB_REF_UNKNOWN"
INPUT_UNKNOWN = "CONTRIB_INPUT_UNKNOWN"
CAPABILITY_RESERVED = "CONTRIB_CAPABILITY_RESERVED"

RULES = ("path", "read", "schema", "limits", "owner", "ids", "protocol", "handler", "refs", "argv", "capabilities")

# Limits the schema cannot express (docs/contribution.md#limits).
MAX_FILE_BYTES = 256 * 1024
MAX_TITLE = 200
MAX_DESCRIPTION = 2000
MAX_STRING = 4096
MAX_LIST = 200
MAX_FIELDS = 64
MAX_ARGV = 64
MAX_ENUM = 200
MAX_FORM_FIELDS = 500

LISTS = ("routes", "widgets", "queries", "commands", "forms", "config_sections", "docs")
PLACEHOLDERS = frozenset({"project_id", "plan_id", "item_id"})
_PLACEHOLDER = re.compile(r"\{([^{}]*)\}")
_PATH_PARAM = re.compile(r"^:([a-z][a-z0-9_]*)$")


@dataclass(frozen=True)
class Finding:
    code: str
    message: str
    pointer: str = ""
    issue: Optional[str] = None  # validation issue code (schema codes, max_length, max_items, pattern)


@dataclass
class RuleResult:
    rule: str
    findings: List[Finding] = field(default_factory=list)
    skipped: Optional[str] = None  # why the rule did not run

    @property
    def failed(self) -> bool:
        return bool(self.findings)


@dataclass
class Evaluation:
    """The rules of one contribution. ``file`` is the realpath of gui.json when the path rule passed."""

    owner: Optional[str]
    kind: Optional[str]
    file: str
    rules: List[RuleResult]
    document: Any = None
    digest: Optional[str] = None
    handler: Optional[Path] = None

    @property
    def rejection(self) -> Optional[Tuple[str, str, List[Finding]]]:
        for result in self.rules:
            if result.failed:
                code = result.findings[0].code
                same = [finding for finding in result.findings if finding.code == code]
                return code, "; ".join(finding.message for finding in same[:5]), same
        return None


def host_contracts() -> Set[Tuple[str, str]]:
    """``(id, version)`` of the contracts of gui and of the foundation."""
    found: Set[Tuple[str, str]] = set()
    for unit in (contracts.SCHEMAS.parent / "unit.json", foundation_root() / "unit.json"):
        try:
            entries = json.loads(unit.read_text(encoding="utf-8"))["provides"]["contracts"]
        except (OSError, ValueError, KeyError, TypeError):
            continue
        for entry in entries if isinstance(entries, list) else ():
            if isinstance(entry, dict) and isinstance(entry.get("id"), str) and isinstance(entry.get("version"), str):
                found.add((entry["id"], entry["version"]))
    return found


# --- one contribution ---------------------------------------------------------------------------------------


def _inside(root: Path, relative: str) -> Optional[Path]:
    """The realpath of ``root/relative`` when it stays inside ``root``; ``None`` otherwise (fail closed)."""
    if not relative or os.path.isabs(relative):
        return None
    try:
        resolved = resolve_path(root / relative)
    except (OSError, ValueError, RuntimeError):
        return None
    return resolved if is_within(resolved, root) else None


def evaluate(source: Source, *, host_protocol: Tuple[str, str] = HOST_PROTOCOL,
             supported: Optional[Set[Tuple[str, str]]] = None) -> Evaluation:
    """Run every rule on one declared contribution; ``source.owner`` may be empty when no manifest names it."""
    root = Path(source.root)
    evaluation = Evaluation(owner=source.owner or None, kind=source.kind or None, file=str(root / source.gui),
                            rules=[])
    results = {rule: RuleResult(rule) for rule in RULES}
    evaluation.rules = [results[rule] for rule in RULES]

    def skip_from(rule: str, why: str) -> None:
        for name in RULES[RULES.index(rule):]:
            results[name].skipped = why

    target = _inside(root, source.gui)
    if target is None:
        results["path"].findings.append(Finding(PATH_ESCAPE, f"{source.gui!r} leaves the owner root"))
        skip_from("read", "the path rule failed")
        return evaluation
    evaluation.file = str(target)
    try:
        size = target.stat().st_size
        document = None if size > MAX_FILE_BYTES else json.loads(target.read_bytes().decode("utf-8"))
    except (OSError, ValueError) as exc:
        size, reason = 0, f"cannot read JSON: {exc.__class__.__name__}"
    else:
        reason = f"the file has {size} bytes, the limit is {MAX_FILE_BYTES}" if size > MAX_FILE_BYTES else None
    if reason:
        results["read"].findings.append(Finding(UNREADABLE, reason))
        skip_from("schema", "the read rule failed")
        return evaluation
    evaluation.document = document
    evaluation.digest = digest_json(document)
    issues = contracts.validate(document, "contribution")
    if issues:
        results["schema"].findings.extend(Finding(INVALID, issue.message, issue.path, issue.code) for issue in issues)
        skip_from("limits", "the schema rule failed")
        return evaluation

    results["limits"].findings.extend(_limits(document))
    if source.owner:
        if document["owner"] != source.owner:
            results["owner"].findings.append(Finding(OWNER_MISMATCH, f"owner {document['owner']!r} differs from the "
                                                                     f"manifest id {source.owner!r}", "/owner"))
    else:
        results["owner"].skipped = "no unit.json or extension.json declares this file"
    results["ids"].findings.extend(_ids(document))
    results["protocol"].findings.extend(_protocol(document, host_protocol,
                                                  host_contracts() if supported is None else supported))
    handler_findings, evaluation.handler = _handler(document, root)
    results["handler"].findings.extend(handler_findings)
    results["refs"].findings.extend(_refs(document, root))
    results["argv"].findings.extend(_argv(document, root))
    results["capabilities"].findings.extend(_capabilities(document))
    return evaluation


def _walk(node: Any, pointer: str = "") -> Iterable[Tuple[str, str, Any]]:
    """``(pointer, key, value)`` of every value below ``node``."""
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{pointer}/{key.replace('~', '~0').replace('/', '~1')}"
            yield child, key, value
            yield from _walk(value, child)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            child = f"{pointer}/{index}"
            yield child, str(index), value
            yield from _walk(value, child)


def _limits(document: dict) -> List[Finding]:
    found = []

    def over(pointer: str, what: str, size: int, limit: int, code: str) -> None:
        if size > limit:
            found.append(Finding(INVALID, f"{pointer}: {what} has {size}, the limit is {limit}", pointer, code))

    for name in LISTS:
        over(f"/{name}", "the list", len(document.get(name, ())), MAX_LIST, "max_items")
    for pointer, key, value in _walk(document):
        if isinstance(value, str):
            limit = MAX_TITLE if key in ("title", "label") else MAX_DESCRIPTION if key == "description" else MAX_STRING
            over(pointer, "the text", len(value), limit, "max_length")
        elif isinstance(value, list):
            limit = {"params": MAX_FIELDS, "input": MAX_FIELDS, "argv": MAX_ARGV, "argv_append": MAX_ARGV,
                     "enum": MAX_ENUM, "fields": MAX_FORM_FIELDS}.get(key)
            if limit is not None:
                over(pointer, "the list", len(value), limit, "max_items")
        if key == "pattern" and isinstance(value, str):
            try:
                re.compile(value)
            except re.error as exc:
                found.append(Finding(INVALID, f"{pointer}: the pattern does not compile: {exc}", pointer, "pattern"))
    return found


def _ids(document: dict) -> List[Finding]:
    found = []
    owner = document["owner"]
    for name in LISTS:
        seen: Set[str] = set()
        for index, item in enumerate(document.get(name, ())):
            local = item["id"]
            pointer = f"/{name}/{index}/id"
            if local.split(".")[0] != owner:
                found.append(Finding(ID_PREFIX, f"{name} id {local!r} must start with {owner + '.'!r}", pointer))
            if local in seen:
                found.append(Finding(CONFLICT, f"{name} id {local!r} is declared twice", pointer))
            seen.add(local)
    paths: Set[str] = set()
    for index, route in enumerate(document.get("routes", ())):
        if route["path"] in paths:
            found.append(Finding(CONFLICT, f"route path {route['path']!r} is declared twice", f"/routes/{index}/path"))
        paths.add(route["path"])
    for kind, key in (("queries", "params"), ("commands", "input")):
        for index, item in enumerate(document.get(kind, ())):
            names = [entry["name"] for entry in item.get(key, ())]
            for name in sorted({name for name in names if names.count(name) > 1}):
                found.append(Finding(CONFLICT, f"{item['id']}: field {name!r} is declared twice",
                                     f"/{kind}/{index}/{key}"))
    return found


def _protocol(document: dict, host: Tuple[str, str], supported: Set[Tuple[str, str]]) -> List[Finding]:
    low, high = int(document["gui_protocol"]["min"]), int(document["gui_protocol"]["max"])
    if low > high:
        return [Finding(INCOMPATIBLE, f"gui_protocol min {low} is greater than max {high}", "/gui_protocol")]
    found = []
    if high < int(host[0]) or low > int(host[1]):
        found.append(Finding(INCOMPATIBLE, f"gui_protocol {low}-{high} excludes the host protocol "
                                           f"{host[0]}-{host[1]}", "/gui_protocol"))
    for index, need in enumerate(document.get("requires_contracts", ())):
        if (need["id"], need["version"]) not in supported:
            found.append(Finding(INCOMPATIBLE, f"the host does not support {need['id']} {need['version']}",
                                 f"/requires_contracts/{index}"))
    return found


def compatibility(source: Source, *, host_protocol: Tuple[str, str] = HOST_PROTOCOL,
                  supported: Optional[Set[Tuple[str, str]]] = None) -> Dict[str, Any]:
    """``{protocol_ok, missing_contracts}`` of a source against the host: the data of ``trust/v1`` ``compatibility``.

    Reads only ``gui_protocol`` and ``requires_contracts`` of the file, so it works for a contribution that other
    rules reject. A file that cannot be read, or whose fields are malformed, says nothing against the host
    (``protocol_ok`` true, nothing missing): the reason is then the rejection itself, not compatibility.
    """
    supported = host_contracts() if supported is None else supported
    target = _inside(Path(source.root), source.gui)
    try:
        document = json.loads(target.read_bytes().decode("utf-8")) if target is not None else None
    except (OSError, ValueError):
        document = None
    protocol_ok, missing = True, []
    if isinstance(document, dict):
        window = document.get("gui_protocol")
        try:
            low, high = int(window["min"]), int(window["max"])
            protocol_ok = low <= high and not (high < int(host_protocol[0]) or low > int(host_protocol[1]))
        except (KeyError, TypeError, ValueError):
            pass
        needs = document.get("requires_contracts")
        for need in needs if isinstance(needs, list) else ():
            if isinstance(need, dict) and isinstance(need.get("id"), str) and isinstance(need.get("version"), str) \
                    and (need["id"], need["version"]) not in supported:
                missing.append({"id": need["id"], "version": need["version"]})
    missing.sort(key=lambda entry: (entry["id"], entry["version"]))
    return {"protocol_ok": protocol_ok, "missing_contracts": missing}


def _handler(document: dict, root: Path) -> Tuple[List[Finding], Optional[Path]]:
    points = set()
    if document.get("queries"):
        points.add("gui:query")
    if any(command["exec"]["kind"] == "invoke" for command in document.get("commands", ())):
        points.add("gui:command")
    handler = document.get("handler")
    if handler is None:
        if points:
            return [Finding(HANDLER_MISSING, f"queries or invoke commands need a handler ({', '.join(sorted(points))})",
                            "/handler")], None
        return [], None
    target = _inside(root, handler["extension"])
    if target is None:
        return [Finding(PATH_ESCAPE, f"handler {handler['extension']!r} leaves the owner root", "/handler/extension")], None
    if not target.is_file():
        return [Finding(HANDLER_MISSING, f"handler {handler['extension']!r} does not exist", "/handler/extension")], None
    try:
        manifest = load_manifest(target)
    except ExtError as exc:
        return [Finding(HANDLER_MISSING, f"handler {handler['extension']!r} is not usable: {exc.code}",
                        "/handler/extension")], None
    if manifest.kind != "command":
        return [Finding(HANDLER_MISSING, f"handler {handler['extension']!r} is a {manifest.kind} plugin, not a command",
                        "/handler/extension")], None
    missing = sorted(points - set(manifest.points))
    if missing:
        return [Finding(HANDLER_MISSING, f"handler {handler['extension']!r} does not provide {', '.join(missing)}",
                        "/handler/extension")], None
    return [], target


def _refs(document: dict, root: Path) -> List[Finding]:
    found = []
    queries = {query["id"]: query for query in document.get("queries", ())}
    commands = {command["id"]: command for command in document.get("commands", ())}
    forms = {form["id"] for form in document.get("forms", ())}
    docs = {entry["id"] for entry in document.get("docs", ())}

    def unknown(pointer: str, message: str) -> None:
        found.append(Finding(REF_UNKNOWN, message, pointer))

    for index, route in enumerate(document.get("routes", ())):
        at = f"/routes/{index}"
        view, query = route["view"], route.get("query")
        if view == "command-form" and "command" not in route:
            unknown(at, f"route {route['id']}: a command-form route needs a command")
        elif view == "markdown" and not (query or route.get("docs")):
            unknown(at, f"route {route['id']}: a markdown route needs a query or docs")
        elif view not in ("command-form", "markdown") and not query:
            unknown(at, f"route {route['id']}: a {view} route needs a query")
        for key, known in (("query", queries), ("command", commands), ("docs", docs)):
            if key in route and route[key] not in known:
                unknown(f"{at}/{key}", f"route {route['id']}: {key} {route[key]!r} is not declared")
        if query in queries and queries[query]["returns"] != view:
            unknown(f"{at}/view", f"route {route['id']}: view {view!r} differs from what query {query!r} returns "
                                  f"({queries[query]['returns']!r})")
        params = {match.group(1) for match in (_PATH_PARAM.match(part) for part in route["path"].split("/")) if match}
        declared = {entry["name"] for entry in queries.get(query, {}).get("params", ())}
        for name in sorted(params - declared):
            unknown(f"{at}/path", f"route {route['id']}: path parameter {name!r} is not a parameter of its query")
        for position, action in enumerate(route.get("actions", ())):
            if action not in commands:
                unknown(f"{at}/actions/{position}", f"route {route['id']}: action {action!r} is not declared")
    for index, widget in enumerate(document.get("widgets", ())):
        query = queries.get(widget["query"])
        if query is None:
            unknown(f"/widgets/{index}/query", f"widget {widget['id']}: query {widget['query']!r} is not declared")
        elif query["returns"] != widget["view"]:
            unknown(f"/widgets/{index}/view", f"widget {widget['id']}: view {widget['view']!r} differs from what "
                                              f"query {widget['query']!r} returns ({query['returns']!r})")
    for index, section in enumerate(document.get("config_sections", ())):
        if "form" in section and section["form"] not in forms:
            unknown(f"/config_sections/{index}/form", f"configuration section {section['id']}: form "
                                                      f"{section['form']!r} is not declared")
    for kind, key in (("queries", "params"), ("commands", "input")):
        for index, item in enumerate(document.get(kind, ())):
            for position, entry in enumerate(item.get(key, ())):
                if (entry["type"] == "enum") != ("enum" in entry):
                    unknown(f"/{kind}/{index}/{key}/{position}", f"{item['id']}: field {entry['name']!r}: enum values "
                                                                 "go with type enum, and only with it")
    for index, command in enumerate(document.get("commands", ())):
        fields = {entry["name"]: entry for entry in command.get("input", ())}
        dry_run = command.get("dry_run", {})
        if "input" in dry_run and fields.get(dry_run["input"], {}).get("type") != "boolean":
            unknown(f"/commands/{index}/dry_run/input", f"command {command['id']}: dry_run input "
                                                        f"{dry_run['input']!r} is not a boolean input field")
        for name in sorted(set(_PLACEHOLDER.findall(command.get("concurrency_key", ""))) - PLACEHOLDERS):
            unknown(f"/commands/{index}/concurrency_key", f"command {command['id']}: unknown placeholder {{{name}}}")
    for index, entry in enumerate(document.get("docs", ())):
        tree = _inside(root, entry["root"])
        page = _inside(tree, entry["index"]) if tree is not None else None
        if tree is None or page is None:
            found.append(Finding(PATH_ESCAPE, f"docs {entry['id']}: {entry['root']!r}/{entry['index']!r} leaves the "
                                              "owner root", f"/docs/{index}"))
        elif not page.is_file():
            unknown(f"/docs/{index}/index", f"docs {entry['id']}: {entry['root']}/{entry['index']} does not exist")
    return found


def _argv(document: dict, root: Path) -> List[Finding]:
    found = []
    for index, command in enumerate(document.get("commands", ())):
        execution = command["exec"]
        if execution["kind"] != "argv":
            continue
        at = f"/commands/{index}/exec/argv"
        fields = {entry["name"]: entry for entry in command.get("input", ())}
        first = execution["argv"][0]
        if not isinstance(first, str):
            found.append(Finding(PATH_ESCAPE, f"command {command['id']}: argv[0] must be a literal path", f"{at}/0"))
        else:
            program = _inside(root, first)
            if program is None:
                found.append(Finding(PATH_ESCAPE, f"command {command['id']}: argv[0] {first!r} leaves the owner root",
                                     f"{at}/0"))
            elif not program.is_file() or not os.access(str(program), os.X_OK):
                found.append(Finding(REF_UNKNOWN, f"command {command['id']}: argv[0] {first!r} is not an executable "
                                                  "file", f"{at}/0"))
        for position, part in enumerate(execution["argv"]):
            if isinstance(part, dict):
                entry = fields.get(part["input"])
                if entry is None:
                    found.append(Finding(INPUT_UNKNOWN, f"command {command['id']}: input {part['input']!r} is not "
                                                        "declared", f"{at}/{position}"))
                elif "flag" in entry:
                    found.append(Finding(INPUT_UNKNOWN, f"command {command['id']}: input {part['input']!r} has a flag "
                                                        "and cannot stand in argv", f"{at}/{position}"))
    return found


def _capabilities(document: dict) -> List[Finding]:
    found = []
    for index, command in enumerate(document.get("commands", ())):
        at = f"/commands/{index}"
        supports = set(command.get("supports", ()))
        if "terminal" in command["effects"]:
            found.append(Finding(CAPABILITY_RESERVED, f"command {command['id']}: the effect terminal is reserved in v1",
                                 f"{at}/effects"))
        if ("dry-run" in supports) != ("dry_run" in command):
            found.append(Finding(CAPABILITY_RESERVED, f"command {command['id']}: supports dry-run and dry_run go "
                                                      "together", f"{at}/supports"))
        if command["exec"]["kind"] == "invoke" and supports & {"stream", "cancel"}:
            found.append(Finding(CAPABILITY_RESERVED, f"command {command['id']}: stream and cancel need an argv exec",
                                 f"{at}/supports"))
    return found


# --- the catalog --------------------------------------------------------------------------------------------


def _local_keys(document: dict) -> Iterable[Tuple[str, str]]:
    yield "owner", document["owner"]
    for name in LISTS:
        for item in document.get(name, ()):
            yield name, item["id"]
    for route in document.get("routes", ()):
        yield "path", f"/x/{document['owner']}/{route['path']}"


def _rejected(owner: Optional[str], file: str, code: str, message: str,
              findings: Sequence[Finding] = ()) -> Dict[str, Any]:
    entry: Dict[str, Any] = {"owner": owner, "file": file, "code": code, "message": message}
    issues = [{"pointer": finding.pointer, "code": finding.issue, "message": finding.message}
              for finding in findings if finding.issue]
    if issues:
        entry["issues"] = issues[:50]
    return entry


@dataclass(frozen=True)
class Owner:
    """What the backend needs of an accepted contribution and the catalog leaves out: the source with its root,
    the realpath of the handler manifest (``None`` without one), the document and the manifest version."""

    source: Source
    handler: Optional[Path]
    document: Dict[str, Any]
    version: Optional[str]


def _manifest_version(manifest: Path) -> Optional[str]:
    try:
        version = json.loads(Path(manifest).read_text(encoding="utf-8")).get("version")
    except (OSError, ValueError, AttributeError):
        return None
    return version if isinstance(version, str) else None


def resolve(collected: Collected, *, host_protocol: Tuple[str, str] = HOST_PROTOCOL,
            supported: Optional[Set[Tuple[str, str]]] = None) -> Dict[str, Any]:
    """The ``catalog/v1`` document of the collected sources."""
    return resolve_indexed(collected, host_protocol=host_protocol, supported=supported)[0]


def index(collected: Collected, **options: Any) -> Dict[str, Owner]:
    """``owner -> Owner`` of the accepted contributions (the same pass as :func:`resolve`; catalog/v1 unchanged)."""
    return resolve_indexed(collected, **options)[1]


def resolve_indexed(collected: Collected, *, host_protocol: Tuple[str, str] = HOST_PROTOCOL,
                    supported: Optional[Set[Tuple[str, str]]] = None) -> Tuple[Dict[str, Any], Dict[str, Owner]]:
    """The ``catalog/v1`` document and the :class:`Owner` of every accepted contribution, in one pass."""
    supported = host_contracts() if supported is None else supported
    accepted: List[Tuple[Source, Evaluation]] = []
    rejected: List[Dict[str, Any]] = [dict(problem) for problem in collected.problems]
    for source in sorted(collected.sources, key=Source.sort_key):
        evaluation = evaluate(source, host_protocol=host_protocol, supported=supported)
        rejection = evaluation.rejection
        if rejection is None:
            accepted.append((source, evaluation))
        else:
            code, message, findings = rejection
            rejected.append(_rejected(source.owner, evaluation.file, code, message, findings))
    claims: Dict[Tuple[str, str], List[int]] = {}
    for position, (_source, evaluation) in enumerate(accepted):  # one participant per source, even for one file
        for key in set(_local_keys(evaluation.document)):
            claims.setdefault(key, []).append(position)
    conflicting: Dict[int, List[str]] = {}
    for (kind, value), participants in sorted(claims.items()):
        if len(participants) > 1:
            for position in participants:
                conflicting.setdefault(position, []).append(f"{kind} {value!r}")
    entries = []
    owners: Dict[str, Owner] = {}
    for position, (source, evaluation) in enumerate(accepted):
        if position in conflicting:
            claimed = conflicting[position]
            rejected.append(_rejected(source.owner, evaluation.file, CONFLICT,
                                      "another contribution also claims " + ", ".join(claimed[:5])))
        else:
            entries.append({"owner": source.owner, "source": source.kind, "file": evaluation.file,
                            "digest": evaluation.digest, "document": evaluation.document})
            owners[source.owner] = Owner(source, evaluation.handler, evaluation.document,
                                         _manifest_version(source.manifest))
    entries.sort(key=lambda entry: (entry["owner"], entry["source"], entry["file"]))
    rejected.sort(key=lambda entry: (entry["owner"] or "", entry["file"], entry["code"], entry["message"]))
    host = {"gui_protocol": {"min": host_protocol[0], "max": host_protocol[1]}}
    digest = digest_json({"host": host, "contributions": [
        {"owner": entry["owner"], "source": entry["source"], "digest": entry["digest"]} for entry in entries]})
    return {"$schema": CATALOG, "host": host, "contributions": entries, "rejected": rejected, "digest": digest}, owners


# --- gui check ----------------------------------------------------------------------------------------------

CHECK_RESULT = "urn:swissknifeman:aicore:check-result:v1"
_OBSERVED_OK = {
    "path": "the file stays inside the owner root",
    "read": "the file is readable JSON within the size limit",
    "schema": "the document is valid contribution/v1",
    "limits": "texts and lists are within the limits",
    "owner": "the owner equals the manifest id",
    "ids": "local ids carry the owner prefix and are unique; route paths are unique",
    "protocol": "the protocol range and the required contracts fit the host",
    "handler": "the handler is present when needed and provides the needed points",
    "refs": "every reference is declared and every docs path stays inside the owner root",
    "argv": "argv[0] is an executable inside the owner root; every input is declared and has no flag",
    "capabilities": "no reserved capability is used",
}
_REMEDIATION = {
    PATH_ESCAPE: "Keep every path relative and inside the owner root, without symlinks that leave it.",
    UNREADABLE: "Write gui.json as UTF-8 JSON under the size limit.",
    INVALID: "Fix the fields named in the evidence (docs/contribution.md).",
    OWNER_MISMATCH: "Set owner to the id of the unit.json or extension.json that declares the file.",
    ID_PREFIX: "Start every local id with '<owner>.'.",
    CONFLICT: "Give every local id, route path and field name one declaration.",
    INCOMPATIBLE: "Fit gui_protocol and requires_contracts to what the host supports.",
    HANDLER_MISSING: "Point handler.extension to a command extension.json that provides gui:query and gui:command.",
    REF_UNKNOWN: "Declare what routes, widgets, actions, forms and docs refer to.",
    INPUT_UNKNOWN: "Use only declared input fields without a flag in argv.",
    CAPABILITY_RESERVED: "Remove the reserved capability (terminal; stream or cancel with invoke; dry-run without "
                         "dry_run).",
}


def candidate(path: Path) -> Optional[Source]:
    """The contribution ``path`` names: a gui.json file or a unit or extension folder that declares one."""
    path = Path(path)
    if path.is_dir():
        for kind, name in (("unit", "unit.json"), ("extension", "extension.json")):
            source = declared(kind, path / name)
            if source is not None:
                return source
        return None
    for kind, name in (("unit", "unit.json"), ("extension", "extension.json")):
        source = declared(kind, path.parent / name)
        if source is not None and _inside(source.root, source.gui) == _inside(path.parent, path.name):
            return source
    return Source(kind="", owner="", root=path.parent, manifest=path, gui=path.name)


def check(path: Path, *, env: Optional[Dict[str, str]] = None, conformance: bool = True) -> List[Dict[str, Any]]:
    """``check-result/v1`` documents of every rule for one contribution, then the conformance of its handler."""
    source = candidate(path)
    if source is None:
        return [{"$schema": CHECK_RESULT, "check_id": "gui.contribution.path", "status": "fail", "category": "content",
                 "observed": f"{path} has no unit.json or extension.json that declares provides.gui",
                 "remediation": "Give a gui.json file, or a unit or extension folder whose manifest has provides.gui."}]
    evaluation = evaluate(source)
    results = []
    for result in evaluation.rules:
        doc: Dict[str, Any] = {"$schema": CHECK_RESULT, "check_id": f"gui.contribution.{result.rule}",
                               "category": "content"}
        if result.failed:
            code = result.findings[0].code
            doc.update(status="fail", observed=f"{code}: {result.findings[0].message}",
                       evidence=[f"{finding.code} {finding.pointer or '/'}: {finding.message}"
                                 for finding in result.findings[:50]],
                       remediation=_REMEDIATION[code])
        elif result.skipped:
            doc.update(status="skip", observed=result.skipped)
        else:
            doc.update(status="ok", observed=_OBSERVED_OK[result.rule])
        results.append(doc)
    if conformance and evaluation.handler is not None:
        results.extend(run_conformance(evaluation.handler, env=env))
    return results
