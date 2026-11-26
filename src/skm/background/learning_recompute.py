"""Periodically rebuild learning confidence for every workspace."""

from base64 import b32encode
from typing import Any, Protocol

from skm.kernel.actor import SYSTEM_PRINCIPAL_ID, Actor, PrincipalKind
from skm.kernel.clock import Clock
from skm.kernel.id_generator import IdGenerator
from skm.kernel.ids import ScopeId
from skm.kernel.ports_uow import RequestMeta, Surface, UnitOfWorkFactory
from skm.kernel.scopes import ScopeKind, ScopeRegistry

from .service_runner import TickResult

__all__ = ["LearningRecompute"]


class _Bus(Protocol):
    def dispatch(self, cmd: object, *, actor: Actor, meta: RequestMeta) -> Any: ...


class _Registry(Protocol):
    def command_by_name(self, name: str) -> Any: ...


class LearningRecompute:
    name = "learning_recompute"

    def __init__(
        self,
        bus: _Bus,
        *,
        registry: _Registry,
        clock: Clock,
        ids: IdGenerator,
        uow_factory: UnitOfWorkFactory,
    ) -> None:
        self._bus = bus
        self._dto = registry.command_by_name("learning.recompute_confidence").dto
        self._clock = clock
        self._ids = ids
        self._uow_factory = uow_factory

    def _meta(self, *, write: bool = False) -> RequestMeta:
        identity = b32encode(self._ids.new_id().bytes).decode("ascii").rstrip("=")
        return RequestMeta(
            "req_" + identity,
            Surface.BACKGROUND,
            "learning:" + identity if write else None,
            self._clock.now(),
        )

    def tick(self) -> TickResult:
        after: ScopeId | None = None
        total = 0
        actor = Actor(SYSTEM_PRINCIPAL_ID, PrincipalKind.SERVICE, "system")
        while True:
            with self._uow_factory(self._meta(), readonly=True) as uow:
                batch = uow.repo(ScopeRegistry).list_scopes(after=after, limit=500)
            if not batch:
                return TickResult(total)
            after = batch[-1].id
            for scope in batch:
                if scope.kind is ScopeKind.WORKSPACE:
                    result = self._bus.dispatch(
                        self._dto.from_json({"workspace_id": str(scope.id)}),
                        actor=actor,
                        meta=self._meta(write=True),
                    )
                    total += int(result["recomputed"])
