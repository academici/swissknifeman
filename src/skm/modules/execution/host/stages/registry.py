"""Only implemented host stages can be registered."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol

from skm.modules.execution.host.stages.base import StageOutcome, StageRequest


class HostStage(Protocol):
    stage_type: str
    side: str
    params_schema_urn: str

    def run(self, request: StageRequest, deps: Any) -> StageOutcome: ...


class StageRegistry:
    def __init__(self, handlers: Iterable[HostStage]) -> None:
        self._handlers: dict[str, HostStage] = {}
        for handler in handlers:
            if handler.side != "host" or handler.stage_type in self._handlers:
                raise ValueError("duplicate or non-host stage")
            self._handlers[handler.stage_type] = handler

    def for_stage(self, stage_type: str, *, side: str = "host") -> HostStage:
        if side != "host":
            raise ValueError("worker executes host stages only")
        try:
            return self._handlers[stage_type]
        except KeyError:
            raise ValueError(f"host stage {stage_type!r} is not implemented") from None
