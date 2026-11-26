"""SchemaRegistry: every packaged schema loaded offline and resolved by URN (kernel-platform §3.3).

Loading reads only the given ``Traversable`` tree. A ``$ref`` may name another schema by its ``urn:skm:``
``$id`` (optionally with a ``#/json/pointer``) or point inside its own document (``#/...``); anything else,
and anything that does not resolve inside the registry, fails the load. Nothing is fetched from a network
or the file system by reference resolution.
"""

import functools
import json
import re
import sys
from collections.abc import Iterator, Mapping
from importlib.resources.abc import Traversable
from types import MappingProxyType
from typing import Any, Final, NamedTuple, cast
from urllib.parse import urljoin

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from referencing import Registry, Resource
from referencing.exceptions import Unresolvable
from referencing.jsonschema import DRAFT202012

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError, ValidationFailed
from skm.kernel.json_types import JsonValue
from skm.platform.schema.findings import SchemaIssue, SchemaLoadError, SchemaLoadProblem, json_pointer
from skm.platform.schema.formats import KNOWN_FORMATS
from skm.platform.schema.locator import default_schema_root
from skm.platform.schema.validator import SchemaValidator, scope, subschemas, text_safe, without_dialect

__all__ = ["DRAFT_2020_12", "MAX_REPORTED_ISSUES", "URN_PATTERN", "SchemaRegistry"]

DRAFT_2020_12: Final = "https://json-schema.org/draft/2020-12/schema"
MAX_REPORTED_ISSUES: Final = 50
URN_PATTERN: Final = re.compile(
    r"urn:skm:(?P<module>[a-z][a-z0-9_-]*)(?::[a-z0-9][a-z0-9._-]*)+:v[1-9][0-9]*"
)

_SCHEMA_FILE = re.compile(r".+\.v[1-9][0-9]*\.json")
_SKIPPED_DIRECTORIES: Final = frozenset({"data", "__pycache__"})
_IN_PLACE_LISTS: Final = ("allOf", "anyOf", "oneOf")
_IN_PLACE_SINGLES: Final = ("not", "if", "then", "else")
_REF_KEYWORDS: Final = ("$ref", "$dynamicRef")
# Schema positions constrained by the bundled Draft 2020-12 metaschema, including its deprecated maps.
# Project these positions one node at a time so schema nesting never becomes Python call-stack depth.
_META_MAPS: Final = ("$defs", "definitions", "properties", "patternProperties", "dependentSchemas")
_META_LISTS: Final = ("allOf", "anyOf", "oneOf", "prefixItems")
_META_SINGLES: Final = (
    "items",
    "additionalProperties",
    "contains",
    "propertyNames",
    "unevaluatedItems",
    "unevaluatedProperties",
    "contentSchema",
    *_IN_PLACE_SINGLES,
)
_SCHEMA_VISITS: Final = 100_000
# A JSON integer token is read as ``json.loads`` reads it while it is within the interpreter's int-to-text
# limit (sys.set_int_max_str_digits), or at any width when that limit is off (0). Past an enabled limit it is
# read in parts of 512 digits (the limit is at least sys.int_info.str_digits_check_threshold, 640 digits)
# up to _INT_DIGITS_MAX digits: that bound only widens what the limit admits, and the parts cost grows with
# the square of the width. A token past both the limit and _INT_DIGITS_MAX is refused, as json.loads would.
_INT_PART_DIGITS: Final = 512
_INT_DIGITS_MAX: Final = 65536

type _Document = dict[str, Any]
type _Parts = tuple[str | int, ...]
type _Bindings = tuple[tuple[str, str], ...]  # (anchor name, base URI of its outermost declaring resource)
type _Context = tuple[int, _Bindings]  # (id of the base resource's contents, dynamic bindings)
type _Edge = tuple[Mapping[str, Any], str]  # (schema object, "$ref" | "$dynamicRef")


def _problem(path: str, pointer: str, code: str, message: str) -> SchemaLoadProblem:
    return SchemaLoadProblem(path, SchemaIssue(pointer, "", code, message))


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate object key {key!r}")
        result[key] = value
    return result


