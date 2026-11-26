"""``planning.create_plan`` (planning §7.1): a plan, its alias and its scope in one unit of work.

The counter row, the scope row and the plan row commit together: a refusal after the allocation (an invalid
title) rolls the number back, so no alias is lost and no scope is left without a plan. The scope row comes
first because ``plans.id`` references ``skm_core.scopes.id``.

Template resources are rendered into an ordinary draft within the same unit of work.
"""

from collections.abc import Mapping
from typing import Any, cast

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.ids import PlanId, ProjectId, ResourceVersionId, ScopeId, WorkspaceId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef, ScopeRegistry
from skm.modules.extensions import public as extensions
from skm.modules.planning.application.commands.save_draft import (
    _require_canonical,  # pyright: ignore[reportPrivateUsage]
    _require_schema,  # pyright: ignore[reportPrivateUsage]
    _require_size,  # pyright: ignore[reportPrivateUsage]
)
from skm.modules.planning.domain import draft as draft_rules
from skm.modules.planning.domain import plan as plan_rules
from skm.modules.planning.domain import templates
from skm.modules.planning.domain.canonical import normalize_document
from skm.modules.planning.domain.events import DraftOpened, PlanCreated
from skm.modules.planning.generated.commands import CreatePlan
from skm.modules.planning.generated.results import CreatePlanResult
from skm.modules.planning.generated.settings import PlanningSettings
from skm.modules.planning.ports import DraftRepository, PlanCounters, PlanRepository
from skm.modules.workspace import public as workspace
from skm.platform.config.sources.document import decode_document

__all__ = ["SPEC", "handle", "scope_of"]


def scope_of(cmd: CreatePlan) -> ScopeRef:
    return ScopeRef(ScopeKind.PROJECT, ScopeId(cmd.project_id))


def _load_manifest(version: Any, bodies: Mapping[str, str] | None) -> Mapping[str, Any] | None:
    if bodies is not None and "manifest.toml" in bodies:
        try:
            return decode_document(bodies["manifest.toml"], "toml")
        except (TypeError, ValueError) as exc:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID, "invalid template bodies", details={"reason": str(exc)}
            ) from exc
    raw_manifest = getattr(version, "manifest", None)
    if isinstance(raw_manifest, Mapping):
        return dict(cast("Mapping[str, Any]", raw_manifest))
    return None


def handle(cmd: CreatePlan, ctx: CommandContext, uow: UnitOfWork) -> CreatePlanResult:
    if cmd.template_inputs is not None and cmd.template_key is None:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "template_inputs requires template_key",
            details={"field": "template_inputs"},
        )
    if cmd.template_key is not None and not cmd.template_key.strip():
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "template_key must not be empty",
            details={"field": "template_key"},
        )
    project_id = ProjectId(cmd.project_id)
    workspace.require_active_project(uow, project_id)
    project = workspace.get_project(uow, project_id)
    settings = ctx.config.section(PlanningSettings)
    plan_no = uow.repo(PlanCounters).allocate_plan_no(WorkspaceId(project.workspace_id), project_id)
    plan = plan_rules.new_plan(
        PlanId(ctx.ids.new_id()),
        project,
        f"{settings.aliases.prefix}{plan_no}",
        cmd.title,
        ctx.actor.principal_id,
        ctx.clock.now(),
    )
    draft = None
    if cmd.template_key is not None:
        resource = extensions.resolve_resource(
            uow,
            extensions.ResourceKind.PLAN_TEMPLATE,
            cmd.template_key,
            config=ctx.config,
        )
        version = extensions.get_resource_version(
            uow, ResourceVersionId(resource.resource_version_id), include_bodies=True
        )
        manifest = _load_manifest(version, version.bodies)
        schema, body = templates.parse_bodies(manifest, version.bodies)
        document = templates.render_template(
            body,
            cmd.template_inputs or {},
            schema,
            plan.title,
            ctx.ids,
            {
                "key": resource.key,
                "version": resource.version,
                "digest": resource.digest,
                "resource_version_id": str(resource.resource_version_id),
            },
        )
        _require_schema(document)
        _require_canonical(document)
        _require_size(document, settings.drafts.max_document_bytes)
        document = normalize_document(document)
        draft = draft_rules.open_draft(
            draft_rules.DraftId(ctx.ids.new_id()),
            plan,
            None,
            document,
            ctx.actor.principal_id,
            ctx.clock.now(),
        )
    uow.repo(ScopeRegistry).create(
        ScopeId(plan.id), ScopeKind.PLAN, parent=ScopeId(project_id), workspace_id=plan.workspace_id
    )
    uow.repo(PlanRepository).add(plan)
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
    if draft is not None:
        uow.repo(DraftRepository).add(draft)
        uow.record(
            DraftOpened(
                plan_id=plan.id,
                workspace_id=plan.workspace_id,
                draft_id=draft.id,
                base_revision_id=None,
                source="template",
                edit_version=draft.edit_version,
            )
        )
    return CreatePlanResult(
        plan_id=plan.id,
        workspace_id=plan.workspace_id,
        project_id=plan.project_id,
        alias=plan.alias,
        title=plan.title,
        lifecycle_state="active",
        row_version=plan.row_version,
        draft_id=None if draft is None else draft.id,
        edit_version=None if draft is None else draft.edit_version,
    )


SPEC = CommandSpec(
    name="planning.create_plan",
    dto=CreatePlan,
    result=CreatePlanResult,
    permission="plan.create",
    scope_of=scope_of,
    idempotency=IdempotencyMode.REQUIRED,
    handler=handle,
)
