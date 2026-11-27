"""Host operation declarations; surfaces are supplied by the module composition."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from skm.kernel.module_manifest import HostOperationSpec

from .local_modes import (
    AskRequest,
    DeliberateRequest,
    DeliberateResult,
    DoRequest,
    LocalAnswer,
    local_ask,
    local_deliberate,
    local_do,
)
from .request_review import run

if TYPE_CHECKING:
    from skm.application_bus.host import HostContext


def _ask(ctx: HostContext, request: AskRequest) -> LocalAnswer:
    return local_ask(ctx.gateways, request)


def _do(ctx: HostContext, request: DoRequest) -> LocalAnswer:
    return local_do(ctx.gateways, request)


def _deliberate(ctx: HostContext, request: DeliberateRequest) -> DeliberateResult:
    return local_deliberate(ctx.gateways, request)


def operations(cli: Any, hook: Any) -> tuple[HostOperationSpec, ...]:
    local = frozenset({cli})
    return (
        HostOperationSpec("execution.host.request_review", run, dict, dict, frozenset({cli, hook})),
        HostOperationSpec("execution.host.local_ask", _ask, AskRequest, LocalAnswer, local),
        HostOperationSpec("execution.host.local_do", _do, DoRequest, LocalAnswer, local),
        HostOperationSpec(
            "execution.host.local_deliberate", _deliberate, DeliberateRequest, DeliberateResult, local
        ),
    )


HOST_OPERATION_NAMES = (
    "execution.host.worker_loop",
    "execution.host.request_review",
    "execution.host.clean_environments",
    "execution.host.local_ask",
    "execution.host.local_do",
    "execution.host.local_deliberate",
)
