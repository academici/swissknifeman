"""``ConfigStore`` over the memory config tables (settings §B.10, §A.11).

The tables live in ``MemoryCoreState``: ``config_entries[scope_id][key]`` is one row of ``skm_config.entries``
as JSON (``id``, ``key``, ``op``, ``value``, ``locked``, ``row_version``; ``id`` is the UUID string) and
``config_generation`` is the counter row. ``write_config_entry``, ``delete_config_entry`` and
``increment_config_generation`` are the only writers; the memory settings repositories use them, so the row
shape is defined here once.

``pending_writes`` is ``True`` when the unit of work changed the config tables and has not committed: either a
writer of this module marked its working copy, or the tables differ from what they were when the store was
created (the bus creates it in ``load_config``, before the handler). A read-only working copy never has
pending writes. The mark lives outside the state, so a committed copy does not carry it into the next unit
of work.
"""

import weakref
from collections.abc import Mapping, Sequence
from copy import deepcopy
from threading import Lock
from typing import Final, cast
from uuid import UUID

from skm.adapters.memory.core.state import MemoryBackendState, MemoryCoreState
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError
from skm.kernel.json_types import JsonObject
from skm.platform.config.keys import copy_json
from skm.platform.config.store import StoredContribution, StoredOp

__all__ = [
    "MemoryConfigStore",
    "delete_config_entry",
    "entry_row",
    "increment_config_generation",
    "write_config_entry",
]

_ROW_FIELDS: Final = frozenset({"id", "key", "op", "value", "locked", "row_version"})

# id(working core) -> weak reference; an entry disappears with its working copy.
_MARKED: dict[int, weakref.ref[MemoryCoreState]] = {}
_MARK_LOCK = Lock()


def _mark(core: MemoryCoreState) -> None:
    key = id(core)

    def forget(_ref: weakref.ref[MemoryCoreState]) -> None:
        with _MARK_LOCK:
            if _MARKED.get(key) is _ref:
                del _MARKED[key]

    with _MARK_LOCK:
        _MARKED[key] = weakref.ref(core, forget)


def _marked(core: MemoryCoreState) -> bool:
    with _MARK_LOCK:
        found = _MARKED.get(id(core))
    return found is not None and found() is core


def entry_row(entry: StoredContribution) -> JsonObject:
    """The JSON row of an entry in ``config_entries``."""
    return {
        "id": str(entry.entry_id),
        "key": entry.key,
        "op": entry.op,
        "value": copy_json(entry.value, entry.key),
        "locked": entry.locked,
        "row_version": entry.row_version,
    }


def _contribution(scope_id: UUID, key: str, row: JsonObject) -> StoredContribution:
    try:
        if frozenset(row) != _ROW_FIELDS or row["key"] != key:
            raise ValueError("row fields")
        return StoredContribution(
            entry_id=UUID(cast("str", row["id"])),
            key=key,
            op=cast("StoredOp", row["op"]),
            value=row["value"],
            locked=cast("bool", row["locked"]),
            row_version=cast("int", row["row_version"]),
        )
    except (TypeError, ValueError, AttributeError) as exc:
        # A row that does not fit the table shape is storage damage: fail closed, never guess a value.
        raise InternalError(
            ErrorCode.INTERNAL_ERROR,
            "config entry row is malformed",
            details={"scope_id": str(scope_id), "key": key},
        ) from exc


def write_config_entry(state: MemoryBackendState, scope_id: UUID, entry: StoredContribution) -> None:
    """Insert or replace the entry of ``(scope_id, entry.key)``; checks and versions belong to the caller."""
    core = state.core
    core.require_writable()
    _mark(core)
    core.config_entries.setdefault(scope_id, {})[entry.key] = entry_row(entry)


def delete_config_entry(state: MemoryBackendState, scope_id: UUID, key: str) -> None:
    core = state.core
    core.require_writable()
    _mark(core)
    rows = core.config_entries.get(scope_id)
    if rows is not None:
        rows.pop(key, None)
        if not rows:
            del core.config_entries[scope_id]


def increment_config_generation(state: MemoryBackendState) -> int:
    """``counter.increment``: the new generation of this unit of work."""
    core = state.core
    core.require_writable()
    _mark(core)
    core.config_generation += 1
    return core.config_generation


class MemoryConfigStore:
    """Read side of the memory config tables on the working copy of one unit of work."""

    def __init__(self, state: MemoryBackendState) -> None:
        self._core = state.core
        self._baseline = (self._core.config_generation, deepcopy(self._core.config_entries))

    def generation(self) -> int:
        return self._core.config_generation

    def pending_writes(self) -> bool:
        core = self._core
        if core.readonly:
            return False
        return _marked(core) or (core.config_generation, core.config_entries) != self._baseline

    def entries_for(self, scope_ids: Sequence[UUID]) -> Mapping[UUID, Mapping[str, StoredContribution]]:
        found: dict[UUID, Mapping[str, StoredContribution]] = {}
        for scope_id in dict.fromkeys(scope_ids):
            rows = self._core.config_entries.get(scope_id)
            if rows:
                found[scope_id] = {key: _contribution(scope_id, key, row) for key, row in rows.items()}
        return found
