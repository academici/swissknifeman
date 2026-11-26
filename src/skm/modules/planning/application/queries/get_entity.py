"""``planning.get_entity`` (planning §8.1): return ``EntityView`` with links and provenance."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from skm.application_bus.registry import QuerySpec
from skm.kernel.ids import ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.planning.application.source_reader import (
    compute_entity_links,
    find_raw_entity,
    first_revision_no_of,
    read_source,
)
from skm.modules.planning.domain.specification import EntityKind
from skm.modules.planning.generated.queries import GetEntity
from skm.modules.planning.generated.views import (
    EntityView,
    EntityViewDefsCheck,
    EntityViewDefsCriterion,
    EntityViewDefsDecision,
    EntityViewDefsItem,
    EntityViewDefsMaterial,
    EntityViewDefsPhase,
    EntityViewDefsRequirement,
    EntityViewDefsUnit,
    EntityViewLinks,
    entity_view_defs_check_from_json,
    entity_view_defs_material_from_json,
    entity_view_defs_source_view_from_json,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from skm.application_bus.context import QueryContext
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["SPEC", "handle", "scope_of"]


def scope_of(query: GetEntity) -> ScopeRef:
    return ScopeRef(ScopeKind.PLAN, ScopeId(query.plan_id))


type _EntityDocument = (
    EntityViewDefsPhase
    | EntityViewDefsItem
    | EntityViewDefsUnit
    | EntityViewDefsRequirement
    | EntityViewDefsCriterion
    | EntityViewDefsCheck
    | EntityViewDefsDecision
    | EntityViewDefsMaterial
)


def _decode_entity_document(kind: EntityKind, raw: Mapping[str, Any]) -> _EntityDocument:
    match kind:
        case EntityKind.PHASE:
            return EntityViewDefsPhase.from_json(raw)
        case EntityKind.ITEM:
            return EntityViewDefsItem.from_json(raw)
        case EntityKind.UNIT:
            return EntityViewDefsUnit.from_json(raw)
        case EntityKind.REQUIREMENT:
            return EntityViewDefsRequirement.from_json(raw)
        case EntityKind.CRITERION:
            return EntityViewDefsCriterion.from_json(raw)
        case EntityKind.CHECK:
            return entity_view_defs_check_from_json(raw)
        case EntityKind.DECISION:
            return EntityViewDefsDecision.from_json(raw)
        case EntityKind.MATERIAL:
            return entity_view_defs_material_from_json(raw)


def handle(query: GetEntity, _ctx: QueryContext, uow: UnitOfWork) -> EntityView:
    source = read_source(
        uow,
        plan_id=query.plan_id,
        revision_id=query.revision_id,
        draft_id=query.draft_id,
        expected_edit_version=query.expected_edit_version,
    )
    entity_id, kind, display_key, raw_obj = find_raw_entity(source, query.ref)
    links = compute_entity_links(uow, source, entity_id)
    first_rev_no = first_revision_no_of(uow, source.plan.id, entity_id)
    revision_id = source.revision.id if source.revision is not None else None

    return EntityView(
        entity_id=entity_id,
        entity_kind=kind.value,
        display_key=display_key,
        revision_id=revision_id,
        first_revision_no=first_rev_no,
        source=entity_view_defs_source_view_from_json(source.source_view_json()),
        document=_decode_entity_document(kind, raw_obj),
        links=EntityViewLinks(
            prerequisites=tuple(m.display_key for m in links.prerequisites),
            dependents=tuple(m.display_key for m in links.dependents),
            criteria=tuple(m.display_key for m in links.criteria),
            checks=tuple(m.display_key for m in links.checks),
            decisions=tuple(m.display_key for m in links.decisions),
            materials=tuple(m.display_key for m in links.materials),
            requirements=tuple(m.display_key for m in links.requirements),
        ),
    )


SPEC = QuerySpec(
    name="planning.get_entity",
    dto=GetEntity,
    result=EntityView,
    permission="plan.read",
    scope_of=scope_of,
    handler=handle,
)
