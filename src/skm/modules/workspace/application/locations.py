"""Resolution of a mount of a project to its checkout binding on a host (workspace §8, §13)."""

from datetime import datetime

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, PreconditionFailed
from skm.kernel.ids import HostId, ProjectId
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.workspace.application.views import location_view
from skm.modules.workspace.domain.checkout_binding import BindingState
from skm.modules.workspace.domain.mount import MountName
from skm.modules.workspace.generated.views import CheckoutLocationView
from skm.modules.workspace.ports import CheckoutBindingRepository, MountRepository, ProjectRepository

__all__ = ["resolve_location"]


def resolve_location(
    uow: UnitOfWork,
    project_id: ProjectId,
    mount_name: str,
    host_id: HostId,
    *,
    now: datetime,
    stale_days: int,
) -> CheckoutLocationView:
    """No mount: ``NOT_FOUND(kind=mount)``; no binding: ``CHECKOUT_UNBOUND``; ``missing|mismatched``:
    ``CHECKOUT_MISMATCH`` with ``details.state``. Permissions are the caller's business."""
    project = uow.repo(ProjectRepository).get(project_id)
    name = MountName(mount_name)
    mount = next(
        (item for item in uow.repo(MountRepository).for_project(project.id) if item.mount_name == name), None
    )
    if mount is None:
        raise NotFound(
            ErrorCode.NOT_FOUND,
            "the project has no such mount",
            details={"kind": "mount", "ref": name.value, "project_id": str(project.id)},
        )
    binding = uow.repo(CheckoutBindingRepository).find(host_id, mount.repository_id)
    if binding is None:
        raise PreconditionFailed(
            ErrorCode.CHECKOUT_UNBOUND,
            "the repository has no checkout on this host",
            details={"repository_id": str(mount.repository_id), "host_id": str(host_id)},
        )
    if binding.state in (BindingState.MISSING, BindingState.MISMATCHED):
        raise PreconditionFailed(
            ErrorCode.CHECKOUT_MISMATCH,
            "the checkout is not usable",
            details={"state": binding.state.value, "binding_id": str(binding.id)},
        )
    return location_view(binding, now=now, stale_days=stale_days)