def _constant(name: str) -> Any:
    raise ValueError(f"{name} is not a JSON number")


def _within_schema_budget(schema: object) -> bool:
    """Bound literal work too, including repeated objects and non-JSON cycles, without recursion."""
    remaining = _SCHEMA_VISITS
    pending: list[Iterator[object]] = [iter((schema,))]
    while pending:
        try:
            item = next(pending[-1])
        except StopIteration:
            pending.pop()
            continue
        remaining -= 1
        if remaining < 0:
            return False
        if isinstance(item, Mapping):
            pending.append(iter(cast("Mapping[str, object]", item).values()))
        elif isinstance(item, list):
            pending.append(iter(cast("list[object]", item)))
    return True


def _schema_projection(node: Mapping[str, Any]) -> tuple[dict[str, Any], list[object]]:
    """Shallow metaschema input and every child that must independently satisfy that metaschema.

    Preserve map keys, array lengths and malformed container/single shapes. Only schema contents become
    booleans; their full checks are queued. In particular, pattern keys and dependency string arrays still
    receive their ordinary format/uniqueness checks from the bundled validator.
    """
    local = dict(node)
    children: list[object] = []
    for keyword in _META_MAPS:
        child = node.get(keyword)
        if isinstance(child, Mapping):
            entries = cast("Mapping[str, object]", child)
            local[keyword] = dict.fromkeys(entries, True)
            children.extend(entries.values())
    for keyword in _META_LISTS:
        child = node.get(keyword)
        if isinstance(child, list):
            entries_list = cast("list[object]", child)
            local[keyword] = [True] * len(entries_list)
            children.extend(entries_list)
    for keyword in _META_SINGLES:
        child = node.get(keyword)
        if isinstance(child, Mapping) or type(child) is bool:
            local[keyword] = True
            children.append(cast("Mapping[str, Any] | bool", child))
    dependencies = node.get("dependencies")
    if isinstance(dependencies, Mapping):
        projected: dict[str, object] = {}
        for name, child in cast("Mapping[str, object]", dependencies).items():
            if isinstance(child, Mapping) or type(child) is bool:
                projected[name] = True
                children.append(cast("Mapping[str, Any] | bool", child))
            else:
                projected[name] = child
        local["dependencies"] = projected
    return local, children


def _integer(text: str) -> int:
    """A JSON integer token (``-?digits``, as the scanner matched it): within the interpreter's int-to-text
    limit (any width with the limit off) as ``int``, past it in parts up to ``_INT_DIGITS_MAX`` digits."""
    limit = sys.get_int_max_str_digits()
    digits = text.removeprefix("-")
    if limit == 0 or len(digits) <= limit:
        return int(text)
    if len(digits) > _INT_DIGITS_MAX:
        raise ValueError(
            f"an integer of {len(digits)} digits is wider than {_INT_DIGITS_MAX}"
            f" and than the interpreter's int-to-text limit of {limit}"
        )
    number = 0
    for start in range(0, len(digits), _INT_PART_DIGITS):
        part = digits[start : start + _INT_PART_DIGITS]
        number = number * 10 ** len(part) + int(part)
    return -number if len(digits) < len(text) else number


def _discover(root: Traversable) -> list[tuple[str, Traversable]]:
    """Every ``*.json`` below ``root`` except the document-data directories, with its relative path."""
    found: list[tuple[str, Traversable]] = []
    pending: list[tuple[tuple[str, ...], Traversable]] = [((), root)]
    while pending:
        parts, directory = pending.pop()
        for child in directory.iterdir():
            if child.is_dir():
                if child.name not in _SKIPPED_DIRECTORIES:
                    pending.append(((*parts, child.name), child))
            elif child.name.endswith(".json") and (parts or child.name != "schema-lock.json"):
                found.append(("/".join((*parts, child.name)), child))
    return sorted(found, key=lambda item: item[0])


def _parse(text: str) -> object:
    return json.loads(text, object_pairs_hook=_object, parse_int=_integer, parse_constant=_constant)


