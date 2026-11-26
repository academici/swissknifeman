"""Items: typed records, route, work-policy override and document form (planning §4.2, §4.2.1)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal, cast

from skm.modules.planning.domain.phase import Strategy
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
from skm.modules.planning.domain.review_requirement import ReviewRequirement, review_from_doc, review_to_doc
from skm.modules.planning.domain.scope import Scope, scope_from_doc, scope_to_doc

if TYPE_CHECKING:
    from collections.abc import Mapping

    from skm.kernel.ids import EntityId
    from skm.kernel.json_types import JsonObject, JsonValue
    from skm.modules.planning.domain.brief import Section
    from skm.modules.planning.domain.reads import Read


class WorkKind(StrEnum):
    CODE = "code"
    DOCS = "docs"
    RESEARCH = "research"
    CONFIG = "config"
    TEST = "test"
    REVIEW = "review"
    OPS = "ops"


class ModelClass(StrEnum):
    ECONOMY = "economy"
    IMPLEMENTATION = "implementation"
    FRONTIER = "frontier"


class Effort(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"
    MAX = "max"


class AuthorityKind(StrEnum):
    ROUTINE = "routine"
    OWNER_GATE = "owner_gate"
    EXTERNAL_GATE = "external_gate"


@dataclass(frozen=True, slots=True)
class ChangeHint:
    mount: str
    pattern: str
    change: Literal["create", "modify", "delete", "any"]
    note: str | None


@dataclass(frozen=True, slots=True)
class ArtifactDecl:
    key: str | None
    mount: str
    path: str
    role: Literal["input", "output"]
    note: str | None


@dataclass(frozen=True, slots=True)
class Relation:
    target: str
    relation: str
    note: str | None


@dataclass(frozen=True, slots=True)
class SkillReq:
    key: str
    version: str | None


@dataclass(frozen=True, slots=True)
class RouteFloor:
    model_class: ModelClass
    effort: Effort


@dataclass(frozen=True, slots=True)
class Route:
    model_class: ModelClass
    effort: Effort
    runtime: str | None
    model: str | None
    correction: RouteFloor | None


@dataclass(frozen=True, slots=True)
class Routine:
    pass


@dataclass(frozen=True, slots=True)
class OwnerGate:
    gate: str | None
    label: str | None
    scope: str


@dataclass(frozen=True, slots=True)
class ExternalGate:
    gate: str | None
    label: str | None
    scope: str


type Authority = Routine | OwnerGate | ExternalGate


@dataclass(frozen=True, slots=True)
class Research:
    need: Literal["none", "optional", "required"]
    question: str | None
    notes: str | None


@dataclass(frozen=True, slots=True)
class Item:
    id: EntityId
    key: str
    phase: str
    title: str
    summary: str
    why: str
    work_kind: WorkKind
    scope: Scope | None
    depends_on: tuple[str, ...]
    relations: tuple[Relation, ...]
    implements: tuple[str, ...]
    decisions: tuple[str, ...]
    skills: tuple[SkillReq, ...]
    reads: tuple[Read, ...]
    examples: tuple[Read, ...]
    change_hints: tuple[ChangeHint, ...]
    artifacts: tuple[ArtifactDecl, ...]
    rules: tuple[str, ...]
    guidance_md: str | None
    deliverables: tuple[str, ...]
    route: Route | None
    work_policy: WorkPolicyOverride | None
    review: ReviewRequirement
    authority: Authority
    research: Research | None
    unit_strategy: Strategy
    sections: tuple[Section, ...]


class Intensity(StrEnum):
    LIGHT = "light"
    MEDIUM = "medium"
    HEAVY = "heavy"


class RoleName(StrEnum):
    SCOUT = "scout"
    EXECUTOR = "executor"
    REVIEWER = "reviewer"
    TRIAGER = "triager"
    ADVISOR = "advisor"
    RESEARCHER = "researcher"
    REGISTRAR = "registrar"


@dataclass(frozen=True, slots=True)
class WorkPolicyOverride:
    """Partial work policy of an item or unit (planning §4.2.1).

    ``None`` members are absent (inherit); ``WorkPolicyOverride()`` is the explicit empty ``{}``.
    Only what was declared is stored: no default or effective value is ever added.
    """

    role_intensity: Mapping[RoleName, Intensity] | None = None
    verification_intensity: Intensity | None = None

    def __post_init__(self) -> None:
        if self.role_intensity is not None:
            object.__setattr__(self, "role_intensity", MappingProxyType(dict(self.role_intensity)))

    def merged_over(self, base: WorkPolicyOverride | None) -> WorkPolicyOverride:
        """This override applied over ``base``: roles merge by key, absent members are inherited."""
        if base is None:
            return self
        roles: dict[RoleName, Intensity] | None = None
        if base.role_intensity is not None or self.role_intensity is not None:
            roles = {**(base.role_intensity or {}), **(self.role_intensity or {})}
        verification = self.verification_intensity or base.verification_intensity
        return WorkPolicyOverride(roles, verification)


def work_policy_from_doc(doc: Mapping[str, JsonValue]) -> WorkPolicyOverride:
    roles = cast("Mapping[str, str] | None", doc.get("role_intensity"))
    verification = doc.get("verification_intensity")
    return WorkPolicyOverride(
        None if roles is None else {RoleName(name): Intensity(level) for name, level in roles.items()},
        None if verification is None else Intensity(str(verification)),
    )


def work_policy_to_doc(policy: WorkPolicyOverride) -> JsonObject:
    doc: JsonObject = {}
    if policy.role_intensity is not None:
        doc["role_intensity"] = {role.value: level.value for role, level in policy.role_intensity.items()}
    if policy.verification_intensity is not None:
        doc["verification_intensity"] = policy.verification_intensity.value
    return doc


def route_from_doc(doc: Mapping[str, JsonValue]) -> Route:
    correction = cast("Mapping[str, str] | None", doc.get("correction"))
    return Route(
        ModelClass(str(doc["class"])),
        Effort(str(doc["effort"])),
        text_of(doc, "runtime"),
        text_of(doc, "model"),
        None
        if correction is None
        else RouteFloor(ModelClass(correction["class"]), Effort(correction["effort"])),
    )


def route_to_doc(route: Route) -> JsonObject:
    return compact(
        {
            "class": route.model_class.value,
            "effort": route.effort.value,
            "runtime": route.runtime,
            "model": route.model,
            "correction": None
            if route.correction is None
            else {"class": route.correction.model_class.value, "effort": route.correction.effort.value},
        }
    )


def authority_from_doc(doc: Mapping[str, JsonValue] | None) -> Authority:
    if doc is None or doc["kind"] == "routine":
        return Routine()
    gate, label, scope = text_of(doc, "gate"), text_of(doc, "label"), str(doc["scope"])
    return OwnerGate(gate, label, scope) if doc["kind"] == "owner_gate" else ExternalGate(gate, label, scope)


def authority_to_doc(authority: Authority) -> JsonObject:
    match authority:
        case Routine():
            return {"kind": "routine"}
        case OwnerGate():
            return compact(
                {
                    "kind": "owner_gate",
                    "gate": authority.gate,
                    "label": authority.label,
                    "scope": authority.scope,
                }
            )
        case ExternalGate():
            return compact(
                {
                    "kind": "external_gate",
                    "gate": authority.gate,
                    "label": authority.label,
                    "scope": authority.scope,
                }
            )


def item_from_doc(doc: Mapping[str, JsonValue]) -> Item:
    def records(name: str) -> list[Mapping[str, JsonValue]]:
        return cast("list[Mapping[str, JsonValue]]", doc.get(name, []))

    scope = cast("Mapping[str, JsonValue] | None", doc.get("scope"))
    route = cast("Mapping[str, JsonValue] | None", doc.get("route"))
    research = cast("Mapping[str, JsonValue] | None", doc.get("research"))
    policy = cast("Mapping[str, JsonValue] | None", doc.get("work_policy"))
    return Item(
        id=entity_id_of(doc),
        key=str(doc["key"]),
        phase=str(doc["phase"]),
        title=str(doc["title"]),
        summary=str(doc["summary"]),
        why=str(doc["why"]),
        work_kind=WorkKind(str(doc.get("work_kind", "code"))),
        scope=None if scope is None else scope_from_doc(scope),
        depends_on=strs_of(doc, "depends_on"),
        relations=tuple(
            Relation(str(r["target"]), str(r["relation"]), text_of(r, "note")) for r in records("relations")
        ),
        implements=strs_of(doc, "implements"),
        decisions=strs_of(doc, "decisions"),
        skills=tuple(SkillReq(str(s["key"]), text_of(s, "version")) for s in records("skills")),
        reads=tuple(read_from_doc(r) for r in records("reads")),
        examples=tuple(read_from_doc(r) for r in records("examples")),
        change_hints=tuple(
            ChangeHint(
                str(h["mount"]),
                str(h["pattern"]),
                cast("Literal['create', 'modify', 'delete', 'any']", h["change"]),
                text_of(h, "note"),
            )
            for h in records("change_hints")
        ),
        artifacts=tuple(
            ArtifactDecl(
                text_of(a, "key"),
                str(a["mount"]),
                str(a["path"]),
                cast("Literal['input', 'output']", a["role"]),
                text_of(a, "note"),
            )
            for a in records("artifacts")
        ),
        rules=strs_of(doc, "rules"),
        guidance_md=text_of(doc, "guidance_md"),
        deliverables=strs_of(doc, "deliverables"),
        route=None if route is None else route_from_doc(route),
        work_policy=None if policy is None else work_policy_from_doc(policy),
        review=review_from_doc(cast("Mapping[str, JsonValue]", doc["review"])),
        authority=authority_from_doc(cast("Mapping[str, JsonValue] | None", doc.get("authority"))),
        research=None
        if research is None
        else Research(
            cast("Literal['none', 'optional', 'required']", research["need"]),
            text_of(research, "question"),
            text_of(research, "notes"),
        ),
        unit_strategy=Strategy(str(doc.get("unit_strategy", "dag"))),
        sections=sections_from_doc(doc),
    )


def item_to_doc(item: Item) -> JsonObject:
    doc = compact(
        {
            "id": str(item.id),
            "key": item.key,
            "phase": item.phase,
            "title": item.title,
            "summary": item.summary,
            "why": item.why,
            "work_kind": item.work_kind.value,
            "scope": None if item.scope is None else scope_to_doc(item.scope),
            "depends_on": list(item.depends_on),
            "relations": [
                compact({"target": r.target, "relation": r.relation, "note": r.note}) for r in item.relations
            ],
            "implements": list(item.implements),
            "decisions": list(item.decisions),
            "skills": [compact({"key": s.key, "version": s.version}) for s in item.skills],
            "reads": [read_to_doc(r) for r in item.reads],
            "examples": [read_to_doc(r) for r in item.examples],
            "change_hints": [
                compact({"mount": h.mount, "pattern": h.pattern, "change": h.change, "note": h.note})
                for h in item.change_hints
            ],
            "artifacts": [
                compact({"key": a.key, "mount": a.mount, "path": a.path, "role": a.role, "note": a.note})
                for a in item.artifacts
            ],
            "rules": list(item.rules),
            "guidance_md": item.guidance_md,
            "deliverables": list(item.deliverables),
            "route": None if item.route is None else route_to_doc(item.route),
            "review": review_to_doc(item.review),
            "authority": authority_to_doc(item.authority),
            "research": None
            if item.research is None
            else compact(
                {"need": item.research.need, "question": item.research.question, "notes": item.research.notes}
            ),
            "unit_strategy": item.unit_strategy.value,
            "sections": sections_to_doc(item.sections),
        }
    )
    if item.work_policy is not None:
        doc["work_policy"] = work_policy_to_doc(item.work_policy)
    return doc
