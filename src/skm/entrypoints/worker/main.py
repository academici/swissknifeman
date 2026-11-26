"""Select the worker transport and enter the shared host loop."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING
from uuid import UUID

from skm.bootstrap.worker import build_http_worker
from skm.bootstrap.worker_entrypoint import main as run_composed_worker
from skm.entrypoints.mcp.server import serve_stage
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.modules.workspace.public import RecordWorkerHeartbeat
from skm.platform.logging.setup import register_secret

if TYPE_CHECKING:
    from skm.application_bus.client import SkmClient
    from skm.application_bus.host import HostServices
    from skm.bootstrap.worker_rotation import TokenRotation
    from skm.kernel.json_types import JsonObject
    from skm.platform.config.bootstrap import BootstrapConfig
    from skm.platform.machine import MachineStore

__all__ = ["main"]


def main(  # noqa: PLR0913 - shared worker entrypoint with explicitly composed dependencies
    argv: Sequence[str] | None = None,
    *,
    host: HostServices | None = None,
    client: SkmClient | None = None,
    request: JsonObject | None = None,
    rotation: TokenRotation | None = None,
    capacity: int | None = None,
    on_result: Callable[[JsonObject], None] | None = None,
    bootstrap: BootstrapConfig | None = None,
    environ: Mapping[str, str] | None = None,
    on_secret: Callable[[str], None] | None = None,
    machine_store: MachineStore | None = None,
) -> int:
    if bootstrap is None or bootstrap.access_mode == "embedded":
        return run_composed_worker(
            argv,
            host=host,
            client=client,
            request=request,
            rotation=rotation,
            capacity=capacity,
            on_result=on_result,
            stage_mcp=serve_stage,
        )
    if argv or request is None or client is not None or rotation is not None:
        raise ValueError("HTTP worker main requires bootstrap and worker registration")

    def remember(value: str) -> None:
        register_secret(value)
        if on_secret is not None:
            on_secret(value)

    remote, client = build_http_worker(
        bootstrap,
        environ=os.environ if environ is None else environ,
        on_secret=remember,
        local_host=host,
        machine_store=machine_store,
    )
    try:
        if str(remote.host_id) != request.get("host_id", str(remote.host_id)):
            raise ValidationFailed(
                ErrorCode.CONFIG_INVALID, "Worker registration belongs to a different host"
            )
        client.dispatch(
            RecordWorkerHeartbeat(UUID(str(request["worker_id"])), None),
            idempotency_key=client.new_idempotency_key(),
        )
        return run_composed_worker(
            host=remote,
            client=client,
            request={**request, "host_id": str(remote.host_id)},
            capacity=capacity,
            on_result=on_result,
            stage_mcp=serve_stage,
        )
    finally:
        remote.close()
