"""Shared read-source loader and view builders for planning queries (planning §8.1).

Loads either a published revision or an exact draft snapshot (``expected_edit_version``) in the caller's
unit of work, verifies workspace and plan ownership, and provides consistent entity, outline, link, and
tree helpers from that single document.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, cast
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, ValidationFailed
from skm.kernel.ids import EntityId, PlanId, ProjectId, RevisionId
from skm.modules.planning.domain import draft as draft_rules
from skm.modules.planning.domain.canonical import normalize_document, specification_digest
from skm.modules.planning.domain.draft import Draft, DraftId
from skm.modules.planning.domain.member import EntityLinks, MemberRef
from skm.modules.planning.domain.plan import Plan
from skm.modules.planning.domain.review_requirement import review_to_doc
from skm.modules.planning.domain.revision import RevisionMeta
from skm.modules.planning.domain.specification import (
    EntityKind,
    SpecEntity,
    Specification,
    from_document,
)
from skm.modules.planning.generated.views import EntityPageViewItemsItem
from skm.modules.planning.ports import (
    DraftRepository,
    PlanningQueries,
    PlanRepository,
    RevisionRepository,
    SpecificationDoc,
)
from skm.modules.workspace import public as workspace

if TYPE_CHECKING:
    from skm.kernel.json_types import JsonObject, JsonValue
    from skm.kernel.ports_uow import UnitOfWork

__all__ = [
    "KIND_ORDER",
    "LoadedSource",
    "build_entity_outlines",
    "build_tree",
    "compute_entity_links",
    "find_raw_entity",
    "first_revision_no_of",
    "read_source",
    "require_plan",
    "require_project",
    "require_revision_in_plan",
]

KIND_ORDER: tuple[EntityKind, ...] = (
    EntityKind.PHASE,
    EntityKind.ITEM,
    EntityKind.UNIT,
    EntityKind.REQUIREMENT,
    EntityKind.CRITERION,
    EntityKind.CHECK,
    EntityKind.DECISION,
    EntityKind.MATERIAL,
)

_KIND_TO_ARRAY: Mapping[EntityKind, str] = {
    EntityKind.PHASE: "phases",
    EntityKind.ITEM: "items",
    EntityKind.UNIT: "units",
    EntityKind.REQUIREMENT: "requirements",
    EntityKind.CRITERION: "criteria",
    EntityKind.CHECK: "checks",
    EntityKind.DECISION: "decisions",
    EntityKind.MATERIAL: "materials",
}


def require_plan(uow: UnitOfWork, plan_id: UUID) -> Plan:
    """Load ``plan_id`` (``NOT_FOUND`` when missing)."""
    return uow.repo(PlanRepository).get(PlanId(plan_id))


def require_project(uow: UnitOfWork, project_id: UUID) -> ProjectId:
    """Verify ``project_id`` exists (``NOT_FOUND`` when missing)."""
    pid = ProjectId(project_id)
    workspace.workspace_of_project(uow, pid)
    return pid


def require_revision_in_plan(meta: RevisionMeta, plan_id: PlanId) -> None:
    """Verify ``meta`` belongs to ``plan_id`` (``NOT_FOUND`` when mismatched)."""
    if meta.plan_id != plan_id:
        raise NotFound(
            ErrorCode.NOT_FOUND,
            "revision not found",
            details={"kind": "revision", "ref": str(meta.id)},
        )


@dataclass(frozen=True, slots=True)
class LoadedSource:
    """Resolved specification source (revision or draft) for consistent query reads."""

    plan: Plan
    kind: Literal["revision", "draft"]
    document: SpecificationDoc
    document_digest: str
    spec: Specification
    revision: RevisionMeta | None = None
    draft: Draft | None = None

    def source_view_json(self) -> JsonObject:
        if self.kind == "revision" and self.revision is not None:
            return {
                "kind": "revision",
                "plan_id": str(self.plan.id),
                "document_digest": self.document_digest,
                "revision_id": str(self.revision.id),
            }
        if self.draft is None:
            raise ValueError("draft source requires draft metadata")
        return {
            "kind": "draft",
            "plan_id": str(self.plan.id),
            "document_digest": self.document_digest,
            "draft_id": str(self.draft.id),
            "edit_version": self.draft.edit_version,
        }


def read_source(
    uow: UnitOfWork,
    *,
    plan_id: UUID,
    revision_id: UUID | None = None,
    draft_id: UUID | None = None,
    expected_edit_version: int | None = None,
) -> LoadedSource:
    """Load a revision or draft source once in the readonly UoW (planning §8.1)."""
    has_rev = revision_id is not None
    has_draft = draft_id is not None
    has_ver = expected_edit_version is not None

    if has_rev and not has_draft and not has_ver:
        plan = require_plan(uow, plan_id)
        rev_repo = uow.repo(RevisionRepository)
        meta = rev_repo.get_meta(RevisionId(revision_id))
        require_revision_in_plan(meta, plan.id)
        doc = normalize_document(rev_repo.get_document(meta.id))
        digest = specification_digest(doc)
        spec, _ = from_document(doc)
        return LoadedSource(
            plan=plan,
            kind="revision",
            document=doc,
            document_digest=digest,
            spec=spec,
            revision=meta,
            draft=None,
        )

    if (
        has_draft
        and has_ver
        and not has_rev
        and not isinstance(expected_edit_version, bool)
        and expected_edit_version >= 1
    ):
        plan = require_plan(uow, plan_id)
        draft = uow.repo(DraftRepository).get(DraftId(draft_id))
        draft_rules.require_in_plan(draft, plan.id)
        if draft.workspace_id != plan.workspace_id:
            raise NotFound(
                ErrorCode.NOT_FOUND,
                "draft not found",
                details={"kind": "draft", "ref": str(draft_id)},
            )
        draft_rules.require_edit_version(draft, expected_edit_version)
        doc = normalize_document(draft.document)
        digest = specification_digest(doc)
        spec, _ = from_document(doc)
        return LoadedSource(
            plan=plan,
            kind="draft",
            document=doc,
            document_digest=digest,
            spec=spec,
            revision=None,
            draft=draft,
        )

    raise ValidationFailed(
        ErrorCode.SCHEMA_INVALID,
        "exactly one of revision_id or (draft_id, expected_edit_version >= 1) is required",
        details={
            "issues": [
                {
                    "pointer": "",
                    "message": "specify either revision_id or draft_id with expected_edit_version >= 1",
                    "schema_pointer": "",
                }
            ]
        },
    )


def build_tree(spec: Specification) -> JsonObject:
    """Build the full phase/item/unit hierarchy for ``get_revision(include_tree=true)`` (planning §8)."""
    phases_out: list[JsonValue] = []
    for phase in spec.phases:
        items_out: list[JsonValue] = []
        for item in spec.items_of(phase.key):
            units_out: list[JsonValue] = [
                {"key": unit.key, "title": unit.title} for unit in spec.units_of(item.key)
            ]
            items_out.append(
                {
                    "key": item.key,
                    "title": item.title,
                    "work_kind": item.work_kind.value,
                    "review_mode": str(review_to_doc(item.review)["mode"]),
                    "units": units_out,
                }
            )
        phases_out.append(
            {
                "key": phase.key,
                "title": phase.title,
                "design_state": phase.design_state.value,
                "items": items_out,
            }
        )
    return {"phases": phases_out}


def _display_key_of_raw(kind: EntityKind, raw: Mapping[str, Any]) -> str:
    key = str(raw.get("key", ""))
    if kind is EntityKind.MATERIAL:
        return key if key.startswith("material/") else f"material/{key}"
    if kind is EntityKind.CHECK:
        owner = str(raw.get("owner", ""))
        return key if ":" in key else f"{owner}:{key}"
    return key


def find_raw_entity(source: LoadedSource, ref: str) -> tuple[EntityId, EntityKind, str, JsonObject]:
    """Resolve ``ref`` (display key or ``entity:<uuid>``) in ``source.document``."""
    target_str = ref.strip()
    if not target_str:
        raise ValidationFailed(
            ErrorCode.INVALID_REFERENCE,
            "entity reference cannot be empty",
            details={"ref": ref},
        )
    want_id: UUID | None = None
    if target_str.startswith("entity:"):
        raw_uuid = target_str[7:]
        try:
            want_id = UUID(raw_uuid)
        except ValueError as err:
            raise ValidationFailed(
                ErrorCode.INVALID_REFERENCE,
                "invalid entity UUID reference",
                details={"ref": ref},
            ) from err

    for kind in KIND_ORDER:
        arr = source.document.get(_KIND_TO_ARRAY[kind])
        if not isinstance(arr, list):
            continue
        for item in arr:
            if not isinstance(item, dict):
                continue
            raw_obj = cast("JsonObject", item)
            raw_id = raw_obj.get("id")
            if not isinstance(raw_id, str):
                continue
            try:
                eid = EntityId(UUID(raw_id))
            except ValueError:
                continue
            dkey = _display_key_of_raw(kind, raw_obj)
            if want_id is not None:
                if UUID(str(eid)) == want_id:
                    return eid, kind, dkey, raw_obj
            elif dkey == target_str or (
                kind is EntityKind.MATERIAL and str(raw_obj.get("key", "")) == target_str
            ):
                return eid, kind, dkey, raw_obj

    raise NotFound(
        ErrorCode.NOT_FOUND,
        "entity not found",
        details={"kind": "entity", "ref": ref},
    )


def build_entity_outlines(source: LoadedSource) -> tuple[EntityPageViewItemsItem, ...]:
    """Build ordered ``EntityOutline`` items across the full source (planning §8.1)."""
    id_by_key: dict[str, UUID] = {}
    records: list[tuple[EntityKind, int, UUID, str, str, Mapping[str, Any]]] = []

    for kind in KIND_ORDER:
        arr = source.document.get(_KIND_TO_ARRAY[kind])
        if not isinstance(arr, list):
            continue
        for pos, item in enumerate(arr):
            if not isinstance(item, dict):
                continue
            raw_id = item.get("id")
            if not isinstance(raw_id, str):
                continue
            eid = UUID(raw_id)
            dkey = _display_key_of_raw(kind, item)
            id_by_key[dkey] = eid
            raw_title = item.get("title")
            title = str(raw_title) if isinstance(raw_title, str) and raw_title else dkey
            records.append((kind, pos, eid, dkey, title, item))

    parent_by_id: dict[UUID, UUID | None] = {}
    children_counts: dict[UUID, int] = {rec[2]: 0 for rec in records}

    for kind, _pos, eid, dkey, _title, raw in records:
        parent_id: UUID | None = None
        if kind is EntityKind.ITEM:
            phase_key = raw.get("phase")
            if isinstance(phase_key, str):
                parent_id = id_by_key.get(phase_key)
        elif kind is EntityKind.UNIT:
            item_key = dkey.split("/", 1)[0]
            parent_ref = raw.get("parent")
            if isinstance(parent_ref, str) and parent_ref:
                qual_parent = parent_ref if "/" in parent_ref else f"{item_key}/{parent_ref}"
                parent_id = id_by_key.get(qual_parent)
            if parent_id is None:
                parent_id = id_by_key.get(item_key)
        elif kind in (EntityKind.CHECK, EntityKind.CRITERION):
            owner_key = raw.get("owner")
            if isinstance(owner_key, str):
                parent_id = id_by_key.get(owner_key)

        parent_by_id[eid] = parent_id
        if parent_id is not None and parent_id in children_counts:
            children_counts[parent_id] += 1

    kind_rank = {k: idx for idx, k in enumerate(KIND_ORDER)}
    records.sort(key=lambda r: (kind_rank[r[0]], r[1], r[2]))

    return tuple(
        EntityPageViewItemsItem(
            entity_id=eid,
            entity_kind=kind.value,
            display_key=dkey,
            title=title,
            parent_id=parent_by_id[eid],
            position=pos,
            children_count=children_counts[eid],
        )
        for kind, pos, eid, dkey, title, _raw in records
    )


def _safe_by_key(spec: Specification, key: str) -> SpecEntity | None:
    try:
        return spec.by_key(key)
    except NotFound:
        return None


def _resolve_ids(
    spec: Specification, keys: Sequence[str], *, check_owner: str | None = None
) -> list[EntityId]:
    out: list[EntityId] = []
    for k in keys:
        lookup = (k if ":" in k else f"{check_owner}:{k}") if check_owner is not None else k
        target = _safe_by_key(spec, lookup)
        if target is not None:
            out.append(target.id)
    return out


def _dependency_edges(spec: Specification) -> list[tuple[EntityId, EntityId]]:
    edges: list[tuple[EntityId, EntityId]] = []
    for pos, phase in enumerate(spec.phases):
        if phase.depends_on is None:
            if pos > 0:
                edges.append((phase.id, spec.phases[pos - 1].id))
        else:
            edges.extend((phase.id, tid) for tid in _resolve_ids(spec, phase.depends_on))
    for item in spec.items:
        edges.extend((item.id, tid) for tid in _resolve_ids(spec, item.depends_on))
    for unit in spec.units:
        item_key = unit.key.split("/", 1)[0]
        unit_refs = [r if "/" in r else f"{item_key}/{r}" for r in unit.depends_on]
        edges.extend((unit.id, tid) for tid in _resolve_ids(spec, unit_refs))
    return edges


def _collect_linked_ids(
    spec: Specification, entity_id: EntityId
) -> tuple[set[EntityId], set[EntityId], set[EntityId], set[EntityId], set[EntityId]]:
    crit_ids: set[EntityId] = set()
    check_ids: set[EntityId] = set()
    req_ids: set[EntityId] = set()
    for c in spec.criteria:
        owner_ent = _safe_by_key(spec, c.owner)
        c_owner_id = None if owner_ent is None else owner_ent.id
        c_checks = _resolve_ids(spec, c.checks, check_owner=c.owner.split("/", 1)[0])
        c_reqs = _resolve_ids(spec, c.requirements)
        if c_owner_id == entity_id or entity_id in c_checks or entity_id in c_reqs:
            crit_ids.add(c.id)
        if c.id == entity_id:
            check_ids.update(c_checks)
            req_ids.update(c_reqs)

    for chk in spec.checks:
        owner_ent = _safe_by_key(spec, chk.owner)
        if owner_ent is not None and owner_ent.id == entity_id:
            check_ids.add(chk.id)
    for u in spec.units:
        if u.id == entity_id:
            check_ids.update(_resolve_ids(spec, u.checks, check_owner=u.key.split("/", 1)[0]))
            req_ids.update(_resolve_ids(spec, u.implements))

    dec_ids: set[EntityId] = {d.id for d in spec.decisions if entity_id in _resolve_ids(spec, d.applies_to)}
    for item in spec.items:
        if item.id == entity_id:
            dec_ids.update(_resolve_ids(spec, item.decisions))
            req_ids.update(_resolve_ids(spec, item.implements))

    mat_ids: set[EntityId] = {m.id for m in spec.materials if entity_id in _resolve_ids(spec, m.applies_to)}
    req_ids.update(r.id for r in spec.requirements if entity_id in _resolve_ids(spec, r.owners))
    return crit_ids, check_ids, dec_ids, mat_ids, req_ids


def compute_entity_links(uow: UnitOfWork, source: LoadedSource, entity_id: EntityId) -> EntityLinks:
    """Compute ``EntityLinks`` for ``entity_id`` from ``source`` (planning §8.1)."""
    if source.kind == "revision" and source.revision is not None:
        return uow.repo(PlanningQueries).entity_links(source.revision.id, entity_id)

    spec = source.spec
    groups: tuple[tuple[EntityKind, Sequence[SpecEntity]], ...] = (
        (EntityKind.PHASE, spec.phases),
        (EntityKind.ITEM, spec.items),
        (EntityKind.UNIT, spec.units),
        (EntityKind.REQUIREMENT, spec.requirements),
        (EntityKind.CRITERION, spec.criteria),
        (EntityKind.CHECK, spec.checks),
        (EntityKind.DECISION, spec.decisions),
        (EntityKind.MATERIAL, spec.materials),
    )
    by_id: dict[EntityId, MemberRef] = {
        ent.id: MemberRef(
            entity_id=ent.id,
            entity_kind=kind,
            display_key=spec.display_key(ent),
            position=pos,
        )
        for kind, entities in groups
        for pos, ent in enumerate(entities)
    }
    edges = _dependency_edges(spec)
    prereqs = sorted(
        {by_id[p] for d, p in edges if d == entity_id and p in by_id},
        key=lambda m: (m.entity_kind.value, m.position),
    )
    dependents = sorted(
        {by_id[d] for d, p in edges if p == entity_id and d in by_id},
        key=lambda m: (m.entity_kind.value, m.position),
    )
    crit_ids, check_ids, dec_ids, mat_ids, req_ids = _collect_linked_ids(spec, entity_id)

    def _by_pos(ids: set[EntityId]) -> tuple[MemberRef, ...]:
        return tuple(sorted((by_id[i] for i in ids if i in by_id), key=lambda m: m.position))

    return EntityLinks(
        prerequisites=tuple(prereqs),
        dependents=tuple(dependents),
        criteria=_by_pos(crit_ids),
        checks=_by_pos(check_ids),
        decisions=_by_pos(dec_ids),
        materials=_by_pos(mat_ids),
        requirements=_by_pos(req_ids),
    )


_REV_PAGE_LIMIT = 100


def first_revision_no_of(uow: UnitOfWork, plan_id: PlanId, entity_id: EntityId) -> int | None:
    """Return the lowest ``revision_no`` of ``plan_id`` containing ``entity_id``, or ``None``."""
    rev_repo = uow.repo(RevisionRepository)
    queries = uow.repo(PlanningQueries)
    before: int | None = None
    found_no: int | None = None
    while True:
        batch = rev_repo.list_for_plan(plan_id, before_revision_no=before, limit=_REV_PAGE_LIMIT)
        if not batch:
            break
        for meta in batch:
            if queries.find_member_by_id(meta.id, entity_id) is not None:
                found_no = meta.revision_no
        if len(batch) < _REV_PAGE_LIMIT:
            break
        before = batch[-1].revision_no
    return found_no
