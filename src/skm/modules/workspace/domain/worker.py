"""Worker identity and capabilities (workspace §4.2, §4.3, §5.3).

A worker is the identity of an execution process in one workspace on one host. Capabilities are what it
declares it can run; ``draining`` stops new assignments without touching the running ones."""

import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed, ValidationFailed
from skm.kernel.ids import HostId, PrincipalId, WorkerId, WorkspaceId
from skm.kernel.isolation import IsolationProfile, parse_isolation_profile

from .host import HostPlatform
from .workspace import valid_title

__all__ = [
    "DISPLAY_NAME_MAX",
    "WORKER_TRANSITIONS",
    "Worker",
    "WorkerCapabilities",
    "WorkerState",
    "ensure_transition",
    "ensure_unconfined_allowed",
    "heartbeat",
    "is_overdue",
    "mark_offline",
    "new_worker",
    "set_state",
]

DISPLAY_NAME_MAX: Final = 100
_RUNTIME: Final = re.compile(r"[a-z][a-z0-9_]{1,31}")
_LABEL: Final = re.compile(r"[a-z0-9][a-z0-9:._-]{0,63}")
_SEMVER: Final = re.compile(r"\d+\.\d+\.\d+(?:[-+.][0-9A-Za-z.-]+)?", re.ASCII)
_RUNTIMES_MAX: Final = 32
_LABELS_MAX: Final = 32
_CONCURRENCY: Final = range(1, 65)


class WorkerState(StrEnum):
    ONLINE = "online"
    DRAINING = "draining"
    OFFLINE = "offline"
    RETIRED = "retired"


WORKER_TRANSITIONS: Final[Mapping[WorkerState, frozenset[WorkerState]]] = MappingProxyType(
    {
        WorkerState.ONLINE: frozenset({WorkerState.DRAINING, WorkerState.OFFLINE, WorkerState.RETIRED}),
        WorkerState.DRAINING: frozenset({WorkerState.ONLINE, WorkerState.OFFLINE, WorkerState.RETIRED}),
        WorkerState.OFFLINE: frozenset({WorkerState.ONLINE, WorkerState.DRAINING, WorkerState.RETIRED}),
        WorkerState.RETIRED: frozenset[WorkerState](),
    }
)


def _invalid(field: str, reason: str) -> ValidationFailed:
    return ValidationFailed(
        ErrorCode.SCHEMA_INVALID,
        f"invalid worker capabilities: {field}",
        details={"field": f"capabilities.{field}", "reason": reason},
    )


@dataclass(frozen=True, slots=True)
class WorkerCapabilities:
    """Document ``urn:skm:workspace:worker-capabilities:v1``."""

    runtimes: tuple[str, ...]
    isolation_profiles: tuple[str, ...]  # IsolationProfile values, plus plugin_id:name (D-REG-6)
    max_concurrency: int
    labels: tuple[str, ...]
    platform: HostPlatform
    skm_version: str

    def __post_init__(self) -> None:
        if len(self.runtimes) > _RUNTIMES_MAX or len(set(self.runtimes)) != len(self.runtimes):
            raise _invalid("runtimes", "count_or_duplicate")
        if not all(_RUNTIME.fullmatch(item) for item in self.runtimes):
            raise _invalid("runtimes", "pattern")
        if not self.isolation_profiles or len(set(self.isolation_profiles)) != len(self.isolation_profiles):
            raise _invalid("isolation_profiles", "empty_or_duplicate")
        for profile in self.isolation_profiles:
            try:
                parse_isolation_profile(profile)
            except ValueError:
                raise _invalid("isolation_profiles", "unknown_profile") from None
        if type(self.max_concurrency) is not int or self.max_concurrency not in _CONCURRENCY:
            raise _invalid("max_concurrency", "range")
        if len(self.labels) > _LABELS_MAX or len(set(self.labels)) != len(self.labels):
            raise _invalid("labels", "count_or_duplicate")
        if not all(_LABEL.fullmatch(item) for item in self.labels):
            raise _invalid("labels", "pattern")
        if not _SEMVER.fullmatch(self.skm_version):
            raise _invalid("skm_version", "pattern")


