"""``replace_text``: exact, digest-guarded edits of narrative fields (planning §5.3 item 7).

Only the fields of ``TEXT_EDIT_FIELDS`` can be edited this way. References, ids and keys, enums, dates, route,
paths, scripts, authority and extensions stay structural edits. Text is compared and replaced byte for byte:
no Unicode normalisation, no line-ending change, no fuzzy matching.
"""

from __future__ import annotations

import hashlib
import re
from typing import TYPE_CHECKING, Final

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, ValidationFailed
from skm.modules.planning.domain.identity import ENTITY_ARRAYS
from skm.modules.planning.domain.references import resolve_ref
from skm.modules.planning.domain.specification import EntityKind

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from skm.kernel.json_types import JsonObject, JsonValue
    from skm.modules.planning.domain.changes import ReplaceTextChange

_SECTIONS: Final = ("sections[].title", "sections[].text")
_BRIEF: Final = (
    "messages[].text",
    "{constraints,environment,out_of_scope}[]",
)

# Owner -> narrative fields. ``[]`` is one concrete array index, ``{a,b}`` a choice of property.
TEXT_EDIT_FIELDS: Final[Mapping[str, Sequence[str]]] = {
    "plan": (
        "title",
        "goal",
        "context_md",
        "non_goals[]",
        "rules[]",
        *(f"brief.{field}" for field in _BRIEF),
        "plan_relations[].note",
        *_SECTIONS,
    ),
    "brief": _BRIEF,
    EntityKind.PHASE.value: (
        "title",
        "goal",
        "context_md",
        "contract.{consumes,produces,boundaries}[]",
        "pitfalls[]",
        "deliverables[]",
        "assurance.{impact,note}",
        "assurance.seams[]",
        "batches[].note",
        "supporting[].why",
        *_SECTIONS,
    ),
    EntityKind.ITEM.value: (
        "title",
        "summary",
        "why",
        "rules[]",
        "guidance_md",
        "deliverables[]",
        "relations[].note",
        "reads[].why",
        "examples[].why",
        "change_hints[].note",
        "artifacts[].note",
        "research.{question,notes}",
        "review.reason",
        "review.reviewer.note",
        *_SECTIONS,
    ),
    EntityKind.UNIT.value: (
        "title",
        "goal",
        "instructions_md",
        "reads[].why",
        "outputs[].note",
        "command.definition.expect",
        *_SECTIONS,
    ),
    EntityKind.REQUIREMENT.value: ("statement",),
    EntityKind.CRITERION.value: ("statement",),
    EntityKind.CHECK.value: ("definition.instructions_md", "definition.expect"),
    EntityKind.DECISION.value: (
        "title",
        "question",
        "context_md",
        "decision",
        "rationale",
        "options[].text",
        "consequences[]",
        "evidence[].note",
        *_SECTIONS,
    ),
    EntityKind.MATERIAL.value: ("title", "why"),
}

_ENTITY_ARRAY_NAMES: Final = frozenset(field for field, _ in ENTITY_ARRAYS)
_OWNED_BY_KIND: Final = {EntityKind.ITEM.value: "phase", EntityKind.CHECK.value: "owner"}


def _compile(pattern: str) -> re.Pattern[str]:
    """``a.b[].{c,d}`` -> a regular expression over the RFC 6901 pointer ``/a/b/<n>/c``."""
    parts: list[str] = []
    for segment in pattern.split("."):
        index = "/[0-9]+" if segment.endswith("[]") else ""
        name = segment.removesuffix("[]")
        if name.startswith("{"):
            name = "(?:" + "|".join(re.escape(choice) for choice in name[1:-1].split(",")) + ")"
        else:
            name = re.escape(name)
        parts.append(f"/{name}{index}")
    return re.compile("".join(parts))


_COMPILED: Final = {
    owner: tuple(_compile(p) for p in patterns) for owner, patterns in TEXT_EDIT_FIELDS.items()
}


def text_digest(value: str) -> str:
    """``sha256:`` + hex digest of the UTF-8 bytes of ``value``."""
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def is_text_field(owner: str, pointer: str) -> bool:
    """Whether ``pointer`` (relative to ``owner``: ``plan``, ``brief`` or an entity kind) is narrative."""
    return any(pattern.fullmatch(pointer) for pattern in _COMPILED.get(owner, ()))


