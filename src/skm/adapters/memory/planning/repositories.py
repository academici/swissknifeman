"""Memory implementations of the planning repository ports (planning §6, §11).

Rows are the immutable domain values themselves; a document and a pin selector cross the port as copies, so a
caller cannot reach a stored row through them. One unit of work runs at a time, so ``lock`` and
``lock_shared`` read like ``get``: the serialisation the database gets from ``FOR UPDATE`` holds for the whole
unit of work.

The checks PostgreSQL gets from constraints and from its ``WHERE`` clauses are made here too: the unique
alias per project, one system plan per project, the plan number counter, the optimistic ``row_version`` of a
plan and ``edit_version`` of a draft (a closed draft answers ``DRAFT_NOT_OPEN`` first, as the domain does),
the columns no update touches (``FIELD_OWNED``), unique ``(plan, revision_no)`` and an entity id that never
moves to another plan (``ID_CONFLICT``). Revisions are append-only: the port offers no update or delete.
Composite FKs and triggers are not imitated (adapters §2.2): their contract cases run on PostgreSQL only.

``MemoryImportJobRepository`` and ``MemoryImportObjectRepository`` stay declarations until their owner leaf.
"""

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import replace
from typing import Final
from uuid import UUID

from skm.adapters.memory.core.state import MemoryBackendState
from skm.adapters.memory.planning.state import (
    MemoryPlanningState,
    StoredIdentity,
    StoredRevision,
    detached_pins,
    planning_state,
)
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, InternalError, NotFound, ValidationFailed
from skm.kernel.ids import EntityId, PlanId, ProjectId, RevisionId, WorkspaceId
from skm.modules.planning.domain.brief import DesignBrief
from skm.modules.planning.domain.draft import Draft, DraftId, DraftState, require_edit_version, require_open
from skm.modules.planning.domain.plan import Plan, PlanPurpose
from skm.modules.planning.domain.plan_relation import PlanRelationKind
from skm.modules.planning.domain.revision import RevisionMeta
from skm.modules.planning.domain.specification import (
    EntityKind,
    SpecEntity,
    Specification,
    from_document,
    to_document,
)
from skm.modules.planning.ports import (
    AliasKind,
    MaterialPin,
    RevisionRecord,
    SpecificationDoc,
)

__all__ = [
    "MemoryDraftRepository",
    "MemoryPlanCounters",
    "MemoryPlanRepository",
    "MemoryRevisionRepository",
]

_PLAN_OWNED: Final = ("workspace_id", "project_id", "alias", "purpose", "created_by", "created_at")
_DRAFT_OWNED: Final = ("plan_id", "workspace_id", "created_by", "created_at")
_ADDED_ALIASES: Final = frozenset({AliasKind.LEGACY, AliasKind.EXTERNAL})


def _not_found(kind: str, ref: object) -> NotFound:
    return NotFound(ErrorCode.NOT_FOUND, f"{kind} not found", details={"kind": kind, "ref": str(ref)})


def _exists(kind: str, **details: str) -> Conflict:
    return Conflict(ErrorCode.ALREADY_EXISTS, f"{kind} already exists", details={"kind": kind, **details})


def _owned(target: str, field: str) -> ValidationFailed:
    return ValidationFailed(
        ErrorCode.FIELD_OWNED, "field is owned", details={"target": target, "field": field}
    )


def _require_unchanged(target: str, stored: object, new: object, fields: tuple[str, ...]) -> None:
    for field in fields:
        if getattr(stored, field) != getattr(new, field):
            raise _owned(target, field)


class _Tables:
    def __init__(self, state: MemoryBackendState) -> None:
        self._state = state
        self._tables: MemoryPlanningState = planning_state(state)

    def _writable(self) -> MemoryPlanningState:
        self._state.core.require_writable()
        return self._tables


