"""Memory implementation of ``PlanningQueries`` (planning §6, §8, §11)."""

import base64
import binascii
import json
from collections.abc import Sequence
from copy import deepcopy
from datetime import datetime
from typing import cast
from uuid import UUID

from skm.adapters.memory.core.state import MemoryBackendState
from skm.adapters.memory.planning.state import MemoryPlanningState, StoredRevision, planning_state
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError, NotFound, ValidationFailed
from skm.kernel.ids import EntityId, PlanId, ProjectId, RevisionId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.pagination import CURSOR_MAX_LENGTH, Cursor, Page
from skm.modules.planning.domain.draft import DraftState
from skm.modules.planning.domain.material import MaterialKind, MaterialRef
from skm.modules.planning.domain.member import EntityLinks, MemberRef
from skm.modules.planning.domain.plan import Plan, PlanPurpose
from skm.modules.planning.domain.reads import compact, format_timestamp, parse_timestamp
from skm.modules.planning.domain.specification import (
    EntityKind,
    SpecEntity,
    Specification,
    from_document,
)
from skm.modules.planning.ports import MaterialPin, PlanListState, PlanSummary

__all__ = ["MemoryPlanningQueries"]

_MAX_LIMIT = 200


def _bad_cursor() -> ValidationFailed:
    return ValidationFailed(
        ErrorCode.SCHEMA_INVALID, "cursor is not valid for this query", details={"field": "after"}
    )


def _encode_cursor(project_id: ProjectId, state: str, updated_at: str, plan_id: str) -> Cursor:
    payload = json.dumps(
        {"p": str(project_id), "s": state, "k": [updated_at, plan_id]},
        separators=(",", ":"),
    ).encode("utf-8")
    text = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    return Cursor(text)


def _decode_cursor(cursor: Cursor | None, project_id: ProjectId, state: str) -> tuple[datetime, UUID] | None:
    if cursor is None:
        return None
    text = str(cursor)
    if not 1 <= len(text) <= CURSOR_MAX_LENGTH or not text.isascii():
        raise _bad_cursor()
    try:
        raw = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
        doc: object = json.loads(raw.decode("utf-8"))
        if not isinstance(doc, dict):
            raise ValueError("not dict")
        body = cast("dict[str, object]", doc)
        if body.get("p") != str(project_id) or body.get("s") != state:
            raise ValueError("filter mismatch")
        keys = body.get("k")
        if not isinstance(keys, list):
            raise ValueError("key shape")
        vals = cast("list[object]", keys)
        if len(vals) != 2 or not all(isinstance(x, str) for x in vals):
            raise ValueError("key shape")
        ts_str, id_str = cast("list[str]", vals)
        moment = datetime.fromisoformat(ts_str)
        if moment.utcoffset() is None:
            raise ValueError("naive")
        return moment, UUID(id_str)
    except (binascii.Error, UnicodeDecodeError, ValueError, TypeError):
        raise _bad_cursor() from None


def _members(spec: Specification) -> tuple[dict[EntityId, MemberRef], list[MemberRef]]:
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
    refs = [
        MemberRef(
            entity_id=e.id,
            entity_kind=kind,
            display_key=spec.display_key(e),
            position=pos,
        )
        for kind, entities in groups
        for pos, e in enumerate(entities)
    ]
    return {m.entity_id: m for m in refs}, refs


def _dep_edges(spec: Specification) -> list[tuple[EntityId, EntityId]]:
    edges: list[tuple[EntityId, EntityId]] = []
    for pos, phase in enumerate(spec.phases):
        if phase.depends_on is None:
            if pos > 0:
                edges.append((phase.id, spec.phases[pos - 1].id))
        else:
            edges.extend((phase.id, spec.by_key(k).id) for k in phase.depends_on)
    edges.extend((item.id, spec.by_key(k).id) for item in spec.items for k in item.depends_on)
    for unit in spec.units:
        item_key = unit.key.split("/", 1)[0]
        edges.extend(
            (unit.id, spec.by_key(ref if "/" in ref else f"{item_key}/{ref}").id) for ref in unit.depends_on
        )
    return edges


