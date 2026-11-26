"""Display keys and reference grammar (planning §4.3); a display key addresses an entity, it is not its id."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed

_FLAGS: Final = re.ASCII
_PHASE: Final = re.compile(r"P[0-9]+", _FLAGS)
_ITEM: Final = re.compile(r"P[0-9]+\.[0-9]+", _FLAGS)
_UNIT: Final = re.compile(r"P[0-9]+\.[0-9]+/U[0-9]+", _FLAGS)
_UNIT_REF: Final = re.compile(r"(P[0-9]+\.[0-9]+/)?U[0-9]+", _FLAGS)
_DECISION: Final = re.compile(r"D[0-9]+", _FLAGS)
_REQUIREMENT: Final = re.compile(r"R[0-9]+", _FLAGS)
_CRITERION: Final = re.compile(r"AC[0-9]+", _FLAGS)
_CHECK: Final = re.compile(r"P[0-9]+(\.[0-9]+)?:V[0-9]+", _FLAGS)
_CHECK_LOCAL: Final = re.compile(r"V[0-9]+", _FLAGS)
_MATERIAL: Final = re.compile(r"material/[a-z0-9][a-z0-9-]{0,62}", _FLAGS)
_MATERIAL_REF: Final = re.compile(
    r"material/[a-z0-9][a-z0-9-]{0,62}(#[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)?", _FLAGS
)
_PLAN_ALIAS: Final = re.compile(r"(?!AC[0-9])[A-Z]{2,8}[1-9][0-9]*", _FLAGS)
_UUID: Final = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", _FLAGS)
_NUMBERS: Final = re.compile(r"[0-9]+")

ENTITY_ID_PREFIX: Final = "entity:"


class KeyKind(StrEnum):
    PLAN = "plan"
    PHASE = "phase"
    ITEM = "item"
    UNIT = "unit"
    REQUIREMENT = "requirement"
    CRITERION = "criterion"
    CHECK = "check"
    DECISION = "decision"
    MATERIAL = "material"


@dataclass(frozen=True, slots=True)
class DisplayKey:
    kind: KeyKind
    text: str

    @property
    def phase_key(self) -> str | None:
        """The phase prefix of an item, unit or check key."""
        if self.kind in (KeyKind.ITEM, KeyKind.UNIT, KeyKind.CHECK):
            return re.split(r"[.:/]", self.text, maxsplit=1)[0]
        return None

    @property
    def item_key(self) -> str | None:
        """The item of a unit, or the item that owns a check; ``None`` for a phase-owned check."""
        if self.kind is KeyKind.UNIT:
            return self.text.split("/", 1)[0]
        if self.kind is KeyKind.CHECK:
            owner = self.text.split(":", 1)[0]
            return owner if _ITEM.fullmatch(owner) else None
        return None

    @property
    def local(self) -> str | None:
        if self.kind is KeyKind.UNIT:
            return self.text.split("/", 1)[1]
        if self.kind is KeyKind.CHECK:
            return self.text.split(":", 1)[1]
        return None


@dataclass(frozen=True, slots=True)
class QualifiedRef:
    plan_alias: str
    key: DisplayKey


@dataclass(frozen=True, slots=True)
class LocalRef:
    key: DisplayKey


@dataclass(frozen=True, slots=True)
class IdRef:
    kind: str
    uuid: UUID


type CliRef = QualifiedRef | LocalRef | IdRef

_ENTITY_PATTERNS: Final = (
    (_PHASE, KeyKind.PHASE),
    (_ITEM, KeyKind.ITEM),
    (_UNIT, KeyKind.UNIT),
    (_DECISION, KeyKind.DECISION),
    (_REQUIREMENT, KeyKind.REQUIREMENT),
    (_CRITERION, KeyKind.CRITERION),
    (_CHECK, KeyKind.CHECK),
    (_MATERIAL, KeyKind.MATERIAL),
)


def _invalid(text: object) -> ValidationFailed:
    return ValidationFailed(ErrorCode.INVALID_REFERENCE, "not a valid reference", details={"text": str(text)})


def parse_key(text: str) -> DisplayKey:
    """Parse an entity display key; a plan alias is recognised only after the entity grammar has failed."""
    for pattern, kind in _ENTITY_PATTERNS:
        if pattern.fullmatch(text):
            return DisplayKey(kind, text)
    if _PLAN_ALIAS.fullmatch(text):
        return DisplayKey(KeyKind.PLAN, text)
    raise _invalid(text)


def key_kind(text: str) -> KeyKind | None:
    """The kind of an entity display key, or ``None`` when ``text`` is not one (never raises)."""
    for pattern, kind in _ENTITY_PATTERNS:
        if pattern.fullmatch(text):
            return kind
    return None


def parse_unit_ref(text: str, *, owner_item: str) -> str:
    if not _UNIT_REF.fullmatch(text) or not _ITEM.fullmatch(owner_item):
        raise _invalid(text)
    return text if "/" in text else f"{owner_item}/{text}"


def parse_check_ref(text: str, *, default_owner: str) -> str:
    if _CHECK.fullmatch(text):
        return text
    if _CHECK_LOCAL.fullmatch(text) and (_PHASE.fullmatch(default_owner) or _ITEM.fullmatch(default_owner)):
        return f"{default_owner}:{text}"
    raise _invalid(text)


def parse_material_ref(text: str) -> tuple[str, str | None]:
    """Split ``material/<key>[#<section>]`` into the material display key and the optional section id."""
    if not _MATERIAL_REF.fullmatch(text):
        raise _invalid(text)
    head, _, section = text.partition("#")
    return head, section or None


def parse_entity_id(text: str) -> UUID:
    """``entity:<uuid>`` -> UUID."""
    if not text.startswith(ENTITY_ID_PREFIX) or not _UUID.fullmatch(text[len(ENTITY_ID_PREFIX) :]):
        raise _invalid(text)
    return UUID(text[len(ENTITY_ID_PREFIX) :])


def parse_cli_ref(text: str) -> CliRef:
    for prefix in ("entity", "revision"):
        if text.startswith(f"{prefix}:") and _UUID.fullmatch(text[len(prefix) + 1 :]):
            return IdRef(prefix, UUID(text[len(prefix) + 1 :]))
    alias, dot, rest = text.partition(".")
    if dot and _PLAN_ALIAS.fullmatch(alias):
        key = parse_key(rest)
        if key.kind in (KeyKind.PLAN, KeyKind.MATERIAL):
            raise _invalid(text)
        return QualifiedRef(alias, key)
    return LocalRef(parse_key(text))


def key_sort_key(key: str) -> tuple[int | str, ...]:
    """Natural order: ``P1.10`` after ``P1.9``; a phase before its own items."""
    parts: list[int | str] = []
    for chunk in re.split(r"([0-9]+)", key):
        if _NUMBERS.fullmatch(chunk):
            parts.append(int(chunk))
        elif chunk:
            parts.append(chunk)
    return tuple(parts)