class MemoryPlanRepository(_Tables):
    def add_design_brief(self, brief: DesignBrief) -> None:
        tables = self._writable()
        if self.get(brief.plan_id).workspace_id != brief.workspace_id:
            raise _not_found("plan", brief.plan_id)
        if brief.id in tables.design_briefs:
            raise _exists("design_brief", ref=str(brief.id))
        tables.design_briefs[brief.id] = brief

    def get_design_brief(self, plan_id: PlanId, brief_id: UUID) -> DesignBrief:
        found = self._tables.design_briefs.get(brief_id)
        if found is None or found.plan_id != plan_id:
            raise _not_found("design_brief", brief_id)
        return found

    def get(self, plan_id: PlanId) -> Plan:
        found = self._tables.plans.get(plan_id)
        if found is None:
            raise _not_found("plan", plan_id)
        return found

    def lock(self, plan_id: PlanId) -> Plan:
        return self.get(plan_id)

    def lock_shared(self, plan_id: PlanId) -> Plan:
        return self.get(plan_id)

    def add(self, plan: Plan) -> None:
        tables = self._writable()
        if plan.id in tables.plans:
            raise _exists("plan", ref=str(plan.id))
        system = plan.purpose is PlanPurpose.REVIEW_REQUESTS
        if system and self.find_review_requests_plan(plan.project_id) is not None:
            raise _exists("plan", alias=plan.alias)
        self._bind_alias(
            tables, plan.project_id, plan.id, plan.alias, AliasKind.SYSTEM if system else AliasKind.SHORT
        )
        tables.plans[plan.id] = plan

    def save(self, plan: Plan, *, expected_version: int) -> None:
        tables = self._writable()
        stored = self.get(plan.id)
        if stored.row_version != expected_version:
            raise Conflict(
                ErrorCode.VERSION_CONFLICT,
                "the plan was changed by another command",
                details={"expected": expected_version, "actual": stored.row_version},
            )
        _require_unchanged("plan", stored, plan, _PLAN_OWNED)
        tables.plans[plan.id] = plan

    def find_by_alias(self, project_id: ProjectId, alias: str) -> Plan | None:
        found = self._tables.aliases.get((project_id, alias))
        return None if found is None else self._tables.plans[found[0]]

    def find_by_id_prefix(self, project_id: ProjectId, prefix: str, *, limit: int) -> tuple[Plan, ...]:
        rows = sorted(
            (
                plan
                for plan in self._tables.plans.values()
                if plan.project_id == project_id and str(plan.id).startswith(prefix)
            ),
            key=lambda plan: str(plan.id),
        )
        return tuple(rows[: max(limit, 0)])

    def project_plan_refs(self, project_id: ProjectId) -> Mapping[str, PlanId]:
        refs = {
            alias: plan_id
            for (project, alias), (plan_id, _) in self._tables.aliases.items()
            if project == project_id
        }
        refs.update(
            {
                f"plan:{plan.id}": plan.id
                for plan in self._tables.plans.values()
                if plan.project_id == project_id
            }
        )
        return refs

    def find_review_requests_plan(self, project_id: ProjectId) -> Plan | None:
        return next(
            (
                plan
                for plan in self._tables.plans.values()
                if plan.project_id == project_id and plan.purpose is PlanPurpose.REVIEW_REQUESTS
            ),
            None,
        )

    def superseded_by(self, plan_id: PlanId) -> tuple[PlanId, ...]:
        rows = (
            (plan.id, self._tables.revisions[plan.current_revision_id])
            for plan in self._tables.plans.values()
            if plan.current_revision_id is not None
        )
        return tuple(sorted((found for found, row in rows if _supersedes(row, plan_id)), key=str))

    def add_alias(self, plan_id: PlanId, alias: str, kind: AliasKind) -> None:
        tables = self._writable()
        if kind not in _ADDED_ALIASES:
            raise InternalError(
                ErrorCode.INTERNAL_ERROR,
                "only a legacy or external alias is added to an existing plan",
                details={"alias_kind": kind.value},
            )
        self._bind_alias(tables, self.get(plan_id).project_id, plan_id, alias, kind)

    def list_aliases(self, plan_id: PlanId) -> tuple[tuple[str, AliasKind], ...]:
        plan = self.get(plan_id)
        primary_kind = AliasKind.SYSTEM if plan.purpose is PlanPurpose.REVIEW_REQUESTS else AliasKind.SHORT
        extras = sorted(
            (
                (alias, kind)
                for (proj_id, alias), (target_id, kind) in self._tables.aliases.items()
                if proj_id == plan.project_id and target_id == plan.id and alias != plan.alias
            ),
            key=lambda item: (item[1].value, item[0]),
        )
        return ((plan.alias, primary_kind), *extras)

    @staticmethod
    def _bind_alias(
        tables: MemoryPlanningState, project_id: ProjectId, plan_id: PlanId, alias: str, kind: AliasKind
    ) -> None:
        if (project_id, alias) in tables.aliases:
            raise _exists("alias", alias=alias)
        tables.aliases[(project_id, alias)] = (plan_id, kind)


