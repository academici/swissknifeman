"""Routing rules: runtimes, models and skills the catalogs do not know (planning §5.7, module ``routing``).

An absent catalog (``None``) is "not available or switched off", never "empty": it reports nothing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from skm.modules.planning.domain.validation.context import Locator
from skm.modules.planning.domain.validation.findings import FindingCode, finding

if TYPE_CHECKING:
    from collections.abc import Iterator

    from skm.kernel.ids import EntityId
    from skm.modules.planning.domain.item import Route
    from skm.modules.planning.domain.validation.context import ValidationContext
    from skm.modules.planning.domain.validation.findings import Finding


def _routes(ctx: ValidationContext) -> Iterator[tuple[str, EntityId, Route]]:
    """``(entity key, entity id, route)`` of every item and unit that declares a route."""
    for item in ctx.spec.items:
        if item.route is not None:
            yield item.key, item.id, item.route
    for unit in ctx.spec.units:
        if unit.route is not None:
            yield unit.key, unit.id, unit.route


def route_unknown_model(ctx: ValidationContext) -> Iterator[Finding]:
    catalog, loc = ctx.runtime_catalog, Locator(ctx.document)
    if catalog is None:
        return
    for key, entity_id, route in _routes(ctx):
        models = None if route.runtime is None else catalog.get(route.runtime)
        if models is not None and route.model is not None and route.model not in models:
            yield finding(
                FindingCode.ROUTE_UNKNOWN_MODEL,
                f"{key} routes to model {route.model}, which runtime {route.runtime} does not list",
                key=key,
                entity_id=entity_id,
                pointer=loc.pointer(key, "route", "model"),
                details={"runtime": route.runtime or "", "model": route.model},
            )


def route_unknown_runtime(ctx: ValidationContext) -> Iterator[Finding]:
    catalog, loc = ctx.runtime_catalog, Locator(ctx.document)
    if catalog is None:
        return
    for key, entity_id, route in _routes(ctx):
        if route.runtime is not None and route.runtime not in catalog:
            yield finding(
                FindingCode.ROUTE_UNKNOWN_RUNTIME,
                f"{key} routes to runtime {route.runtime}, which the runtime catalog does not have",
                key=key,
                entity_id=entity_id,
                pointer=loc.pointer(key, "route", "runtime"),
                details={"runtime": route.runtime},
            )


def skill_unknown(ctx: ValidationContext) -> Iterator[Finding]:
    known, loc = ctx.known_skills, Locator(ctx.document)
    if known is None:
        return
    for item in ctx.spec.items:
        for n, skill in enumerate(item.skills):
            if skill.key not in known:
                yield finding(
                    FindingCode.SKILL_UNKNOWN,
                    f"{item.key} requires skill {skill.key}, which the registry does not know",
                    key=item.key,
                    entity_id=item.id,
                    pointer=loc.pointer(item.key, "skills", n, "key"),
                    details={"skill": skill.key},
                )


# Inside the module the rules follow the alphabetical order of their codes.
RULES: Final = (route_unknown_model, route_unknown_runtime, skill_unknown)
