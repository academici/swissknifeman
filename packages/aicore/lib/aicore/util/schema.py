"""Closed-profile JSON Schema validator (stdlib only).

The one validator of the shared contracts. It supports exactly the keywords in ``SUPPORTED_KEYWORDS`` and the
annotations in ``ANNOTATIONS`` (accepted, never evaluated); any other keyword in a schema file fails closed
with ``SchemaProfileError`` at load time. Validation collects every issue instead of stopping at the first
one. ``load_contract`` loads one contract directory ``<contract>/v<N>/`` of the foundation schemas.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Iterator

from .jsonschema_core import (  # noqa: F401  (re-exported: the names other modules and tests use)
    ANNOTATIONS,
    DIALECT,
    ERROR_CODES,
    SUPPORTED_KEYWORDS,
    RefError,
    SchemaProfileError,
    ValidationIssue,
    _anchor_end,
    _check,
    _check_profile,
    _compile,
    _equal,
    validate_node,
)

CONTRACT_URN_PREFIX = "urn:swissknifeman:aicore:"
_VERSION_DIR = re.compile(r"v[1-9][0-9]*")
_cache: dict[tuple[Path, str, tuple[str, ...], str, tuple[Path, ...]], "Registry"] = {}
_CONTRACT_REF = re.compile(r"([a-z][a-z0-9-]*):(v[1-9][0-9]*)")
_SET_ID = re.compile(r"(.+:)([a-z][a-z0-9-]*):(v[1-9][0-9]*)")
_MODULE_REF = re.compile(r"([a-z][a-z0-9-]*):(?:[a-z][a-z0-9-]*:)?(v[1-9][0-9]*)")  # <contract>[:<kind>]:v<N>
_FOUNDATION_SCHEMAS = Path(__file__).resolve().parents[3] / "schemas"


class Registry:
    """Loaded schemas by ``$id``; read-only after construction."""

    def __init__(self, schemas: dict[str, dict], *, urn_prefix: str, kinds: tuple[str, ...], version: str = "v1"):
        self._schemas = schemas
        self.urn_prefix = urn_prefix
        self.kinds = tuple(kinds)
        self.version = version

    def for_kind(self, kind: str) -> tuple[dict, str]:
        schema_id = f"{self.urn_prefix}{kind}:{self.version}"
        if kind not in self.kinds or schema_id not in self._schemas:
            raise SchemaProfileError(f"unknown schema kind: {kind!r}")
        return self._schemas[schema_id], schema_id

    def resolve(self, ref: str, base_id: str) -> tuple[dict, str]:
        """Resolve ``#/$defs/x`` or ``<id>#/$defs/x``; return the node and the id of its owning schema."""
        document, _, fragment = ref.partition("#")
        owner = document or base_id
        node: Any = self._schemas.get(owner)
        if node is None:
            raise RefError(f"unknown schema {owner!r} in $ref {ref!r}")
        if fragment:
            if not fragment.startswith("/$defs/") or fragment.count("/") != 2:
                raise RefError(f"unsupported $ref fragment in {ref!r}")
            node = node.get("$defs", {}).get(fragment[len("/$defs/"):])
            if not isinstance(node, dict):
                raise RefError(f"$ref {ref!r} does not resolve")
        return node, owner


def load_registry(schema_dir: Path, *, urn_prefix: str, kinds: tuple[str, ...], version: str = "v1",
                  extra_dirs: tuple[Path, ...] = ()) -> Registry:
    """Load and profile-check schemas; cache by directory and registry parameters.

    ``version`` is the suffix of the ``$id`` of every kind (``<urn_prefix><kind>:<version>``). The schemas of
    ``extra_dirs`` join the registry for ``$ref`` resolution only; ``kinds`` names the schemas to validate.
    """
    directory = Path(schema_dir).resolve()
    extras = tuple(Path(extra).resolve() for extra in extra_dirs)
    key = (directory, urn_prefix, tuple(kinds), version, extras)
    cached = _cache.get(key)
    if cached is not None:
        return cached
    schemas = _read_schemas(directory)
    for extra in extras:
        for schema_id, schema in _read_schemas(extra).items():
            if schema_id in schemas:
                raise SchemaProfileError(f"{extra}: duplicate $id {schema_id!r}")
            schemas[schema_id] = schema
    registry = Registry(schemas, urn_prefix=urn_prefix, kinds=tuple(kinds), version=version)
    _cache[key] = registry
    return registry


