"""Janitor tasks that keep the outbox and the idempotency store bounded (kernel-platform §6).

``OutboxGc`` and ``IdempotencyGc`` are built by bootstrap and ticked by ``background/janitor.py``. Each run
purges in short writable units of work of at most ``batch_size`` rows until a batch is not full, so no long
transaction holds locks over the tables the relay and the bus write.
"""

from collections.abc import Callable
from datetime import timedelta
from typing import Final

from skm.application_bus.client import new_request_id
from skm.application_bus.ports import ConsumerReceipts, IdempotencyStore, OutboxStore
from skm.application_bus.subscribers import EventConfigLoader
from skm.kernel.clock import Clock
from skm.kernel.id_generator import IdGenerator
from skm.kernel.ports_uow import Isolation, RequestMeta, Surface, UnitOfWork, UnitOfWorkFactory
from skm.platform.config.store import ConfigStore, ScopeTree

__all__ = ["IdempotencyGc", "OutboxGc"]

_GC_BATCH: Final = 1000
_RETENTION_KEY: Final = "events.outbox.delivered_retention_hours"
_RETENTION_DEFAULT: Final = 168
_RETENTION_BOUNDS: Final = range(1, 8761)


def _drain(
    uow_factory: UnitOfWorkFactory,
    meta: Callable[[], RequestMeta],
    purge: Callable[[UnitOfWork], int],
    batch: int,
) -> int:
    """Short units of work until a batch is not full; rows a batch left locked wait for the next run."""
    total = 0
    while True:
        with uow_factory(meta(), isolation=Isolation.READ_COMMITTED) as uow:
            removed = purge(uow)
            uow.commit()
        total += removed
        if removed < batch:
            return total


class _Gc:
    """What the janitor's housekeeping tasks share: short writable units of work in batches."""

    def __init__(
        self, uow_factory: UnitOfWorkFactory, clock: Clock, ids: IdGenerator, batch_size: int
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        self._uow_factory = uow_factory
        self._clock = clock
        self._ids = ids
        self._batch = batch_size

    def _meta(self) -> RequestMeta:
        return RequestMeta(
            new_request_id(self._ids), Surface.BACKGROUND, None, self._clock.now(), client="janitor"
        )


class IdempotencyGc(_Gc):
    """Janitor task ``idempotency_gc``: ``IdempotencyStore.purge_expired`` at the clock's now, in batches.

    A receipt is purged once its ``expires_at`` has passed; live receipts stay and a second run finds nothing.
    """

    name = "idempotency_gc"

    def __init__(
        self, *, uow_factory: UnitOfWorkFactory, clock: Clock, ids: IdGenerator, batch_size: int = _GC_BATCH
    ) -> None:
        super().__init__(uow_factory, clock, ids, batch_size)

    def run(self) -> int:
        now = self._clock.now()
        return _drain(
            self._uow_factory,
            self._meta,
            lambda uow: uow.repo(IdempotencyStore).purge_expired(now, limit=self._batch),
            self._batch,
        )


class OutboxGc(_Gc):
    """Janitor task ``outbox_gc`` (kernel-platform §6): delivered rows, then the receipts nothing guards.

    ``before = now - events.outbox.delivered_retention_hours`` (instance, live, read on every run):
    ``purge_delivered``, then ``ConsumerReceipts.purge`` for receipts older than the cutoff whose pair has no
    ``pending|failed|dead`` row. Those rows are never touched, ``domain_events`` and audit neither.
    """

    name = "outbox_gc"

    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        config: EventConfigLoader,
        clock: Clock,
        ids: IdGenerator,
        batch_size: int = _GC_BATCH,
    ) -> None:
        super().__init__(uow_factory, clock, ids, batch_size)
        self._config = config

    def _retention(self) -> timedelta:
        with self._uow_factory(self._meta(), readonly=True) as uow:
            config = self._config.effective(uow.repo(ConfigStore), uow.repo(ScopeTree), None)
        hours = config.get(_RETENTION_KEY)
        if isinstance(hours, int) and not isinstance(hours, bool) and hours in _RETENTION_BOUNDS:
            return timedelta(hours=hours)
        return timedelta(hours=_RETENTION_DEFAULT)

    def run(self) -> int:
        before = self._clock.now() - self._retention()
        rows = _drain(
            self._uow_factory,
            self._meta,
            lambda uow: uow.repo(OutboxStore).purge_delivered(before=before, limit=self._batch),
            self._batch,
        )
        receipts = _drain(
            self._uow_factory,
            self._meta,
            lambda uow: uow.repo(ConsumerReceipts).purge(before=before, limit=self._batch),
            self._batch,
        )
        return rows + receipts
