"""Decisions: typed record and document form (planning §4.2)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date
from enum import StrEnum
from typing import TYPE_CHECKING, cast

from skm.modules.planning.domain.brief import Section
from skm.modules.planning.domain.reads import compact, entity_id_of

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Literal

    from skm.kernel.ids import EntityId
    from skm.kernel.json_types import JsonObject, JsonValue


class DecisionState(StrEnum):
    OPEN = "open"
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


@dataclass(frozen=True, slots=True)
class DecisionOption:
    key: str
    text: str


@dataclass(frozen=True, slots=True)
class DecisionEvidence:
    kind: Literal["material", "url", "entity", "note"]
    ref: str
    note: str | None


@dataclass(frozen=True, slots=True)
class DecisionOrigin:
    kind: Literal["owner", "agent", "advice", "panel", "import"]
    ref: str | None


@dataclass(frozen=True, slots=True)
class Decision:
    id: EntityId
    key: str
    title: str
    date: Date | None
    state: DecisionState
    question: str | None
    options: tuple[DecisionOption, ...]
    context_md: str | None
    decision: str | None
    rationale: str | None
    consequences: tuple[str, ...]
    applies_to: tuple[str, ...]
    is_global: bool
    supersedes: tuple[str, ...]
    evidence: tuple[DecisionEvidence, ...]
    origin: DecisionOrigin | None
    answered_by: Literal["owner", "agent"] | None
    sections: tuple[Section, ...]


def _text(doc: Mapping[str, JsonValue], name: str) -> str | None:
    value = doc.get(name)
    return None if value is None else str(value)


def _strs(doc: Mapping[str, JsonValue], name: str) -> tuple[str, ...]:
    return tuple(str(v) for v in cast("list[JsonValue]", doc.get(name, [])))


def decision_from_doc(doc: Mapping[str, JsonValue]) -> Decision:
    origin = cast("Mapping[str, JsonValue] | None", doc.get("origin"))
    raw_date = _text(doc, "date")
    return Decision(
        id=entity_id_of(doc),
        key=str(doc["key"]),
        title=str(doc["title"]),
        date=None if raw_date is None else Date.fromisoformat(raw_date),
        state=DecisionState(str(doc["state"])),
        question=_text(doc, "question"),
        options=tuple(
            DecisionOption(str(o["key"]), str(o["text"]))
            for o in cast("list[Mapping[str, JsonValue]]", doc.get("options", []))
        ),
        context_md=_text(doc, "context_md"),
        decision=_text(doc, "decision"),
        rationale=_text(doc, "rationale"),
        consequences=_strs(doc, "consequences"),
        applies_to=_strs(doc, "applies_to"),
        is_global=bool(doc.get("global", False)),
        supersedes=_strs(doc, "supersedes"),
        evidence=tuple(
            DecisionEvidence(
                cast("Literal['material', 'url', 'entity', 'note']", e["kind"]),
                str(e["ref"]),
                _text(e, "note"),
            )
            for e in cast("list[Mapping[str, JsonValue]]", doc.get("evidence", []))
        ),
        origin=None
        if origin is None
        else DecisionOrigin(
            cast("Literal['owner', 'agent', 'advice', 'panel', 'import']", origin["kind"]),
            _text(origin, "ref"),
        ),
        answered_by=cast("Literal['owner', 'agent'] | None", doc.get("answered_by")),
        sections=tuple(
            Section(str(s["id"]), str(s["title"]), str(s["text"]))
            for s in cast("list[Mapping[str, JsonValue]]", doc.get("sections", []))
        ),
    )


def decision_to_doc(decision: Decision) -> JsonObject:
    return compact(
        {
            "id": str(decision.id),
            "key": decision.key,
            "title": decision.title,
            "date": None if decision.date is None else decision.date.isoformat(),
            "state": decision.state.value,
            "question": decision.question,
            "options": [{"key": o.key, "text": o.text} for o in decision.options],
            "context_md": decision.context_md,
            "decision": decision.decision,
            "rationale": decision.rationale,
            "consequences": list(decision.consequences),
            "applies_to": list(decision.applies_to),
            "global": True if decision.is_global else None,
            "supersedes": list(decision.supersedes),
            "evidence": [compact({"kind": e.kind, "ref": e.ref, "note": e.note}) for e in decision.evidence],
            "origin": None
            if decision.origin is None
            else compact({"kind": decision.origin.kind, "ref": decision.origin.ref}),
            "answered_by": decision.answered_by,
            "sections": [{"id": s.id, "title": s.title, "text": s.text} for s in decision.sections],
        }
    )
