"""``workspace.host.register_this_host`` (workspace §4.5, §9, §12, §18 K17): register local host."""

from __future__ import annotations

import platform as std_platform
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, cast

from skm.application_bus.host import HostContext
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, NotFound, PreconditionFailed, ValidationFailed
from skm.kernel.ids import HostId
from skm.kernel.module_manifest import HostOperationSpec
from skm.modules.access.public import WhoAmI, WhoAmIView
from skm.modules.workspace.domain.host import HostArch, HostOs, HostPlatform
from skm.modules.workspace.generated.commands import (
    HostArch as DtoHostArch,
)
from skm.modules.workspace.generated.commands import (
    HostOs as DtoHostOs,
)
from skm.modules.workspace.generated.commands import (
    RegisterHost,
    RegisterHostDefsHostPlatform,
)
from skm.modules.workspace.generated.queries import GetHost
from skm.modules.workspace.generated.results import RegisterHostResult
from skm.modules.workspace.generated.views import HostView

if TYPE_CHECKING:
    from skm.kernel.json_types import JsonObject

__all__ = [
    "SPEC",
    "RegisterThisHostOperation",
    "RegisterThisHostReport",
    "RegisterThisHostRequest",
    "detect_host_platform",
    "register_this_host",
    "run",
]


@dataclass(frozen=True, slots=True)
class RegisterThisHostRequest:
    """Parameters for ``workspace.host.register_this_host``."""

    name: str | None = None
    os: str | None = None
    arch: str | None = None
    is_worker: bool = False
    host_id_setting: str | None = None
    persist_host_id: Callable[[HostId], None] | None = None
    recorded_host_id: HostId | None = None
    replace: bool = False
    default_name: str | None = None


@dataclass(frozen=True, slots=True)
class RegisterThisHostReport:
    """Outcome of ``workspace.host.register_this_host``."""

    host_id: HostId
    name: str
    platform: HostPlatform
    persisted: bool = False

    def to_json(self) -> JsonObject:
        return {
            "host_id": str(self.host_id),
            "name": self.name,
            "platform": {
                "os": self.platform.os.value,
                "arch": self.platform.arch.value,
            },
            "persisted": self.persisted,
        }


class RegisterThisHostOperation(Protocol):
    def __call__(
        self, ctx: HostContext, request: RegisterThisHostRequest | Mapping[str, Any] | None = None
    ) -> RegisterThisHostReport: ...


def detect_host_platform(os_override: str | None = None, arch_override: str | None = None) -> HostPlatform:
    """Detect or normalize ``(os, arch)`` for the current machine."""
    if os_override is not None:
        raw_os = os_override.strip().lower()
    else:
        sys_name = std_platform.system().lower()
        if sys_name == "darwin":
            raw_os = "macos"
        elif sys_name in {"linux", "windows"}:
            raw_os = sys_name
        else:
            raw_os = "linux"
    if raw_os not in {member.value for member in HostOs}:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            f"Unsupported host OS {raw_os!r}",
            details={"field": "os", "value": raw_os},
        )

    if arch_override is not None:
        raw_arch = arch_override.strip().lower()
    else:
        machine = std_platform.machine().lower()
        if machine in {"x86_64", "amd64"}:
            raw_arch = "x86_64"
        elif machine in {"aarch64", "arm64"}:
            raw_arch = "arm64"
        else:
            raw_arch = "other"
    if raw_arch not in {member.value for member in HostArch}:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            f"Unsupported host architecture {raw_arch!r}",
            details={"field": "arch", "value": raw_arch},
        )
    return HostPlatform(os=HostOs(raw_os), arch=HostArch(raw_arch))


def _coerce_request(
    request: RegisterThisHostRequest | Mapping[str, Any] | None,
) -> RegisterThisHostRequest:
    if request is None:
        return RegisterThisHostRequest()
    if isinstance(request, RegisterThisHostRequest):
        return request
    return RegisterThisHostRequest(
        name=None if request.get("name") is None else str(request["name"]),
        os=None if request.get("os") is None else str(request["os"]),
        arch=None if request.get("arch") is None else str(request["arch"]),
        is_worker=bool(request.get("is_worker", False)),
        host_id_setting=None if request.get("host_id_setting") is None else str(request["host_id_setting"]),
        persist_host_id=cast("Callable[[HostId], None] | None", request.get("persist_host_id")),
        recorded_host_id=cast("HostId | None", request.get("recorded_host_id")),
        replace=bool(request.get("replace", False)),
        default_name=cast("str | None", request.get("default_name")),
    )