def _segments(pointer: str, details: Mapping[str, JsonValue]) -> list[str]:
    if not pointer.startswith("/") or pointer == "/":
        raise ValidationFailed(
            ErrorCode.INVALID_REFERENCE,
            "pointer is not an RFC 6901 pointer",
            details={**details, "reason": "bad_pointer"},
        )
    return [segment.replace("~1", "/").replace("~0", "~") for segment in pointer[1:].split("/")]


def _owned_field(owner: str, segments: list[str]) -> str | None:
    first = segments[0]
    if len(segments) == 1 and first in ("id", "key") and owner not in ("plan", "brief"):
        return first
    if len(segments) == 1 and _OWNED_BY_KIND.get(owner) == first:
        return first
    if owner == "plan" and (first == "schema" or first in _ENTITY_ARRAY_NAMES):
        return first
    return None


def _child(container: JsonValue, key: str | int) -> JsonValue:
    if isinstance(container, list) and isinstance(key, int):
        return container[key]
    if isinstance(container, dict) and isinstance(key, str):
        return container[key]
    return None


def _key_in(container: JsonValue, segment: str) -> str | int | None:
    """``segment`` as the key of an existing member of ``container``, else ``None``."""
    if isinstance(container, dict):
        return segment if segment in container else None
    if (
        isinstance(container, list)
        and re.fullmatch(r"0|[1-9][0-9]*", segment)
        and int(segment) < len(container)
    ):
        return int(segment)
    return None


def _fetch(node: JsonValue, segments: list[str]) -> tuple[JsonObject | list[JsonValue], str | int] | None:
    """The container and key of the member at ``segments`` below ``node``; ``None`` if there is none."""
    container: JsonValue = node
    for position, segment in enumerate(segments):
        key = _key_in(container, segment)
        if key is None:
            return None
        if position == len(segments) - 1:
            return (container, key) if isinstance(container, dict | list) else None
        container = _child(container, key)
    return None


def _occurrences(text: str, needle: str) -> int:
    """Number of matches of ``needle`` in ``text``, overlapping ones included."""
    count, start = 0, text.find(needle)
    while start != -1:
        count += 1
        start = text.find(needle, start + 1)
    return count


def apply_replace_text(doc: JsonObject, change: ReplaceTextChange, change_index: int) -> None:
    """Apply ``change`` to ``doc`` in place; ``doc`` is a batch's working copy, discarded when this raises."""
    where: dict[str, JsonValue] = {
        "target": change.target,
        "pointer": change.pointer,
        "change_index": change_index,
        "applied": False,
    }
    root: JsonValue
    if change.target in ("plan", "brief", "execution_constraints"):
        owner = change.target
        root = doc if owner == "plan" else doc.get(owner, {})
    else:
        location = resolve_ref(doc, change.target, change_index=change_index)
        owner = location.kind.value
        root = _child(_child(doc, location.array), location.index)
    segments = _segments(change.pointer, where)
    field = _owned_field(owner, segments)
    if field is not None:
        raise ValidationFailed(
            ErrorCode.FIELD_OWNED,
            "field is owned and cannot be edited as text",
            details={
                "target": change.target,
                "field": field,
                "pointer": change.pointer,
                "change_index": change_index,
                "applied": False,
            },
        )
    if not is_text_field(owner, change.pointer):
        raise ValidationFailed(
            ErrorCode.INVALID_REFERENCE,
            "pointer is not an editable narrative field",
            details={**where, "reason": "not_text_field"},
        )
    found = _fetch(root, segments)
    current = None if found is None else _child(*found)
    if found is None or not isinstance(current, str):
        raise ValidationFailed(
            ErrorCode.INVALID_REFERENCE,
            "pointer does not address an existing string",
            details={**where, "reason": "not_a_string"},
        )
    if change.old_text == "":
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "old_text must not be empty",
            details={**where, "reason": "old_text_empty"},
        )
    if text_digest(current) != change.expected_text_digest:
        raise Conflict(
            ErrorCode.VERSION_CONFLICT,
            "text changed since it was read",
            details={**where, "reason": "text_changed"},
        )
    occurrences = _occurrences(current, change.old_text)
    if occurrences != 1:
        raise Conflict(
            ErrorCode.VERSION_CONFLICT,
            "old_text must occur exactly once",
            details={**where, "reason": "text_match_count", "occurrences": occurrences},
        )
    at = current.index(change.old_text)
    replaced = current[:at] + change.new_text + current[at + len(change.old_text) :]
    container, key = found
    if isinstance(container, list) and isinstance(key, int):
        container[key] = replaced
    elif isinstance(container, dict):
        container[str(key)] = replaced
