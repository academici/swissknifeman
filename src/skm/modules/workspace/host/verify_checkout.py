"""``workspace.host.verify_checkout`` (workspace §6.3, §9, §12): re-observe checkouts and record state."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Protocol, cast
from uuid import UUID

from skm.application_bus.host import HostContext
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, ValidationFailed
from skm.kernel.ids import HostId, ProjectId, RepositoryId
from skm.kernel.module_manifest import HostOperationSpec
from skm.modules.workspace.domain.checkout_binding import CheckoutBindingId
from skm.modules.workspace.generated.commands import RecordCheckoutVerification
from skm.modules.workspace.generated.queries import (
    ListProjectRepositories,
    ResolveCheckout,
)
from skm.modules.workspace.generated.results import RecordCheckoutVerificationResult
from skm.modules.workspace.generated.views import (
    CheckoutLocationView,
    ListProjectRepositoriesView,
    MountView,
)
from skm.modules.workspace.ports import RepositoryInspector

from .checkout_config import checkout_marker_relpath, git_timeout_seconds
from .checkout_transaction import BeginVerification, VerifyCheckoutRoot

if TYPE_CHECKING:
    from skm.kernel.json_types import JsonObject

__all__ = [
    "SPEC",
    "VerifyCheckoutItem",
    "VerifyCheckoutOperation",
    "VerifyCheckoutReport",
    "VerifyCheckoutRequest",
    "run",
    "verify_checkout",
]

type BindingStateLiteral = Literal["active", "missing", "mismatched", "removed"]


@dataclass(frozen=True, slots=True)
class VerifyCheckoutRequest:
    """Parameters for ``workspace.host.verify_checkout``."""

    project_id: ProjectId | None = None
    repository_id: RepositoryId | None = None
    mount_name: str | None = None
    binding_id: CheckoutBindingId | None = None
    local_locator: str | None = None
    expected_row_version: int | None = None


@dataclass(frozen=True, slots=True)
class VerifyCheckoutItem:
    """Verification outcome for a single checkout binding."""

    binding_id: CheckoutBindingId
    repository_id: RepositoryId | None
    mount_name: str | None
    local_locator: str
    state: BindingStateLiteral
    reason: str | None
    row_version: int

    def to_json(self) -> JsonObject:
        return {
            "binding_id": str(self.binding_id),
            "repository_id": None if self.repository_id is None else str(self.repository_id),
            "mount_name": self.mount_name,
            "local_locator": self.local_locator,
            "state": self.state,
            "reason": self.reason,
            "row_version": self.row_version,
        }


@dataclass(frozen=True, slots=True)
class VerifyCheckoutReport:
    """Outcome of ``workspace.host.verify_checkout``."""

    host_id: HostId
    project_id: ProjectId | None
    items: tuple[VerifyCheckoutItem, ...]

    def to_json(self) -> JsonObject:
        return {
            "host_id": str(self.host_id),
            "project_id": None if self.project_id is None else str(self.project_id),
            "items": [item.to_json() for item in self.items],
        }


class VerifyCheckoutOperation(Protocol):
    def __call__(
        self, ctx: HostContext, request: VerifyCheckoutRequest | Mapping[str, Any]
    ) -> VerifyCheckoutReport: ...


def _coerce_request(request: VerifyCheckoutRequest | Mapping[str, Any]) -> VerifyCheckoutRequest:
    if isinstance(request, VerifyCheckoutRequest):
        return request
    proj_raw = request.get("project_id")
    repo_raw = request.get("repository_id")
    bind_raw = request.get("binding_id")
    ver_raw = request.get("expected_row_version")
    return VerifyCheckoutRequest(
        project_id=None
        if proj_raw is None
        else ProjectId(proj_raw if isinstance(proj_raw, UUID) else UUID(str(proj_raw))),
        repository_id=None
        if repo_raw is None
        else RepositoryId(repo_raw if isinstance(repo_raw, UUID) else UUID(str(repo_raw))),
        mount_name=None if request.get("mount_name") is None else str(request["mount_name"]),
        binding_id=None
        if bind_raw is None
        else CheckoutBindingId(bind_raw if isinstance(bind_raw, UUID) else UUID(str(bind_raw))),
        local_locator=None if request.get("local_locator") is None else str(request["local_locator"]),
        expected_row_version=None if ver_raw is None else int(ver_raw),
    )


def _verify_one(  # noqa: PLR0913
    ctx: HostContext,
    inspector: RepositoryInspector,
    *,
    binding_id: CheckoutBindingId,
    repository_id: RepositoryId | None,
    mount_name: str | None,
    local_locator: str,
    expected_row_version: int,
    marker_relpath: str,
    timeout_seconds: float,
    begin: BeginVerification | None = None,
    wire_locator: str | None = None,
) -> VerifyCheckoutItem:
    observed = inspector.observe(
        local_locator, marker_relpath=marker_relpath, timeout_seconds=timeout_seconds
    )
    transaction = begin(wire_locator, observed) if begin is not None and wire_locator is not None else None
    observed_locator = observed.toplevel
    if transaction is not None and observed_locator is not None:
        if observed_locator != local_locator:
            raise ValidationFailed(ErrorCode.CHECKOUT_MISMATCH, "Checkout root changed during verification")
        observed_locator = transaction.locator
    command = RecordCheckoutVerification(
        binding_id=binding_id,
        expected_row_version=expected_row_version,
        observed_exists=observed.exists,
        observed_toplevel=observed_locator,
        observed_remotes=tuple(item.value for item in observed.remotes),
        observed_head=observed.head,
        observed_dirty=observed.dirty,
        observed_at=observed.observed_at,
    )
    result = cast(
        "RecordCheckoutVerificationResult",
        ctx.client.dispatch(command, idempotency_key=ctx.client.new_idempotency_key())
        if transaction is None
        else transaction.dispatch("verify_checkout", command),
    )
    return VerifyCheckoutItem(
        binding_id=CheckoutBindingId(result.binding_id),
        repository_id=repository_id,
        mount_name=mount_name,
        local_locator=local_locator,
        state=result.state,
        reason=result.reason,
        row_version=result.row_version,
    )


def verify_checkout(
    ctx: HostContext,
    request: VerifyCheckoutRequest | Mapping[str, Any],
    *,
    resolve_root: VerifyCheckoutRoot | None = None,
    begin: BeginVerification | None = None,
) -> VerifyCheckoutReport:
    """Re-observe local checkouts for a project (or single binding) and record verification state."""
    req = _coerce_request(request)
    inspector = ctx.gateways.get(RepositoryInspector)
    marker_relpath = checkout_marker_relpath(ctx)
    timeout_seconds = git_timeout_seconds(ctx)

    if req.binding_id is not None and req.local_locator is not None and req.expected_row_version is not None:
        item = _verify_one(
            ctx,
            inspector,
            binding_id=req.binding_id,
            repository_id=req.repository_id,
            mount_name=req.mount_name,
            local_locator=req.local_locator,
            expected_row_version=req.expected_row_version,
            marker_relpath=marker_relpath,
            timeout_seconds=timeout_seconds,
        )
        return VerifyCheckoutReport(host_id=ctx.host_id, project_id=req.project_id, items=(item,))

    if req.project_id is None:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "project_id is required to verify project checkouts",
            details={"reason": "project_required"},
        )

    mounts_raw = ctx.client.ask(ListProjectRepositories(project_id=req.project_id, host_id=ctx.host_id))
    if isinstance(mounts_raw, ListProjectRepositoriesView):
        selected: list[MountView] = list(mounts_raw.items)
    else:
        selected = list(cast("tuple[MountView, ...]", mounts_raw))
    if req.repository_id is not None:
        selected = [m for m in selected if RepositoryId(m.repository.repository_id) == req.repository_id]
    if req.mount_name is not None:
        selected = [m for m in selected if m.mount_name == req.mount_name]
    if req.binding_id is not None:
        selected = [m for m in selected if m.binding is not None and m.binding.binding_id == req.binding_id]
    if (
        req.repository_id is not None or req.mount_name is not None or req.binding_id is not None
    ) and not selected:
        raise NotFound(
            ErrorCode.NOT_FOUND,
            "Requested repository or mount is not attached to the project",
            details={
                "kind": "mount",
                "project_id": str(req.project_id),
                "repository_id": None if req.repository_id is None else str(req.repository_id),
                "mount_name": req.mount_name,
            },
        )

    verified_items: list[VerifyCheckoutItem] = []
    for mount in selected:
        if mount.binding is None:
            continue
        locator = mount.binding.local_locator
        if locator is None:
            loc_view = cast(
                "CheckoutLocationView",
                ctx.client.ask(
                    ResolveCheckout(
                        project_id=req.project_id,
                        mount_name=mount.mount_name,
                        host_id=ctx.host_id,
                    )
                ),
            )
            locator = loc_view.local_locator
        verified_items.append(
            _verify_one(
                ctx,
                inspector,
                binding_id=CheckoutBindingId(mount.binding.binding_id),
                repository_id=RepositoryId(mount.repository.repository_id),
                mount_name=mount.mount_name,
                local_locator=(
                    resolve_root(locator, mount.repository.repository_id) if resolve_root else locator
                ),
                wire_locator=locator,
                begin=begin,
                expected_row_version=mount.binding.row_version,
                marker_relpath=marker_relpath,
                timeout_seconds=timeout_seconds,
            )
        )

    return VerifyCheckoutReport(
        host_id=ctx.host_id,
        project_id=req.project_id,
        items=tuple(verified_items),
    )


def run(ctx: HostContext, request: VerifyCheckoutRequest | Mapping[str, Any]) -> VerifyCheckoutReport:
    return verify_checkout(ctx, request)


SPEC = HostOperationSpec(
    name="workspace.host.verify_checkout",
    run=run,
    request=cast("type[object]", VerifyCheckoutRequest),
    result=VerifyCheckoutReport,
    surfaces=cast("frozenset[Any]", frozenset({"cli", "worker"})),
)
