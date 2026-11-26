"""Facade of the planning module (planning §13): the only surface other modules import.

Every function receives the ``uow`` of the calling transaction, opens none of its own and checks no
permission. Behavior is implemented by the owning leaf; the signatures and result types are the contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import TYPE_CHECKING
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, ValidationFailed
from skm.kernel.ids import EntityId, PlanId, ProjectId, RevisionId, WorkspaceId, parse_uuid

from .application.queries.get_plan import plan_view
from .application.revision_writer import publish_service_review_revision, validate_published_revision
from .domain import compile_graph as _compile_graph
from .domain import material_status as _material_status
from .domain import plan as _plan_rules
from .domain.brief import DesignBrief
from .domain.canonical import normalize_document
from .domain.compile_graph import BatchGroup, ExecutionGraph, TaskEdge, TaskKind, TaskNode
from .domain.display_keys import ENTITY_ID_PREFIX, key_kind
from .domain.draft import DraftId
from .domain.material import (
    Freshness,
    FreshnessPolicy,
    Material,
    MaterialKind,
    MaterialRef,
    MaterialStage,
)
from .domain.material_status import MaterialAssessment, MaterialObservation, MaterialState
from .domain.plan import Plan, PlanLifecycle, PlanPurpose
from .domain.review_request import (
    CommitReviewTarget,
    ReviewRequestSpec,
    ReviewRequestTarget,
    WorkingTreeReviewTarget,
)
from .domain.revision import RevisionMeta
from .domain.specification import EntityKind, SpecEntity, Specification, from_document
from .domain.validation.context import FileVersionObservation, FileVersionStatus
from .domain.validation.findings import Finding, ValidationReport
from .generated.views import PlanView
from .ports import PlanningQueries, PlanRepository, RevisionRepository, SpecificationDoc

if TYPE_CHECKING:
    from datetime import datetime

    from skm.kernel.actor import Actor
    from skm.kernel.id_generator import IdGenerator
    from skm.kernel.ports_uow import UnitOfWork
    from skm.kernel.scopes import ScopeRecord
    from skm.platform.config import EffectiveConfig


@dataclass(frozen=True, slots=True)
class PlanRef:
    """What a consumer needs to address a plan; ``require_active_plan`` returns it under ``FOR SHARE``."""

    plan_id: PlanId
    workspace_id: WorkspaceId
    project_id: ProjectId
    alias: str
    title: str
    purpose: PlanPurpose
    lifecycle: PlanLifecycle
    current_revision_id: RevisionId | None


@dataclass(frozen=True, slots=True)
class RevisionMetaView:
    """Persisted facts of one revision; ``digest`` is the canonical digest of ``revision_payloads``."""

    revision_id: RevisionId
    plan_id: PlanId
    project_id: ProjectId
    workspace_id: WorkspaceId
    revision_no: int
    digest: str
    published_at: datetime
    compiler_version: int
    plan_purpose: PlanPurpose
    plan_lifecycle: PlanLifecycle


@dataclass(frozen=True, slots=True)
class EntityRef:
    """A specification entity resolved in one revision; the id is stable, the display key is not."""

    entity_id: EntityId
    entity_kind: EntityKind
    display_key: str


def _to_plan_ref(plan: Plan) -> PlanRef:
    return PlanRef(
        plan_id=plan.id,
        workspace_id=plan.workspace_id,
        project_id=plan.project_id,
        alias=plan.alias,
        title=plan.title,
        purpose=plan.purpose,
        lifecycle=plan.lifecycle,
        current_revision_id=plan.current_revision_id,
    )


def _to_revision_meta_view(plan: Plan, meta: RevisionMeta) -> RevisionMetaView:
    return RevisionMetaView(
        revision_id=meta.id,
        plan_id=plan.id,
        project_id=plan.project_id,
        workspace_id=plan.workspace_id,
        revision_no=meta.revision_no,
        digest=meta.content_digest,
        published_at=meta.published_at,
        compiler_version=meta.compiler_version,
        plan_purpose=plan.purpose,
        plan_lifecycle=plan.lifecycle,
    )


def get_design_brief(uow: UnitOfWork, plan_id: PlanId, brief_id: UUID) -> DesignBrief:
    return uow.repo(PlanRepository).get_design_brief(plan_id, brief_id)


def get_revision_specification(uow: UnitOfWork, revision_id: RevisionId) -> Specification:
    document = uow.repo(RevisionRepository).get_document(revision_id)
    spec, _ = from_document(normalize_document(document))
    return spec


def get_revision_meta(uow: UnitOfWork, revision_id: RevisionId) -> RevisionMetaView:
    meta = uow.repo(RevisionRepository).get_meta(revision_id)
    plan = uow.repo(PlanRepository).get(meta.plan_id)
    return _to_revision_meta_view(plan, meta)


def find_revision_id(uow: UnitOfWork, plan_id: PlanId, revision_no: int) -> RevisionId | None:
    """Resolve a published revision number within its owning plan."""
    meta = uow.repo(RevisionRepository).find_by_number(plan_id, revision_no)
    return meta.id if meta is not None else None


def compile_execution_graph(spec: Specification, revision_id: RevisionId | None = None) -> ExecutionGraph:
    return _compile_graph.compile_execution_graph(spec, revision_id)


def resolve_entity(uow: UnitOfWork, revision_id: RevisionId, ref: str) -> EntityRef:
    uow.repo(RevisionRepository).get_meta(revision_id)
    target = ref.strip()
    if not target:
        raise ValidationFailed(
            ErrorCode.INVALID_REFERENCE,
            "entity reference cannot be empty",
            details={"ref": ref},
        )

    queries = uow.repo(PlanningQueries)
    if target.startswith(ENTITY_ID_PREFIX):
        raw_uuid = target[len(ENTITY_ID_PREFIX) :]
        try:
            entity_uuid: UUID = parse_uuid(raw_uuid)
        except ValueError as err:
            raise ValidationFailed(
                ErrorCode.INVALID_REFERENCE,
                "invalid entity UUID reference",
                details={"ref": ref},
            ) from err
        member = queries.find_member_by_id(revision_id, EntityId(entity_uuid))
    else:
        if key_kind(target) is None:
            raise ValidationFailed(
                ErrorCode.INVALID_REFERENCE,
                "not a valid entity reference",
                details={"ref": ref},
            )
        member = queries.find_member(revision_id, target)

    if member is None:
        raise NotFound(
            ErrorCode.NOT_FOUND,
            "entity not found",
            details={"kind": "entity", "ref": ref},
        )
    return EntityRef(
        entity_id=member.entity_id,
        entity_kind=member.entity_kind,
        display_key=member.display_key,
    )


def revision_materials(uow: UnitOfWork, revision_id: RevisionId) -> tuple[MaterialRef, ...]:
    return uow.repo(PlanningQueries).revision_materials(revision_id)


def assess_material(
    material: Material | MaterialRef,
    observation: MaterialObservation | None,
    *,
    now: datetime,
) -> MaterialAssessment:
    return _material_status.assess_material(material, observation, now=now)


def require_active_plan(uow: UnitOfWork, plan_id: PlanId) -> PlanRef:
    plan = uow.repo(PlanRepository).lock_shared(plan_id)
    _plan_rules.require_active(plan)
    return _to_plan_ref(plan)


def get_plan_ref(uow: UnitOfWork, plan_id: PlanId) -> PlanRef:
    plan = uow.repo(PlanRepository).get(plan_id)
    return _to_plan_ref(plan)


def get_plan_summary(uow: UnitOfWork, plan_id: PlanId) -> PlanView:
    return plan_view(uow, uow.repo(PlanRepository).get(plan_id))


def validate_revision(
    uow: UnitOfWork,
    revision_id: RevisionId,
    *,
    scope_chain: tuple[ScopeRecord, ...],
    config: EffectiveConfig,
    now: datetime,
) -> ValidationReport:
    return validate_published_revision(
        uow,
        revision_id,
        scope_chain=scope_chain,
        config=config,
        now=now,
    )


def publish_review_request_revision(
    uow: UnitOfWork,
    actor: Actor,
    project_id: ProjectId,
    spec: ReviewRequestSpec,
    *,
    ids: IdGenerator,
    now: datetime,
) -> RevisionMetaView:
    written = publish_service_review_revision(
        uow,
        actor,
        project_id,
        spec,
        ids=ids,
        now=now,
    )
    return _to_revision_meta_view(written.plan, written.meta)


if TYPE_CHECKING:
    from .generated.commands import (
        AbandonDraft as AbandonDraft,
    )
    from .generated.commands import (
        ArchivePlan as ArchivePlan,
    )
    from .generated.commands import (
        CreatePlan as CreatePlan,
    )
    from .generated.commands import (
        DesignPlan as DesignPlan,
    )
    from .generated.commands import (
        ImportSpecification as ImportSpecification,
    )
    from .generated.commands import (
        OpenDraft as OpenDraft,
    )
    from .generated.commands import (
        PublishRevision as PublishRevision,
    )
    from .generated.commands import (
        RebaseDraft as RebaseDraft,
    )
    from .generated.commands import (
        RestoreRevision as RestoreRevision,
    )
    from .generated.commands import (
        SaveDraft as SaveDraft,
    )
    from .generated.queries import (
        DiffRevisions as DiffRevisions,
    )
    from .generated.queries import (
        ExportSpecification as ExportSpecification,
    )
    from .generated.queries import (
        GetDraft as GetDraft,
    )
    from .generated.queries import (
        GetEntity as GetEntity,
    )
    from .generated.queries import (
        GetPlan as GetPlan,
    )
    from .generated.queries import (
        GetRevision as GetRevision,
    )
    from .generated.queries import (
        ListDrafts as ListDrafts,
    )
    from .generated.queries import (
        ListEntities as ListEntities,
    )
    from .generated.queries import (
        ListPlans as ListPlans,
    )
    from .generated.queries import (
        ListRevisions as ListRevisions,
    )
    from .generated.queries import (
        PlanStats as PlanStats,
    )
    from .generated.queries import (
        PreviewPublication as PreviewPublication,
    )
    from .generated.queries import (
        ReadText as ReadText,
    )
    from .generated.queries import (
        ReadyPreview as ReadyPreview,
    )
    from .generated.queries import (
        ResolvePlanRef as ResolvePlanRef,
    )
    from .generated.queries import (
        Simulate as Simulate,
    )
    from .generated.queries import (
        ValidateDraft as ValidateDraft,
    )
    from .generated.results import (
        AbandonDraftResult as AbandonDraftResult,
    )
    from .generated.results import (
        ArchivePlanResult as ArchivePlanResult,
    )
    from .generated.results import (
        CreatePlanResult as CreatePlanResult,
    )
    from .generated.results import (
        DesignPlanResult as DesignPlanResult,
    )
    from .generated.results import (
        ImportSpecificationResult as ImportSpecificationResult,
    )
    from .generated.results import (
        ListDraftsResult as ListDraftsResult,
    )
    from .generated.results import (
        OpenDraftResult as OpenDraftResult,
    )
    from .generated.results import (
        PublishRevisionResult as PublishRevisionResult,
    )
    from .generated.results import (
        RebaseDraftResult as RebaseDraftResult,
    )
    from .generated.results import (
        RestoreRevisionResult as RestoreRevisionResult,
    )
    from .generated.results import (
        SaveDraftResult as SaveDraftResult,
    )
    from .generated.views import (
        DraftView as DraftView,
    )
    from .generated.views import (
        EntityPageView as EntityPageView,
    )
    from .generated.views import (
        EntityView as EntityView,
    )
    from .generated.views import (
        PlanRefView as PlanRefView,
    )
    from .generated.views import (
        PlanStatsView as PlanStatsView,
    )
    from .generated.views import (
        PlansView as PlansView,
    )
    from .generated.views import (
        PublicationPreviewView as PublicationPreviewView,
    )
    from .generated.views import (
        ReadyPreviewView as ReadyPreviewView,
    )
    from .generated.views import (
        RevisionsView as RevisionsView,
    )
    from .generated.views import (
        RevisionView as RevisionView,
    )
    from .generated.views import (
        SimulationView as SimulationView,
    )
    from .generated.views import (
        SpecDiffView as SpecDiffView,
    )
    from .generated.views import (
        SpecificationExportView as SpecificationExportView,
    )
    from .generated.views import (
        TextFragmentView as TextFragmentView,
    )
    from .generated.views import (
        ValidationReportView as ValidationReportView,
    )

_LAZY_EXPORTS: dict[str, str] = {
    **dict.fromkeys(
        (
            "AbandonDraft",
            "ArchivePlan",
            "CreatePlan",
            "DesignPlan",
            "ImportSpecification",
            "OpenDraft",
            "PublishRevision",
            "RebaseDraft",
            "RestoreRevision",
            "SaveDraft",
        ),
        ".generated.commands",
    ),
    **dict.fromkeys(
        (
            "DiffRevisions",
            "ExportSpecification",
            "GetDraft",
            "GetEntity",
            "GetPlan",
            "GetRevision",
            "ListDrafts",
            "ListEntities",
            "ListPlans",
            "ListRevisions",
            "PlanStats",
            "PreviewPublication",
            "ReadText",
            "ReadyPreview",
            "ResolvePlanRef",
            "Simulate",
            "ValidateDraft",
        ),
        ".generated.queries",
    ),
    **dict.fromkeys(
        (
            "AbandonDraftResult",
            "ArchivePlanResult",
            "CreatePlanResult",
            "DesignPlanResult",
            "ImportSpecificationResult",
            "ListDraftsResult",
            "OpenDraftResult",
            "PublishRevisionResult",
            "RebaseDraftResult",
            "RestoreRevisionResult",
            "SaveDraftResult",
        ),
        ".generated.results",
    ),
    **dict.fromkeys(
        (
            "DraftView",
            "EntityPageView",
            "EntityView",
            "PlanRefView",
            "PlanStatsView",
            "PlansView",
            "PublicationPreviewView",
            "ReadyPreviewView",
            "SimulationView",
            "RevisionView",
            "RevisionsView",
            "SpecDiffView",
            "SpecificationExportView",
            "TextFragmentView",
            "ValidationReportView",
        ),
        ".generated.views",
    ),
}


def __getattr__(name: str) -> object:
    module_name = _LAZY_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name, __package__), name)
    globals()[name] = value
    return value


# fmt: off
__all__ = [
    "AbandonDraft", "AbandonDraftResult", "ArchivePlan", "ArchivePlanResult", "BatchGroup",
    "CommitReviewTarget", "CreatePlan", "CreatePlanResult", "DesignPlan", "DesignPlanResult",
    "DiffRevisions", "DraftId", "DraftView",
    "EntityKind", "EntityPageView", "EntityRef", "EntityView", "ExecutionGraph", "ExportSpecification",
    "FileVersionObservation", "FileVersionStatus", "Finding", "Freshness", "FreshnessPolicy", "GetDraft",
    "GetEntity", "GetPlan", "GetRevision", "ImportSpecification", "ImportSpecificationResult",
    "ListDrafts", "ListDraftsResult", "ListEntities", "ListPlans", "ListRevisions", "Material",
    "MaterialAssessment", "MaterialKind", "MaterialObservation", "MaterialRef", "MaterialStage",
    "MaterialState", "OpenDraft", "OpenDraftResult", "Plan", "PlanLifecycle", "PlanPurpose", "PlanRef",
    "PlanRefView", "PlanStats", "PlanStatsView", "PlanView", "PlansView", "PreviewPublication",
    "PublicationPreviewView", "PublishRevision", "PublishRevisionResult", "ReadText", "ReadyPreview",
    "ReadyPreviewView", "RebaseDraft", "RebaseDraftResult", "ResolvePlanRef", "RestoreRevision",
    "RestoreRevisionResult", "ReviewRequestSpec", "ReviewRequestTarget", "RevisionMeta",
    "RevisionMetaView", "RevisionView", "RevisionsView", "SaveDraft", "SaveDraftResult", "Simulate",
    "SimulationView", "SpecDiffView", "SpecEntity", "Specification", "SpecificationDoc",
    "SpecificationExportView", "TaskEdge", "TaskKind", "TaskNode", "TextFragmentView", "ValidateDraft",
    "ValidationReport",
    "ValidationReportView", "WorkingTreeReviewTarget", "assess_material", "compile_execution_graph",
    "find_revision_id",
    "get_design_brief", "get_plan_ref", "get_plan_summary", "get_revision_meta", "get_revision_specification",
    "publish_review_request_revision", "require_active_plan", "resolve_entity", "revision_materials",
    "validate_revision",
]
# fmt: on
