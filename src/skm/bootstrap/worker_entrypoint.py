"""Thin worker entry point: construct one HostContext per capacity slot and enter the host loop."""

from __future__ import annotations

import signal
from collections.abc import Callable, Sequence
from threading import Lock
from typing import TYPE_CHECKING, cast

from skm.bootstrap.host_services import run_worker_contexts, with_worker_tick
from skm.bootstrap.stage_broker import StageMcpServer, bind_stage_broker
from skm.bootstrap.worker_rotation import TokenRotation
from skm.kernel.cancel import CancelSource
from skm.modules.execution.host.context import WorkerServices
from skm.modules.runtimes.host.detect_runtimes import detect_runtimes
from skm.modules.runtimes.public import WorkerModelOfferPolicy
from skm.platform.logging.logger import get_logger
from skm.platform.system_clock import SystemMonotonic

if TYPE_CHECKING:
    from types import FrameType
    from uuid import UUID

    from skm.application_bus.client import SkmClient
    from skm.application_bus.host import HostServices
    from skm.kernel.json_types import JsonObject
    from skm.platform.config import EffectiveConfig

__all__ = ["main"]


def main(
    argv: Sequence[str] | None = None,
    *,
    host: HostServices | None = None,
    client: SkmClient | None = None,
    request: JsonObject | None = None,
    rotation: TokenRotation | None = None,
    capacity: int | None = None,
    on_result: Callable[[JsonObject], None] | None = None,
    stage_mcp: StageMcpServer | None = None,
) -> int:
    if argv or host is None or client is None or request is None:
        raise ValueError(
            "worker main requires explicitly composed host services, worker client and registration"
        )
    if stage_mcp is not None:
        host = bind_stage_broker(host, stage_mcp)
    if rotation is None and host.gateways.has(TokenRotation):
        rotation = host.gateways.get(TokenRotation)
    if rotation is not None:
        host = with_worker_tick(host, rotation.tick)
        client = rotation.client
    shutdown = CancelSource()
    if host.gateways.has(WorkerModelOfferPolicy):
        probe_host = host
        redact = host.gateways.get(WorkerServices).redact_runtime_probe
        # All slots share one probe per host process.
        lock = Lock()
        clock = SystemMonotonic()
        next_probe = 0.0
        publisher: UUID | None = None

        def refresh_offers() -> None:
            nonlocal next_probe, publisher
            with lock:
                credential = None if rotation is None else rotation.token_id()
                if credential != publisher or clock.monotonic() >= next_probe:
                    detect_runtimes(
                        probe_host.context(
                            client=client, cancel=shutdown.token, log=get_logger("worker.host")
                        ),
                        publish_local_details=False,
                        redact=redact,
                    )
                    publisher = credential
                    next_probe = clock.monotonic() + 60

        host = with_worker_tick(host, refresh_offers, refresh_offers=True)
    slots = (
        capacity
        if capacity is not None
        else cast("EffectiveConfig", host.host_config()).get("worker.capacity")
    )
    if not isinstance(slots, int) or isinstance(slots, bool) or slots < 1:
        raise ValueError("worker.capacity must be a positive integer")
    contexts = tuple(
        host.context(
            client=client, cancel=CancelSource(parent=shutdown.token).token, log=get_logger("worker.host")
        )
        for _ in range(1 if request.get("once") else slots)
    )

    def stop(_signum: int, _frame: FrameType | None) -> None:
        shutdown.cancel("shutdown")

    previous = signal.signal(signal.SIGTERM, stop)
    try:
        result = run_worker_contexts(contexts, request)
        if on_result is not None:
            on_result(result)
        results = cast("list[JsonObject]", result["slots"])
        return int(any(slot.get("reason") in {"cleanup_unconfirmed", "lease_lost"} for slot in results))
    finally:
        signal.signal(signal.SIGTERM, previous)
