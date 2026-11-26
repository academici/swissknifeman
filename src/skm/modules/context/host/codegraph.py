"""Resolve the project's bound checkout before invoking native CodeGraph."""

from typing import TYPE_CHECKING, cast
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed
from skm.kernel.ids import ProjectId
from skm.kernel.json_types import JsonObject
from skm.modules.context.domain.research_rules import invalid
from skm.modules.context.ports import CodeGraphIndex
from skm.modules.workspace.public import CheckoutLocationView, ResolveCheckout

if TYPE_CHECKING:
    from skm.application_bus.host import HostContext

__all__ = ["run"]


def run(ctx: "HostContext", request: JsonObject) -> JsonObject:
    action = request.get("action")
    if action not in ("init", "index", "status", "doctor"):
        raise invalid("invalid_codegraph_action")
    mount = str(request.get("mount") or "main")
    project_id = ProjectId(UUID(str(request["project_id"])))
    location = cast("CheckoutLocationView", ctx.client.ask(ResolveCheckout(project_id, mount, ctx.host_id)))
    if location.state != "active" or location.is_stale:
        raise PreconditionFailed(ErrorCode.CHECKOUT_UNBOUND, "An active checkout binding is required")
    result = ctx.gateways.get(CodeGraphIndex).manage(action, location.local_locator, cancel=ctx.cancel)
    return {"project_id": str(project_id), "mount": mount, **result}
