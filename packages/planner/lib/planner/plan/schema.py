"""Closed-profile JSON Schema validator for v4 plan documents (stdlib only).

The profile check and the validation are the shared core ``_jsonschema_core`` (vendored from
``aicore.util.jsonschema_core``, so planner still runs without aicore); this module adds the plan registry and the
extension slots.

A ``$ref`` to an id under ``EXTENSION_PREFIX`` names an extension slot: the engine declares the field, a bridge
supplies its schema (``extends`` of ``bridge.json``, see ``extensions``). A slot without a supplier is an
``extension`` issue, never a crash.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from ._jsonschema_core import (  # noqa: F401  (re-exported: the names the planner and its tests use)
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

SCHEMA_URN_PREFIX = "urn:swissknifeman:task:plan:"
KINDS = ("plan", "brief", "phase", "item", "unit", "decision", "log-event", "document", "snapshot", "envelope",
         "bridge", "check-evidence", "read-get", "read-list", "read-events", "read-artifact", "read-links",
         "read-neighborhood", "read-catalog", "read-commits", "read-ready", "read-followups", "read-plans",
         "scout-map", "context-pack", "review-receipt", "read-readiness")
EXTENSION_PREFIX = f"{SCHEMA_URN_PREFIX}extension:"
# Issue code of an extension slot without a usable supplier; engine-only, outside the shared closed profile.
EXTENSION_CODE = "extension"
_cache: dict[Path, "Registry"] = {}


class ExtensionUnavailable(RefError):
    """An extension slot that no bridge supplies (or whose supplied schema is unusable)."""

    issue_code = EXTENSION_CODE


class Registry:
    """Loaded schemas by ``$id``; read-only after construction."""

    def __init__(self, schemas: dict[str, dict]):
        self._schemas = schemas

    def for_kind(self, kind: str) -> tuple[dict, str]:
        schema_id = f"{SCHEMA_URN_PREFIX}{kind}:v1"
        if kind not in KINDS or schema_id not in self._schemas:
            raise SchemaProfileError(f"unknown schema kind: {kind!r}")
        return self._schemas[schema_id], schema_id

    def resolve(self, ref: str, base_id: str) -> tuple[dict, str]:
        """Resolve ``#/$defs/x`` or ``<id>#/$defs/x``; return the node and the id of its owning schema."""
        document, _, fragment = ref.partition("#")
        owner = document or base_id
        node: Any = self._schemas.get(owner)
        if node is None and owner.startswith(EXTENSION_PREFIX):
            from . import extensions  # late: extensions reads bridge manifests, which are validated here
            node = extensions.schema_for(owner)
        if node is None:
            raise RefError(f"unknown schema {owner!r} in $ref {ref!r}")
        if fragment:
            if not fragment.startswith("/$defs/") or fragment.count("/") != 2:
                raise RefError(f"unsupported $ref fragment in {ref!r}")
            node = node.get("$defs", {}).get(fragment[len("/$defs/"):])
            if not isinstance(node, dict):
                raise RefError(f"$ref {ref!r} does not resolve")
        return node, owner


def default_schema_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "schemas" / "plan" / "v1"


def load_registry(schema_dir: Path | None = None) -> Registry:
    """Load and profile-check ``*.schema.json`` files; cached per directory path."""
    directory = Path(schema_dir) if schema_dir is not None else default_schema_dir()
    key = directory.resolve()
    cached = _cache.get(key)
    if cached is not None:
        return cached
    schemas: dict[str, dict] = {}
    for path in sorted(key.glob("*.schema.json")):
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
        raise SchemaProfileError(f"no *.schema.json files in {key}")
    registry = Registry(schemas)
    _cache[key] = registry
    return registry


def clear_registry_cache() -> None:
    _cache.clear()
    from . import extensions
    extensions.clear_cache()


class _OpenSlots:
    """A registry in which an extension slot whose supplier is unavailable accepts any value; a supplied slot keeps its
    schema. Validation then decides every ``oneOf`` on the other fields, wherever the slot sits."""

    def __init__(self, registry: Registry):
        self._registry = registry

    def for_kind(self, kind: str) -> tuple[dict, str]:
        return self._registry.for_kind(kind)

    def resolve(self, ref: str, base_id: str) -> tuple[dict, str]:
        try:
            return self._registry.resolve(ref, base_id)
        except ExtensionUnavailable:
            return {}, ref.partition("#")[0] or base_id


def validate_open_slots(doc: object, kind: str, registry: Registry | None = None) -> list[ValidationIssue]:
    """``validate``, except that an extension slot without a usable supplier is not an issue: for a document the planner
    writes from plan data that ``check`` already reports the slot of (``EXTENSION_UNAVAILABLE``)."""
    return validate(doc, kind, _OpenSlots(registry if registry is not None else load_registry()))


def validate(doc: object, kind: str, registry: Registry | None = None) -> list[ValidationIssue]:
    """Validate ``doc`` against the schema of ``kind``; return every issue found."""
    reg = registry if registry is not None else load_registry()
    schema, schema_id = reg.for_kind(kind)
    issues: list[ValidationIssue] = []
    _check(reg, schema, schema_id, doc, "", issues)
    return issues