def _read_schemas(directory: Path) -> dict[str, dict]:
    schemas: dict[str, dict] = {}
    for path in sorted(directory.glob("*.schema.json")):
        try:
            schema = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise SchemaProfileError(f"{path.name}: cannot load schema: {exc}") from exc
        _check_profile(schema, path.name, "", root=True)
        schema_id = schema.get("$id")
        if not isinstance(schema_id, str) or not schema_id:
            raise SchemaProfileError(f"{path.name}: missing $id")
        if schema_id in schemas:
            raise SchemaProfileError(f"{path.name}: duplicate $id {schema_id!r}")
        schemas[schema_id] = schema
    if not schemas:
        raise SchemaProfileError(f"no *.schema.json files in {directory}")
    return schemas


def load_schema_file(path: Path, *, urn_prefix: str, kind: str, version: str = "v1") -> Registry:
    """Load and profile-check one schema file whose ``$id`` must be ``<urn_prefix><kind>:<version>``.

    For schemas that live outside the foundation contracts (a module's config schema). Not cached.
    """
    path = Path(path)
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SchemaProfileError(f"{path.name}: cannot load schema: {exc}") from exc
    _check_profile(schema, path.name, "", root=True)
    schema_id = f"{urn_prefix}{kind}:{version}"
    if schema.get("$id") != schema_id:
        raise SchemaProfileError(f"{path.name}: $id must be {schema_id!r}, got {schema.get('$id')!r}")
    return Registry({schema_id: schema}, urn_prefix=urn_prefix, kinds=(kind,), version=version)


def load_contract(contract_dir: Path, *, urn_prefix: str = CONTRACT_URN_PREFIX,
                  foundation: Path | None = None) -> tuple[Registry, str]:
    """Load one contract directory ``<contract>/v<N>/``; return its registry and its kind.

    The kind is the stem of the single ``<kind>.schema.json`` file and must equal the contract name; the
    ``$id`` must be ``<urn_prefix><kind>:v<N>`` for the version ``v<N>`` named by the directory. ``foundation``
    is the directory of the foundation contracts that a reference may reach when they are not beside this one
    (default: the schemas of aicore itself).
    """
    directory = Path(contract_dir).resolve()
    version, kind = directory.name, directory.parent.name
    if not _VERSION_DIR.fullmatch(version):
        raise SchemaProfileError(f"{directory}: directory name must be v<N>, got {version!r}")
    files = sorted(directory.glob("*.schema.json"))
    if [path.name for path in files] != [f"{kind}.schema.json"]:
        raise SchemaProfileError(f"{directory}: expected exactly {kind}.schema.json, found "
                                 f"{[path.name for path in files]}")
    extras = _referenced_contract_dirs(directory, urn_prefix, foundation)
    registry = load_registry(directory, urn_prefix=urn_prefix, kinds=(kind,), version=version, extra_dirs=extras)
    registry.for_kind(kind)  # raises when the $id does not match the directory
    return registry, kind


def load_contract_set(contract_dir: Path, *, foundation: Path | None = None,
                      open_slots: bool = False) -> tuple[Registry, list[str]]:
    """Load a contract directory ``<contract>/v<N>/`` that holds several ``<kind>.schema.json`` documents.

    The kind of a document is the last segment of its ``$id``; every ``$id`` must be ``<prefix><kind>:v<N>`` for
    one ``<prefix>`` shared by the directory and for the version ``v<N>`` named by the directory. The file name is
    not read (it may spell the kind with dots). References to the foundation contracts resolve as in
    ``load_contract`` (including ``foundation``). Return the registry and the sorted kinds.

    ``open_slots`` lets a set leave extension slots open: a reference to ``<prefix>extension:<slot>:v<N>`` that no
    document of the set holds (the module that fills the slot supplies it at run time, as a bridge does for
    ``plan/v1`` -> ``orchestration.options``) resolves to a placeholder object schema; any other reference must
    still resolve. The registry is then not cached.
    """
    directory = Path(contract_dir).resolve()
    version = directory.name
    if not _VERSION_DIR.fullmatch(version):
        raise SchemaProfileError(f"{directory}: directory name must be v<N>, got {version!r}")
    schemas = _read_schemas(directory)
    prefix: str | None = None
    kinds: list[str] = []
    for schema_id in schemas:
        match = _SET_ID.fullmatch(schema_id)
        if match is None or match.group(3) != version:
            raise SchemaProfileError(f"{directory}: $id {schema_id!r} must be <prefix><kind>:{version}")
        if prefix is not None and match.group(1) != prefix:
            raise SchemaProfileError(f"{directory}: $id {schema_id!r} does not share the prefix {prefix!r}")
        prefix = match.group(1)
        kinds.append(match.group(2))
    kinds.sort()
    module = prefix.rstrip(":").rpartition(":")[0] + ":" if prefix else None  # urn:<ns>:<module>: of <module>:<set>:
    registry = load_registry(directory, urn_prefix=prefix or "", kinds=tuple(kinds), version=version,
                             extra_dirs=_referenced_contract_dirs(directory, CONTRACT_URN_PREFIX, foundation,
                                                                  module_prefix=module))
    if open_slots:
        slots = sorted({ref.partition("#")[0] for document in schemas.values() for ref in _refs(document)
                        if ref.startswith(f"{prefix}extension:") and ref.partition("#")[0] not in registry._schemas})
        if slots:
            registry = Registry({**registry._schemas, **{slot: {"$id": slot, "type": "object"} for slot in slots}},
                                urn_prefix=registry.urn_prefix, kinds=registry.kinds, version=registry.version)
    for schema_id, document in schemas.items():
        for ref in _refs(document):
            try:
                registry.resolve(ref, schema_id)
            except RefError as exc:
                raise SchemaProfileError(f"{directory.parent.name}/{version}: unresolved reference {ref!r}: {exc}") from None
    return registry, kinds