def register_this_host(
    ctx: HostContext, request: RegisterThisHostRequest | Mapping[str, Any] | None = None
) -> RegisterThisHostReport:
    """Register the current machine via ``workspace.register_host`` and optionally persist ``host.id``."""
    req = _coerce_request(request)

    whoami = None
    caller_is_worker = req.is_worker
    if not caller_is_worker:
        # A failing WhoAmI (expired token, unreachable server) is the real cause of the failure; registering
        # anyway would only bury it under whatever RegisterHost then reports.
        whoami = ctx.client.ask(WhoAmI())
        caller_is_worker = isinstance(whoami, WhoAmIView) and whoami.principal.kind == "worker"

    if caller_is_worker:
        if req.host_id_setting == "auto":
            raise PreconditionFailed(
                ErrorCode.INVALID_TRANSITION,
                "Host is not registered; run skm host register",
                details={"reason": "host_not_registered", "hint": "skm host register"},
            )
        raise Forbidden(
            ErrorCode.FORBIDDEN,
            "Workers cannot register hosts",
            details={"reason": "worker_cannot_register_host"},
        )

    if req.recorded_host_id is not None:
        if not isinstance(whoami, WhoAmIView) or "host.manage" not in whoami.effective_permissions:
            raise Forbidden(ErrorCode.FORBIDDEN, "Host registration requires host.manage")
        try:
            recorded = cast("HostView", ctx.client.ask(GetHost(host_id=req.recorded_host_id)))
        except NotFound:
            pass
        else:
            if not req.replace:
                raise PreconditionFailed(
                    ErrorCode.INVALID_TRANSITION,
                    f"This machine is already registered as host {recorded.name!r} (use --replace)",
                    details={
                        "reason": "host_already_registered",
                        "host_id": str(recorded.host_id),
                        "name": recorded.name,
                        "hint": "skm host register --replace NAME",
                    },
                )
            if not req.name or req.name == recorded.name:
                current = detect_host_platform(recorded.platform.os.value, recorded.platform.arch.value)
                if (
                    detect_host_platform(req.os or current.os.value, req.arch or current.arch.value)
                    != current
                ):
                    raise PreconditionFailed(
                        ErrorCode.INVALID_TRANSITION,
                        "Recorded host platform differs",
                        details={"reason": "host_platform_mismatch"},
                    )
                return RegisterThisHostReport(HostId(recorded.host_id), recorded.name, current, True)

    host_name = (req.name or req.default_name or std_platform.node() or "localhost").strip()
    host_platform = detect_host_platform(req.os, req.arch)

    result = cast(
        "RegisterHostResult",
        ctx.client.dispatch(
            RegisterHost(
                name=host_name,
                platform=RegisterHostDefsHostPlatform(
                    os=DtoHostOs(host_platform.os.value),
                    arch=DtoHostArch(host_platform.arch.value),
                ),
            ),
            idempotency_key=ctx.client.new_idempotency_key(),
        ),
    )
    host_id = HostId(result.host_id)
    persisted = False
    if req.persist_host_id is not None:
        req.persist_host_id(host_id)
        persisted = True

    return RegisterThisHostReport(
        host_id=host_id,
        name=result.name,
        platform=host_platform,
        persisted=persisted,
    )


def run(
    ctx: HostContext, request: RegisterThisHostRequest | Mapping[str, Any] | None = None
) -> RegisterThisHostReport:
    return register_this_host(ctx, request)


SPEC = HostOperationSpec(
    name="workspace.host.register_this_host",
    run=run,
    request=cast("type[object]", RegisterThisHostRequest),
    result=RegisterThisHostReport,
    surfaces=cast("frozenset[Any]", frozenset({"cli"})),
)
