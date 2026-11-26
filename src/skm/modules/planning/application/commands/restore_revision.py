"""``planning.restore_revision`` (planning §7.9): publish a new revision copied from a past revision.

History is never rewritten: restoring ``R_k`` publishes a new revision ``R_n`` with ``origin = "restore"``,
``parent_revision_id = current``, and ``restored_from_revision_id = R_k``. Material version pins are kept
verbatim from ``R_k`` without re-evaluating ``latest_at_publish``, validated in the current environment,
and written through ``write_revision`` before recording ``PlanRevisionRestored``.
"""

from __future__ import annotations

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, NotFound, PreconditionFailed
from skm.kernel.ids import PlanId, RevisionId, ScopeId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.artifacts import public as artifacts
from skm.modules.planning.application.publication_candidate import (
    finding_to_json,
    rule_failure_to_json,
)
from skm.modules.planning.application.revision_writer import write_revision
from skm.modules.planning.application.validation_context import build_validation_context
from skm.modules.planning.domain import plan as plan_rules
from skm.modules.planning.domain.canonical import (
    CANONICALIZATION_VERSION,
    normalize_document,
    specification_digest,
)
from skm.modules.planning.domain.events import PlanRevisionRestored
from skm.modules.planning.domain.material import MaterialKind
from skm.modules.planning.domain.revision import RevisionOrigin
from skm.modules.planning.domain.specification import from_document
from skm.modules.planning.domain.validation.findings import Severity
from skm.modules.planning.domain.validation.pipeline import validate
from skm.modules.planning.generated.commands import RestoreRevision
from skm.modules.planning.generated.results import RestoreRevisionResult
from skm.modules.planning.generated.settings import PlanningSettings
from skm.modules.planning.ports import PlanRepository, RevisionRepository
from skm.modules.workspace import public as workspace

__all__ = ["SPEC", "handle", "permissions_of", "scope_of"]


def scope_of(cmd: RestoreRevision) -> ScopeRef:
    return ScopeRef(ScopeKind.PLAN, ScopeId(cmd.plan_id))


def permissions_of(_cmd: RestoreRevision) -> tuple[str, ...]:
    """Require both ``plan.publish`` and ``plan.read`` up front (including idempotent replays)."""
    return ("plan.publish", "plan.read")


def _plugin_failures_block(settings: PlanningSettings) -> bool:
    return settings.validation.external_failure == "error"


def handle(cmd: RestoreRevision, ctx: CommandContext, uow: UnitOfWork) -> RestoreRevisionResult:
    plan = uow.repo(PlanRepository).lock(PlanId(cmd.plan_id))
    plan_rules.require_editable(plan)
    workspace.require_active_project(uow, plan.project_id)

    if (
        cmd.expected_current_revision_id is not None
        and RevisionId(cmd.expected_current_revision_id) != plan.current_revision_id
    ):
        raise Conflict(
            ErrorCode.BASE_REVISION_CHANGED,
            "the plan has a new current revision",
            details={
                "expected_current_revision_id": str(cmd.expected_current_revision_id),
                "base_revision_id": str(cmd.expected_current_revision_id),
                "current_revision_id": (
                    None if plan.current_revision_id is None else str(plan.current_revision_id)
                ),
            },
        )

    revisions = uow.repo(RevisionRepository)
    source = revisions.find_by_number(plan.id, cmd.revision_no)
    if source is None:
        raise NotFound(
            ErrorCode.NOT_FOUND,
            "revision not found",
            details={
                "kind": "revision",
                "plan_id": str(plan.id),
                "revision_no": cmd.revision_no,
            },
        )

    # Restore preserves historical pins from source without re-evaluating latest_at_publish (§7.9).
    document = normalize_document(revisions.get_document(source.id))
    spec, _ = from_document(document)

    project_scope = ScopeRef(ScopeKind.PROJECT, ScopeId(plan.project_id))
    for mat in spec.materials:
        if mat.kind is MaterialKind.FILE_VERSION and mat.file_version_id is not None:
            artifacts.require_version_read(
                uow,
                ctx.actor,
                ctx.clock,
                mat.file_version_id,
                default_scope=project_scope,
            )

    settings = ctx.config.section(PlanningSettings)
    now = ctx.clock.now()
    vctx = build_validation_context(
        uow,
        ctx,
        plan,
        spec,
        document,
        settings=settings,
        now=now,
    )
    report = validate(vctx)
    if report.has_errors(plugin_failures_block=_plugin_failures_block(settings)):
        raise PreconditionFailed(
            ErrorCode.PLAN_NOT_READY,
            "the restored specification has validation errors in the current context",
            details={
                "findings": [finding_to_json(f) for f in report.findings if f.severity is Severity.ERROR],
                "rule_failures": [rule_failure_to_json(rf) for rf in report.rule_failures],
            },
        )

    digest = (
        source.content_digest
        if source.canonicalization_version == CANONICALIZATION_VERSION
        else specification_digest(document)
    )
    if plan.current_revision_id is not None:
        current_meta = revisions.get_meta(plan.current_revision_id)
        if digest == current_meta.content_digest:
            raise PreconditionFailed(
                ErrorCode.NO_CHANGES,
                "the restored specification is identical to the current revision",
                details={
                    "current_revision_id": str(plan.current_revision_id),
                    "restored_from_revision_id": str(source.id),
                    "content_digest": digest,
                },
            )

    written = write_revision(
        uow,
        ctx,
        plan,
        spec,
        document,
        digest,
        origin=RevisionOrigin.RESTORE,
        reason=cmd.reason,
        restored_from=source.id,
        emit_event=True,
    )
    uow.record(
        PlanRevisionRestored(
            plan_id=plan.id,
            workspace_id=plan.workspace_id,
            revision_id=written.revision_id,
            revision_no=written.revision_no,
            restored_from_revision_id=source.id,
            restored_from_revision_no=source.revision_no,
            content_digest=written.content_digest,
        )
    )
    return RestoreRevisionResult(
        plan_id=plan.id,
        revision_id=written.revision_id,
        revision_no=written.revision_no,
        parent_revision_id=written.meta.parent_revision_id,
        restored_from_revision_id=source.id,
        restored_from_revision_no=source.revision_no,
        content_digest=written.content_digest,
    )


SPEC = CommandSpec(
    name="planning.restore_revision",
    dto=RestoreRevision,
    result=RestoreRevisionResult,
    permission="plan.publish",
    permissions_of=permissions_of,
    scope_of=scope_of,
    idempotency=IdempotencyMode.REQUIRED,
    handler=handle,
)
