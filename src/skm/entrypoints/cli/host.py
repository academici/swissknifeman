"""Host context for host-kind commands (cli §1, §1.1): the local facts of this machine plus the client.

The CLI builds no gateways itself: ``HostServices`` (bootstrap) owns them. This module only turns the
services and the invocation's client into the ``HostContext`` a host operation receives, so a host command
reaches the control plane through ``ctx.client`` and nothing else.
"""

from collections.abc import Callable

from skm.application_bus.client import SkmClient
from skm.application_bus.host import HostContext, HostServices
from skm.entrypoints.cli.context import CliContext
from skm.kernel.cancel import CancelSource
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable
from skm.platform.logging.logger import get_logger

__all__ = ["build_host_context", "host_context_factory"]


def host_context_factory(services: HostServices | None, client: SkmClient) -> Callable[[], HostContext]:
    """Factory for ``CliSession.host_factory``; without services (no checkout here) it refuses."""

    def make() -> HostContext:
        if services is None:
            raise CapabilityUnavailable(
                ErrorCode.CAPABILITY_UNAVAILABLE,
                "host services are not available in this composition",
                details={"reason": "no_host_services"},
            )
        return services.context(client=client, cancel=CancelSource().token, log=get_logger("cli.host"))

    return make


def build_host_context(ctx: CliContext) -> HostContext:
    """``HostContext`` for the host operation of a host-kind command (cli §6)."""
    return ctx.host_context()
