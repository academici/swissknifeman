"""Autopilot service: each project tick is an independent system bus command."""

from base64 import b32encode
from collections.abc import Callable, Iterable
from typing import Any

from skm.kernel.actor import SYSTEM_PRINCIPAL_ID, Actor, PrincipalKind
from skm.kernel.clock import Clock
from skm.kernel.id_generator import IdGenerator
from skm.kernel.ids import ProjectId
from skm.kernel.ports_uow import RequestMeta, Surface

from .service_runner import TickResult

__all__ = ["Autopilot"]


class Autopilot:
    name = "autopilot"

    def __init__(
        self,
        bus: Any,
        *,
        registry: Any,
        clock: Clock,
        ids: IdGenerator,
        projects: Callable[[], Iterable[ProjectId]],
    ) -> None:
        self._bus, self._clock, self._ids, self._projects = bus, clock, ids, projects
        self._dto = registry.command_by_name("execution.autopilot_tick").dto

    def tick(self) -> TickResult:
        processed = 0
        for project in self._projects():
            self._bus.dispatch(
                self._dto.from_json({"project_id": str(project)}),
                actor=Actor(SYSTEM_PRINCIPAL_ID, PrincipalKind.SERVICE, "system"),
                meta=RequestMeta(
                    "req_" + b32encode(self._ids.new_id().bytes).decode("ascii").rstrip("="),
                    Surface.BACKGROUND,
                    None,
                    self._clock.now(),
                ),
            )
            processed += 1
        return TickResult(processed)