def _read_document(
    path: str, node: Traversable, problems: list[SchemaLoadProblem]
) -> tuple[str, _Document] | None:
    """The text of one schema file and its parsed document (``None``, with a problem, when unreadable)."""
    try:
        text = node.read_text(encoding="utf-8")
        document = _parse(text)
    except (OSError, ValueError) as exc:
        problems.append(_problem(path, "", "json", f"cannot read JSON: {exc}"))
        return None
    if not isinstance(document, dict):
        problems.append(_problem(path, "", "type", "a schema document must be a JSON object"))
        return None
    return text, cast("_Document", document)


@functools.lru_cache(maxsize=8192)
def _metaschema_violation(text: str) -> tuple[str, str, str] | None:
    """The first Draft 2020-12 metaschema violation of the document ``text`` as (pointer, code, message).

    The check is the most expensive step of a load and a pure function of the document, which is a pure
    function of its text; keying on the text lets every further registry built in the process (tests,
    tools, explicit validated loads) reuse the verdict for unchanged files.
    """
    try:
        # a message may quote a literal: wide integers are checked as text-safe copies (the same values)
        Draft202012Validator.check_schema(cast("_Document", text_safe(_parse(text))))
    except SchemaError as exc:
        code = cast("str | None", exc.validator)
        return json_pointer(exc.absolute_path), code or "schema", exc.message
    return None


def _admit(
    path: str, text: str, document: _Document, problems: list[SchemaLoadProblem], *, validate: bool = True
) -> str | None:
    """Check identity, dialect and the metaschema of one document; return its URN when it is sound."""
    before = len(problems)
    urn = document.get("$id")
    match = URN_PATTERN.fullmatch(urn) if isinstance(urn, str) else None
    if match is None:
        message = "$id must match urn:skm:<module>:<kind>(:<name>)*:v<major>"
        problems.append(_problem(path, "/$id", "$id", message))
    else:
        module = path.split("/")[0] if "/" in path else None
        if module is None:
            message = "a schema file must live in a module directory"
            problems.append(_problem(path, "/$id", "$id", message))
        elif match.group("module") != module:
            message = f"module {match.group('module')!r} of $id differs from directory {module!r}"
            problems.append(_problem(path, "/$id", "$id", message))
    if document.get("$schema") != DRAFT_2020_12:
        problems.append(_problem(path, "/$schema", "$schema", f"$schema must be {DRAFT_2020_12}"))
    violation = _metaschema_violation(text) if validate else None
    if violation is not None:
        problems.append(_problem(path, *violation))
    return cast("str", urn) if len(problems) == before else None


class _Node(NamedTuple):
    """One schema object of a registered document, with the resolver of its (``$id``-aware) scope."""

    urn: str
    parts: _Parts
    node: Mapping[str, Any]
    resolver: Any


def _target_defect(target: object, trusted: set[int], verdicts: dict[int, str | None]) -> str | None:
    """Why ``target`` cannot be applied as a schema (``None`` when it can)."""
    if isinstance(target, bool):
        return None
    if not isinstance(target, dict):
        return f"it points to a JSON {type(target).__name__}, not a schema"
    typed_target = cast("dict[str, Any]", target)
    key = id(typed_target)
    if key in trusted:
        return None
    if key not in verdicts:
        try:
            Draft202012Validator.check_schema(cast("_Document", text_safe(typed_target)))
            verdicts[key] = None
        except SchemaError as exc:
            verdicts[key] = f"it points to an invalid schema: {exc.message}"
    return verdicts[key]


def _check_keywords(nodes: list[_Node], paths: Mapping[str, str], problems: list[SchemaLoadProblem]) -> None:
    """Every ``$ref``/``$dynamicRef`` is local or ``urn:skm:`` and resolves to a schema; formats are known."""
    trusted = {id(item.node) for item in nodes}
    verdicts: dict[int, str | None] = {}
    for urn, parts, node, resolver in nodes:
        path = paths[urn]
        for keyword in _REF_KEYWORDS:
            ref = node.get(keyword)
            if ref is None:
                continue
            pointer = json_pointer((*parts, keyword))
            if not isinstance(ref, str) or not ref.startswith(("#", "urn:skm:")):
                message = f"reference {ref!r} must be local or urn:skm:, network/file refs are forbidden"
                problems.append(_problem(path, pointer, keyword, message))
                continue
            try:
                resolved = resolver.lookup(ref)
            except Unresolvable:
                problems.append(_problem(path, pointer, keyword, f"unresolved reference {ref!r}"))
                continue
            defect = _target_defect(resolved.contents, trusted, verdicts)
            if defect is not None:
                message = f"reference {ref!r} is not a schema: {defect}"
                problems.append(_problem(path, pointer, keyword, message))
        declared = node.get("format")
        if isinstance(declared, str) and declared not in KNOWN_FORMATS:
            message = f"unknown format {declared!r}; known: {', '.join(sorted(KNOWN_FORMATS))}"
            problems.append(_problem(path, json_pointer((*parts, "format")), "format", message))