def ensure_unconfined_allowed(capabilities: WorkerCapabilities, *, allow_unconfined: bool) -> None:
    """``none`` may be declared only on a host that sets ``policy.host.allow_unconfined``."""
    if not allow_unconfined and IsolationProfile.NONE.value in capabilities.isolation_profiles:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "the host does not allow unconfined workers",
            details={"field": "capabilities.isolation_profiles", "reason": "unconfined_not_allowed"},
        )


@dataclass(frozen=True, slots=True)
class Worker:
    id: WorkerId
    workspace_id: WorkspaceId
    host_id: HostId
    principal_id: PrincipalId
    display_name: str
    capabilities: WorkerCapabilities
    state: WorkerState
    last_heartbeat_at: datetime | None
    registered_at: datetime
    row_version: int


def new_worker(
    *,
    worker_id: WorkerId,
    workspace_id: WorkspaceId,
    host_id: HostId,
    principal_id: PrincipalId,
    display_name: str,
    capabilities: WorkerCapabilities,
    now: datetime,
) -> Worker:
    """A registered worker starts ``offline`` until its first heartbeat."""
    name = valid_title(display_name, field="display_name")
    if len(name) > DISPLAY_NAME_MAX:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            f"display_name must be 1..{DISPLAY_NAME_MAX} characters",
            details={"field": "display_name"},
        )
    return Worker(
        id=worker_id,
        workspace_id=workspace_id,
        host_id=host_id,
        principal_id=principal_id,
        display_name=name,
        capabilities=capabilities,
        state=WorkerState.OFFLINE,
        last_heartbeat_at=None,
        registered_at=now,
        row_version=1,
    )


def ensure_transition(source: WorkerState, target: WorkerState) -> None:
    if target not in WORKER_TRANSITIONS[source]:
        raise PreconditionFailed(
            ErrorCode.INVALID_TRANSITION,
            f"worker cannot go from {source.value} to {target.value}",
            details={"from": source.value, "to": target.value},
        )


def set_state(worker: Worker, target: WorkerState) -> Worker:
    """Operator transition per ``WORKER_TRANSITIONS``; the same state again is a no-op (no event)."""
    if worker.state is target:
        return worker
    ensure_transition(worker.state, target)
    return replace(worker, state=target, row_version=worker.row_version + 1)


def mark_offline(worker: Worker) -> Worker:
    """The sweeper's transition: ``online|draining -> offline``; offline and retired stay as they are."""
    if worker.state in (WorkerState.OFFLINE, WorkerState.RETIRED):
        return worker
    return set_state(worker, WorkerState.OFFLINE)


def heartbeat(worker: Worker, capabilities: WorkerCapabilities | None, now: datetime) -> Worker:
    """Record liveness: ``offline -> online``; other live states stay; a retired worker never returns."""
    if worker.state is WorkerState.RETIRED:
        raise PreconditionFailed(
            ErrorCode.INVALID_TRANSITION,
            "a retired worker cannot send heartbeats",
            details={"from": worker.state.value, "to": WorkerState.ONLINE.value},
        )
    state = WorkerState.ONLINE if worker.state is WorkerState.OFFLINE else worker.state
    return replace(
        worker,
        state=state,
        capabilities=worker.capabilities if capabilities is None else capabilities,
        last_heartbeat_at=now,
        row_version=worker.row_version + 1,
    )


def is_overdue(worker: Worker, now: datetime, offline_after: timedelta) -> bool:
    """True for a live worker (online or draining) whose last heartbeat — or registration — is too old."""
    if worker.state not in (WorkerState.ONLINE, WorkerState.DRAINING):
        return False
    return now - (worker.last_heartbeat_at or worker.registered_at) > offline_after
