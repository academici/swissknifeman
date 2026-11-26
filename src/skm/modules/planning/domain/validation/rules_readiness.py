"""Readiness rules: what a detailed phase must say, skeletons, default texts (planning §5.7, ``readiness``).

``incomplete`` is the authoring rule of planning; execution readiness (execution §5.12) is a separate report.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from skm.modules.planning.domain.check_spec import CheckCategory
from skm.modules.planning.domain.phase import DesignState
from skm.modules.planning.domain.validation.context import Locator
from skm.modules.planning.domain.validation.findings import FindingCode, finding

if TYPE_CHECKING:
    from collections.abc import Iterator

    from skm.modules.planning.domain.item import Item
    from skm.modules.planning.domain.specification import Specification
    from skm.modules.planning.domain.validation.context import ValidationContext
    from skm.modules.planning.domain.validation.findings import Finding


def _same(left: str | None, right: str) -> bool:
    return left is not None and left.strip() == right.strip()


def context_default(ctx: ValidationContext) -> Iterator[Finding]:
    spec, loc = ctx.spec, Locator(ctx.document)
    for field, text in (("goal", spec.goal), ("context_md", spec.context_md)):
        if _same(text, spec.title):
            yield finding(
                FindingCode.CONTEXT_DEFAULT,
                f"the plan {field} still equals the title; write it",
                pointer=f"/{field}",
                details={"field": field},
            )
    for phase in spec.phases:
        for field, text in (("goal", phase.goal), ("context_md", phase.context_md)):
            if _same(text, phase.title):
                yield finding(
                    FindingCode.CONTEXT_DEFAULT,
                    f"{phase.key} {field} still equals its title; write it",
                    key=phase.key,
                    entity_id=phase.id,
                    pointer=loc.pointer(phase.key, field),
                    details={"field": field},
                )
    for unit in spec.units:
        if _same(unit.goal, unit.title):
            yield finding(
                FindingCode.CONTEXT_DEFAULT,
                f"{unit.key} goal still equals its title; write it",
                key=unit.key,
                entity_id=unit.id,
                pointer=loc.pointer(unit.key, "goal"),
                details={"field": "goal"},
            )


def _owned(spec: Specification, item: Item) -> frozenset[str]:
    """Keys of the item and of its units: the owners whose checks and criteria count for the item."""
    return frozenset((item.key, *(unit.key for unit in spec.units_of(item.key))))


def incomplete(ctx: ValidationContext) -> Iterator[Finding]:
    spec, loc = ctx.spec, Locator(ctx.document)
    detailed = {phase.key for phase in spec.phases if phase.design_state is DesignState.DETAILED}
    for phase in spec.phases:
        if phase.key in detailed and not spec.items_of(phase.key):
            yield finding(
                FindingCode.INCOMPLETE,
                f"detailed phase {phase.key} has no items",
                key=phase.key,
                entity_id=phase.id,
                pointer=loc.pointer(phase.key),
                details={"missing": "items"},
            )
    for item in spec.items:
        if item.phase not in detailed:
            continue
        owners = _owned(spec, item)
        lacking: list[tuple[str, str]] = []  # (missing part, pointer)
        if item.scope is None or not item.scope.include:
            lacking.append(("scope.include", loc.pointer(item.key, "scope") or ""))
        has_check = any(c.category is CheckCategory.ACCEPTANCE and c.owner in owners for c in spec.checks)
        has_criterion = any(c.owner in owners for c in spec.criteria)
        if not has_check and not has_criterion:
            lacking.append(("acceptance", loc.pointer(item.key) or ""))
        if not item.deliverables:
            lacking.append(("deliverables", loc.pointer(item.key, "deliverables") or ""))
        if not (item.reads or item.change_hints or item.guidance_md or item.sections):
            lacking.append(("reads", loc.pointer(item.key, "reads") or ""))
        for part, pointer in lacking:
            yield finding(
                FindingCode.INCOMPLETE,
                f"detailed item {item.key} needs {part}",
                key=item.key,
                entity_id=item.id,
                pointer=pointer,
                details={"missing": part},
            )


def phase_skeleton(ctx: ValidationContext) -> Iterator[Finding]:
    loc = Locator(ctx.document)
    for phase in ctx.spec.phases:
        if phase.design_state is DesignState.SKELETON:
            yield finding(
                FindingCode.PHASE_SKELETON,
                f"phase {phase.key} is a skeleton; execution readiness will refuse its tasks",
                key=phase.key,
                entity_id=phase.id,
                pointer=loc.pointer(phase.key, "design_state"),
            )


def research_question_missing(ctx: ValidationContext) -> Iterator[Finding]:
    loc = Locator(ctx.document)
    for item in ctx.spec.items:
        research = item.research
        if research is not None and research.need == "required" and not (research.question or "").strip():
            yield finding(
                FindingCode.RESEARCH_QUESTION_MISSING,
                f"{item.key} requires research but names no question",
                key=item.key,
                entity_id=item.id,
                pointer=loc.pointer(item.key, "research"),
            )


RULES: Final = (context_default, incomplete, phase_skeleton, research_question_missing)
