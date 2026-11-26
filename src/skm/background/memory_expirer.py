"""Dispatch the internal knowledge expiry operation as the system principal."""

from base64 import b32encode
from typing import Any, Protocol

from skm.kernel.actor import SYSTEM_PRINCIPAL_ID, Actor, PrincipalKind
from skm.kernel.clock import Clock
from skm.kernel.id_generator import IdGenerator
from skm.kernel.ports_uow import RequestMeta, Surface

from .service_runner import TickResult

__all__ = ["MemoryExpirer"]


class _Bus(Protocol):
    def dispatch(self, cmd: object, *, actor: Actor, meta: RequestMeta) -> Any: ...


class _Registry(Protocol):
    def command_by_name(self, name: str) -> Any: ...


class MemoryExpirer:
    name = "memory_expirer"

    def __init__(self, bus: _Bus, *, registry: _Registry, clock: Clock, ids: IdGenerator) -> None:
        self._bus = bus
        self._dto = registry.command_by_name("knowledge.expire_memory").dto
        self._clock = clock
        self._ids = ids

    def tick(self) -> TickResult:
        request_id = "req_" + b32encode(self._ids.new_id().bytes).decode("ascii").rstrip("=")
        command = self._dto.from_json({"batch": 500})
        result = self._bus.dispatch(
            command,
            actor=Actor(SYSTEM_PRINCIPAL_ID, PrincipalKind.SERVICE, "system"),
            meta=RequestMeta(request_id, Surface.BACKGROUND, None, self._clock.now()),
        ).to_json()
        expired, purged = int(result["expired"]), int(result["purged"])
        batch = int(command["batch"])
        return TickResult(expired + purged, 0.0 if max(expired, purged) >= batch else None)