def _in_place_children(node: Mapping[str, Any]) -> Iterator[Mapping[str, Any]]:
    """Subschemas that apply to the same instance as ``node`` (their cycles never consume input)."""
    for keyword in _IN_PLACE_SINGLES:
        child = node.get(keyword)
        if isinstance(child, dict):
            yield cast("_Document", child)
    for keyword in _IN_PLACE_LISTS:
        children = node.get(keyword)
        if isinstance(children, list):
            for child in cast("list[Any]", children):
                if isinstance(child, dict):
                    yield cast("_Document", child)
    dependent = node.get("dependentSchemas")
    if isinstance(dependent, dict):
        for child in cast("dict[str, Any]", dependent).values():
            if isinstance(child, dict):
                yield cast("_Document", child)


def _resource_base(urn: str, root: Mapping[str, Any], parts: _Parts) -> str:
    """Base URI of the resource that contains the schema object at ``parts`` (nested ``$id`` starts one)."""
    base = urn
    cursor: Any = root
    if isinstance(root.get("$id"), str):
        base = urljoin(base, root["$id"])
    for part in parts:
        cursor = cursor[part]  # pyright: ignore[reportUnknownVariableType]
        if isinstance(cursor, dict):
            typed_cursor = cast("dict[str, Any]", cursor)
            if isinstance(typed_cursor.get("$id"), str):
                base = urljoin(base, typed_cursor["$id"])
    return base


def _declared_anchors(nodes: list[_Node]) -> dict[str, frozenset[str]]:
    """Base URI of every resource -> names of the ``$dynamicAnchor`` it declares."""
    roots = {item.urn: item.node for item in nodes if not item.parts}
    found: dict[str, set[str]] = {}
    for item in nodes:
        name = item.node.get("$dynamicAnchor")
        if isinstance(name, str):
            found.setdefault(_resource_base(item.urn, roots[item.urn], item.parts), set()).add(name)
    return {uri: frozenset(names) for uri, names in found.items()}


