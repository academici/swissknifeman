"""Host recovery operates only on a verified containment, never a bare PID."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from skm.kernel.json_types import JsonObject

if TYPE_CHECKING:
    from skm.application_bus.host import HostContext


class RecoveryContainment(Protocol):
    def verify(self, request: JsonObject) -> bool: ...
    def snapshot(self, request: JsonObject, *, stream_bytes: int, events: int) -> JsonObject: ...
    def cancel(self, request: JsonObject, *, grace_seconds: int) -> bool: ...
    def kill(self, request: JsonObject, *, grace_seconds: int) -> bool: ...


class RecoveryOperation:
    def __init__(self, containment: RecoveryContainment) -> None:
        self.containment = containment

    def __call__(self, ctx: HostContext, request: JsonObject) -> JsonObject:
        del ctx
        action = request.get("action", "snapshot")
        if not self.containment.verify(request):
            return {"identity_verified": False, "stopped": False, "reason_code": "OWNERSHIP_UNKNOWN"}
        if action == "snapshot":
            return self.containment.snapshot(request, stream_bytes=65536, events=50)
        if request.get("intervention_authorized") is not True:
            return {"identity_verified": True, "stopped": False, "reason_code": "STALL_SUSPECTED"}
        grace = int(str(request.get("grace_seconds", 60)))
        if action not in {"cooperative_cancel", "kill_group"} or not 1 <= grace <= 600:
            raise ValueError("invalid recovery action or grace")
        operation = self.containment.cancel if action == "cooperative_cancel" else self.containment.kill
        stopped = operation(request, grace_seconds=grace)
        return {
            "identity_verified": True,
            "stopped": stopped,
            "host_degraded": action == "kill_group" and not stopped,
            "reason_code": None if stopped else "CANCEL_IGNORED",
        }
