"""Ports of the bus pipeline, the event store and outbox delivery (kernel-platform §4.1, §4.3).

Core repository ports (``IdempotencyStore``, ``AuditLog``, ``EventReader``, ``OutboxStore``,
``ConsumerReceipts``) are reached through ``uow.repo(port)``; their memory and PostgreSQL adapters live in
``adapters/{memory,postgres}/core``. ``Authorizer`` is ``access.public.RbacAuthorizer``,
``ScopeChainResolver`` is ``workspace.public.ScopeChain``; bootstrap passes both to
the bus. ``ExternalConsumer`` is implemented by the owning module (``integrations``, prefix ``hook``).

``DoctorRunner`` is the control-plane gateway of ``platform.doctor`` (kernel-platform §5.2a, §5.6): it serves
the reports that bootstrap's ``DoctorCheckCollector`` recorded outside every unit of work and composes beneath
them the restart-pending observation of the process serving the request (``CurrentProcessObserver``), never of
other processes or hosts. Nothing behind this port executes a registered check.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal, Protocol
from uuid import UUID

from skm.application_bus.context import SubscriberContext
from skm.kernel.actor import Actor
from skm.kernel.cancel import CancelToken
from skm.kernel.events import EventEnvelope
from skm.kernel.gateways import control_plane_gateway
from skm.kernel.generated.documents import CheckResult
from skm.kernel.ids import EventId, PrincipalId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.kernel.outcomes import Severity
from skm.kernel.pagination import Page
from skm.kernel.ports_uow import UnitOfWork, repository_port
from skm.kernel.scopes import ScopeRecord, ScopeRef
from skm.platform.config.keys import Chain
from skm.platform.config.scopes import ScopeRef as ConfigScopeRef
from skm.platform.config.store import ConfigStore, ScopeTree

__all__ = [
    "AuditLog",
    "AuditRecord",
    "Authorizer",
    "AuthzDecision",
    "ConsumerReceipts",
    "CurrentProcessObservation",
    "CurrentProcessObserver",
    "DeliveryPlan",
    "DoctorRunner",
    "EventReader",
    "ExternalConsumer",
    "GiveUp",
    "IdempotencyReceipt",
    "IdempotencyStore",
    "OutboxEntry",
    "OutboxItem",
    "OutboxState",
    "OutboxStore",
    "PendingRestart",
    "ProcessObservationState",
    "RegisteredCheckReport",
    "RetryAt",
    "ScopeChainResolver",
    "SendResult",
    "Sent",
]


@dataclass(frozen=True, slots=True)
class AuthzDecision:
    allowed: bool
    # "NO_MEMBERSHIP" | "ROLE_LACKS_PERMISSION" | "TOKEN_NARROWED" | "TOKEN_SCOPE" | "PRINCIPAL_DISABLED"
    # | "KIND_NOT_ALLOWED"; reported as FORBIDDEN details.reason_code, not as an ErrorCode
    reason_code: str | None = None


class Authorizer(Protocol):
    def authorize(
        self,
        uow: UnitOfWork,
        actor: Actor,
        permission: str,
        chain: tuple[ScopeRecord, ...],
    ) -> AuthzDecision: ...


class ScopeChainResolver(Protocol):
    def chain(self, uow: UnitOfWork, scope: ScopeRef | None) -> tuple[ScopeRecord, ...]:
        """Scope records from instance to ``scope``; ``None`` is the instance scope. ``NotFound``."""
        ...


@dataclass(frozen=True, slots=True)
class IdempotencyReceipt:
    workspace_id: WorkspaceId | None
    principal_id: PrincipalId
    operation: str
    key: str
    request_digest: str  # application_bus.middleware.request_digest(spec, dto); the body is never stored
    result: JsonObject  # secret-free result
    created_at: datetime
    expires_at: datetime


@repository_port
class IdempotencyStore(Protocol):
    def get(
        self,
        workspace_id: WorkspaceId | None,
        principal_id: PrincipalId,
        operation: str,
        key: str,
    ) -> IdempotencyReceipt | None:
        """Never returns expired rows."""
        ...

    def put(self, receipt: IdempotencyReceipt) -> None:
        """Overwrites an expired row of the same key; a live row is ``Conflict`` (receipt race)."""
        ...

    def purge_expired(self, now: datetime, *, limit: int) -> int: ...


@dataclass(frozen=True, slots=True)
class AuditRecord:
    id: UUID
    workspace_id: WorkspaceId | None
    actor_id: PrincipalId
    action: str  # command or query name
    target: JsonObject
    decision: Literal["allowed", "denied"]
    reason_code: str | None
    request_id: str
    recorded_at: datetime


@repository_port
class AuditLog(Protocol):
    def append(self, record: AuditRecord) -> None: ...


@repository_port
class EventReader(Protocol):
    """Reads committed events for SSE, ``SkmClient.events`` and the outbox relay."""

    def after_global_position(self, after: int, *, limit: int) -> tuple[EventEnvelope, ...]:
        """Instance feed only."""
        ...

    def after_workspace_seq(
        self,
        workspace_id: WorkspaceId,
        after: int,
        *,
        types: frozenset[str] | None,
        limit: int,
    ) -> tuple[EventEnvelope, ...]: ...

    def by_ids(self, ids: Sequence[EventId]) -> tuple[EventEnvelope, ...]: ...

    def head_workspace_seq(self, workspace_id: WorkspaceId) -> int:
        """``max(workspace_seq)`` in the UoW snapshot; 0 when the workspace has no events."""
        ...


class OutboxState(StrEnum):
    """Values of ``ck_outbox__state`` in ``skm_core.outbox``; there is no delivering state."""

    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"
    DEAD = "dead"


@dataclass(frozen=True, slots=True)
class OutboxItem:
    id: UUID
    event_id: EventId
    destination: str  # consumer_id, "sse" or "<prefix>:<rest>"
    attempts: int
    delivery_generation: int
    claimed_at: datetime


@dataclass(frozen=True, slots=True)
class OutboxEntry:
    """One row as an operator sees it (``platform.list_dead_outbox``); ``last_error`` is already redacted."""

    id: UUID
    event_id: EventId
    destination: str
    state: OutboxState
    attempts: int
    last_error: str | None
    created_at: datetime
    available_at: datetime


@repository_port
class OutboxStore(Protocol):
    """Outbox rows of ``skm_core.outbox``; claims expire, ``mark_*`` succeed only for the current claimant.

    ``list_dead`` and ``list`` page by row id (``Page.next`` is the opaque cursor of the next page).
    """

    def due_destinations(
        self,
        *,
        consumer_ids: frozenset[str],
        prefixes: frozenset[str],
        include_sse: bool,
        now: datetime,
        after: str | None,
        limit: int,
    ) -> tuple[str, ...]: ...

    def claim(
        self,
        *,
        destination: str,
        relay_id: str,
        now: datetime,
        limit: int,
    ) -> tuple[OutboxItem, ...]: ...

    def mark_delivered(self, item_id: UUID, *, at: datetime, relay_id: str | None = None) -> bool:
        """With ``relay_id`` only while ``claimed_by = relay_id``; a stale claim returns ``False``.

        The PostgreSQL adapter sends ``NOTIFY skm_events`` for a delivered ``sse`` row in the same
        transaction, so listeners see it only after the commit.
        """
        ...

    def mark_failed(
        self,
        item_id: UUID,
        *,
        relay_id: str,
        error: str,
        next_at: datetime,
        dead: bool,
    ) -> bool:
        """Only while ``claimed_by = relay_id``; a stale claim returns ``False`` and changes nothing."""
        ...

    def claim_dead_notifications(
        self,
        *,
        prefixes: frozenset[str],
        relay_id: str,
        now: datetime,
        limit: int,
    ) -> tuple[OutboxItem, ...]: ...

    def mark_dead_notified(
        self,
        item_id: UUID,
        *,
        relay_id: str,
        generation: int,
        claimed_at: datetime,
        at: datetime,
    ) -> bool: ...

    def defer_dead_notification(
        self,
        item_id: UUID,
        *,
        relay_id: str,
        generation: int,
        claimed_at: datetime,
        next_at: datetime,
        error: str,
    ) -> bool: ...

    def retry_dead(
        self,
        *,
        outbox_id: UUID | None,
        event_id: EventId | None,
        destination: str | None,
        now: datetime,
    ) -> int:
        """Dead rows only: attempts and claims reset, ``delivery_generation`` + 1. A filter is required."""
        ...

    def list_dead(self, *, after: str | None, limit: int) -> Page[OutboxEntry]: ...

    def list(
        self,
        *,
        destination_prefix: str,
        state: OutboxState | None,
        workspace_id: WorkspaceId | None,
        after: str | None,
        limit: int,
    ) -> Page[OutboxEntry]:
        """Operator states: ``PENDING`` includes ``FAILED`` rows awaiting another delivery attempt."""
        ...

    def purge_delivered(self, *, before: datetime, limit: int) -> int: ...


@repository_port
class ConsumerReceipts(Protocol):
    def seen(self, consumer_id: str, event_id: EventId) -> bool: ...

    def add(self, consumer_id: str, event_id: EventId, at: datetime) -> None: ...

    def purge(self, *, before: datetime, limit: int) -> int: ...


@dataclass(frozen=True, slots=True)
class DeliveryPlan:
    """Result of ``ExternalConsumer.prepare``; secrets appear only as ``SecretRef``."""

    payload: object
    timeout_seconds: float | None = None  # None -> events.delivery.timeout_seconds
    max_attempts: int | None = None  # None -> spec.max_attempts, then events.delivery.max_attempts


@dataclass(frozen=True, slots=True)
class Sent:
    pass


@dataclass(frozen=True, slots=True)
class RetryAt:
    next_at: datetime
    error: str


@dataclass(frozen=True, slots=True)
class GiveUp:
    error: str


type SendResult = Sent | RetryAt | GiveUp


# "observed": the process captured its restart values and the current UoW was compared with them;
# any other state means the restart status of this process is unknown, never that nothing is pending.
type ProcessObservationState = Literal["observed", "snapshot_missing", "instance_mismatch", "uncommitted"]


@dataclass(frozen=True, slots=True)
class PendingRestart:
    """A restart key whose committed value differs from the value this process captured; no values."""

    key: str
    chain: Chain
    target: ConfigScopeRef  # the instance (work chain) or the captured host chain root (host or instance)
    severity: Severity = Severity.INFO  # the loader diagnostic's; settings §B.7: informational


@dataclass(frozen=True, slots=True)
class CurrentProcessObservation:
    """Restart-pending state of the current process only: its instance work chain and captured host chain.

    ``host_target is None`` means no host chain was captured, not that other hosts were checked.
    """

    state: ProcessObservationState
    instance_scope_id: UUID | None
    host_target: ConfigScopeRef | None
    process_generation: int | None
    pending: tuple[PendingRestart, ...] = ()


class CurrentProcessObserver(Protocol):
    """Process-observation seam composed beneath ``DoctorRunner``; not a gateway of its own."""

    def observe(self, store: ConfigStore, scopes: ScopeTree) -> CurrentProcessObservation:
        """Read through the ports of the caller's read-only UoW; never opens a UoW, starts or replaces the
        process snapshot. A process without a captured snapshot is ``snapshot_missing``."""
        ...


@dataclass(frozen=True, slots=True)
class RegisteredCheckReport:
    """The last collection of one registered check, bound to the id it was registered under (provenance).

    ``collected``: the check ran to completion and every finding was normalized and redacted; ``failed``: it
    raised or returned an unnormalizable finding, so it has no findings. The findings' own ids may differ from
    ``check_id``; a selector names ``check_id`` and selects all of them.
    """

    check_id: str
    state: Literal["collected", "failed"]
    findings: tuple[CheckResult, ...] = ()


@control_plane_gateway
class DoctorRunner(CurrentProcessObserver, Protocol):
    """``platform.doctor`` gateway: registered checks of the platform, the enabled modules and plugins.

    Bootstrap builds the ``DoctorContext`` and runs the checks host-side, outside every unit of work; this
    port only serves what that collection recorded. The handler never executes a check, directly or through
    this port.
    """

    def check_ids(self) -> frozenset[str]:
        """Ids of the registered checks; ``only`` may name each of them."""
        ...

    def reports(self, only: frozenset[str] | None) -> tuple[RegisteredCheckReport, ...]:
        """Recorded reports of every registered check (``None``) or of those named in ``only``.

        A registered check that was never collected has no report. Executes no check, opens no UoW.
        """
        ...


class ExternalConsumer(Protocol):
    def prepare(
        self,
        item: OutboxItem,
        envelope: EventEnvelope,
        ctx: SubscriberContext,
        uow: UnitOfWork,
    ) -> DeliveryPlan | None:
        """Read-only UoW; ``None`` means there is nothing to deliver."""
        ...

    def send(
        self,
        plan: DeliveryPlan,
        *,
        attempt: int,
        timeout_seconds: float,
        cancel: CancelToken,
    ) -> SendResult:
        """External call outside any transaction; an exception is retried with backoff."""
        ...