class _CycleScan:
    """Finds ``$ref`` loops that never descend into the instance (validation would not terminate)."""

    def __init__(self, nodes: list[_Node]) -> None:
        self._nodes = nodes
        self._owner = {id(item.node): (item.urn, json_pointer(item.parts)) for item in nodes}
        # (id(node), base + dynamic bindings) -> finished; absent = unseen. A ``$dynamicRef`` lands on the
        # outermost ``$dynamicAnchor`` of the dynamic scope, so a finished walk is reused only in its context.
        self._state: dict[tuple[int, _Context], bool] = {}
        self._declared = _declared_anchors(nodes)
        self.found: list[tuple[str, str, str]] = []  # (urn, pointer of the closing reference, chain of refs)

    def run(self) -> None:
        for item in self._nodes:
            self._visit(item.node, item.resolver, [], None)

    def _context(self, resolver: Any) -> _Context:
        """What besides the node decides where its references go: the effective base resource and, per anchor
        name, the outermost resource of the dynamic scope that declares it (finite and ordered)."""
        if not self._declared:
            return (0, ())
        try:
            base = id(resolver.lookup("#").contents)  # a ``$dynamicRef`` can enter a node under another base
        except Unresolvable:
            base = 0
        outermost: dict[str, str] = {}
        for uri, _ in resolver.dynamic_scope():  # most recent first, so older scopes overwrite
            for name in self._declared.get(uri, ()):
                outermost[name] = uri
        return (base, tuple(sorted(outermost.items())))

    def _visit(self, node: Mapping[str, Any], resolver: Any, chain: list[str], origin: _Edge | None) -> None:
        """Walk ``node`` and what applies to the same instance; ``origin`` is the last reference followed."""
        resolver = scope(node, resolver)
        key = (id(node), self._context(resolver))
        state = self._state.get(key)
        if state is not None:
            if state is False and origin is not None:  # back to a node still being walked: no progress
                self._report(origin, chain)
            return
        self._state[key] = False
        for keyword in _REF_KEYWORDS:
            ref = node.get(keyword)
            if isinstance(ref, str):
                self._follow(node, keyword, ref, resolver, chain)
        for child in _in_place_children(node):
            self._visit(child, resolver, chain, origin)
        self._state[key] = True

    def _follow(
        self, node: Mapping[str, Any], keyword: str, ref: str, resolver: Any, chain: list[str]
    ) -> None:
        try:
            resolved = resolver.lookup(ref)
        except Unresolvable:
            return  # reported by the reference check
        target = resolved.contents
        if isinstance(target, dict):
            self._visit(cast("_Document", target), resolved.resolver, [*chain, ref], (node, keyword))

    def _report(self, origin: _Edge, chain: list[str]) -> None:
        owner = self._owner.get(id(origin[0]))
        if owner is None:
            return
        found = (owner[0], f"{owner[1]}/{origin[1]}", " -> ".join(chain))
        if found not in self.found:
            self.found.append(found)


