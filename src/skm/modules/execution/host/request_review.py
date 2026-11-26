"""Resolve host Git inputs before dispatching an immutable review target."""

from __future__ import annotations

import hashlib
from typing import Any, cast
from uuid import UUID

from skm.application_bus.host import HostContext
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.ids import ProjectId, WorkspaceId
from skm.modules.artifacts.public import AddFile, GetFile, ListFiles
from skm.modules.execution.generated.host import RequestReviewReport, RequestReviewRequest
from skm.modules.execution.ports import ReviewCheckoutPathResolver, Vcs
from skm.modules.workspace.public import (
    GetProject,
    ResolveCheckout,
    checkout_id_from_locator,
)


def run(ctx: HostContext, request: RequestReviewRequest) -> RequestReviewReport:
    if request.get("working_tree") and request.get("head") is not None:
        raise error_for(ErrorCode.SCHEMA_INVALID, "head and working_tree are mutually exclusive")
    key = str(request.get("idempotency_key") or ctx.client.new_idempotency_key())
    project_id = ProjectId(UUID(str(request["project_id"])))
    mount = str(request.get("mount", "main"))
    project: Any = ctx.client.ask(GetProject(project_id=project_id))
    if ctx.gateways.has(ReviewCheckoutPathResolver):
        root = ctx.gateways.get(ReviewCheckoutPathResolver).resolve(project_id, mount)
    else:
        checkout: Any = ctx.client.ask(ResolveCheckout(project_id, mount, ctx.host_id))
        root = checkout.local_locator
        if checkout_id_from_locator(root) is not None:
            raise error_for(ErrorCode.CHECKOUT_UNBOUND, "Checkout requires verified machine storage")
    inspector: Any = ctx.gateways.named("skm.modules.workspace.ports.RepositoryInspector")
    vcs = ctx.gateways.get(Vcs)
    head = inspector.resolve_commit(root, str(request.get("head") or "HEAD"))
    if request.get("base") is not None:
        base = inspector.resolve_commit(root, str(request["base"]))
    else:
        branch = request.get("integration_branch")
        if not isinstance(branch, str) or not branch:
            raise error_for(ErrorCode.CONFIG_INVALID, "resolved project integration branch is required")
        integration = inspector.resolve_commit(root, branch)
        base = inspector.merge_base(root, integration, head)
    target: dict[str, Any] = {"kind": "commits", "base_commit": base, "head_commit": head}
    if request.get("working_tree"):
        # The patch is against the pinned base, including both committed and dirty changes.
        patch = vcs.diff(inspector.checkout_path(root), base)
        patch_digest = hashlib.sha256(patch).hexdigest()
        add_key = "review_patch_" + hashlib.sha256((key + patch_digest).encode()).hexdigest()
        version_id = None
        after = None
        while True:
            page: Any = ctx.client.ask(
                ListFiles.from_json(
                    {
                        "workspace_id": str(project.workspace_id),
                        "project_id": str(project_id),
                        "origin": "patch",
                        "limit": 200,
                        **({"after": after} if after else {}),
                    }
                )
            )
            for item in page.items:
                if item.title == add_key:
                    stored: Any = ctx.client.ask(GetFile(file_id=item.file_id))
                    if stored.current_version.digest == "sha256:" + patch_digest:
                        version_id = stored.current_version.file_version_id
                    break
            if version_id is not None or page.next is None:
                break
            after = page.next
        if version_id is None:
            staged = ctx.client.upload_blob(
                WorkspaceId(project.workspace_id), (patch,), size=len(patch), media_type="text/x-diff"
            )
            version: Any = ctx.client.dispatch(
                AddFile.from_json(
                    {
                        "workspace_id": str(project.workspace_id),
                        "project_id": str(project_id),
                        "title": add_key,
                        "original_filename": "review.patch",
                        "blob": staged.to_json(),
                        "origin": "patch",
                        "classification": "internal",
                        "source": {"kind": "generated"},
                    }
                ),
                idempotency_key=add_key,
            )
            version_id = version.file_version_id
        target = {
            "kind": "working_tree",
            "base_commit": base,
            "patch_file_version_id": str(version_id),
        }
    from skm.modules.execution.domain.review_request import RequestReview as ReviewCommand

    command = ReviewCommand.from_json(
        {
            "project_id": str(project_id),
            "mount": mount,
            "target": target,
            "profile_key": str(request.get("profile_key", "reviewer")),
            "reason": str(request.get("reason", "Owner requested review")),
        }
    )
    result: Any = ctx.client.dispatch(command, idempotency_key=key)
    return cast("RequestReviewReport", result.to_json())