class MemoryPlanningQueries:
    """In-memory implementation of ``PlanningQueries``."""

    def __init__(self, state: MemoryBackendState) -> None:
        self._tables: MemoryPlanningState = planning_state(state)

    def _summary(self, plan: Plan) -> PlanSummary:
        rev = (
            None if plan.current_revision_id is None else self._tables.revisions.get(plan.current_revision_id)
        )
        open_drafts = sum(
            1 for d in self._tables.drafts.values() if d.plan_id == plan.id and d.state is DraftState.OPEN
        )
        return {
            "plan_id": str(plan.id),
            "alias": plan.alias,
            "title": plan.title,
            "purpose": plan.purpose.value,
            "lifecycle_state": plan.lifecycle.value,
            "current_revision_id": None
            if plan.current_revision_id is None
            else str(plan.current_revision_id),
            "current_revision_no": None if rev is None else rev.meta.revision_no,
            "open_drafts": open_drafts,
            "updated_at": format_timestamp(plan.updated_at),
        }

    def list_plans(
        self, project_id: ProjectId, *, state: PlanListState, cursor: Cursor | None, limit: int
    ) -> Page[PlanSummary]:
        if isinstance(limit, bool) or not 1 <= limit <= _MAX_LIMIT:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                f"limit must be between 1 and {_MAX_LIMIT}",
                details={"field": "limit"},
            )
        if state not in ("active", "archived", "all"):
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID, "invalid plan list state", details={"field": "state"}
            )
        bound = _decode_cursor(cursor, project_id, state)
        matching = [
            p
            for p in self._tables.plans.values()
            if p.project_id == project_id
            and p.purpose is PlanPurpose.STANDARD
            and (state == "all" or p.lifecycle.value == state)
            and (bound is None or (p.updated_at, UUID(str(p.id))) < bound)
        ]
        matching.sort(key=lambda p: (p.updated_at, UUID(str(p.id))), reverse=True)
        sliced = matching[: limit + 1]
        items = tuple(self._summary(p) for p in sliced[:limit])
        next_cur = (
            None
            if len(sliced) <= limit
            else _encode_cursor(
                project_id,
                state,
                cast("str", items[-1]["updated_at"]),
                cast("str", items[-1]["plan_id"]),
            )
        )
        return Page(items=items, next=next_cur)

    def plan_summary(self, plan_id: PlanId) -> PlanSummary:
        plan = self._tables.plans.get(plan_id)
        if plan is None:
            raise NotFound(
                ErrorCode.NOT_FOUND, "plan not found", details={"kind": "plan", "ref": str(plan_id)}
            )
        return self._summary(plan)

    def find_member(self, revision_id: RevisionId, display_key: str) -> MemberRef | None:
        row = self._tables.revisions.get(revision_id)
        if row is None:
            return None
        spec, _ = from_document(row.document)
        _, refs = _members(spec)
        return next((m for m in refs if m.display_key == display_key), None)

    def find_member_by_id(self, revision_id: RevisionId, entity_id: EntityId) -> MemberRef | None:
        row = self._tables.revisions.get(revision_id)
        if row is None:
            return None
        spec, _ = from_document(row.document)
        by_id, _ = _members(spec)
        return by_id.get(entity_id)

    def entity_links(self, revision_id: RevisionId, entity_id: EntityId) -> EntityLinks:
        row = self._tables.revisions.get(revision_id)
        if row is None:
            return EntityLinks((), (), (), (), (), (), ())
        spec, _ = from_document(row.document)
        by_id, _ = _members(spec)
        edges = _dep_edges(spec)

        prereqs = sorted(
            {by_id[p] for d, p in edges if d == entity_id},
            key=lambda m: (m.entity_kind.value, m.position),
        )
        dependents = sorted(
            {by_id[d] for d, p in edges if p == entity_id},
            key=lambda m: (m.entity_kind.value, m.position),
        )

        crit_ids: set[EntityId] = set()
        check_ids: set[EntityId] = set()
        req_ids: set[EntityId] = set()
        for c in spec.criteria:
            c_owner_id = spec.by_key(c.owner).id
            c_checks = [
                spec.by_key(r if ":" in r else f"{c.owner.split('/', 1)[0]}:{r}").id for r in c.checks
            ]
            c_reqs = [spec.by_key(k).id for k in c.requirements]
            if c_owner_id == entity_id or entity_id in c_checks or entity_id in c_reqs:
                crit_ids.add(c.id)
            if c.id == entity_id:
                check_ids.update(c_checks)
                req_ids.update(c_reqs)

        for chk in spec.checks:
            if spec.by_key(chk.owner).id == entity_id:
                check_ids.add(chk.id)
        for u in spec.units:
            if u.id == entity_id:
                item_key = u.key.split("/", 1)[0]
                check_ids.update(spec.by_key(r if ":" in r else f"{item_key}:{r}").id for r in u.checks)
                req_ids.update(spec.by_key(k).id for k in u.implements)

        dec_ids: set[EntityId] = {
            d.id for d in spec.decisions if any(spec.by_key(k).id == entity_id for k in d.applies_to)
        }
        for item in spec.items:
            if item.id == entity_id:
                dec_ids.update(spec.by_key(k).id for k in item.decisions)
                req_ids.update(spec.by_key(k).id for k in item.implements)

        mat_ids: set[EntityId] = {
            m.id for m in spec.materials if any(spec.by_key(k).id == entity_id for k in m.applies_to)
        }
        req_ids.update(
            r.id for r in spec.requirements if any(spec.by_key(k).id == entity_id for k in r.owners)
        )

        def _by_pos(ids: set[EntityId]) -> tuple[MemberRef, ...]:
            return tuple(sorted((by_id[i] for i in ids), key=lambda m: m.position))

        return EntityLinks(
            prerequisites=tuple(prereqs),
            dependents=tuple(dependents),
            criteria=_by_pos(crit_ids),
            checks=_by_pos(check_ids),
            decisions=_by_pos(dec_ids),
            materials=_by_pos(mat_ids),
            requirements=_by_pos(req_ids),
        )

    def _revision_row(self, revision_id: RevisionId) -> StoredRevision:
        row = self._tables.revisions.get(revision_id)
        if row is None:
            raise NotFound(
                ErrorCode.NOT_FOUND,
                "revision not found",
                details={"kind": "revision", "ref": str(revision_id)},
            )
        return row

    def revision_pins(self, revision_id: RevisionId) -> tuple[MaterialPin, ...]:
        row = self._revision_row(revision_id)
        spec, _ = from_document(row.document)
        pos_by_id = {mat.id: idx for idx, mat in enumerate(spec.materials)}
        pins = list(row.pins)
        pins.sort(key=lambda pin: pos_by_id.get(pin.material_id, len(pos_by_id)))
        return tuple(pins)

    def revision_materials(self, revision_id: RevisionId) -> tuple[MaterialRef, ...]:
        row = self._revision_row(revision_id)
        spec, _ = from_document(row.document)
        by_id, _ = _members(spec)
        pin_by_id = {pin.material_id: pin for pin in row.pins}
        raw_ret_by_id: dict[str, str] = {}
        raw_mats = row.document.get("materials")
        if isinstance(raw_mats, list):
            for raw_item in raw_mats:
                if isinstance(raw_item, dict):
                    raw_id = raw_item.get("id")
                    raw_ret = raw_item.get("retrieved_at")
                    if isinstance(raw_id, str) and isinstance(raw_ret, str):
                        raw_ret_by_id[raw_id] = raw_ret

        items: list[MaterialRef] = []
        for mat in spec.materials:
            bound_refs = sorted(
                {by_id[spec.by_key(k).id] for k in mat.applies_to},
                key=lambda m: (m.entity_kind.value, m.position),
            )
            if mat.kind is MaterialKind.FILE_VERSION:
                pin = pin_by_id.get(mat.id)
                if pin is None:
                    raise InternalError(
                        ErrorCode.INTERNAL_ERROR,
                        f"corrupt skm_planning.revision_file_bindings row {mat.id}",
                    )
                eff_role = pin.role
                fvid: str | None = str(pin.file_version_id)
                sel_val: JsonValue = deepcopy(pin.selector)
            else:
                eff_role = mat.role
                fvid = None if mat.file_version_id is None else str(mat.file_version_id)
                sel_val = deepcopy(mat.selector)
            ret_str: str | None = None
            if mat.retrieved_at is not None:
                saved = raw_ret_by_id.get(str(mat.id))
                ret_str = (
                    saved
                    if saved is not None and parse_timestamp(saved) == mat.retrieved_at
                    else format_timestamp(mat.retrieved_at)
                )
            freshness: JsonObject = compact(
                {
                    "policy": mat.freshness.policy.value,
                    "max_age_seconds": mat.freshness.max_age_seconds,
                }
            )
            items.append(
                {
                    "material_id": str(mat.id),
                    "key": mat.key,
                    "title": mat.title,
                    "kind": mat.kind.value,
                    "role": eff_role,
                    "required_for": [stage.value for stage in mat.required_for],
                    "freshness": freshness,
                    "file_version_id": fvid,
                    "mount": mat.mount,
                    "path": mat.path,
                    "url": mat.url,
                    "retrieved_at": ret_str,
                    "content_digest": mat.content_digest,
                    "selector": sel_val,
                    "why": mat.why,
                    "applies_to": [m.display_key for m in bound_refs],
                    "applies_to_entity_ids": [str(m.entity_id) for m in bound_refs],
                    "is_global": mat.is_global,
                    "external_source_id": mat.external_source_id,
                }
            )
        return tuple(items)

    def revisions_pinning_file_version(self, file_version_id: UUID) -> tuple[RevisionId, ...]:
        matching = [
            row.meta
            for row in self._tables.revisions.values()
            if any(pin.file_version_id == file_version_id for pin in row.pins)
        ]
        matching.sort(key=lambda meta: (meta.published_at, UUID(str(meta.id))), reverse=True)
        return tuple(meta.id for meta in matching)