class SchemaRegistry:
    """All packaged schemas by URN, with cached validators. Build it with ``load`` / ``load_default``."""

    def __init__(self, documents: Mapping[str, Mapping[str, JsonValue]], registry: Registry[Any]) -> None:
        self._documents = dict(documents)
        self._registry = registry
        self._validators: dict[str, SchemaValidator] = {}
        self._for_validation: tuple[dict[str, _Document], Registry[Any]] | None = None
        # Registry() disables remote retrieval; jsonschema supplies its bundled metaschema resources.
        self._schema_checker: Any = Draft202012Validator(
            Draft202012Validator.META_SCHEMA,
            registry=Registry(),
            format_checker=Draft202012Validator.FORMAT_CHECKER,
        )

    def _validation_set(self) -> tuple[dict[str, _Document], Registry[Any]]:
        """Dialect-free copies of the documents and a registry over them, built once for all validators."""
        if self._for_validation is None:
            copies = {urn: without_dialect(doc) for urn, doc in self._documents.items()}
            registry: Registry[Any] = Registry[Any]().with_resources(
                (urn, DRAFT202012.create_resource(doc)) for urn, doc in copies.items()
            )
            self._for_validation = (copies, registry)
        return self._for_validation

    @classmethod
    def load(cls, root: Traversable, *, validate: bool = True) -> "SchemaRegistry":
        """Load every ``*.v<N>.json`` below ``root`` (``data/`` directories hold documents, not schemas)."""
        problems: list[SchemaLoadProblem] = []
        candidates: dict[str, list[tuple[str, _Document]]] = {}
        for path, node in _discover(root):
            if _SCHEMA_FILE.fullmatch(node.name) is None:
                problems.append(
                    _problem(path, "", "file-name", "schema files are named <name>.v<major>.json")
                )
                continue
            read = _read_document(path, node, problems)
            if read is None:
                continue
            text, document = read
            urn = _admit(path, text, document, problems, validate=validate)
            if urn is not None:
                candidates.setdefault(urn, []).append((path, document))
        documents: dict[str, _Document] = {}
        paths: dict[str, str] = {}
        for urn, entries in candidates.items():
            if len(entries) == 1:
                paths[urn], documents[urn] = entries[0]
                continue
            files = ", ".join(path for path, _ in entries)
            message = f"duplicate $id {urn} in: {files}"
            problems.extend(_problem(path, "/$id", "duplicate-urn", message) for path, _ in entries)
        registry: Registry[Any] = Registry[Any]().with_resources(
            (urn, Resource.from_contents(document, default_specification=DRAFT202012))
            for urn, document in documents.items()
        )
        if validate:
            nodes = [
                _Node(urn, parts, node, resolver)
                for urn, document in documents.items()
                for parts, node, resolver in subschemas(document, (), registry.resolver(base_uri=urn))
            ]
            _check_keywords(nodes, paths, problems)
            scan = _CycleScan(nodes)
            scan.run()
            for urn, pointer, chain in scan.found:
                message = f"circular reference without progress: {chain}"
                problems.append(_problem(paths[urn], pointer, pointer.rsplit("/", 1)[-1], message))
        if problems:
            raise SchemaLoadError(problems)
        return cls(documents, registry)

    @classmethod
    def load_default(cls) -> "SchemaRegistry":
        return _load_default_registry()

    @property
    def registry(self) -> Registry[Any]:
        """The ``referencing`` registry that backs ``$ref`` resolution."""
        return self._registry

    def dialect_free_registry(self) -> Registry[Any]:
        """A registry over dialect-free, text-safe copies of every document, built once per instance.

        It is what ``SchemaValidator(..., dialect_free_inputs=True)`` expects; sharing it avoids copying the
        whole schema tree again for every consumer that compiles its own validators.
        """
        return self._validation_set()[1]

    def resolver_for(self, schema: Mapping[str, JsonValue]) -> Any:
        """A resolver over this registry rooted at a free-standing Draft 2020-12 ``schema`` (its ``#`` refs).

        Lookups stay offline: a reference outside ``schema`` and the registered URNs raises ``Unresolvable``.
        """
        return self._registry.resolver_with_root(DRAFT202012.create_resource(dict(schema)))

    def is_valid_schema(self, schema: Mapping[str, JsonValue]) -> bool:
        """Check Draft 2020-12 structure offline, without admitting a resource or resolving its refs.

        A missing dialect means Draft 2020-12; its empty-fragment alias is equivalent. Other root dialects
        are refused. Schema nodes are checked iteratively, with at most 100,000 literal visits per call.
        Oversized/cyclic inputs and library recursion failures return False. Text-safe integer copies keep
        exact comparisons without changing interpreter state.
        """
        if schema.get("$schema", DRAFT_2020_12) not in (DRAFT_2020_12, DRAFT_2020_12 + "#"):
            return False
        if not _within_schema_budget(schema):
            return False
        pending: list[object] = [schema]
        try:
            while pending:
                node = pending.pop()
                if type(node) is bool:
                    continue
                if not isinstance(node, Mapping):
                    return False
                local, children = _schema_projection(cast("Mapping[str, Any]", node))
                if not self._schema_checker.is_valid(text_safe(local)):
                    return False
                pending.extend(children)
        except RecursionError:
            # Literal keyword checks can recurse too, for example while compiling a nested regex.
            return False
        return True

    def get(self, urn: str) -> Mapping[str, JsonValue]:
        try:
            return MappingProxyType(self._documents[urn])
        except KeyError as exc:
            raise InternalError(
                ErrorCode.INTERNAL_ERROR, f"unknown schema URN {urn!r}", details={"urn": urn}
            ) from exc

    def urns(self) -> frozenset[str]:
        return frozenset(self._documents)

    def validator(self, urn: str) -> SchemaValidator:
        cached = self._validators.get(urn)
        if cached is None:
            self.get(urn)  # unknown URN -> InternalError
            copies, registry = self._validation_set()
            cached = SchemaValidator(copies[urn], registry, dialect_free_inputs=True)
            self._validators[urn] = cached
        return cached

    def validate(self, urn: str, instance: object) -> tuple[SchemaIssue, ...]:
        return self.validator(urn).issues(instance)

    def require_valid(self, urn: str, instance: object) -> None:
        issues = self.validate(urn, instance)
        if issues:
            reported = cast("list[JsonValue]", [issue.to_json() for issue in issues[:MAX_REPORTED_ISSUES]])
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                f"instance does not match {urn}: {len(issues)} issue(s)",
                details={"urn": urn, "issues": reported},
            )


@functools.cache
def _load_default_registry() -> SchemaRegistry:
    return SchemaRegistry.load(default_schema_root(), validate=False)
