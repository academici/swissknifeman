"""Phases: typed records and document form (planning §4.2)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, cast

from skm.modules.planning.domain.reads import (
    compact,
    entity_id_of,
    read_from_doc,
    read_to_doc,
    sections_from_doc,
    sections_to_doc,
    strs_of,
    text_of,
)
from skm.modules.planning.domain.scope import scope_from_doc, scope_to_doc

if TYPE_CHECKING:
    from collections.abc import Mapping

    from skm.kernel.ids import EntityId
    from skm.kernel.json_types import JsonObject, JsonValue
    from skm.modules.planning.domain.brief import Section
    from skm.modules.planning.domain.reads import Read
    from skm.modules.planning.domain.scope import Scope


class BatchMode(StrEnum):
    RECOMMENDED = "recommended"
    REQUIRED = "required"


class DesignState(StrEnum):
    SKELETON = "skeleton"
    DETAILED = "detailed"


class Strategy(StrEnum):
    DAG = "dag"
    SEQUENTIAL = "sequential"


@dataclass(frozen=True, slots=True)
class Batch:
    key: str
    items: tuple[str, ...]
    mode: BatchMode
    note: str | None


@dataclass(frozen=True, slots=True)
class PhaseContract:
    consumes: tuple[str, ...]
    produces: tuple[str, ...]
    boundaries: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Assurance:
    impact: str | None
    seams: tuple[str, ...]
    live: bool | None
    note: str | None


@dataclass(frozen=True, slots=True)
class Phase:
    id: EntityId
    key: str
    title: str
    goal: str
    context_md: str | None
    contract: PhaseContract
    scope: Scope | None
    depends_on: tuple[str, ...] | None
    pitfalls: tuple[str, ...]
    deliverables: tuple[str, ...]
    assurance: Assurance | None
    supporting: tuple[Read, ...]
    batches: tuple[Batch, ...]
    design_state: DesignState
    strategy: Strategy
    sections: tuple[Section, ...]


def phase_from_doc(doc: Mapping[str, JsonValue]) -> Phase:
    contract = cast("Mapping[str, JsonValue]", doc.get("contract", {}))
    assurance = cast("Mapping[str, JsonValue] | None", doc.get("assurance"))
    scope = cast("Mapping[str, JsonValue] | None", doc.get("scope"))
    live = None if assurance is None else assurance.get("live")
    return Phase(
        id=entity_id_of(doc),
        key=str(doc["key"]),
        title=str(doc["title"]),
        goal=str(doc["goal"]),
        context_md=text_of(doc, "context_md"),
        contract=PhaseContract(
            strs_of(contract, "consumes"), strs_of(contract, "produces"), strs_of(contract, "boundaries")
        ),
        scope=None if scope is None else scope_from_doc(scope),
        depends_on=strs_of(doc, "depends_on") if "depends_on" in doc else None,
        pitfalls=strs_of(doc, "pitfalls"),
        deliverables=strs_of(doc, "deliverables"),
        assurance=None
        if assurance is None
        else Assurance(
            text_of(assurance, "impact"),
            strs_of(assurance, "seams"),
            None if live is None else bool(live),
            text_of(assurance, "note"),
        ),
        supporting=tuple(
            read_from_doc(r) for r in cast("list[Mapping[str, JsonValue]]", doc.get("supporting", []))
        ),
        batches=tuple(
            Batch(str(b["key"]), strs_of(b, "items"), BatchMode(str(b["mode"])), text_of(b, "note"))
            for b in cast("list[Mapping[str, JsonValue]]", doc.get("batches", []))
        ),
        design_state=DesignState(str(doc["design_state"])),
        strategy=Strategy(str(doc.get("strategy", "dag"))),
        sections=sections_from_doc(doc),
    )


def phase_to_doc(phase: Phase) -> JsonObject:
    doc = compact(
        {
            "id": str(phase.id),
            "key": phase.key,
            "title": phase.title,
            "goal": phase.goal,
            "context_md": phase.context_md,
            "contract": compact(
                {
                    "consumes": list(phase.contract.consumes),
                    "produces": list(phase.contract.produces),
                    "boundaries": list(phase.contract.boundaries),
                }
            )
            or None,
            "scope": None if phase.scope is None else scope_to_doc(phase.scope),
            "pitfalls": list(phase.pitfalls),
            "deliverables": list(phase.deliverables),
            "assurance": None
            if phase.assurance is None
            else compact(
                {
                    "impact": phase.assurance.impact,
                    "seams": list(phase.assurance.seams),
                    "live": phase.assurance.live,
                    "note": phase.assurance.note,
                }
            ),
            "supporting": [read_to_doc(r) for r in phase.supporting],
            "batches": [
                compact({"key": b.key, "items": list(b.items), "mode": b.mode.value, "note": b.note})
                for b in phase.batches
            ],
            "design_state": phase.design_state.value,
            "strategy": phase.strategy.value,
            "sections": sections_to_doc(phase.sections),
        }
    )
    if phase.depends_on is not None:
        doc["depends_on"] = list(phase.depends_on)
    return doc
