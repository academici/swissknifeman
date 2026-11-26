"""What a validation run is given: the specification, its document and the facts the caller observed."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime
    from uuid import UUID

    from skm.kernel.ids import EntityId, PlanId
    from skm.kernel.json_types import JsonObject, JsonValue
    from skm.modules.planning.domain.specification import EntityKind, Specification


class FileVersionStatus(StrEnum):
    READY = "ready"
    NOT_READY = "not_ready"
    MISSING = "missing"
    OTHER_WORKSPACE = "other_workspace"


@dataclass(frozen=True, slots=True)
class FileVersionObservation:
    status: FileVersionStatus
    created_at: datetime | None


@dataclass(frozen=True, slots=True)
class ValidationContext:
    spec: Specification
    document: JsonObject
    project_mounts: frozenset[str]
    known_identities: Mapping[EntityId, EntityKind]
    file_versions: Mapping[UUID, FileVersionObservation]
    known_skills: frozenset[str] | None
    runtime_catalog: Mapping[str, frozenset[str]] | None
    project_plans: Mapping[str, PlanId]
    now: datetime
    settings: JsonObject  # the resolved ``planning`` section, as ``PlanningSettings.to_json()`` shapes it


@dataclass(frozen=True, slots=True)
class ValidationSettings:
    """The keys of ``planning.validation`` the rules read, taken from the resolved section.

    The section arrives complete (the settings registry fills the defaults); a missing or mistyped key is a
    defect of the caller and raises, which the pipeline records as a ``RuleFailure``.
    """

    require_acceptance_links: bool
    external_checks: bool
    code_suffixes: tuple[str, ...]
    heavy_check_markers: tuple[str, ...]
    heavy_text_bytes: int

    @classmethod
    def of(cls, settings: JsonObject) -> ValidationSettings:
        section = settings["validation"]
        if not isinstance(section, dict):
            raise TypeError("planning.validation is not an object")
        suffixes, markers = section["code_suffixes"], section["heavy_check_markers"]
        limit = section["heavy_text_bytes"]
        if not isinstance(suffixes, list) or not isinstance(markers, list) or not isinstance(limit, int):
            raise TypeError(
                "planning.validation has a malformed code_suffixes, heavy_check_markers or heavy_text_bytes"
            )
        return cls(
            require_acceptance_links=bool(section["require_acceptance_links"]),
            external_checks=bool(section["external_checks"]),
            code_suffixes=tuple(str(suffix) for suffix in suffixes),
            heavy_check_markers=tuple(str(marker) for marker in markers),
            heavy_text_bytes=limit,
        )


_ARRAYS: Final = ("phases", "items", "units", "requirements", "criteria", "checks", "decisions", "materials")


class Locator:
    """Where the entities of one document sit: display key -> (array, index), for JSON pointers of findings.

    The first occurrence of a repeated key wins, as in ``from_document``.
    """

    def __init__(self, document: Mapping[str, JsonValue]) -> None:
        self._at: dict[str, tuple[str, int]] = {}
        for array in _ARRAYS:
            entities = document.get(array)
            for index, entity in enumerate(entities if isinstance(entities, list) else ()):
                if isinstance(entity, dict):
                    self._at.setdefault(_display_key(array, entity), (array, index))

    def at(self, key: str) -> tuple[str, int] | None:
        return self._at.get(key)

    def pointer(self, key: str, *tail: str | int) -> str | None:
        """JSON pointer of the entity with display key ``key`` (plus ``tail``); ``None`` if there is none."""
        found = self._at.get(key)
        if found is None:
            return None
        return "".join(f"/{part}" for part in (*found, *tail))


def _display_key(array: str, entity: Mapping[str, JsonValue]) -> str:
    key = str(entity.get("key", ""))
    if array == "checks":
        return f"{entity.get('owner', '')}:{key}"
    if array == "materials":
        return f"material/{key}"
    return key
