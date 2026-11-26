"""Compose local projection reconciliation with Git excludes for bound checkouts."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import replace
from typing import Any, cast

from skm.application_bus.host import HostContext
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, PreconditionFailed
from skm.kernel.ids import ProjectId, WorkspaceId, parse_uuid
from skm.kernel.module_manifest import HostOperationSpec
from skm.modules.integrations.domain.conflict_names import conflict_path
from skm.modules.integrations.domain.decisions import FileDecisionKind
from skm.modules.integrations.generated.host import (
    SyncProjectionsRequest,
    SyncProjectionsResult,
    SyncProjectionsResultCheckoutsItem,
    UntrackServiceFilesRequest,
    UntrackServiceFilesResult,
    sync_projections_request_from_json,
    untrack_service_files_request_from_json,
)
from skm.modules.integrations.ports import CheckoutGitExcludes, ProjectionConfig
from skm.modules.workspace.public import (
    CheckoutBindingId,
    CheckoutLocationView,
    GetProject,
    GetWorkspace,
    ListProjects,
    ListProjectsView,
    ProjectView,
    WorkspaceView,
)

from .apply_projection import apply_projection
from .observe import (
    bind_checkout_fs,
    has_regular_conflict,
    integrations_settings,
    outcome_to_wire,
    require_local_apply,
    resolve_checkout_for_mount,
)
from .plan_projection import plan_projection

__all__ = ["SYNC_SPEC", "UNTRACK_SPEC", "sync", "untrack"]


def _workspace_projects(ctx: HostContext, workspace_id: WorkspaceId) -> Iterator[ProjectView]:
    after = None
    while True:
        page = ctx.client.ask(ListProjects(workspace_id, state="active", after=after))
        assert isinstance(page, ListProjectsView)  # noqa: S101
        for item in page.items:
            yield _active_project(ctx, ProjectId(item.project_id))
        if page.next is None:
            break
        after = page.next


def _active_project(ctx: HostContext, project_id: ProjectId) -> ProjectView:
    project = ctx.client.ask(GetProject(project_id=project_id))
    assert isinstance(project, ProjectView)  # noqa: S101
    if project.state != "active":
        raise PreconditionFailed(ErrorCode.PROJECT_ARCHIVED, "The project must be active to sync projections")
    return project


def _require_active_workspace(ctx: HostContext, workspace_id: WorkspaceId) -> None:
    view = ctx.client.ask(GetWorkspace(workspace_id=workspace_id))
    assert isinstance(view, WorkspaceView)  # noqa: S101
    if view.state != "active":
        raise PreconditionFailed(
            ErrorCode.PROJECT_ARCHIVED, "The workspace must be active to sync projections"
        )


def _local_mounts(
    ctx: HostContext, projects: Iterator[ProjectView]
) -> list[tuple[ProjectId, str, CheckoutLocationView]]:
    mounts: list[tuple[ProjectId, str, CheckoutLocationView]] = []
    seen: dict[str, ProjectId] = {}
    for project in projects:
        project_id = ProjectId(project.project_id)
        for mount in project.mounts:
            try:
                checkout = resolve_checkout_for_mount(ctx, project_id, mount.mount_name)
            except PreconditionFailed as exc:
                if exc.code is ErrorCode.CHECKOUT_UNBOUND and "binding_id" not in exc.details:
                    continue
                raise
            if seen.setdefault(checkout.local_locator, project_id) != project_id:
                raise Conflict(
                    ErrorCode.PROJECTION_CONFLICT,
                    "Multiple projects share a checkout. Use `skm project activate` to select one.",
                    details={"project_id": str(project_id), "mount": mount.mount_name},
                )
            mounts.append((project_id, mount.mount_name, checkout))
    return mounts


def _sync_mount(
    ctx: HostContext,
    git: CheckoutGitExcludes,
    project_id: ProjectId,
    mount: str,
    checkout: CheckoutLocationView,
) -> SyncProjectionsResultCheckoutsItem:
    config = ctx.gateways.get(ProjectionConfig)(project_id)
    ctx = replace(ctx, config=config)
    plans = plan_projection(ctx, project_id=project_id, mount=mount, resolved_checkout=checkout)
    suffix = integrations_settings(ctx).conflict_suffix
    fs = bind_checkout_fs(ctx, checkout.local_locator)
    paths = {decision.relative_path for plan in plans for decision in plan.decisions}
    conflicts: dict[str, str] = {}
    for plan in plans:
        for write in plan.writes:
            if write.decision is FileDecisionKind.CONFLICT_WRITE_NEW:
                conflicts[write.relative_path] = write.write_path
    # Recover excludes for sidecars already present from a prior apply.
    for path in paths:
        sidecar = conflict_path(path, suffix=suffix)
        if sidecar not in paths and has_regular_conflict(fs, sidecar):
            conflicts[path] = sidecar
    if paths.intersection(conflicts.values()):
        raise Conflict(ErrorCode.PROJECTION_CONFLICT, "A conflict sidecar overlaps a projection path")
    updated = git.sync(
        checkout.local_locator,
        conflict_sources=conflicts.keys(),
        conflict_suffix=suffix,
    )
    outcomes = apply_projection(
        ctx, plans, expected_locators={CheckoutBindingId(checkout.binding_id): checkout.local_locator}
    )
    return {
        "project_id": str(project_id),
        "mount": mount,
        "exclude_updated": updated,
        "outcomes": [outcome_to_wire(outcome) for outcome in outcomes],
    }


def sync(ctx: HostContext, request: object) -> SyncProjectionsResult:
    req = cast("Mapping[str, str]", sync_projections_request_from_json(request))
    scope_id = parse_uuid(req["scope_id"])
    if req["scope"] == "project":
        project = _active_project(ctx, ProjectId(scope_id))
        _require_active_workspace(ctx, WorkspaceId(project.workspace_id))
        projects = iter((project,))
    else:
        workspace_id = WorkspaceId(scope_id)
        _require_active_workspace(ctx, workspace_id)
        projects = _workspace_projects(ctx, workspace_id)
    mounts = _local_mounts(ctx, projects)
    if not mounts and req["scope"] == "project":
        raise PreconditionFailed(ErrorCode.CHECKOUT_UNBOUND, "The project has no checkout on this host")
    for project_id in dict.fromkeys(project_id for project_id, _, _ in mounts):
        require_local_apply(ctx, project_id)
    git = ctx.gateways.get(CheckoutGitExcludes)
    for project_id, mount, checkout in mounts:
        try:
            git.require_untracked(checkout.local_locator)
        except PreconditionFailed as exc:
            if exc.code is not ErrorCode.TRACKED_SERVICE_FILE:
                raise
            command = f"skm integrations untrack-service-files --project {project_id} --mount {mount}"
            raise PreconditionFailed(
                exc.code,
                f"{exc.message}. Run `{command}` and retry.",
                details={**exc.details, "project_id": str(project_id), "mount": mount},
            ) from exc
    return {
        "checkouts": [
            _sync_mount(ctx, git, project_id, mount, checkout) for project_id, mount, checkout in mounts
        ]
    }


def untrack(ctx: HostContext, request: object) -> UntrackServiceFilesResult:
    req = cast("Mapping[str, str]", untrack_service_files_request_from_json(request))
    project_id = ProjectId(parse_uuid(req["project_id"]))
    require_local_apply(ctx, project_id)
    checkout = resolve_checkout_for_mount(ctx, project_id, req.get("mount"))
    git = ctx.gateways.get(CheckoutGitExcludes)
    git.sync(checkout.local_locator)
    return {"untracked": list(git.untrack_service_files(checkout.local_locator))}


SYNC_SPEC = HostOperationSpec(
    name="integrations.host.sync_projections",
    run=sync,
    request=SyncProjectionsRequest,
    result=SyncProjectionsResult,
    surfaces=cast("frozenset[Any]", frozenset({"cli"})),
)

UNTRACK_SPEC = HostOperationSpec(
    name="integrations.host.untrack_service_files",
    run=untrack,
    request=UntrackServiceFilesRequest,
    result=UntrackServiceFilesResult,
    surfaces=cast("frozenset[Any]", frozenset({"cli"})),
)
