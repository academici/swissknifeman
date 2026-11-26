"""Materials: typed record and document form (planning §4.2)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, cast
from uuid import UUID

from skm.kernel.ids import FileVersionId
from skm.modules.planning.domain.reads import compact, entity_id_of, format_timestamp, parse_timestamp

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime
    from typing import Literal

    from skm.kernel.ids import EntityId
    from skm.kernel.json_types import JsonObject, JsonValue


class MaterialKind(StrEnum):
    FILE_VERSION = "file_version"
    REPOSITORY_PATH = "repository_path"
    EXTERNAL_SOURCE = "external_source"


class MaterialStage(StrEnum):
    EXECUTION = "execution"
    REVIEW = "review"
    ACCEPTANCE = "acceptance"


class FreshnessPolicy(StrEnum):
    PINNED = "pinned"
    LATEST_AT_PUBLISH = "latest_at_publish"
    MUST_REFRESH = "must_refresh"


@dataclass(frozen=True, slots=True)
class Freshness:
    policy: FreshnessPolicy
    max_age_seconds: int | None


def must_refresh_expired(max_age_seconds: int | None, observed_at: datetime | None, now: datetime) -> bool:
    """Whether a ``must_refresh`` material needs a refresh (planning §5.11 item 4).

    True when its age is unknown, no maximum age is set, or it is older than ``max_age_seconds``.
    """
    if observed_at is None or max_age_seconds is None:
        return True
    return (now - observed_at).total_seconds() > max_age_seconds


type Selector = JsonObject


@dataclass(frozen=True, slots=True)
class Material:
    id: EntityId
    key: str
    title: str
    kind: MaterialKind
    file_version_id: FileVersionId | None
    mount: str | None
    path: str | None
    url: str | None
    retrieved_at: datetime | None
    content_digest: str | None
    selector: Selector | None
    role: Literal["input", "reference"]
    required_for: tuple[MaterialStage, ...]
    freshness: Freshness
    why: str | None
    applies_to: tuple[str, ...]
    is_global: bool
    external_source_id: str | None = None


type MaterialRef = JsonObject


def _text(doc: Mapping[str, JsonValue], name: str) -> str | None:
    value = doc.get(name)
    return None if value is None else str(value)


def material_from_doc(doc: Mapping[str, JsonValue]) -> Material:
    freshness = cast("Mapping[str, JsonValue]", doc.get("freshness", {"policy": "pinned"}))
    max_age = freshness.get("max_age_seconds")
    file_version, retrieved = _text(doc, "file_version_id"), _text(doc, "retrieved_at")
    return Material(
        id=entity_id_of(doc),
        key=str(doc["key"]),
        title=str(doc["title"]),
        kind=MaterialKind(str(doc["kind"])),
        file_version_id=None if file_version is None else FileVersionId(UUID(file_version)),
        mount=_text(doc, "mount"),
        path=_text(doc, "path"),
        url=_text(doc, "url"),
        retrieved_at=None if retrieved is None else parse_timestamp(retrieved),
        content_digest=_text(doc, "content_digest"),
        selector=cast("JsonObject | None", doc.get("selector")),
        role=cast("Literal['input', 'reference']", doc["role"]),
        required_for=tuple(
            MaterialStage(str(v)) for v in cast("list[JsonValue]", doc.get("required_for", []))
        ),
        freshness=Freshness(
            FreshnessPolicy(str(freshness["policy"])), None if max_age is None else int(cast("int", max_age))
        ),
        why=_text(doc, "why"),
        applies_to=tuple(str(v) for v in cast("list[JsonValue]", doc.get("applies_to", []))),
        is_global=bool(doc.get("global", False)),
        external_source_id=_text(doc, "external_source_id"),
    )


def material_to_doc(material: Material) -> JsonObject:
    freshness: JsonObject = {"policy": material.freshness.policy.value}
    if material.freshness.max_age_seconds is not None:
        freshness["max_age_seconds"] = material.freshness.max_age_seconds
    return compact(
        {
            "id": str(material.id),
            "key": material.key,
            "title": material.title,
            "kind": material.kind.value,
            "file_version_id": None if material.file_version_id is None else str(material.file_version_id),
            "mount": material.mount,
            "path": material.path,
            "url": material.url,
            "retrieved_at": None
            if material.retrieved_at is None
            else format_timestamp(material.retrieved_at),
            "content_digest": material.content_digest,
            "selector": material.selector,
            "role": material.role,
            "required_for": [stage.value for stage in material.required_for],
            "freshness": freshness,
            "why": material.why,
            "applies_to": list(material.applies_to),
            "global": True if material.is_global else None,
            "external_source_id": material.external_source_id,
        }
    )
