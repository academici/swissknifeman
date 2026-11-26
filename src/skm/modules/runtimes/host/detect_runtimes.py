"""Host operation ``runtimes.host.detect_runtimes`` (runtimes §4.4, §7.1, §14).

Runs on the local host (CLI or worker), probes every registered runtime in ``RuntimeRegistry`` in
deterministic order without touching the database directly, isolates per-adapter probe errors so one failing
adapter never aborts the rest, omits uninstalled runtimes, and records the observed state via
``ctx.client.dispatch``.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final, Protocol, cast

from skm.application_bus.host import HostContext
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.modules.runtimes.domain.capability import Capability
from skm.modules.runtimes.domain.catalog_records import WORKER_OFFER_TTL
from skm.modules.runtimes.domain.classes import Effort
from skm.modules.runtimes.domain.detection import DetectProbe
from skm.modules.runtimes.domain.installation import (
    AuthState,
    RuntimeInstallation,
    public_installation_details,
    public_runtime_version,
)
from skm.modules.runtimes.generated.commands import (
    RecordHostRuntimes,
    RecordHostRuntimesInstallationsItem,
    RecordHostRuntimesModelOffersItem,
)
from skm.modules.runtimes.generated.host import (
    DetectRuntimesReport,
    DetectRuntimesReportRuntimesItem,
    DetectRuntimesRequest,
)
from skm.modules.runtimes.generated.queries import ListModels
from skm.modules.runtimes.generated.results import RecordHostRuntimesResult
from skm.modules.runtimes.generated.views import ModelsView
from skm.modules.runtimes.ports import RuntimeRegistry, WorkerModelOfferPolicy

if TYPE_CHECKING:
    from skm.kernel.json_types import JsonObject

__all__ = ["DetectRuntimesOperation", "detect_runtimes"]

_DEFAULT_TIMEOUT_SECONDS: Final = 10
_MAX_ERROR_CHARS: Final = 300
_SENTINEL_DETECTED_AT: Final = datetime(1970, 1, 1, tzinfo=UTC)
_CONTROL_RE: Final = re.compile(r"[\x00-\x1f\x7f]+")


def _unchanged(value: str) -> str:
    return value


class DetectRuntimesOperation(Protocol):
    def __call__(
        self, ctx: HostContext, request: DetectRuntimesRequest | JsonObject
    ) -> DetectRuntimesReport: ...


def _config_mapping(config: object, key: str) -> dict[str, object]:
    getter = getattr(config, "get", None)
    value: object = None
    if callable(getter):
        value = getter(key)
    elif isinstance(config, Mapping):
        value = cast("Mapping[str, object]", config).get(key)
    if isinstance(value, Mapping):
        raw_map = cast("Mapping[object, object]", value)
        return {str(k): v for k, v in raw_map.items()}
    return {}


def _extra_env_for_runtime(config: object, runtime_id: str) -> tuple[str, ...]:
    getter = getattr(config, "get", None)
    value: object = None
    if callable(getter):
        value = getter("runtimes.extra_env_allow")
    elif isinstance(config, Mapping):
        value = cast("Mapping[str, object]", config).get("runtimes.extra_env_allow")
    if isinstance(value, Mapping):
        per_runtime = cast("Mapping[object, object]", value).get(runtime_id)
        if isinstance(per_runtime, list | tuple):
            seq = cast("Sequence[object]", per_runtime)
            return tuple(item for item in seq if isinstance(item, str))
        return ()
    if isinstance(value, list | tuple):
        seq = cast("Sequence[object]", value)
        return tuple(item for item in seq if isinstance(item, str))
    return ()


def _safe_error_text(exc: BaseException) -> str:
    text = _CONTROL_RE.sub(" ", str(exc)).strip()
    if not text:
        text = type(exc).__name__
    return text[:_MAX_ERROR_CHARS]


def _is_not_installed(inst: RuntimeInstallation) -> bool:
    if inst.details.get("installed") == "false":
        return True
    return (
        inst.version is None
        and inst.binary_locator is None
        and inst.auth_state is AuthState.MISSING
        and not inst.details
    )


def _worker_publication(
    ctx: HostContext,
    policy: WorkerModelOfferPolicy,
    items: list[RecordHostRuntimesInstallationsItem],
    available: set[str],
) -> RecordHostRuntimes:
    offers: list[RecordHostRuntimesModelOffersItem] = []
    observed = policy.now()
    if available:
        view = cast("ModelsView", ctx.client.ask(ListModels(host_id=ctx.host_id)))
        for model in view.models:
            runtime_id, model_id = model.get("runtime_id"), model.get("id")
            if not isinstance(runtime_id, str) or not isinstance(model_id, str):
                continue
            if runtime_id not in available or model.get("status") == "deprecated":
                continue
            efforts = model.get("efforts")
            if not isinstance(efforts, list):
                continue
            offers.extend(
                RecordHostRuntimesModelOffersItem(
                    runtime_id, model_id, effort.value, observed, observed + WORKER_OFFER_TTL
                )
                for effort in Effort
                if effort in efforts and policy.allows_model(runtime_id, model_id, effort)
            )
    return RecordHostRuntimes(
        host_id=ctx.host_id,
        installations=tuple(items),
        model_offers_observed_at=observed,
        model_offers=tuple(offers),
        refresh_model_offers=True,
    )


def detect_runtimes(
    ctx: HostContext,
    request: DetectRuntimesRequest | JsonObject | None = None,
    *,
    publish_local_details: bool = True,
    redact: Callable[[str], str] = _unchanged,
) -> DetectRuntimesReport:
    """Probe registered runtimes on ``ctx.host_id`` and record the result via ``RecordHostRuntimes``."""
    if request is not None and not isinstance(request, DetectRuntimesRequest):
        DetectRuntimesRequest.from_json(request)

    registry = ctx.gateways.get(RuntimeRegistry)
    binaries = _config_mapping(ctx.config, "runtimes.binaries")

    policy = ctx.gateways.get(WorkerModelOfferPolicy) if ctx.gateways.has(WorkerModelOfferPolicy) else None
    items: list[RecordHostRuntimesInstallationsItem] = []
    available: set[str] = set()
    for runtime_id in sorted(registry.ids()):
        raw_binary = binaries.get(runtime_id)
        binary = raw_binary if isinstance(raw_binary, str) and raw_binary else None
        probe = DetectProbe(
            host_id=ctx.host_id,
            binary=binary,
            env_allowlist=_extra_env_for_runtime(ctx.config, runtime_id),
            timeout_seconds=_DEFAULT_TIMEOUT_SECONDS,
        )
        runtime = None
        observed_installation = None
        try:
            runtime = registry.get(runtime_id)
            installation = runtime.detect(probe)
            if (
                policy is not None
                and installation.version
                and policy.account_available(installation)
                and all(
                    runtime.capabilities().supports(capability)
                    for capability in (Capability.HEADLESS_EXECUTION, Capability.EFFORT_CONTROL)
                )
            ):
                available.add(runtime_id)
            observed_installation = None if _is_not_installed(installation) else installation
        except FileNotFoundError:
            continue
        except SkmError as exc:
            if exc.code in (ErrorCode.RUNTIME_NOT_INSTALLED, ErrorCode.NOT_FOUND):
                continue
            items.append(
                RecordHostRuntimesInstallationsItem(
                    runtime_id=runtime_id,
                    version=None,
                    binary_locator=binary if publish_local_details else None,
                    auth_state="unknown",
                    detected_at=_SENTINEL_DETECTED_AT,
                    details={"error": _safe_error_text(exc)} if publish_local_details else {},
                )
            )
            continue
        except Exception as exc:  # noqa: BLE001 - isolate broken adapter so other runtimes still detect
            items.append(
                RecordHostRuntimesInstallationsItem(
                    runtime_id=runtime_id,
                    version=None,
                    binary_locator=binary if publish_local_details else None,
                    auth_state="unknown",
                    detected_at=_SENTINEL_DETECTED_AT,
                    details={"error": _safe_error_text(exc)} if publish_local_details else {},
                )
            )
            continue

        finally:
            if policy is not None and runtime is not None:
                policy.observe_installation(runtime, observed_installation)

        if observed_installation is None:
            continue

        version = (
            installation.version
            if publish_local_details
            else public_runtime_version(installation.version, redact)
        )
        if version is None:
            available.discard(runtime_id)
        items.append(
            RecordHostRuntimesInstallationsItem(
                runtime_id=runtime_id,
                version=version,
                binary_locator=installation.binary_locator if publish_local_details else None,
                auth_state=("ok" if runtime_id in available and version else installation.auth_state.value),
                detected_at=installation.detected_at,
                details=dict(installation.details)
                if publish_local_details
                else public_installation_details(installation.details, redact),
            )
        )

    cmd = (
        RecordHostRuntimes(host_id=ctx.host_id, installations=tuple(items))
        if policy is None
        else _worker_publication(ctx, policy, items, available)
    )
    dispatched = ctx.client.dispatch(cmd, idempotency_key=ctx.client.new_idempotency_key())
    if isinstance(dispatched, RecordHostRuntimesResult):
        recorded = dispatched
    elif isinstance(dispatched, Mapping):
        recorded = RecordHostRuntimesResult.from_json(cast("Mapping[str, object]", dispatched))
    else:
        raise TypeError(f"unexpected RecordHostRuntimes dispatch result: {type(dispatched).__name__}")

    return DetectRuntimesReport(
        host_id=recorded.host_id,
        runtimes=tuple(
            DetectRuntimesReportRuntimesItem(
                runtime_id=item.runtime_id,
                version=item.version,
                auth_state=item.auth_state,
                changed=item.changed,
            )
            for item in recorded.runtimes
        ),
        removed=recorded.removed,
    )