def _supersedes(row: StoredRevision, plan_id: PlanId) -> bool:
    relations = row.document.get("plan_relations")
    if not isinstance(relations, list):
        return False
    return any(
        target == plan_id
        and isinstance(relation, dict)
        and relation.get("kind") == PlanRelationKind.SUPERSEDES.value
        for relation, target in zip(relations, row.plan_relation_targets, strict=False)
    )


class MemoryPlanCounters(_Tables):
    def allocate_plan_no(self, workspace_id: WorkspaceId, project_id: ProjectId) -> int:  # noqa: ARG002 - FK
        tables = self._writable()
        number = tables.next_plan_no.get(project_id, 1)
        tables.next_plan_no[project_id] = number + 1
        return number


class MemoryDraftRepository(_Tables):
    def _stored(self, draft_id: DraftId) -> Draft:
        found = self._tables.drafts.get(draft_id)
        if found is None:
            raise _not_found("draft", draft_id)
        return found

    def get(self, draft_id: DraftId) -> Draft:
        return _detached(self._stored(draft_id))

    def lock(self, draft_id: DraftId) -> Draft:
        return self.get(draft_id)

    def add(self, draft: Draft) -> None:
        tables = self._writable()
        if draft.id in tables.drafts:
            raise _exists("draft", ref=str(draft.id))
        tables.drafts[draft.id] = _detached(draft)

    def save(self, draft: Draft, *, expected_edit_version: int) -> None:
        tables = self._writable()
        stored = self._stored(draft.id)
        require_open(stored)
        require_edit_version(stored, expected_edit_version)
        _require_unchanged("draft", stored, draft, _DRAFT_OWNED)
        if draft.document.get("schema") != stored.document.get("schema"):
            raise _owned("draft", "schema")
        tables.drafts[draft.id] = _detached(draft)

    def list_for_plan(self, plan_id: PlanId, *, state: DraftState | None) -> tuple[Draft, ...]:
        rows = (
            draft
            for draft in self._tables.drafts.values()
            if draft.plan_id == plan_id and (state is None or draft.state is state)
        )
        ordered = sorted(rows, key=lambda row: (row.created_at, str(row.id)))
        return tuple(_detached(draft) for draft in ordered)

    def lock_open_for_plan(self, plan_id: PlanId) -> tuple[Draft, ...]:
        rows = self.list_for_plan(plan_id, state=DraftState.OPEN)
        return tuple(sorted(rows, key=lambda row: str(row.id)))

    def count_open(self, plan_id: PlanId) -> int:
        return sum(
            1
            for draft in self._tables.drafts.values()
            if draft.plan_id == plan_id and draft.state is DraftState.OPEN
        )


def _detached(draft: Draft) -> Draft:
    return replace(draft, document=deepcopy(draft.document))


