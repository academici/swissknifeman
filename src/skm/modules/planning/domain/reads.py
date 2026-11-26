"""Read declarations of items, units and phases, and their document form."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Final, SupportsIndex, cast, override
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.ids import EntityId
from skm.modules.planning.domain.brief import Section

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from datetime import tzinfo

    from skm.kernel.json_types import JsonObject, JsonValue


class ReadPurpose(StrEnum):
    READ = "read"
    EXAMPLE = "example"
    SUPPORTING = "supporting"


@dataclass(frozen=True, slots=True)
class RepositoryPathRead:
    why: str
    required: bool
    mount: str
    path: str
    section: str | None


@dataclass(frozen=True, slots=True)
class MaterialRead:
    why: str
    required: bool
    ref: str


@dataclass(frozen=True, slots=True)
class PlanEntityRead:
    why: str
    required: bool
    ref: str


@dataclass(frozen=True, slots=True)
class ArtifactRead:
    why: str
    required: bool
    ref: str


@dataclass(frozen=True, slots=True)
class ExternalSourceRead:
    why: str
    required: bool
    url: str
    external_source_id: str | None = None


type Read = RepositoryPathRead | MaterialRead | PlanEntityRead | ArtifactRead | ExternalSourceRead


def compact(fields: Mapping[str, JsonValue | None]) -> JsonObject:
    """Drop ``None`` and empty arrays: an absent optional member is the canonical form of an empty one."""
    return {name: value for name, value in fields.items() if value is not None and value != []}


def entity_id_of(doc: Mapping[str, JsonValue]) -> EntityId:
    """The ``id`` of a document entity; ids are assigned (``assign_missing_ids``) before the model."""
    raw = doc.get("id")
    if not isinstance(raw, str):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID, "entity id required", details={"key": str(doc.get("key", ""))}
        )
    return EntityId(UUID(raw))


def read_from_doc(doc: Mapping[str, JsonValue]) -> Read:
    why, required = str(doc["why"]), bool(doc["required"])
    match doc["kind"]:
        case "repository_path":
            section = doc.get("section")
            return RepositoryPathRead(
                why, required, str(doc["mount"]), str(doc["path"]), None if section is None else str(section)
            )
        case "material":
            return MaterialRead(why, required, str(doc["ref"]))
        case "plan_entity":
            return PlanEntityRead(why, required, str(doc["ref"]))
        case "artifact":
            return ArtifactRead(why, required, str(doc["ref"]))
        case _:
            source = doc.get("external_source_id")
            return ExternalSourceRead(why, required, str(doc["url"]), None if source is None else str(source))


def read_to_doc(read: Read) -> JsonObject:
    match read:
        case RepositoryPathRead():
            return compact(
                {
                    "kind": "repository_path",
                    "mount": read.mount,
                    "path": read.path,
                    "section": read.section,
                    "why": read.why,
                    "required": read.required,
                }
            )
        case MaterialRead():
            return {"kind": "material", "ref": read.ref, "why": read.why, "required": read.required}
        case PlanEntityRead():
            return {"kind": "plan_entity", "ref": read.ref, "why": read.why, "required": read.required}
        case ArtifactRead():
            return {"kind": "artifact", "ref": read.ref, "why": read.why, "required": read.required}
        case ExternalSourceRead():
            return compact(
                {
                    "kind": "external_source",
                    "url": read.url,
                    "why": read.why,
                    "required": read.required,
                    "external_source_id": read.external_source_id,
                }
            )


_TIMESTAMP: Final = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.(\d{1,6}))?Z")


class Timestamp(datetime):
    """A schema ``timestamp`` that remembers how many fraction digits its text wrote.

    The document keeps strings as written (planning §5.6 (d)): ``…:00.5Z`` and ``…:00.500000Z`` are one
    instant but two documents, so ``to_document`` writes back the digits ``from_document`` read. Comparison,
    hashing and arithmetic stay those of the instant; a computed value has no written text.
    """

    __slots__ = ("_fraction_digits",)

    @classmethod
    def of(cls, moment: datetime, fraction_digits: int) -> Timestamp:
        utc = moment.astimezone(UTC)
        if not 0 <= fraction_digits <= 6 or utc.microsecond % 10 ** (6 - fraction_digits):
            raise ValueError(f"{fraction_digits} fraction digits cannot write {utc.microsecond} microseconds")
        stamp = cls(
            utc.year, utc.month, utc.day, utc.hour, utc.minute, utc.second, utc.microsecond, tzinfo=UTC
        )
        object.__setattr__(stamp, "_fraction_digits", fraction_digits)
        return stamp

    @property
    def fraction_digits(self) -> int | None:
        """Digits after the seconds as written (0 to 6); ``None`` for a value computed from a timestamp."""
        return cast("int | None", getattr(self, "_fraction_digits", None))

    @override
    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(f"{type(self).__name__} is immutable")

    @override
    def __delattr__(self, name: str) -> None:
        raise AttributeError(f"{type(self).__name__} is immutable")

    @override
    def __reduce_ex__(self, protocol: SupportsIndex) -> tuple[Callable[..., Timestamp], tuple[object, ...]]:
        # the wall time with its own zone and fold, not the UTC text: a converted copy stays converted
        fields = (self.year, self.month, self.day, self.hour, self.minute, self.second, self.microsecond)
        return _restore_timestamp, (type(self), fields, self.tzinfo, self.fold, self.fraction_digits)


def _restore_timestamp(
    cls: type[Timestamp], fields: tuple[int, ...], zone: tzinfo | None, fold: int, fraction_digits: int | None
) -> Timestamp:
    """A copy or an unpickled :class:`Timestamp`; a computed value stays without written digits."""
    stamp = cls(*fields, tzinfo=zone, fold=fold)
    if fraction_digits is not None:
        object.__setattr__(stamp, "_fraction_digits", fraction_digits)
    return stamp


def parse_timestamp(text: str) -> datetime:
    """A schema ``timestamp`` (UTC, ``...Z``) as a tz-aware :class:`Timestamp` keeping its fraction digits."""
    moment = datetime.fromisoformat(text).astimezone(UTC)
    written = _TIMESTAMP.fullmatch(text)
    return moment if written is None else Timestamp.of(moment, len(written.group(1) or ""))


def format_timestamp(moment: datetime) -> str:
    """The schema text of ``moment``: a parsed timestamp with its own digits, any other with six or none."""
    utc = moment.astimezone(UTC)
    digits = moment.fraction_digits if isinstance(moment, Timestamp) else None
    if digits is None:
        return utc.isoformat().replace("+00:00", "Z")
    fraction = f".{utc.microsecond:06d}"[: digits + 1] if digits else ""
    return f"{utc.isoformat(timespec='seconds').removesuffix('+00:00')}{fraction}Z"


def sections_from_doc(doc: Mapping[str, JsonValue]) -> tuple[Section, ...]:
    return tuple(
        Section(str(s["id"]), str(s["title"]), str(s["text"]))
        for s in cast("list[Mapping[str, JsonValue]]", doc.get("sections", []))
    )


def sections_to_doc(sections: tuple[Section, ...]) -> list[JsonValue]:
    return [{"id": s.id, "title": s.title, "text": s.text} for s in sections]


def strs_of(doc: Mapping[str, JsonValue], name: str) -> tuple[str, ...]:
    """A string array member as a tuple; absent is empty."""
    return tuple(str(v) for v in cast("list[JsonValue]", doc.get(name, [])))


def text_of(doc: Mapping[str, JsonValue], name: str) -> str | None:
    value = doc.get(name)
    return None if value is None else str(value)
