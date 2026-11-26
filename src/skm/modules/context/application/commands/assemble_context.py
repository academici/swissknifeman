"""Assemble a standalone project context draft owned by the acting principal."""

from typing import cast

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.ids import ContextManifestId, ProjectId, ResourceVersionId, ScopeId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.context.application.assemble_draft import assemble_draft
from skm.modules.context.domain.request import (
    ContextRequest,
    ExecutionBlocks,
    PermissionsSummary,
    RunParams,
    RuntimeTarget,
    StepPurpose,
)
from skm.modules.context.generated.commands import AssembleContext
from skm.modules.context.generated.results import AssembleContextResult
from skm.modules.extensions import public as extensions
from skm.modules.workspace import public as workspace


def scope_of(command: AssembleContext) -> ScopeRef:
    return ScopeRef(ScopeKind.PROJECT, ScopeId(command.project_id))


def handle(command: AssembleContext, ctx: CommandContext, uow: UnitOfWork) -> AssembleContextResult:
    project_id = ProjectId(command.project_id)
    workspace.require_active_project(uow, project_id)
    project = workspace.get_project(uow, project_id)
    config = ctx.config
    packs = extensions.pinned_pack_versions(uow, config=config)
    profile = extensions.select_agent_profile(
        uow, command.role, stage_profile=None, config=config, pins=packs
    )
    role_intensity = cast("JsonObject", config.get("execution.work_policy.role_intensity"))
    role_warn = cast("dict[str, dict[str, int]]", config.get("execution.work_policy.role_warn_seconds"))
    intensity = cast("str", role_intensity[command.role])
    policy: JsonObject = {
        "intensity": intensity,
        "verification_intensity": config.get("execution.work_policy.verification_intensity"),
        "warn_seconds": role_warn[command.role][intensity],
    }
    manifest_id = ContextManifestId(ctx.ids.new_id())
    request = ContextRequest(
        WorkspaceId(project.workspace_id),
        project_id,
        None,
        None,
        None,
        project.slug,
        StepPurpose(command.role, "standalone", None, 1, 1),
        ResourceVersionId(profile.resource_version_id),
        RuntimeTarget(
            command.runtime_id,
            command.model,
            command.context_window_tokens,
            frozenset(),
            frozenset(),
            (),
            "explicit",
            "new_implementation",
            "isolated",
            (),
            frozenset(),
            (),
        ),
        PermissionsSummary((), (), (), (), "none", (), ()),
        RunParams(str(manifest_id), "standalone", 1, 1, None, "none", "notes", "auto", ()),
        ExecutionBlocks(policy, (), None, None, None, (), None, (), ()),
        None,
        "low",
        (),
        packs,
    )
    draft = assemble_draft(
        uow,
        ctx.gateways,
        request,
        config=config,
        actor=ctx.actor,
        owner_ref=f"standalone:{ctx.actor.principal_id}",
        manifest_id=manifest_id,
    )
    return AssembleContextResult(manifest_id=manifest_id, draft_digest=draft.draft_digest)


SPEC = CommandSpec(
    name="context.assemble_context",
    dto=AssembleContext,
    result=AssembleContextResult,
    permission="context.assemble",
    scope_of=scope_of,
    handler=handle,
    idempotency=IdempotencyMode.OPTIONAL,
)
