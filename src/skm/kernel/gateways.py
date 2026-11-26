"""Two kinds of gateways and their typed container (kernel-platform §2.11a, mechanisms/01 §4).

Bus handlers reach control-plane gateways through ``CommandContext.gateways``; host operations reach host
gateways through ``HostContext.gateways``. A port is a Protocol declared in ``modules/<owner>/ports.py`` (or
``kernel/tokens.py``, ``platform/config/secrets.py``) and marked with one of the decorators below.

``GatewayTable.get``/``has`` check the port marker against the table kind and report a missing port as
``CAPABILITY_UNAVAILABLE``.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Protocol

from skm.kernel.errors import CapabilityUnavailable
from skm.kernel.generated.error_codes import ErrorCode
from skm.kernel.ports_uow import PORT_KIND_ATTRIBUTE

__all__ = [
    "GatewayTable",
    "GatewayTableKind",
    "Gateways",
    "control_plane_gateway",
    "host_gateway",
    "shared_gateway",
]

type GatewayTableKind = Literal["control_plane_gateway", "host_gateway"]


class Gateways(Protocol):
    def get[G](self, port: type[G]) -> G:
        """Gateway registered for ``port``; none is ``CapabilityUnavailable(CAPABILITY_UNAVAILABLE)``."""
        ...

    def has(self, port: type[object]) -> bool: ...

    def named(self, qualified_name: str) -> object: ...


@dataclass(frozen=True, slots=True)
class GatewayTable:
    """Gateways implementation assembled by bootstrap; one table per kind, never mixed.

    ``get`` accepts only ports whose marker is ``kind`` or ``"shared_gateway"`` (otherwise ``TypeError``).
    """

    entries: Mapping[type[object], object]
    kind: GatewayTableKind

    def _check_marker(self, port: type[object]) -> None:
        marker = getattr(port, PORT_KIND_ATTRIBUTE, None)
        if marker != self.kind and marker != "shared_gateway":
            raise TypeError(f"{port.__name__} (marker {marker!r}) is not allowed in a {self.kind} table")

    def get[G](self, port: type[G]) -> G:
        self._check_marker(port)
        try:
            return self.entries[port]  # type: ignore[return-value]
        except KeyError:
            raise CapabilityUnavailable(
                ErrorCode.CAPABILITY_UNAVAILABLE,
                f"gateway {port.__name__} is not available",
                details={"port": port.__name__},
            ) from None

    def named(self, qualified_name: str) -> object:
        """Resolve a host gateway contract without importing a foreign module's ports."""
        for port in self.entries:
            if port.__module__ + "." + port.__name__ == qualified_name:
                return self.get(port)
        raise CapabilityUnavailable(
            ErrorCode.CAPABILITY_UNAVAILABLE, "gateway is not available", details={"port": qualified_name}
        )

    def has(self, port: type[object]) -> bool:
        self._check_marker(port)
        return port in self.entries


def control_plane_gateway[T: type[object]](cls: T) -> T:
    """Mark a Protocol as a control-plane gateway: bus handlers only, through ``CommandContext.gateways``."""
    setattr(cls, PORT_KIND_ATTRIBUTE, "control_plane_gateway")
    return cls


def host_gateway[T: type[object]](cls: T) -> T:
    """Mark a Protocol as a host gateway: host operations only, through ``HostContext.gateways``."""
    setattr(cls, PORT_KIND_ATTRIBUTE, "host_gateway")
    return cls


def shared_gateway[T: type[object]](cls: T) -> T:
    """Mark a Protocol over immutable data without IO; allowed in tables of both kinds."""
    setattr(cls, PORT_KIND_ATTRIBUTE, "shared_gateway")
    return cls