def _referenced_contract_dirs(directory: Path, urn_prefix: str,
                              foundation: Path | None = None, *,
                              module_prefix: str | None = None) -> tuple[Path, ...]:
    """Sibling contract directories that ``$ref`` values reach from ``directory``, transitively.

    A ``$ref`` to ``<urn_prefix><contract>:v<N>`` (with or without a fragment) names the directory
    ``<schemas>/<contract>/v<N>`` next to the one being loaded; for the foundation prefix a directory missing
    there is looked up in ``foundation`` (default: the schemas of aicore itself). A module contract (a prefix
    other than the foundation one) may also reference the foundation contracts: those references are looked up
    in ``foundation`` only. ``module_prefix`` (``urn:swissknifeman:<module>:`` of a set of kinds) lets a set refer
    to a sibling set of the same module, ``<module_prefix><contract>:<kind>:v<N>`` -> ``<schemas>/<contract>/v<N>``;
    a sibling folder that is not there is left to the reference check.
    """
    schemas_root = directory.parent.parent
    foundation_root = foundation or _FOUNDATION_SCHEMAS
    found: list[Path] = []
    pending = [directory]
    seen = {directory}
    while pending:
        current = pending.pop(0)
        current_schemas = _read_schemas(current)
        own_ids = set(current_schemas)
        for schema in current_schemas.values():
            for ref in _refs(schema):
                document = ref.partition("#")[0]
                if document in own_ids:
                    continue
                if document.startswith(urn_prefix):
                    match = _CONTRACT_REF.fullmatch(document[len(urn_prefix):])
                    target = schemas_root / match.group(1) / match.group(2) if match else None
                    if match and urn_prefix == CONTRACT_URN_PREFIX and not _has_schemas(target):
                        target = foundation_root / match.group(1) / match.group(2)
                elif module_prefix and document.startswith(module_prefix):
                    match = _MODULE_REF.fullmatch(document[len(module_prefix):])
                    target = schemas_root / match.group(1) / match.group(2) if match else None
                    if target is None or not _has_schemas(target):
                        continue
                elif document.startswith(CONTRACT_URN_PREFIX):
                    match = _CONTRACT_REF.fullmatch(document[len(CONTRACT_URN_PREFIX):])
                    target = foundation_root / match.group(1) / match.group(2) if match else None
                else:
                    continue
                if target is None or not _has_schemas(target):
                    raise SchemaProfileError(f"{current.parent.name}/{current.name}: unresolved contract "
                                             f"reference {ref!r}")
                target = target.resolve()
                if target not in seen:
                    seen.add(target)
                    found.append(target)
                    pending.append(target)
    return tuple(found)


def _has_schemas(directory: Path | None) -> bool:
    return directory is not None and directory.is_dir() and any(directory.glob("*.schema.json"))


def _refs(node: Any) -> Iterator[str]:
    """Every ``$ref`` string in the schema nodes below ``node`` (keyword values that hold schemas only)."""
    if not isinstance(node, dict):
        return
    if isinstance(node.get("$ref"), str):
        yield node["$ref"]
    for keyword in ("properties", "$defs", "patternProperties"):
        for child in (node.get(keyword) or {}).values():
            yield from _refs(child)
    for keyword in ("items", "propertyNames", "not"):
        yield from _refs(node.get(keyword))
    for child in node.get("oneOf") or ():
        yield from _refs(child)




def clear_registry_cache() -> None:
    _cache.clear()

def validate(doc: object, kind: str, registry: Registry) -> list[ValidationIssue]:
    """Validate ``doc`` against the schema of ``kind``; return every issue found."""
    reg = registry
    schema, schema_id = reg.for_kind(kind)
    issues: list[ValidationIssue] = []
    _check(reg, schema, schema_id, doc, "", issues)
    return issues
