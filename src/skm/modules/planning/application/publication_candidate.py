"""Prepare and validate a draft's publication candidate (planning §7.5 steps 4-6, §8.3).

``prepare_publication_candidate`` works on a canonical copy of ``draft.document``, resolves any
``latest_at_publish`` file materials once through ``resolve_publication_materials``, runs the domain
validation pipeline over ``build_validation_context``, and computes both the raw draft digest and the
resolved candidate ``content_digest``. ``require_publishable`` enforces the publication gates in normative
order: ``PLAN_NOT_READY``, ``VERSION_CONFLICT(reason="candidate_changed")``, and ``NO_CHANGES``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, NotFound, PreconditionFailed
from skm.kernel.ids import ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.planning.application.revision_writer import (
    PinnedMaterial,
    resolve_publication_materials,
)
from skm.modules.planning.application.validation_context import build_validation_context
from skm.modules.planning.domain import draft as draft_rules
from skm.modules.planning.domain import plan as plan_rules
from skm.modules.planning.domain.canonical import normalize_document, specification_digest
from skm.modules.planning.domain.specification import Specification, from_document
from skm.modules.planning.domain.validation.findings import (
    Finding,
    RuleFailure,
    Severity,
    ValidationReport,
)
from skm.modules.planning.domain.validation.pipeline import validate
from skm.modules.planning.generated.settings import PlanningSettings
from skm.modules.planning.ports import RevisionRepository, SpecificationDoc
from skm.modules.workspace import public as workspace

if TYPE_CHECKING:
    from collections.abc import Mapping

    from skm.application_bus.context import CommandContext, QueryContext
    from skm.kernel.json_types import JsonObject, JsonValue
    from skm.kernel.ports_uow import UnitOfWork
    from skm.modules.planning.domain.draft import Draft
    from skm.modules.planning.domain.plan import Plan

__all__ = [
    "PublicationCandidate",
    "finding_to_json",
    "prepare",
    "prepare_publication_candidate",
    "require_publishable",
    "rule_failure_to_json",
]


@dataclass(frozen=True, slots=True)
class PublicationCandidate:
    """Prepared publication candidate shared by ``publish_revision`` and ``preview_publication``."""

    spec: Specification
    document: SpecificationDoc
    document_digest: str
    content_digest: str
    pinned_materials: tuple[PinnedMaterial, ...]
    report: ValidationReport
    counts: Mapping[Severity, int]
    has_errors: bool
    base_changed: bool
    no_changes: bool
    publishable: bool


def finding_to_json(found: Finding) -> JsonObject:
    """Serialize a domain ``Finding`` into structured error details JSON."""
    return {
        "code": found.code,
        "severity": found.severity.value,
        "message": found.message,
        "entity_key": found.entity_key,
        "entity_id": None if found.entity_id is None else str(found.entity_id),
        "pointer": found.pointer,
        "details": dict(found.details),
    }


def rule_failure_to_json(failure: RuleFailure) -> JsonObject:
    """Serialize a validator ``RuleFailure`` into structured error details JSON."""
    return {
        "rule": failure.rule,
        "error_type": failure.error_type,
        "message": failure.message,
        "plugin": failure.plugin,
    }


def _plugin_failures_block(
    settings: PlanningSettings | Mapping[str, JsonValue],
) -> bool:
    if isinstance(settings, PlanningSettings):
        return settings.validation.external_failure.value == "error"
    validation_sec = settings.get("validation")
    if isinstance(validation_sec, dict):
        return validation_sec.get("external_failure") == "error"
    return False


def prepare_publication_candidate(
    uow: UnitOfWork,
    ctx: CommandContext | QueryContext,
    plan: Plan,
    draft: Draft,
    *,
    expected_edit_version: int | None = None,
    settings: PlanningSettings | Mapping[str, JsonValue] | None = None,
) -> PublicationCandidate:
    """Prepare and validate the publication candidate for ``draft`` without mutating ``draft``."""
    draft_rules.require_in_plan(draft, plan.id)
    if draft.workspace_id != plan.workspace_id:
        raise NotFound(
            ErrorCode.NOT_FOUND,
            "draft not found",
            details={"kind": "draft", "ref": str(draft.id)},
        )
    plan_rules.require_editable(plan)
    draft_rules.require_open(draft)
    if expected_edit_version is not None:
        draft_rules.require_edit_version(draft, expected_edit_version)
    draft_rules.require_current_base(draft, plan)
    workspace.require_active_project(uow, plan.project_id)

    resolved_settings = ctx.config.section(PlanningSettings) if settings is None else settings
    normalized_draft_doc = normalize_document(draft.document)
    document_digest = specification_digest(normalized_draft_doc)

    resolved_doc, pinned_materials = resolve_publication_materials(
        uow,
        plan.workspace_id,
        normalized_draft_doc,
        ctx=ctx,
        default_scope=ScopeRef(ScopeKind.PROJECT, ScopeId(plan.project_id)),
    )
    canonical_doc = normalize_document(resolved_doc)
    spec, _ = from_document(canonical_doc)

    vctx = build_validation_context(
        uow,
        ctx,
        plan,
        spec=spec,
        document=canonical_doc,
        settings=resolved_settings,
        now=ctx.clock.now(),
    )
    report = validate(vctx)
    counts = report.counts()
    has_errors = report.has_errors(plugin_failures_block=_plugin_failures_block(resolved_settings))

    content_digest = specification_digest(canonical_doc)
    base_changed = draft.base_revision_id != plan.current_revision_id

    if plan.current_revision_id is not None:
        current_meta = uow.repo(RevisionRepository).get_meta(plan.current_revision_id)
        no_changes = content_digest == current_meta.content_digest
    else:
        no_changes = False

    publishable = not base_changed and not no_changes and not has_errors
    return PublicationCandidate(
        spec=spec,
        document=canonical_doc,
        document_digest=document_digest,
        content_digest=content_digest,
        pinned_materials=pinned_materials,
        report=report,
        counts=counts,
        has_errors=has_errors,
        base_changed=base_changed,
        no_changes=no_changes,
        publishable=publishable,
    )


prepare = prepare_publication_candidate


def require_publishable(
    candidate: PublicationCandidate,
    *,
    plan: Plan,
    expected_content_digest: str,
) -> None:
    """Enforce publication readiness, digest CAS, and non-empty diff (planning §7.5 steps 5-6)."""
    if candidate.has_errors:
        findings_json: list[JsonValue] = [
            finding_to_json(found) for found in candidate.report.findings if found.severity is Severity.ERROR
        ]
        failures_json: list[JsonValue] = [
            rule_failure_to_json(failure) for failure in candidate.report.rule_failures
        ]
        raise PreconditionFailed(
            ErrorCode.PLAN_NOT_READY,
            "the specification has validation errors",
            details={
                "findings": findings_json,
                "rule_failures": failures_json,
            },
        )

    if candidate.content_digest != expected_content_digest:
        raise Conflict(
            ErrorCode.VERSION_CONFLICT,
            "the publication candidate digest does not match expected_content_digest",
            details={
                "reason": "candidate_changed",
                "expected_content_digest": expected_content_digest,
                "actual_content_digest": candidate.content_digest,
            },
        )

    if candidate.no_changes:
        raise PreconditionFailed(
            ErrorCode.NO_CHANGES,
            "the specification has no changes from the current revision",
            details={
                "plan_id": str(plan.id),
                "current_revision_id": None
                if plan.current_revision_id is None
                else str(plan.current_revision_id),
                "content_digest": candidate.content_digest,
            },
        )
