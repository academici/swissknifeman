"""Reference rules: self references, unknown targets, artifacts, plan relations (§5.7, ``references``).

References are resolved by kind from ``REFERENCE_FIELDS`` (§5.3 item 6); a string is never taken for a
reference because it looks like a key. Existence is judged on the document, so a target that ``from_document``
dropped as a repeated key still exists here (the repetition is ``duplicate_key``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from skm.modules.planning.domain.references import REFERENCE_FIELDS, RefKind
from skm.modules.planning.domain.validation.context import Locator
from skm.modules.planning.domain.validation.findings import (
    FindingCode,
    doc_entity_id,
    finding,
    pointer_of,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Mapping

    from skm.kernel.ids import EntityId
    from skm.kernel.json_types import JsonValue
    from skm.modules.planning.domain.references import ReferenceField
    from skm.modules.planning.domain.specification import Specification
    from skm.modules.planning.domain.validation.context import ValidationContext
    from skm.modules.planning.domain.validation.findings import Finding

_ENTITY_PREFIX: Final = "entity:"
type _Own = tuple[str, EntityId, tuple[str | int, ...]]


def artifact_duplicate(ctx: ValidationContext) -> Iterator[Finding]:
    loc = Locator(ctx.document)
    first: dict[str, str] = {}
    for item in ctx.spec.items:
        for index, artifact in enumerate(item.artifacts):
            if artifact.role != "output" or artifact.key is None:
                continue
            pointer = loc.pointer(item.key, "artifacts", index, "key")
            if artifact.key not in first:
                first[artifact.key] = f"{item.key}#{index}"
                continue
            yield finding(
                FindingCode.ARTIFACT_DUPLICATE,
                f"output artifact {artifact.key} is declared more than once",
                key=item.key,
                entity_id=item.id,
                pointer=pointer,
                details={"artifact": artifact.key, "first": first[artifact.key]},
            )


def artifact_path_mismatch(ctx: ValidationContext) -> Iterator[Finding]:
    loc = Locator(ctx.document)
    outputs: dict[str, tuple[str, str]] = {}
    for item in ctx.spec.items:
        for artifact in item.artifacts:
            if artifact.role == "output" and artifact.key is not None:
                outputs.setdefault(artifact.key, (artifact.mount, artifact.path))
    for item in ctx.spec.items:
        for index, artifact in enumerate(item.artifacts):
            declared = None if artifact.key is None else outputs.get(artifact.key)
            if artifact.role != "input" or declared is None or declared == (artifact.mount, artifact.path):
                continue
            yield finding(
                FindingCode.ARTIFACT_PATH_MISMATCH,
                f"input artifact {artifact.key} names {artifact.mount}:{artifact.path}, "
                f"its output is {declared[0]}:{declared[1]}",
                key=item.key,
                entity_id=item.id,
                pointer=loc.pointer(item.key, "artifacts", index, "path"),
                details={"artifact": artifact.key or "", "output": f"{declared[0]}:{declared[1]}"},
            )


def plan_relation_unresolved(ctx: ValidationContext) -> Iterator[Finding]:
    for index, relation in enumerate(ctx.spec.plan_relations):
        if relation.target not in ctx.project_plans:
            yield finding(
                FindingCode.PLAN_RELATION_UNRESOLVED,
                f"plan relation target {relation.target} is not a plan of this project",
                pointer=pointer_of("plan_relations", index, "target"),
                details={"target": relation.target, "kind": relation.kind.value},
            )


class _Known:
    """Display keys and ids of the entities a reference may name, taken from the document."""

    def __init__(self, document: Mapping[str, JsonValue]) -> None:
        self.keys: dict[str, set[str]] = {}
        self.ids: set[str] = set()
        for array in (
            "phases",
            "items",
            "units",
            "requirements",
            "criteria",
            "decisions",
            "checks",
            "materials",
        ):
            keys = self.keys.setdefault(array, set())
            entities = document.get(array)
            for entity in entities if isinstance(entities, list) else ():
                if not isinstance(entity, dict):
                    continue
                key = str(entity.get("key", ""))
                keys.add(f"{entity.get('owner', '')}:{key}" if array == "checks" else key)
                if array == "materials":
                    keys.add(f"material/{key}")
                if isinstance(entity.get("id"), str):
                    self.ids.add(f"{_ENTITY_PREFIX}{entity['id']}")

    def has(self, field: ReferenceField, value: str, context: str | None) -> bool:
        if value.startswith(_ENTITY_PREFIX):
            return field.ref in _ID_REFS and value in self.ids
        arrays = _KIND_ARRAYS.get(field.ref)
        if arrays is not None:
            return any(value in self.keys[array] for array in arrays)
        if field.ref is RefKind.UNIT_REF:
            return _completed(value, "/", context) in self.keys["units"]
        if field.ref is RefKind.MATERIAL:
            return value.partition("#")[0] in self.keys["materials"]
        return _completed(value, ":", context) in self.keys["checks"]  # CHECK_REF, CHECK_LOCAL


def _completed(value: str, separator: str, context: str | None) -> str:
    """A local reference (``U1``, ``V1``) completed by the item it is written in; a full one stays."""
    return value if separator in value or context is None else f"{context}{separator}{value}"


_ENTITY_ARRAYS: Final = ("phases", "items", "units", "decisions", "requirements", "criteria")
_ID_REFS: Final = frozenset({RefKind.ENTITY, RefKind.WORK})
_KIND_ARRAYS: Final = {
    RefKind.PHASE: ("phases",),
    RefKind.ITEM: ("items",),
    RefKind.WORK: ("phases", "items", "units"),
    RefKind.ENTITY: _ENTITY_ARRAYS,
    RefKind.REQUIREMENT: ("requirements",),
    RefKind.DECISION: ("decisions",),
}


def _context_item(array: str, entity: Mapping[str, JsonValue]) -> str | None:
    """The item a local reference of ``entity`` is written in (``references._context_item``)."""
    if array == "units":
        return str(entity.get("key", "")).split("/", 1)[0]
    if array == "criteria":
        return str(entity.get("owner", "")).split("/", 1)[0]
    return None


def _leaves(
    node: JsonValue, segments: tuple[str, ...], pointer: tuple[str | int, ...]
) -> Iterator[tuple[tuple[str | int, ...], Mapping[str, JsonValue], str]]:
    """``(pointer, holder, text)`` of the reference leaves under ``node`` along ``segments``."""
    if not isinstance(node, dict):
        return
    name = segments[0].removesuffix("[]")
    child = node.get(name)
    if child is None:
        return
    last = len(segments) == 1
    if segments[0].endswith("[]"):
        for index, element in enumerate(child if isinstance(child, list) else ()):
            if last:
                if isinstance(element, str):
                    yield (*pointer, name, index), node, element
            else:
                yield from _leaves(element, segments[1:], (*pointer, name, index))
    elif last:
        if isinstance(child, str):
            yield (*pointer, name), node, child
    else:
        yield from _leaves(child, segments[1:], (*pointer, name))


_ARTIFACT_PREFIX: Final = "artifact/"
_READ_CONTAINERS: Final = (
    ("phases", "supporting"),
    ("items", "reads"),
    ("items", "examples"),
    ("units", "reads"),
)


def _output_artifacts(document: Mapping[str, JsonValue]) -> set[str]:
    """Keys of the output artifacts the document declares; an input names one, it does not declare it."""
    items = document.get("items")
    declared: set[str] = set()
    for item in items if isinstance(items, list) else ():
        artifacts = item.get("artifacts") if isinstance(item, dict) else None
        for artifact in artifacts if isinstance(artifacts, list) else ():
            if isinstance(artifact, dict) and artifact.get("role") == "output":
                key = artifact.get("key")
                if isinstance(key, str):
                    declared.add(key)
    return declared


def _unknown_artifact_reads(ctx: ValidationContext) -> Iterator[Finding]:
    """Reads of ``kind: artifact`` whose ``artifact/<key>`` no output artifact of the document declares."""
    doc = ctx.document
    declared = _output_artifacts(doc)
    for array, member in _READ_CONTAINERS:
        entities = doc.get(array)
        for index, entity in enumerate(entities if isinstance(entities, list) else ()):
            if not isinstance(entity, dict):
                continue
            reads = entity.get(member)
            for n, read in enumerate(reads if isinstance(reads, list) else ()):
                ref = read.get("ref") if isinstance(read, dict) else None
                if not isinstance(read, dict) or read.get("kind") != "artifact" or not isinstance(ref, str):
                    continue
                if ref.startswith(_ARTIFACT_PREFIX) and ref[len(_ARTIFACT_PREFIX) :] in declared:
                    continue
                owner = _owner_key(array, entity)
                yield finding(
                    FindingCode.REF_UNKNOWN,
                    f"{owner} refers to {ref}, which is not declared",
                    key=owner,
                    entity_id=doc_entity_id(entity),
                    pointer=pointer_of(array, index, member, n, "ref"),
                    details={"ref": ref, "kind": "artifact"},
                )


def ref_unknown(ctx: ValidationContext) -> Iterator[Finding]:
    yield from _unknown_artifact_reads(ctx)
    doc = ctx.document
    known = _Known(doc)
    for field in REFERENCE_FIELDS:
        entities = doc.get(field.array)
        for index, entity in enumerate(entities if isinstance(entities, list) else ()):
            if not isinstance(entity, dict):
                continue
            context = _context_item(field.array, entity)
            for pointer, holder, value in _leaves(entity, field.path, (field.array, index)):
                if field.when is not None and holder.get(field.when[0]) != field.when[1]:
                    continue
                if known.has(field, value, context):
                    continue
                owner = _owner_key(field.array, entity)
                yield finding(
                    FindingCode.REF_UNKNOWN,
                    f"{owner} refers to {value}, which is not declared",
                    key=owner,
                    entity_id=doc_entity_id(entity),
                    pointer=pointer_of(*pointer),
                    details={"ref": value, "kind": field.ref.value},
                )


def _owner_key(array: str, entity: Mapping[str, JsonValue]) -> str:
    key = str(entity.get("key", ""))
    if array == "checks":
        return f"{entity.get('owner', '')}:{key}"
    return f"material/{key}" if array == "materials" else key


def _own(key: str, entity_id: EntityId, field: str, targets: Iterable[str]) -> Iterator[_Own]:
    for n, target in enumerate(targets):
        if target == key:
            yield key, entity_id, (field, n)


def _self_links(spec: Specification) -> Iterator[_Own]:
    """``(key, id, tail of the pointer)`` of every place an entity names itself."""
    for phase in spec.phases:
        yield from _own(phase.key, phase.id, "depends_on", phase.depends_on or ())
    for item in spec.items:
        yield from _own(item.key, item.id, "depends_on", item.depends_on)
        for n, relation in enumerate(item.relations):
            if relation.target in (item.key, f"{_ENTITY_PREFIX}{item.id}"):
                yield item.key, item.id, ("relations", n, "target")
    for unit in spec.units:
        owner = unit.key.split("/", 1)[0]
        yield from _own(unit.key, unit.id, "depends_on", (_completed(d, "/", owner) for d in unit.depends_on))
        if unit.parent is not None and _completed(unit.parent, "/", owner) == unit.key:
            yield unit.key, unit.id, ("parent",)
    for decision in spec.decisions:
        yield from _own(decision.key, decision.id, "supersedes", decision.supersedes)


def self_reference(ctx: ValidationContext) -> Iterator[Finding]:
    loc = Locator(ctx.document)
    for key, entity_id, tail in _self_links(ctx.spec):
        yield finding(
            FindingCode.SELF_REFERENCE,
            f"{key} refers to itself",
            key=key,
            entity_id=entity_id,
            pointer=loc.pointer(key, *tail),
            details={"field": str(tail[0])},
        )


RULES: Final = (
    artifact_duplicate,
    artifact_path_mismatch,
    plan_relation_unresolved,
    ref_unknown,
    self_reference,
)
