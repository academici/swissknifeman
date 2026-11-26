"""Units: typed records and document form (planning §4.2)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Literal, cast

from skm.modules.planning.domain.check_spec import (
    CheckKind,
    CommandDefinition,
    ShellDefinition,
    definition_from_doc,
    definition_to_doc,
)
from skm.modules.planning.domain.item import (
    WorkKind,
    WorkPolicyOverride,
    route_from_doc,
    route_to_doc,
    work_policy_from_doc,
    work_policy_to_doc,
)
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

if TYPE_CHECKING:
    from collections.abc import Mapping

    from skm.kernel.ids import EntityId
    from skm.kernel.json_types import JsonObject, JsonValue
    from skm.modules.planning.domain.brief import Section
    from skm.modules.planning.domain.item import Route
    from skm.modules.planning.domain.reads import Read


class UnitKind(StrEnum):
    PREPARATION = "preparation"
    IMPLEMENTATION = "implementation"
    REVIEW = "review"
    VERIFICATION = "verification"
    INTEGRATION = "integration"
    COMMAND = "command"


class UnitMode(StrEnum):
    SELF = "self"
    DELEGATE = "delegate"
    EITHER = "either"


@dataclass(frozen=True, slots=True)
class WriteScopeEntry:
    mount: str
    pattern: str


@dataclass(frozen=True, slots=True)
class OutputEntry:
    mount: str
    path: str
    note: str | None


@dataclass(frozen=True, slots=True)
class UnitCommand:
    kind: Literal["command", "shell"]
    definition: CommandDefinition | ShellDefinition


@dataclass(frozen=True, slots=True)
class Unit:
    id: EntityId
    key: str
    title: str
    goal: str
    unit_kind: UnitKind
    work_kind: WorkKind | None
    mode: UnitMode
    parent: str | None
    write_scope: tuple[WriteScopeEntry, ...]
    reads: tuple[Read, ...]
    depends_on: tuple[str, ...]
    checks: tuple[str, ...]
    route: Route | None
    work_policy: WorkPolicyOverride | None
    instructions_md: str | None
    command: UnitCommand | None
    outputs: tuple[OutputEntry, ...]
    implements: tuple[str, ...]
    sections: tuple[Section, ...]


def unit_from_doc(doc: Mapping[str, JsonValue]) -> Unit:
    def records(name: str) -> list[Mapping[str, JsonValue]]:
        return cast("list[Mapping[str, JsonValue]]", doc.get(name, []))

    route = cast("Mapping[str, JsonValue] | None", doc.get("route"))
    policy = cast("Mapping[str, JsonValue] | None", doc.get("work_policy"))
    command = cast("Mapping[str, JsonValue] | None", doc.get("command"))
    work_kind = text_of(doc, "work_kind")
    return Unit(
        id=entity_id_of(doc),
        key=str(doc["key"]),
        title=str(doc["title"]),
        goal=str(doc["goal"]),
        unit_kind=UnitKind(str(doc.get("unit_kind", "implementation"))),
        work_kind=None if work_kind is None else WorkKind(work_kind),
        mode=UnitMode(str(doc.get("mode", "either"))),
        parent=text_of(doc, "parent"),
        write_scope=tuple(
            WriteScopeEntry(str(w["mount"]), str(w["pattern"])) for w in records("write_scope")
        ),
        reads=tuple(read_from_doc(r) for r in records("reads")),
        depends_on=strs_of(doc, "depends_on"),
        checks=strs_of(doc, "checks"),
        route=None if route is None else route_from_doc(route),
        work_policy=None if policy is None else work_policy_from_doc(policy),
        instructions_md=text_of(doc, "instructions_md"),
        command=None
        if command is None
        else UnitCommand(
            cast("Literal['command', 'shell']", command["kind"]),
            cast(
                "CommandDefinition | ShellDefinition",
                definition_from_doc(
                    CheckKind(str(command["kind"])), cast("Mapping[str, JsonValue]", command["definition"])
                ),
            ),
        ),
        outputs=tuple(
            OutputEntry(str(o["mount"]), str(o["path"]), text_of(o, "note")) for o in records("outputs")
        ),
        implements=strs_of(doc, "implements"),
        sections=sections_from_doc(doc),
    )


def unit_to_doc(unit: Unit) -> JsonObject:
    doc = compact(
        {
            "id": str(unit.id),
            "key": unit.key,
            "title": unit.title,
            "goal": unit.goal,
            "unit_kind": unit.unit_kind.value,
            "work_kind": None if unit.work_kind is None else unit.work_kind.value,
            "mode": unit.mode.value,
            "parent": unit.parent,
            "write_scope": [{"mount": w.mount, "pattern": w.pattern} for w in unit.write_scope],
            "reads": [read_to_doc(r) for r in unit.reads],
            "depends_on": list(unit.depends_on),
            "checks": list(unit.checks),
            "route": None if unit.route is None else route_to_doc(unit.route),
            "instructions_md": unit.instructions_md,
            "command": None
            if unit.command is None
            else {"kind": unit.command.kind, "definition": definition_to_doc(unit.command.definition)},
            "outputs": [compact({"mount": o.mount, "path": o.path, "note": o.note}) for o in unit.outputs],
            "implements": list(unit.implements),
            "sections": sections_to_doc(unit.sections),
        }
    )
    if unit.work_policy is not None:
        doc["work_policy"] = work_policy_to_doc(unit.work_policy)
    return doc
