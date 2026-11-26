"""Shared revision publication writer and material pinning helpers (planning §7.5, §7.9, §7.11).

``resolve_publication_materials`` resolves ``latest_at_publish`` references once into concrete
``file_version_id`` values inside a normalized document copy (for publication preview and step 6a of
``publish_revision``). ``write_revision`` verifies every pinned ``file_version`` via
``artifacts.public.require_ready_versions`` before writing the immutable revision, its
``revision_file_bindings`` rows, and the updated ``Plan`` inside the caller's unit of work.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from functools import cache
from typing import TYPE_CHECKING, Literal, cast
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError, NotFound, PreconditionFailed, ValidationFailed
from skm.kernel.ids import (
    EntityId,
    FileVersionId,
    PlanId,
    PrincipalId,
    ProjectId,
    RevisionId,
    ScopeId,
    WorkspaceId,
    parse_uuid,
)
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.languages import CODE_SUFFIXES
from skm.kernel.scopes import ScopeKind, ScopeRecord, ScopeRef, ScopeRegistry
from skm.modules.artifacts import public as artifacts
from skm.modules.planning.application.validation_context import build_validation_context
from skm.modules.planning.domain import draft as draft_rules
from skm.modules.planning.domain import plan as plan_rules
from skm.modules.planning.domain.canonical import normalize_document, specification_digest
from skm.modules.planning.domain.draft import Draft
from skm.modules.planning.domain.events import PlanCreated, PlanRevisionPublished
from skm.modules.planning.domain.material import FreshnessPolicy, MaterialKind
from skm.modules.planning.domain.plan import Plan, PlanPurpose, record_publication
from skm.modules.planning.domain.review_request import (
    REVIEW_REQUESTS_ALIAS,
    REVIEW_REQUESTS_TITLE,
    ReviewRequestSpec,
    build_review_request_document,
    coerce_review_request_spec,
)
from skm.modules.planning.domain.revision import RevisionMeta, RevisionOrigin, new_revision_meta
from skm.modules.planning.domain.specification import (
    SPECIFICATION_URN,
    EntityKind,
    SpecEntity,
    Specification,
    from_document,
)
from skm.modules.planning.domain.validation.context import ValidationContext
from skm.modules.planning.domain.validation.findings import Severity, ValidationReport
from skm.modules.planning.domain.validation.pipeline import validate
from skm.modules.planning.generated.settings import PlanningSettings
from skm.modules.planning.ports import (
    DraftRepository,
    MaterialPin,
    PlanRepository,
    RevisionRecord,
    RevisionRepository,
    SpecificationDoc,
)
from skm.modules.workspace import public as workspace
from skm.platform.schema.registry import SchemaRegistry

if TYPE_CHECKING:
    from datetime import datetime

    from skm.application_bus.context import CommandContext, QueryContext
    from skm.kernel.actor import Actor
    from skm.kernel.id_generator import IdGenerator
    from skm.kernel.ports_uow import UnitOfWork
    from skm.platform.config import EffectiveConfig

__all__ = [
    "PinnedMaterial",
    "WrittenRevision",
    "extract_material_pins",
    "publish_service_review_revision",
    "resolve_publication_materials",
    "validate_published_revision",
    "write_revision",
]


@cache
def _schemas() -> SchemaRegistry:
    return SchemaRegistry.load_default()


@dataclass(frozen=True, slots=True)
class PinnedMaterial:
    """Material pin resolution record reported by publication (planning §7.5)."""

    material_key: str
    file_version_id: FileVersionId
    resolved_from: Literal["pinned", "latest_at_publish"]


@dataclass(frozen=True, slots=True)
class WrittenRevision:
    """Outcome of ``write_revision``: updated ``Plan``, persisted ``RevisionMeta`` and material pins."""

    plan: Plan
    meta: RevisionMeta
    pins: tuple[MaterialPin, ...]
    pinned_materials: tuple[PinnedMaterial, ...]
    draft: Draft | None = None

    @property
    def revision_id(self) -> RevisionId:
        return self.meta.id

    @property
    def revision_no(self) -> int:
        return self.meta.revision_no

    @property
    def content_digest(self) -> str:
        return self.meta.content_digest


def _parse_version_id(raw_vid: object, index: int) -> FileVersionId:
    if not isinstance(raw_vid, str):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "file_version_id must be a UUID string",
            details={"pointer": f"/materials/{index}/file_version_id"},
        )
    try:
        return FileVersionId(parse_uuid(raw_vid))
    except ValueError as exc:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "file_version_id must be a valid UUID",
            details={"pointer": f"/materials/{index}/file_version_id"},
        ) from exc


def _material_policy(raw_mat: Mapping[str, JsonValue]) -> str:
    freshness = raw_mat.get("freshness")
    if isinstance(freshness, Mapping):
        f_map = cast("Mapping[str, JsonValue]", freshness)
        return str(f_map.get("policy", FreshnessPolicy.PINNED.value))
    return FreshnessPolicy.PINNED.value


def resolve_publication_materials(
    uow: UnitOfWork,
    workspace_id: WorkspaceId,
    document: SpecificationDoc,
    *,
    ctx: CommandContext | QueryContext | None = None,
    default_scope: ScopeRef | None = None,
) -> tuple[SpecificationDoc, tuple[PinnedMaterial, ...]]:
    """Normalize ``document`` and resolve ``latest_at_publish`` file materials to concrete version IDs.

    When ``ctx`` is provided, checks ``file.read`` in the owning file/project scope and, for a worker, an
    active file ``AccessGrant`` before resolving ``latest_at_publish`` or returning resolved metadata.
    Returns ``(resolved_document, pinned_materials)`` without mutating ``document``. Raises ``NOT_FOUND``
    (``kind="file_version"``) when a referenced ``file_version_id`` does not exist or belongs to another
    workspace, and ``PreconditionFailed(FILE_VERSION_NOT_READY, details={"file_ids": [...]})`` when a
    ``latest_at_publish`` target file is trashed or has no ready version (planning §7.5 step 4).
    """
    resolved = normalize_document(document)
    raw_materials = resolved.get("materials")
    if not isinstance(raw_materials, list):
        return resolved, ()

    missing_versions: dict[FileVersionId, None] = {}
    unready_files: dict[artifacts.FileId, None] = {}
    missing_keys: list[JsonValue] = []
    pinned_items: list[PinnedMaterial] = []

    for index, raw_entry in enumerate(raw_materials):
        if not isinstance(raw_entry, dict):
            continue
        raw_mat = cast("JsonObject", raw_entry)
        if raw_mat.get("kind") != MaterialKind.FILE_VERSION.value:
            continue
        mat_key = str(raw_mat.get("key", f"materials[{index}]"))
        raw_vid = raw_mat.get("file_version_id")
        if raw_vid is None:
            missing_keys.append(mat_key)
            continue
        version_id = _parse_version_id(raw_vid, index)
        if ctx is not None:
            artifacts.require_version_read(
                uow,
                ctx.actor,
                ctx.clock,
                version_id,
                default_scope=default_scope,
            )
        if _material_policy(raw_mat) == FreshnessPolicy.LATEST_AT_PUBLISH.value:
            try:
                file_id = artifacts.file_id_of_version(uow, workspace_id, version_id)
            except NotFound:
                missing_versions[version_id] = None
                continue
            latest = artifacts.latest_ready_version(uow, workspace_id, file_id)
            if latest is None:
                unready_files[file_id] = None
                continue
            latest_vid = FileVersionId(latest.file_version_id)
            if ctx is not None and latest_vid != version_id:
                artifacts.require_version_read(
                    uow,
                    ctx.actor,
                    ctx.clock,
                    latest_vid,
                    default_scope=default_scope,
                    reported_version_id=version_id,
                )
            raw_mat["file_version_id"] = str(latest_vid)
            pinned_items.append(PinnedMaterial(mat_key, latest_vid, "latest_at_publish"))
        else:
            pinned_items.append(PinnedMaterial(mat_key, version_id, "pinned"))

    if missing_keys:
        raise PreconditionFailed(
            ErrorCode.FILE_VERSION_NOT_READY,
            "file_version material has no file_version_id",
            details={"material_keys": missing_keys},
        )
    if missing_versions:
        missing_ids: list[JsonValue] = [str(vid) for vid in missing_versions]
        raise NotFound(
            ErrorCode.NOT_FOUND,
            "file version not found",
            details={"kind": "file_version", "ids": missing_ids},
        )
    if unready_files:
        unready_ids: list[JsonValue] = [str(fid) for fid in unready_files]
        raise PreconditionFailed(
            ErrorCode.FILE_VERSION_NOT_READY,
            "file has no ready version for publication",
            details={"file_ids": unready_ids},
        )
    return resolved, tuple(pinned_items)


def extract_material_pins(spec: Specification) -> tuple[MaterialPin, ...]:
    """Extract immutable ``MaterialPin`` rows for all ``file_version`` materials in ``spec``."""
    missing_keys: list[JsonValue] = []
    pins: list[MaterialPin] = []
    for material in spec.materials:
        if material.kind is not MaterialKind.FILE_VERSION:
            continue
        if material.file_version_id is None:
            missing_keys.append(material.key)
            continue
        pins.append(
            MaterialPin(
                material_id=material.id,
                file_version_id=UUID(str(material.file_version_id)),
                role=material.role,
                selector=None if material.selector is None else deepcopy(material.selector),
            )
        )
    if missing_keys:
        raise PreconditionFailed(
            ErrorCode.FILE_VERSION_NOT_READY,
            "file_version material has no file_version_id",
            details={"material_keys": missing_keys},
        )
    return tuple(pins)


def _spec_entities(spec: Specification) -> tuple[tuple[EntityId, EntityKind], ...]:
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
    return tuple((entity.id, kind) for kind, entities in groups for entity in entities)


def _resolve_execution_deps(
    ctx: CommandContext | None,
    actor: PrincipalId | None,
    ids: IdGenerator | None,
    now: datetime | None,
) -> tuple[PrincipalId, IdGenerator | None, datetime]:
    resolved_actor = actor if actor is not None else (None if ctx is None else ctx.actor.principal_id)
    resolved_ids = ids if ids is not None else (None if ctx is None else ctx.ids)
    resolved_now = now if now is not None else (None if ctx is None else ctx.clock.now())
    if resolved_actor is None or resolved_now is None:
        raise InternalError(
            ErrorCode.INTERNAL_ERROR,
            "write_revision requires either CommandContext or explicit actor and now",
            details={"reason": "missing_context"},
        )
    return resolved_actor, resolved_ids, resolved_now


def write_revision(  # noqa: PLR0913 -- shared revision writer contract (planning §7.5, §7.9, §7.11)
    uow: UnitOfWork,
    ctx: CommandContext | None,
    plan: Plan,
    spec: Specification,
    document: SpecificationDoc,
    digest: str,
    *,
    origin: RevisionOrigin,
    reason: str,
    restored_from: RevisionId | None = None,
    revision_id: RevisionId | None = None,
    actor: PrincipalId | None = None,
    ids: IdGenerator | None = None,
    now: datetime | None = None,
    pinned_materials: tuple[PinnedMaterial, ...] | None = None,
    draft: Draft | None = None,
    emit_event: bool = False,
) -> WrittenRevision:
    """Verify file-version readiness and persist the immutable revision, pins, and updated plan."""
    resolved_actor, resolved_ids, resolved_now = _resolve_execution_deps(ctx, actor, ids, now)
    if revision_id is None:
        if resolved_ids is None:
            raise InternalError(
                ErrorCode.INTERNAL_ERROR,
                "write_revision requires CommandContext.ids, ids, or an explicit revision_id",
                details={"reason": "missing_id_generator"},
            )
        rev_id = RevisionId(resolved_ids.new_id())
    else:
        rev_id = revision_id

    pins = extract_material_pins(spec)
    if pins:
        artifacts.require_ready_versions(
            uow,
            plan.workspace_id,
            tuple(FileVersionId(pin.file_version_id) for pin in pins),
        )

    meta = new_revision_meta(
        rev_id,
        plan,
        content_digest=digest,
        origin=origin,
        restored_from=restored_from,
        change_reason=reason,
        actor=resolved_actor,
        now=resolved_now,
    )

    revisions = uow.repo(RevisionRepository)
    plans = uow.repo(PlanRepository)
    if spec.design_brief_id is not None:
        plans.get_design_brief(plan.id, spec.design_brief_id)
    known = revisions.identities(plan.id)
    new_identities = tuple(
        (entity_id, kind) for entity_id, kind in _spec_entities(spec) if entity_id not in known
    )
    project_refs = plans.project_plan_refs(plan.project_id)
    plan_relation_targets = tuple(project_refs.get(rel.target) for rel in spec.plan_relations)

    record = RevisionRecord(
        meta=meta,
        spec=spec,
        document=deepcopy(document),
        new_identities=new_identities,
        pins=pins,
        plan_relation_targets=plan_relation_targets,
    )
    revisions.add(record)

    updated_plan = record_publication(plan, meta.id, spec.title, resolved_now)
    plans.save(updated_plan, expected_version=plan.row_version)

    published_draft: Draft | None = None
    if draft is not None:
        published_draft = draft_rules.mark_published(draft, meta.id, resolved_now, actor=resolved_actor)
        uow.repo(DraftRepository).save(published_draft, expected_edit_version=draft.edit_version)

    if emit_event:
        uow.record(
            PlanRevisionPublished(
                plan_id=plan.id,
                workspace_id=plan.workspace_id,
                revision_id=meta.id,
                revision_no=meta.revision_no,
                parent_revision_id=meta.parent_revision_id,
                content_digest=meta.content_digest,
                title=spec.title,
                origin=origin,
                draft_id=None if draft is None else draft.id,
            )
        )

    resolved_pinned = (
        pinned_materials
        if pinned_materials is not None
        else tuple(
            PinnedMaterial(
                material_key=material.key,
                file_version_id=FileVersionId(UUID(str(material.file_version_id))),
                resolved_from="pinned",
            )
            for material in spec.materials
            if material.kind is MaterialKind.FILE_VERSION and material.file_version_id is not None
        )
    )
    return WrittenRevision(
        plan=updated_plan,
        meta=meta,
        pins=pins,
        pinned_materials=resolved_pinned,
        draft=published_draft,
    )


@dataclass(frozen=True, slots=True)
class _FacadeValidationContext:
    """Minimal context carrier supplying ``scope_chain`` and ``config`` to ``build_validation_context``."""

    scope_chain: tuple[ScopeRecord, ...]
    config: EffectiveConfig


def validate_published_revision(
    uow: UnitOfWork,
    revision_id: RevisionId,
    *,
    scope_chain: tuple[ScopeRecord, ...],
    config: EffectiveConfig,
    now: datetime,
) -> ValidationReport:
    """Validate a persisted revision in the current project/workspace/config context (planning §13)."""
    revisions = uow.repo(RevisionRepository)
    meta = revisions.get_meta(revision_id)
    plan = uow.repo(PlanRepository).get(meta.plan_id)
    document = normalize_document(revisions.get_document(revision_id))
    spec, _ = from_document(document)
    facade_ctx = cast("QueryContext", _FacadeValidationContext(scope_chain=scope_chain, config=config))
    return validate(build_validation_context(uow, facade_ctx, plan, spec=spec, document=document, now=now))


def _ensure_review_requests_plan(
    uow: UnitOfWork, project_id: ProjectId, *, actor: PrincipalId, ids: IdGenerator, now: datetime
) -> Plan:
    plans = uow.repo(PlanRepository)
    existing = plans.find_review_requests_plan(project_id)
    if existing is not None:
        plan_rules.require_active(existing)
        return existing

    project = workspace.get_project(uow, project_id)
    plan = plan_rules.new_plan(
        PlanId(ids.new_id()),
        project,
        REVIEW_REQUESTS_ALIAS,
        REVIEW_REQUESTS_TITLE,
        actor,
        now,
        purpose=PlanPurpose.REVIEW_REQUESTS,
    )
    uow.repo(ScopeRegistry).create(
        ScopeId(plan.id), ScopeKind.PLAN, parent=ScopeId(project_id), workspace_id=plan.workspace_id
    )
    plans.add(plan)
    uow.record(
        PlanCreated(
            plan_id=plan.id,
            workspace_id=plan.workspace_id,
            project_id=plan.project_id,
            alias=plan.alias,
            title=plan.title,
            purpose=plan.purpose,
        )
    )
    return plan


def _raise_not_ready(report: ValidationReport) -> None:
    findings_json: list[JsonValue] = [
        {
            "code": f.code,
            "severity": f.severity.value,
            "message": f.message,
            "entity_key": f.entity_key,
            "entity_id": None if f.entity_id is None else str(f.entity_id),
            "pointer": f.pointer,
            "details": dict(f.details),
        }
        for f in report.findings
        if f.severity is Severity.ERROR
    ]
    failures_json: list[JsonValue] = [
        {"rule": r.rule, "error_type": r.error_type, "message": r.message, "plugin": r.plugin}
        for r in report.rule_failures
    ]
    raise PreconditionFailed(
        ErrorCode.PLAN_NOT_READY,
        "the specification has validation errors",
        details={"findings": findings_json, "rule_failures": failures_json},
    )


@cache
def _default_planning_settings() -> JsonObject:
    return PlanningSettings.from_json(
        {
            "validation": {
                "require_acceptance_links": True,
                "warn_unknown_skills": False,
                "warn_unknown_models": False,
                "external_checks": False,
                "external_failure": "warn",
                "code_suffixes": list(CODE_SUFFIXES),
                "heavy_check_markers": [],
                "heavy_text_bytes": 16384,
            },
            "references": {"max_supersede_chain": 8},
            "design_audit": "none",
            "defaults": {"route_class": "implementation", "route_effort": "high", "review_mode": "required"},
            "drafts": {"max_document_bytes": 8388608, "max_open": 20},
            "aliases": {"prefix": "PLAN"},
            "display": {"tree_depth": 3},
        }
    ).to_json()


def publish_service_review_revision(
    uow: UnitOfWork,
    actor: Actor,
    project_id: ProjectId,
    spec: ReviewRequestSpec,
    *,
    ids: IdGenerator,
    now: datetime,
) -> WrittenRevision:
    """Create or reuse the project's ``review_requests`` plan and publish one system revision (§7.11)."""
    validated_spec = coerce_review_request_spec(spec)
    workspace.require_active_project(uow, project_id)
    plan = _ensure_review_requests_plan(uow, project_id, actor=actor.principal_id, ids=ids, now=now)

    revisions = uow.repo(RevisionRepository)
    current_doc = (
        None if plan.current_revision_id is None else revisions.get_document(plan.current_revision_id)
    )
    document = build_review_request_document(validated_spec, ids=ids, current_document=current_doc)
    _schemas().require_valid(SPECIFICATION_URN, document)

    parsed_spec, _ = from_document(document)
    vctx = ValidationContext(
        spec=parsed_spec,
        document=document,
        project_mounts=workspace.project_mounts(uow, plan.project_id),
        known_identities=revisions.identities(plan.id),
        file_versions={},
        known_skills=None,
        runtime_catalog=None,
        project_plans=uow.repo(PlanRepository).project_plan_refs(plan.project_id),
        now=now,
        settings=_default_planning_settings(),
    )
    report = validate(vctx)
    if report.has_errors(plugin_failures_block=False):
        _raise_not_ready(report)

    return write_revision(
        uow,
        None,
        plan,
        parsed_spec,
        document,
        specification_digest(document),
        origin=RevisionOrigin.SYSTEM,
        reason=f"review request {validated_spec.request_id}",
        actor=actor.principal_id,
        ids=ids,
        now=now,
        emit_event=True,
    )