class MemoryRevisionRepository(_Tables):
    def _stored(self, revision_id: RevisionId) -> StoredRevision:
        found = self._tables.revisions.get(revision_id)
        if found is None:
            raise _not_found("revision", revision_id)
        return found

    def get_meta(self, revision_id: RevisionId) -> RevisionMeta:
        return self._stored(revision_id).meta

    def find_by_number(self, plan_id: PlanId, revision_no: int) -> RevisionMeta | None:
        return next(
            (
                row.meta
                for row in self._tables.revisions.values()
                if row.meta.plan_id == plan_id and row.meta.revision_no == revision_no
            ),
            None,
        )

    def get_document(self, revision_id: RevisionId) -> SpecificationDoc:
        return deepcopy(self._stored(revision_id).document)

    def load_typed_document(self, revision_id: RevisionId) -> SpecificationDoc:
        """Reconstruct normalized document overlaying detached ``StoredRevision.pins`` (planning I8)."""
        stored = self._stored(revision_id)
        doc = deepcopy(stored.document)
        pins = stored.pins
        if not pins:
            return doc
        pin_by_id = {str(pin.material_id): pin for pin in pins}
        raw_materials = doc.get("materials")
        if isinstance(raw_materials, list):
            for mat in raw_materials:
                if isinstance(mat, dict) and mat.get("kind") == "file_version":
                    pin = pin_by_id.get(str(mat.get("id", "")))
                    if pin is not None:
                        mat["file_version_id"] = str(pin.file_version_id)
                        mat["role"] = pin.role
                        if pin.selector is not None:
                            mat["selector"] = deepcopy(pin.selector)
        spec_model, _ = from_document(doc)
        return to_document(spec_model)

    def identities(self, plan_id: PlanId) -> Mapping[EntityId, EntityKind]:
        return {
            entity_id: identity.kind
            for entity_id, identity in self._tables.identities.items()
            if identity.plan_id == plan_id
        }

    def add(self, record: RevisionRecord) -> None:
        tables = self._writable()
        meta = record.meta
        if meta.id in tables.revisions:
            raise _exists("revision", ref=str(meta.id))
        if self.find_by_number(meta.plan_id, meta.revision_no) is not None:
            raise _exists("revision", revision_no=str(meta.revision_no))
        id_pairs = _collect_identities(record.spec, record.new_identities)
        taken = sorted(
            str(entity_id)
            for entity_id in id_pairs
            if entity_id in tables.identities and tables.identities[entity_id].plan_id != meta.plan_id
        )
        if taken:
            raise Conflict(
                ErrorCode.ID_CONFLICT,
                "an entity id belongs to another plan",
                details={"entity_ids": list(taken)},
            )
        for entity_id, kind in id_pairs.items():
            existing = tables.identities.get(entity_id)
            if existing is not None and existing.kind is not kind:
                raise ValidationFailed(
                    ErrorCode.SCHEMA_INVALID,
                    f"entity {entity_id} changed kind from {existing.kind.value!r} to {kind.value!r}",
                )
        if record.spec.design_brief_id is not None:
            MemoryPlanRepository(self._state).get_design_brief(meta.plan_id, record.spec.design_brief_id)
        _validate_pins(record.pins)
        tables.revisions[meta.id] = StoredRevision(
            meta, deepcopy(record.document), detached_pins(record.pins), record.plan_relation_targets
        )
        for entity_id, kind in id_pairs.items():
            tables.identities.setdefault(entity_id, StoredIdentity(meta.plan_id, kind))

    def list_for_plan(
        self, plan_id: PlanId, *, before_revision_no: int | None, limit: int
    ) -> tuple[RevisionMeta, ...]:
        rows = sorted(
            (
                row.meta
                for row in self._tables.revisions.values()
                if row.meta.plan_id == plan_id
                and (before_revision_no is None or row.meta.revision_no < before_revision_no)
            ),
            key=lambda meta: meta.revision_no,
            reverse=True,
        )
        return tuple(rows[: max(limit, 0)])


def _collect_identities(
    spec: Specification, new_identities: Sequence[tuple[EntityId, EntityKind]]
) -> dict[EntityId, EntityKind]:
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
    pairs: dict[EntityId, EntityKind] = dict(new_identities)
    for kind, entities in groups:
        for entity in entities:
            pairs.setdefault(entity.id, kind)
    return pairs


def _validate_pins(pins: Sequence[MaterialPin]) -> None:
    seen: set[EntityId] = set()
    for pin in pins:
        if pin.material_id in seen:
            raise _exists("revision_file_binding", material_id=str(pin.material_id))
        seen.add(pin.material_id)
        if pin.role not in ("input", "reference"):
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "invalid file binding role",
                details={"field": "role", "value": pin.role},
            )
