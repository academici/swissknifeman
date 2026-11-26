"""Structure rules: identities, keys and key prefixes of the document (planning §5.7, module ``structure``).

They read the document, not only the typed model: ``from_document`` keeps the first of two entities with one
key, so a repeated key is only visible in the document.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from skm.modules.planning.domain.identity import identity_findings
from skm.modules.planning.domain.validation.findings import (
    FindingCode,
    doc_entity_id,
    finding,
    pointer_of,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from skm.kernel.json_types import JsonValue
    from skm.modules.planning.domain.validation.context import ValidationContext
    from skm.modules.planning.domain.validation.findings import Finding

_KEYED: Final = ("phases", "items", "units", "requirements", "criteria", "checks", "decisions", "materials")
_SECTIONED: Final = ("phases", "items", "units", "decisions")

type _Named = list[tuple[str, str]]  # (name, pointer of the member that carries it)


def _label(array: str, entity: Mapping[str, JsonValue]) -> str:
    key = str(entity.get("key", ""))
    if array == "checks":
        return f"{entity.get('owner', '')}:{key}"
    return f"material/{key}" if array == "materials" else key


def _objects(value: JsonValue | None) -> Iterator[tuple[int, Mapping[str, JsonValue]]]:
    """``(index, member)`` of the object members of a document array (other members keep their index)."""
    for index, member in enumerate(value if isinstance(value, list) else ()):
        if isinstance(member, dict):
            yield index, member


def duplicate_id(ctx: ValidationContext) -> Iterator[Finding]:
    for found in identity_findings(ctx.document):
        if found.code == FindingCode.DUPLICATE_ID:
            yield found


def entity_kind_changed(ctx: ValidationContext) -> Iterator[Finding]:
    for found in identity_findings(ctx.document, ctx.known_identities):
        if found.code == FindingCode.ENTITY_KIND_CHANGED:
            yield found


def _repeats(named: _Named, what: str, owner: str | None) -> Iterator[Finding]:
    """One finding per name used again; it points at the later use and records the earlier one."""
    first: dict[str, str] = {}
    for name, pointer in named:
        if name not in first:
            first[name] = pointer
            continue
        yield finding(
            FindingCode.DUPLICATE_KEY,
            f"{what} {name} is declared more than once",
            key=name if owner is None else owner,
            pointer=pointer,
            details={"scope": what, "key": name, "first_pointer": first[name]},
        )


def duplicate_key(ctx: ValidationContext) -> Iterator[Finding]:
    doc = ctx.document
    for array in _KEYED:
        named = [
            (_label(array, entity), pointer_of(array, i, "key")) for i, entity in _objects(doc.get(array))
        ]
        yield from _repeats(named, "key", None)
    for i, phase in _objects(doc.get("phases")):
        owner = _label("phases", phase)
        batches = [
            (f"{owner}/{batch.get('key')}", pointer_of("phases", i, "batches", n, "key"))
            for n, batch in _objects(phase.get("batches"))
        ]
        yield from _repeats(batches, "batch key", None)
    for i, decision in _objects(doc.get("decisions")):
        options = [
            (str(option.get("key")), pointer_of("decisions", i, "options", n, "key"))
            for n, option in _objects(decision.get("options"))
        ]
        yield from _repeats(options, "option key", _label("decisions", decision))
    brief = doc.get("brief")
    if isinstance(brief, dict):
        messages = [
            (str(message.get("key")), pointer_of("brief", "messages", n, "key"))
            for n, message in _objects(brief.get("messages"))
        ]
        yield from _repeats(messages, "brief message key", None)
    yield from _repeats(_section_ids(doc.get("sections"), ()), "section id", None)
    for array in _SECTIONED:
        for i, entity in _objects(doc.get(array)):
            sections = _section_ids(entity.get("sections"), (array, i))
            yield from _repeats(sections, "section id", _label(array, entity))


def _section_ids(sections: JsonValue | None, base: tuple[str | int, ...]) -> _Named:
    return [
        (str(section.get("id")), pointer_of(*base, "sections", n, "id")) for n, section in _objects(sections)
    ]


def key_prefix_mismatch(ctx: ValidationContext) -> Iterator[Finding]:
    doc = ctx.document
    item_keys = {str(item.get("key")) for _, item in _objects(doc.get("items"))}
    for index, item in _objects(doc.get("items")):
        key, phase = str(item.get("key")), str(item.get("phase"))
        if not key.startswith(f"{phase}."):
            yield finding(
                FindingCode.KEY_PREFIX_MISMATCH,
                f"item {key} does not start with its phase {phase}",
                key=key,
                entity_id=doc_entity_id(item),
                pointer=pointer_of("items", index, "phase"),
                details={"phase": phase, "expected_prefix": f"{phase}."},
            )
    for index, unit in _objects(doc.get("units")):
        key = str(unit.get("key"))
        owner = key.split("/", 1)[0] if "/" in key else None
        if owner is None or owner not in item_keys:
            yield finding(
                FindingCode.KEY_PREFIX_MISMATCH,
                f"unit {key} does not start with the key of an existing item",
                key=key,
                entity_id=doc_entity_id(unit),
                pointer=pointer_of("units", index, "key"),
                details={"item": owner},
            )


RULES: Final = (duplicate_id, duplicate_key, entity_kind_changed, key_prefix_mismatch)
