"""Host operation declarations; surfaces are supplied by the module composition."""

from typing import Any

from skm.kernel.module_manifest import HostOperationSpec

from .request_review import run


def operations(cli: Any, hook: Any) -> tuple[HostOperationSpec, ...]:
    return (HostOperationSpec("execution.host.request_review", run, dict, dict, frozenset({cli, hook})),)


HOST_OPERATION_NAMES = (
    "execution.host.worker_loop",
    "execution.host.request_review",
    "execution.host.clean_environments",
)
