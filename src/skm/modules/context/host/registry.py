"""Host operation declarations for checkout context packs."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from skm.kernel.module_manifest import HostOperationSpec

from .pack_context import PackContextRequest, PackContextResult, pack_context

if TYPE_CHECKING:
    from skm.application_bus.host import HostContext


def _pack(ctx: HostContext, request: PackContextRequest) -> PackContextResult:
    return pack_context(ctx.gateways, request)


def operations(cli: Any) -> tuple[HostOperationSpec, ...]:
    return (
        HostOperationSpec(
            "context.host.pack_context", _pack, PackContextRequest, PackContextResult, frozenset({cli})
        ),
    )


HOST_OPERATION_NAMES = ("context.host.research_query", "context.host.pack_context")
