"""Repository ports of the settings module (settings §A.6, storage §A.11).

Every implementation runs on the connection of the current unit of work. Version checks are kept in the
repository too, not only in the domain rule R11: ``save`` and ``remove`` are conditional on the version the
command read (``WHERE id = … AND row_version = …``), so a concurrent writer that slipped in between makes
the conditional update touch zero rows and the call raise ``Conflict(VERSION_CONFLICT, {expected, actual})``
(``entry.version_conflict``; ``actual = 0`` when the entry is gone). ``expected_version`` is always the
version of the entry as read, not of an intermediate step: a value change together with a lock change
(``change_entry`` then ``set_lock``, §A.7.1) saves ``expected_version + 2`` in one conditional update.

Inside settings application code, resolve ``repo = uow.repo(ConfigEntryRepository)`` on the caller's UoW,
then use ``repo.find(scope_id, key)``. Bootstrap supplies the memory or PostgreSQL implementation;
handlers do not instantiate adapters or commit independently. Other modules read ``ctx.config``.
"""

from collections.abc import Mapping, Sequence
from typing import Protocol
from uuid import UUID

from skm.kernel.pagination import Page
from skm.kernel.ports_uow import repository_port
from skm.kernel.scopes import ScopeKind

from .domain.entry import ConfigEntry, ConfigEntryId
from .domain.history import HistoryRecord

__all__ = ["ConfigEntryRepository", "ConfigGenerationCounter", "ConfigHistoryRepository"]


@repository_port
class ConfigEntryRepository(Protocol):
    def get(self, entry_id: ConfigEntryId) -> ConfigEntry: ...  # NotFound
    def find(self, scope_id: UUID, key: str, *, for_update: bool = False) -> ConfigEntry | None: ...
    def entries_of_scope(self, scope_id: UUID, *, for_update: bool = False) -> Mapping[str, ConfigEntry]: ...
    def entries_for(self, scope_ids: Sequence[UUID]) -> Mapping[UUID, Mapping[str, ConfigEntry]]: ...
    def add(self, entry: ConfigEntry) -> None: ...  # Conflict(ALREADY_EXISTS) на (scope_id, key)
    def save(self, entry: ConfigEntry, *, expected_version: int) -> None:
        """Conditional update (CAS): ``Conflict(VERSION_CONFLICT)`` unless the stored version is
        ``expected_version``; then stores ``entry`` with its own ``row_version``, the result of one or more
        domain operations on the read entry (``ValueError`` unless it is above ``expected_version``)."""
        ...

    def remove(self, entry_id: ConfigEntryId, *, expected_version: int) -> None:
        """Conditional delete (CAS): ``Conflict(VERSION_CONFLICT)`` unless the stored version matches."""
        ...

    def list(
        self,
        *,
        scope_id: UUID | None,
        level: ScopeKind | None,
        key_prefix: str | None,
        after: str | None,
        limit: int,
        exclude_keys: frozenset[str] = frozenset(),
    ) -> Page[ConfigEntry]: ...  # keyset по (key, scope_id)
    def count_shadowed_below(self, scope_id: UUID, key: str) -> int: ...  # записи ключа в потомках scope


@repository_port
class ConfigHistoryRepository(Protocol):
    def append(self, record: HistoryRecord) -> None: ...
    def list(
        self,
        *,
        scope_id: UUID | None,
        key: str | None,
        after: str | None,
        limit: int,
        exclude_keys: frozenset[str] = frozenset(),
    ) -> Page[HistoryRecord]: ...

    #   порядок: changed_at DESC, id DESC; курсор — base64(changed_at|id)


@repository_port
class ConfigGenerationCounter(Protocol):
    def current(self) -> int: ...
    def increment(self) -> int: ...  # новое значение; блокирует строку до конца транзакции
