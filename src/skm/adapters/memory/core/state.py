"""State of the memory backend (adapters §2.2).

``MemoryBackendState`` is the committed state; every unit of work works on a deep copy of it and the copy
replaces the committed state only on commit. ``MemoryCoreState`` holds the tables of ``skm_core``.
"""

from copy import copy, deepcopy
from dataclasses import Field, dataclass, field, fields
from datetime import datetime
from typing import Any, ClassVar, Final, Protocol, Self, cast
from uuid import UUID

from skm.application_bus.ports import AuditRecord, IdempotencyReceipt, OutboxState
from skm.kernel.clock import Clock
from skm.kernel.events import EventEnvelope
from skm.kernel.ids import EventId, PrincipalId, ScopeId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.kernel.scopes import ScopeRecord

__all__ = [
    "NIL_UUID",
    "ClockRef",
    "MemoryBackendState",
    "MemoryCoreState",
    "OutboxRecord",
    "copy_tables",
]

NIL_UUID: Final = UUID(int=0)  # feed key of the instance feed and key part of an instance-level receipt

# Tables whose rows are immutable values: frozen records (``EventEnvelope``, ``AuditRecord``,
# ``IdempotencyReceipt``, ``ScopeRecord``) or scalars and tuples. Their writers store an independent copy of
# every JSON payload and their readers hand out copies, so a working copy may share the rows and only needs
# its own container.
_SHARED_ROW_TABLES: Final = frozenset(
    {"scopes", "stream_seq", "feed_seq", "events", "outbox_keys", "consumer_receipts", "idempotency", "audit"}
)


class _TableState(Protocol):
    """A dataclass of memory tables (what ``dataclasses.fields`` accepts)."""

    __dataclass_fields__: ClassVar[dict[str, Field[Any]]]


def copy_tables[S: _TableState](
    state: S,
    memo: dict[int, object],
    *,
    shared_rows: frozenset[str],
    copied_rows: frozenset[str] = frozenset(),
) -> S:
    """A working copy of the table dataclass ``state``, as independent as ``deepcopy`` but cheaper.

    ``shared_rows`` name tables whose rows are immutable values (frozen records whose JSON is stored as an
    independent copy and handed out as copies, scalars, tuples): only their container is copied.
    ``copied_rows`` name dict tables of mutable rows with scalar fields: every row is shallow-copied. Any
    other field, including one added later, is deep-copied. Deep-copying immutable rows on every unit of
    work made each command cost time linear in everything the backend ever stored.
    """
    values: dict[str, Any] = {}
    for item in fields(state):
        value: Any = getattr(state, item.name)
        if item.name in shared_rows:
            values[item.name] = copy(value)
        elif item.name in copied_rows:
            values[item.name] = {key: copy(row) for key, row in cast("dict[object, object]", value).items()}
        else:
            values[item.name] = deepcopy(value, memo)
    clone = type(state)(**values)
    memo[id(state)] = clone
    return clone


class ClockRef:
    """The backend clock inside the state; a copy of the state shares it instead of duplicating it."""

    __slots__ = ("clock",)

    def __init__(self, clock: Clock | None = None) -> None:
        self.clock = clock

    def now(self) -> datetime:
        if self.clock is None:
            raise RuntimeError("the memory backend has no clock")
        return self.clock.now()

    def __deepcopy__(self, memo: dict[int, object]) -> Self:
        return self

    def __copy__(self) -> Self:
        return self


@dataclass(slots=True)
class OutboxRecord:
    """A row of ``skm_core.outbox``."""

    id: UUID
    event_id: EventId
    destination: str
    workspace_id: WorkspaceId | None
    created_at: datetime
    available_at: datetime
    state: OutboxState = OutboxState.PENDING
    attempts: int = 0
    delivery_generation: int = 0
    claimed_by: str | None = None
    claimed_at: datetime | None = None
    last_error: str | None = None
    delivered_at: datetime | None = None
    dead_notified_at: datetime | None = None


@dataclass
class MemoryCoreState:
    scopes: dict[ScopeId, ScopeRecord] = field(default_factory=dict[ScopeId, ScopeRecord])
    stream_seq: dict[tuple[str, UUID], int] = field(default_factory=dict[tuple[str, UUID], int])
    feed_seq: dict[UUID, int] = field(default_factory=dict[UUID, int])  # nil UUID = the instance feed
    events: list[EventEnvelope] = field(default_factory=list[EventEnvelope])
    outbox: dict[UUID, OutboxRecord] = field(default_factory=dict[UUID, OutboxRecord])
    outbox_keys: set[tuple[EventId, str]] = field(default_factory=set[tuple[EventId, str]])
    # ``(consumer_id, event_id)`` -> when the receipt was added (``purge(before=…)`` needs the time)
    consumer_receipts: dict[tuple[str, EventId], datetime] = field(
        default_factory=dict[tuple[str, EventId], datetime]
    )
    idempotency: dict[tuple[UUID, PrincipalId, str, str], IdempotencyReceipt] = field(
        default_factory=dict[tuple[UUID, PrincipalId, str, str], IdempotencyReceipt]
    )
    audit: list[AuditRecord] = field(default_factory=list[AuditRecord])
    # Level entries by scope id and the generation counter; written by the settings module,
    # read by ConfigStore.
    config_entries: dict[UUID, dict[str, JsonObject]] = field(
        default_factory=dict[UUID, dict[str, JsonObject]]
    )
    config_generation: int = 0
    clock: ClockRef = field(default_factory=ClockRef)
    # Set on the working copy of a readonly unit of work: repositories refuse to write.
    readonly: bool = False

    def require_writable(self) -> None:
        if self.readonly:
            raise RuntimeError("write in a readonly unit of work")

    def __deepcopy__(self, memo: dict[int, object]) -> Self:
        # outbox rows are mutable (claims, retries) but hold only scalars
        return copy_tables(self, memo, shared_rows=_SHARED_ROW_TABLES, copied_rows=frozenset({"outbox"}))


@dataclass
class MemoryBackendState:
    core: MemoryCoreState = field(default_factory=MemoryCoreState)
    # module id -> state dataclass from ``adapters/memory/<module>/__init__.STATE_FACTORY``
    modules: dict[str, object] = field(default_factory=dict[str, object])
