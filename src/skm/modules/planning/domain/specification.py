"""The typed specification: records, indexes, ``from_document`` / ``to_document`` (planning §4.1, §5.1).

Pure domain code: the input document is never mutated, and nothing here does IO.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import date as Date
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound
from skm.kernel.ids import parse_uuid
from skm.modules.planning.domain.brief import Brief, BriefChannel, BriefMessage, BriefMessageKind, Section
from skm.modules.planning.domain.check_spec import CheckSpec, check_from_doc, check_to_doc
from skm.modules.planning.domain.criterion import Criterion, criterion_from_doc, criterion_to_doc
from skm.modules.planning.domain.decision import Decision, decision_from_doc, decision_to_doc
from skm.modules.planning.domain.execution_constraints import (
    ExecutionConstraints,
    PathRule,
    constraints_from_doc,
    constraints_to_doc,
)
from skm.modules.planning.domain.item import (
    ChangeHint,
    Item,
    Route,
    WorkKind,
    item_from_doc,
    item_to_doc,
)
from skm.modules.planning.domain.material import Material, material_from_doc, material_to_doc
from skm.modules.planning.domain.phase import Phase, phase_from_doc, phase_to_doc
from skm.modules.planning.domain.plan_relation import (
    PlanRelation,
    plan_relation_from_doc,
    plan_relation_to_doc,
)
from skm.modules.planning.domain.reads import (
    compact,
    format_timestamp,
    parse_timestamp,
    sections_from_doc,
    sections_to_doc,
    strs_of,
    text_of,
)
from skm.modules.planning.domain.requirement import Requirement, requirement_from_doc, requirement_to_doc
from skm.modules.planning.domain.review_requirement import ReviewRequirement
from skm.modules.planning.domain.unit import Unit, unit_from_doc, unit_to_doc
from skm.modules.planning.domain.validation.findings import Finding, Severity

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from uuid import UUID

    from skm.kernel.ids import EntityId
    from skm.kernel.json_types import JsonObject, JsonValue

SPECIFICATION_URN: Final = "urn:skm:planning:specification:v1"


class EntityKind(StrEnum):
    PHASE = "phase"
    ITEM = "item"
    UNIT = "unit"
    REQUIREMENT = "requirement"
    CRITERION = "criterion"
    CHECK = "check"
    DECISION = "decision"
    MATERIAL = "material"


type SpecEntity = Phase | Item | Unit | Requirement | Criterion | CheckSpec | Decision | Material


@dataclass(frozen=True, slots=True)
class Specification:
    title: str
    goal: str
    context_md: str | None
    non_goals: tuple[str, ...]
    rules: tuple[str, ...]
    brief: Brief | None
    requirements: tuple[Requirement, ...]
    phases: tuple[Phase, ...]
    items: tuple[Item, ...]
    units: tuple[Unit, ...]
    criteria: tuple[Criterion, ...]
    checks: tuple[CheckSpec, ...]
    decisions: tuple[Decision, ...]
    materials: tuple[Material, ...]
    plan_relations: tuple[PlanRelation, ...]
    execution_constraints: ExecutionConstraints
    sections: tuple[Section, ...]
    extensions: Mapping[str, JsonObject]
    design_brief_id: UUID | None = None
    _index: SpecIndex = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_index", _build_index(self))

    def entity(self, entity_id: EntityId) -> SpecEntity:
        found = self._index.by_id.get(entity_id)
        if found is None:
            raise NotFound(
                ErrorCode.NOT_FOUND, "entity not found", details={"kind": "entity", "ref": str(entity_id)}
            )
        return found

    def by_key(self, key: str) -> SpecEntity:
        found = self._index.by_key.get(key)
        if found is None:
            raise NotFound(ErrorCode.NOT_FOUND, "entity not found", details={"kind": "entity", "ref": key})
        return found

    def items_of(self, phase_key: str) -> tuple[Item, ...]:
        return tuple(item for item in self.items if item.phase == phase_key)

    def units_of(self, item_key: str) -> tuple[Unit, ...]:
        return tuple(unit for unit in self.units if unit.key.split("/", 1)[0] == item_key)

    def checks_of(self, owner_key: str) -> tuple[CheckSpec, ...]:
        return tuple(check for check in self.checks if check.owner == owner_key)

    def criteria_of(self, owner_key: str) -> tuple[Criterion, ...]:
        return tuple(criterion for criterion in self.criteria if criterion.owner == owner_key)

    def display_key(self, entity: SpecEntity) -> str:
        return _display_key(entity)

    def ancestors(self, entity_id: EntityId) -> tuple[SpecEntity, ...]:
        """Nearest first: owner of a check or criterion; item and phase of a unit; phase of an item."""
        entity = self.entity(entity_id)
        chain: list[SpecEntity] = []
        parent = self._parent_key(entity)
        while parent is not None:
            owner = self._index.by_key.get(parent)
            if owner is None:
                break
            chain.append(owner)
            parent = self._parent_key(owner)
        return tuple(chain)

    def _parent_key(self, entity: SpecEntity) -> str | None:
        if isinstance(entity, Unit):
            return entity.key.split("/", 1)[0]
        if isinstance(entity, Item):
            return entity.phase
        if isinstance(entity, CheckSpec | Criterion):
            return entity.owner
        return None

    def criteria_for(self, entity_id: EntityId) -> tuple[Criterion, ...]:
        return self.criteria_of(self._display_key_of_id(entity_id))

    def checks_for(self, entity_id: EntityId) -> tuple[CheckSpec, ...]:
        return self.checks_of(self._display_key_of_id(entity_id))

    def _display_key_of_id(self, entity_id: EntityId) -> str:
        return _display_key(self.entity(entity_id))

    def _item_of(self, entity: SpecEntity) -> Item | None:
        if isinstance(entity, Item):
            return entity
        if isinstance(entity, Unit):
            owner = self._index.by_key.get(entity.key.split("/", 1)[0])
            return owner if isinstance(owner, Item) else None
        return None

    def review_requirement_for(self, entity_id: EntityId) -> ReviewRequirement | None:
        """The review contract of an item; a unit inherits the one of its item."""
        item = self._item_of(self.entity(entity_id))
        return None if item is None else item.review

    def declared_write_scope_for(self, entity_id: EntityId) -> tuple[PathRule, ...] | None:
        """The write scope a unit declares; ``None`` when it declares none (or the entity is not a unit)."""
        entity = self.entity(entity_id)
        if isinstance(entity, Unit) and entity.write_scope:
            return tuple(PathRule(entry.mount, entry.pattern) for entry in entity.write_scope)
        return None

    def route_for(self, entity_id: EntityId) -> Route | None:
        """The route of a unit, else that of its item (a unit without ``route`` inherits the item's)."""
        entity = self.entity(entity_id)
        if isinstance(entity, Unit) and entity.route is not None:
            return entity.route
        item = self._item_of(entity)
        return None if item is None else item.route

    def work_kind_for(self, entity_id: EntityId) -> str:
        """The work kind of a unit, else that of its item; any other entity has none and reports ``code``."""
        entity = self.entity(entity_id)
        if isinstance(entity, Unit) and entity.work_kind is not None:
            return entity.work_kind.value
        item = self._item_of(entity)
        return WorkKind.CODE.value if item is None else item.work_kind.value

    def materials_for(self, entity_id: EntityId) -> tuple[Material, ...]:
        raise NotImplementedError("owner leaf")

    def requirements_for(self, entity_id: EntityId) -> tuple[Requirement, ...]:
        raise NotImplementedError("owner leaf")

    def decisions_for(self, entity_id: EntityId) -> tuple[Decision, ...]:
        raise NotImplementedError("owner leaf")

    def change_hints_for(self, entity_id: EntityId) -> tuple[ChangeHint, ...]:
        """The change hints of an item; a unit reports the hints of its item."""
        item = self._item_of(self.entity(entity_id))
        return () if item is None else item.change_hints

    def review_groups(self) -> tuple[JsonObject, ...]:
        raise NotImplementedError("owner leaf")

    def gate_checks(self, scope: str, entity_id: EntityId | None = None) -> tuple[CheckSpec, ...]:
        raise NotImplementedError("owner leaf")


@dataclass(frozen=True, slots=True)
class SpecIndex:
    by_id: Mapping[EntityId, SpecEntity]
    by_key: Mapping[str, SpecEntity]


def _display_key(entity: SpecEntity) -> str:
    if isinstance(entity, CheckSpec):
        return f"{entity.owner}:{entity.key}"
    if isinstance(entity, Material):
        return f"material/{entity.key}"
    return entity.key


def _build_index(spec: Specification) -> SpecIndex:
    by_id: dict[EntityId, SpecEntity] = {}
    by_key: dict[str, SpecEntity] = {}
    groups: tuple[tuple[SpecEntity, ...], ...] = (
        spec.phases, spec.items, spec.units, spec.requirements, spec.criteria, spec.checks, spec.decisions,
        spec.materials,
    )  # fmt: skip
    for group in groups:
        for entity in group:
            by_id.setdefault(entity.id, entity)
            by_key.setdefault(_display_key(entity), entity)
    return SpecIndex(MappingProxyType(by_id), MappingProxyType(by_key))


def _brief_at(raw: str) -> Date | object:
    return Date.fromisoformat(raw) if len(raw) == len("2026-10-20") else parse_timestamp(raw)


def _brief_from_doc(doc: Mapping[str, JsonValue]) -> Brief:
    messages: list[BriefMessage] = []
    for message in cast("list[Mapping[str, JsonValue]]", doc.get("messages", [])):
        at, channel = text_of(message, "at"), text_of(message, "channel")
        messages.append(
            BriefMessage(
                key=str(message["key"]),
                at=None if at is None else cast("Date", _brief_at(at)),
                channel=None if channel is None else BriefChannel(channel),
                kind=BriefMessageKind(str(message["kind"])),
                text=str(message["text"]),
            )
        )
    # The schema declares ``brief.environment`` as an array of texts, brief.py as ``str | None`` (brief.py is
    # outside this leaf's write set): the lines are carried as a tuple until that declaration follows.
    environment = cast("str | None", strs_of(doc, "environment") if "environment" in doc else None)
    return Brief(tuple(messages), strs_of(doc, "constraints"), environment, strs_of(doc, "out_of_scope"))


def _brief_to_doc(brief: Brief) -> JsonObject:
    messages: list[JsonValue] = []
    for message in brief.messages:
        at: str | None = None
        if isinstance(message.at, datetime):
            at = format_timestamp(message.at)
        elif isinstance(message.at, Date):
            at = message.at.isoformat()
        messages.append(
            compact(
                {
                    "key": message.key,
                    "at": at,
                    "channel": None if message.channel is None else message.channel.value,
                    "kind": message.kind.value,
                    "text": message.text,
                }
            )
        )
    environment = cast("tuple[str, ...] | str | None", brief.environment)
    return {
        "messages": messages,
        **compact(
            {
                "constraints": list(brief.constraints),
                "environment": None
                if environment is None
                else list(environment)
                if not isinstance(environment, str)
                else [environment],
                "out_of_scope": list(brief.out_of_scope),
            }
        ),
    }


def _doc_key(array: str, entity: Mapping[str, JsonValue]) -> str:
    key = str(entity.get("key", ""))
    if array == "checks":
        return f"{entity.get('owner', '')}:{key}"
    if array == "materials":
        return f"material/{key}"
    return key


def _entities[T](
    doc: Mapping[str, JsonValue],
    array: str,
    parse: Callable[[Mapping[str, JsonValue]], T],
    findings: list[Finding],
) -> tuple[T, ...]:
    """Parse ``doc[array]``; a repeated display key is reported and only its first occurrence is modelled."""
    seen: dict[str, int] = {}
    parsed: list[T] = []
    for index, entity in enumerate(cast("list[Mapping[str, JsonValue]]", doc.get(array, []))):
        key = _doc_key(array, entity)
        if key in seen:
            findings.append(
                Finding(
                    "duplicate_key",
                    Severity.ERROR,
                    f"{key} is declared more than once",
                    key,
                    None,
                    f"/{array}/{index}/key",
                    {"first_pointer": f"/{array}/{seen[key]}"},
                )
            )
            continue
        seen[key] = index
        parsed.append(parse(entity))
    return tuple(parsed)


def from_document(doc: Mapping[str, JsonValue]) -> tuple[Specification, tuple[Finding, ...]]:
    """Build the typed specification from a schema-valid document; ``doc`` is not mutated.

    Defaults that carry meaning are written explicitly (planning §5.1). Structural problems the schema cannot
    express come back as findings (``duplicate_key``, ``key_prefix_mismatch``); the model is built on the
    first occurrence so the remaining rules can run. Entity ids must be assigned (``assign_missing_ids``).
    """
    findings: list[Finding] = []
    items = _entities(doc, "items", item_from_doc, findings)
    for index, item in enumerate(items):
        if item.key.split(".", 1)[0] != item.phase:
            findings.append(
                Finding(
                    "key_prefix_mismatch",
                    Severity.ERROR,
                    f"{item.key} does not start with its phase {item.phase}",
                    item.key,
                    item.id,
                    f"/items/{index}/key",
                    {"phase": item.phase},
                )
            )
    brief = cast("Mapping[str, JsonValue] | None", doc.get("brief"))
    spec = Specification(
        title=str(doc["title"]),
        goal=str(doc["goal"]),
        context_md=text_of(doc, "context_md"),
        non_goals=strs_of(doc, "non_goals"),
        rules=strs_of(doc, "rules"),
        brief=None if brief is None else _brief_from_doc(brief),
        requirements=_entities(doc, "requirements", requirement_from_doc, findings),
        phases=_entities(doc, "phases", phase_from_doc, findings),
        items=items,
        units=_entities(doc, "units", unit_from_doc, findings),
        criteria=_entities(doc, "criteria", criterion_from_doc, findings),
        checks=_entities(doc, "checks", check_from_doc, findings),
        decisions=_entities(doc, "decisions", decision_from_doc, findings),
        materials=_entities(doc, "materials", material_from_doc, findings),
        plan_relations=tuple(
            plan_relation_from_doc(r)
            for r in cast("list[Mapping[str, JsonValue]]", doc.get("plan_relations", []))
        ),
        execution_constraints=constraints_from_doc(
            cast("Mapping[str, JsonValue] | None", doc.get("execution_constraints"))
        ),
        sections=sections_from_doc(doc),
        design_brief_id=None
        if (brief_id := text_of(doc, "design_brief_id")) is None
        else parse_uuid(brief_id),
        extensions=MappingProxyType(
            copy.deepcopy(dict(cast("Mapping[str, JsonObject]", doc.get("extensions", {}))))
        ),
    )
    return spec, tuple(findings)


def to_document(spec: Specification) -> JsonObject:
    """The document form of ``spec``; absent optional members and empty arrays are omitted."""
    doc: JsonObject = {"schema": SPECIFICATION_URN, "title": spec.title, "goal": spec.goal}
    doc.update(
        compact(
            {
                "context_md": spec.context_md,
                "design_brief_id": str(spec.design_brief_id) if spec.design_brief_id is not None else None,
                "non_goals": list(spec.non_goals),
                "rules": list(spec.rules),
                "brief": None if spec.brief is None else _brief_to_doc(spec.brief),
                "requirements": [requirement_to_doc(e) for e in spec.requirements],
            }
        )
    )
    doc["phases"] = [phase_to_doc(e) for e in spec.phases]
    doc["items"] = [item_to_doc(e) for e in spec.items]
    doc.update(
        compact(
            {
                "units": [unit_to_doc(e) for e in spec.units],
                "criteria": [criterion_to_doc(e) for e in spec.criteria],
                "checks": [check_to_doc(e) for e in spec.checks],
                "decisions": [decision_to_doc(e) for e in spec.decisions],
                "materials": [material_to_doc(e) for e in spec.materials],
                "plan_relations": [plan_relation_to_doc(e) for e in spec.plan_relations],
            }
        )
    )
    doc["execution_constraints"] = constraints_to_doc(spec.execution_constraints)
    doc.update(compact({"sections": sections_to_doc(spec.sections)}))
    if spec.extensions:
        doc["extensions"] = copy.deepcopy(dict(spec.extensions))
    return doc
