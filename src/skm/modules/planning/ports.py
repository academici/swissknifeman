"""Repository ports of the planning module (planning §6).

Ports never open a transaction: they run in the unit of work of the calling handler. Lock order of every
handler that needs several rows is plan -> drafts (by id) -> counters -> file versions (by id), so a handler
that holds a plan lock may take draft locks and never the reverse (planning §7.10, decision E13).
Revisions are append-only: ``RevisionRepository`` has no method that updates or deletes a revision.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Literal, Protocol

from skm.kernel.ports_uow import repository_port

if TYPE_CHECKING:
    from collections.abc import Mapping
    from uuid import UUID

    from skm.kernel.ids import EntityId, PlanId, ProjectId, RevisionId, WorkspaceId
    from skm.kernel.json_types import JsonObject, JsonValue
    from skm.kernel.pagination import Cursor, Page
    from skm.modules.planning.domain.brief import DesignBrief
    from skm.modules.planning.domain.draft import Draft, DraftId, DraftState
    from skm.modules.planning.domain.material import MaterialRef
    from skm.modules.planning.domain.member import EntityLinks, MemberRef
    from skm.modules.planning.domain.plan import Plan
    from skm.modules.planning.domain.revision import RevisionMeta
    from skm.modules.planning.domain.specification import EntityKind, Specification

type Digest = str

# The normalized specification document (``generated.documents.SpecificationDoc`` on the wire); the domain
# works on the plain JSON object, ports cannot import generated code.
type SpecificationDoc = JsonObject

# Read models of ``PlanningQueries``: the generated ``PlanSummary`` view in its JSON form.
type PlanSummary = JsonObject

type PlanListState = Literal["active", "archived", "all"]


class AliasKind(StrEnum):
    SHORT = "short"
    SYSTEM = "system"
    LEGACY = "legacy"
    EXTERNAL = "external"


@repository_port
class PlanRepository(Protocol):
    def get(self, plan_id: PlanId) -> Plan: ...
    def lock(self, plan_id: PlanId) -> Plan: ...  # FOR UPDATE: first lock of the order, before any draft
    def lock_shared(self, plan_id: PlanId) -> Plan: ...
    def add(self, plan: Plan) -> None: ...
    def save(self, plan: Plan, *, expected_version: int) -> None: ...  # CAS on row_version
    def find_by_alias(self, project_id: ProjectId, alias: str) -> Plan | None: ...
    def find_by_id_prefix(self, project_id: ProjectId, prefix: str, *, limit: int) -> tuple[Plan, ...]: ...
    def project_plan_refs(self, project_id: ProjectId) -> Mapping[str, PlanId]: ...
    def find_review_requests_plan(self, project_id: ProjectId) -> Plan | None: ...
    def superseded_by(self, plan_id: PlanId) -> tuple[PlanId, ...]: ...
    def add_alias(self, plan_id: PlanId, alias: str, kind: AliasKind) -> None: ...
    def add_design_brief(self, brief: DesignBrief) -> None: ...
    def get_design_brief(self, plan_id: PlanId, brief_id: UUID) -> DesignBrief: ...
    def list_aliases(self, plan_id: PlanId) -> tuple[tuple[str, AliasKind], ...]: ...


@repository_port
class PlanCounters(Protocol):
    def allocate_plan_no(
        self, workspace_id: WorkspaceId, project_id: ProjectId
    ) -> int: ...  # row lock to commit


@repository_port
class DraftRepository(Protocol):
    def get(self, draft_id: DraftId) -> Draft: ...
    def lock(self, draft_id: DraftId) -> Draft: ...  # FOR UPDATE: after the plan lock when both are needed
    def add(self, draft: Draft) -> None: ...
    def save(self, draft: Draft, *, expected_edit_version: int) -> None: ...  # CAS on edit_version
    def list_for_plan(self, plan_id: PlanId, *, state: DraftState | None) -> tuple[Draft, ...]: ...
    def lock_open_for_plan(self, plan_id: PlanId) -> tuple[Draft, ...]: ...  # FOR UPDATE, ORDER BY id
    def count_open(self, plan_id: PlanId) -> int: ...  # only under PlanRepository.lock


@dataclass(frozen=True, slots=True)
class MaterialPin:
    material_id: EntityId
    file_version_id: UUID
    role: str
    selector: JsonValue | None


@dataclass(frozen=True, slots=True)
class RevisionRecord:
    meta: RevisionMeta
    spec: Specification
    document: SpecificationDoc
    new_identities: tuple[tuple[EntityId, EntityKind], ...]
    pins: tuple[MaterialPin, ...]
    plan_relation_targets: tuple[PlanId | None, ...]


@repository_port
class RevisionRepository(Protocol):
    def get_meta(self, revision_id: RevisionId) -> RevisionMeta: ...
    def find_by_number(self, plan_id: PlanId, revision_no: int) -> RevisionMeta | None: ...
    def get_document(self, revision_id: RevisionId) -> SpecificationDoc: ...
    def load_typed_document(self, revision_id: RevisionId) -> SpecificationDoc: ...
    def identities(self, plan_id: PlanId) -> Mapping[EntityId, EntityKind]: ...
    def add(self, record: RevisionRecord) -> None: ...
    def list_for_plan(
        self, plan_id: PlanId, *, before_revision_no: int | None, limit: int
    ) -> tuple[RevisionMeta, ...]: ...


@repository_port
class PlanningQueries(Protocol):
    def list_plans(
        self, project_id: ProjectId, *, state: PlanListState, cursor: Cursor | None, limit: int
    ) -> Page[PlanSummary]: ...
    def plan_summary(self, plan_id: PlanId) -> PlanSummary: ...
    def find_member(self, revision_id: RevisionId, display_key: str) -> MemberRef | None: ...
    def find_member_by_id(self, revision_id: RevisionId, entity_id: EntityId) -> MemberRef | None: ...
    def entity_links(self, revision_id: RevisionId, entity_id: EntityId) -> EntityLinks: ...
    def revision_pins(self, revision_id: RevisionId) -> tuple[MaterialPin, ...]: ...
    def revision_materials(self, revision_id: RevisionId) -> tuple[MaterialRef, ...]: ...
    def revisions_pinning_file_version(self, file_version_id: UUID) -> tuple[RevisionId, ...]: ...
