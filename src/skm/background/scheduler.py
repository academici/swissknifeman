"""Background bus dispatch with system authority and a fresh request per tick."""

from base64 import b32encode
from typing import Any, Protocol

from skm.kernel.actor import SYSTEM_PRINCIPAL_ID, Actor, PrincipalKind
from skm.kernel.clock import Clock
from skm.kernel.id_generator import IdGenerator
from skm.kernel.ports_uow import RequestMeta, Surface

from .service_runner import TickResult

__all__ = ["ExecutionService", "Scheduler"]


class _Bus(Protocol):
    def dispatch(self, cmd: object, *, actor: Actor, meta: RequestMeta) -> object: ...


class _Registry(Protocol):
    def command_by_name(self, name: str) -> Any: ...


class ExecutionService:
    name: str
    operation: str
    count_key: str

    def __init__(
        self, bus: _Bus, *, registry: _Registry, clock: Clock, ids: IdGenerator, limit: int = 100
    ) -> None:
        if type(limit) is not int or limit < 1:
            raise ValueError("background limit must be a positive integer")
        self._bus = bus
        self._dto = registry.command_by_name(self.operation).dto
        self._clock, self._ids, self._limit = clock, ids, limit

    def tick(self) -> TickResult:
        cmd = self._dto.from_json({"limit": self._limit})
        result: Any = self._bus.dispatch(
            cmd,
            actor=Actor(SYSTEM_PRINCIPAL_ID, PrincipalKind.SERVICE, "system"),
            meta=RequestMeta(
                "req_" + b32encode(self._ids.new_id().bytes).decode("ascii").rstrip("="),
                Surface.BACKGROUND,
                None,
                self._clock.now(),
            ),
        )
        data = result.to_json()
        count = len(data["scheduled"]) if self.count_key == "scheduled" else int(data[self.count_key])
        return TickResult(count, 0.0 if count == self._limit else None)


class Scheduler(ExecutionService):
    name = "scheduler"
    operation = "execution.schedule_ready_tasks"
    count_key = "scheduled"
