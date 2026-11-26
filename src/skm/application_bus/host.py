"""Context of host operations (kernel-platform §4.2a, mechanisms/01 §5.2).

A host operation ``def run(ctx: HostContext, request: XRequest) -> XResult`` runs where the checkout
and the runtime are (CLI, worker, hook). It never opens a UoW: every state change is a command through
``ctx.client`` with an idempotency key. ``gateways`` here is always a ``GatewayTable(kind="host_gateway")``.

``HostServices`` does operation lookup, the surface check and context construction. Fields
typed ``object`` wait for their owner declarations: ``config`` is ``EffectiveConfig`` of the host chain plus
invocation, ``log`` is ``StructLogger`` (``docs/architecture/contracts.md``, "Deferred types").
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID

from skm.kernel.cancel import CancelToken
from skm.kernel.errors import Forbidden, InternalError
from skm.kernel.gateways import Gateways, GatewayTable
from skm.kernel.generated.error_codes import ErrorCode
from skm.kernel.ids import HostId
from skm.kernel.ports_uow import Surface

if TYPE_CHECKING:
    from skm.application_bus.client import SkmClient
    from skm.kernel.module_manifest import HostOperationSpec

__all__ = ["HostContext", "HostServices", "check_host_operation_name"]

_HOST_OP_NAME = re.compile(r"[a-z][a-z0-9_]*\.host\.[a-z][a-z0-9_]*")


def _default_logger() -> object:
    from skm.platform.logging.logger import get_logger

    return get_logger("application_bus.host")


def check_host_operation_name(key: str, spec: HostOperationSpec) -> None:
    """Host operations live in ``<module>.host.<operation>`` and the registry key equals ``spec.name``."""
    if not _HOST_OP_NAME.fullmatch(key) or spec.name != key:
        raise ValueError(
            f"host operation {key!r} must be named '<module>.host.<operation>' and match its spec"
        )


@dataclass(frozen=True, slots=True)
class HostContext:
    client: SkmClient  # the only channel to the control plane (embedded or HTTP)
    gateways: Gateways  # host gateways only
    host_id: HostId  # registered host of this process
    config: object  # EffectiveConfig: host chain (instance -> host) + invocation
    log: object  # StructLogger
    cancel: CancelToken
    instance_id: UUID | None = None


@dataclass(slots=True)
class HostServices:
    """Host operation registry plus context factory; ``close`` releases only resources it owns."""

    host_id: HostId
    surface: Surface
    gateways: GatewayTable
    host_config: Callable[[], object]  # re-reads the host chain: EffectiveConfig
    operations: Mapping[str, HostOperationSpec]
    owned_resources: Sequence[Callable[[], None]] = field(
        default=()
    )  # closers of resources built by bootstrap
    log_factory: Callable[[], object] = field(
        default=_default_logger
    )  # StructLogger of a context when the caller passes none
    instance_id: UUID | None = None
    _closed: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.gateways.kind != "host_gateway":
            raise TypeError("HostServices requires a GatewayTable(kind='host_gateway')")
        for key, spec in self.operations.items():
            check_host_operation_name(key, spec)

    def _admit(self, client: SkmClient, operation: str | None = None) -> None:
        bus = getattr(client, "_bus", None)
        guard = getattr(bus, "guard", None)
        if guard is not None:
            guard.host(operation, self.surface)

    def context(self, *, client: SkmClient, cancel: CancelToken, log: object) -> HostContext:
        self._admit(client)
        return HostContext(
            client=client,
            gateways=self.gateways,
            host_id=self.host_id,
            config=self.host_config(),
            instance_id=self.instance_id,
            log=log,
            cancel=cancel,
        )

    def run(
        self, name: str, request: object, *, client: SkmClient, cancel: CancelToken, log: object | None = None
    ) -> object:
        self._admit(client, name)
        spec = self.operations.get(name)
        if spec is None:
            raise InternalError(
                ErrorCode.INTERNAL_ERROR, f"unknown host operation {name!r}", details={"operation": name}
            )
        check_host_operation_name(name, spec)
        if self.surface not in spec.surfaces:
            raise Forbidden(
                ErrorCode.FORBIDDEN,
                f"host operation {name!r} is not allowed on surface {self.surface.value!r}",
                details={"reason_code": "SURFACE_NOT_ALLOWED", "operation": name},
            )
        ctx = self.context(client=client, cancel=cancel, log=self.log_factory() if log is None else log)
        return spec.run(ctx, request)

    def close(self) -> None:
        """Run owned closers once, last registered first; the first failure is raised after all ran."""
        if self._closed:
            return
        self._closed = True
        first: BaseException | None = None
        for closer in reversed(tuple(self.owned_resources)):
            try:
                closer()
            except Exception as exc:  # noqa: BLE001 - keep closing the rest
                first = first or exc
        if first is not None:
            raise first
