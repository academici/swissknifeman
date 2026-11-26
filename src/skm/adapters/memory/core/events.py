"""``EventReader`` over the memory state: committed envelopes only (the UoW publishes them on commit)."""

from collections.abc import Sequence
from copy import deepcopy

from skm.adapters.memory.core.state import MemoryBackendState
from skm.kernel.events import EventEnvelope
from skm.kernel.ids import EventId, WorkspaceId

__all__ = ["MemoryEventReader"]


def _copies(rows: Sequence[EventEnvelope]) -> tuple[EventEnvelope, ...]:
    """Independent envelopes (adapters §2.3): a caller changing a payload cannot rewrite the history."""
    return tuple(deepcopy(row) for row in rows)


class MemoryEventReader:
    def __init__(self, state: MemoryBackendState) -> None:
        self._events = state.core.events

    def after_global_position(self, after: int, *, limit: int) -> tuple[EventEnvelope, ...]:
        rows = [e for e in self._events if e.workspace_id is None and (e.global_position or 0) > after]
        rows.sort(key=lambda e: e.global_position or 0)
        return _copies(rows[: max(limit, 0)])

    def after_workspace_seq(
        self,
        workspace_id: WorkspaceId,
        after: int,
        *,
        types: frozenset[str] | None,
        limit: int,
    ) -> tuple[EventEnvelope, ...]:
        rows = [
            e
            for e in self._events
            if e.workspace_id == workspace_id
            and (e.workspace_seq or 0) > after
            and (types is None or e.type in types)
        ]
        rows.sort(key=lambda e: e.workspace_seq or 0)
        return _copies(rows[: max(limit, 0)])

    def by_ids(self, ids: Sequence[EventId]) -> tuple[EventEnvelope, ...]:
        by_id = {e.id: e for e in self._events}
        return _copies([by_id[event_id] for event_id in ids if event_id in by_id])

    def head_workspace_seq(self, workspace_id: WorkspaceId) -> int:
        return max((e.workspace_seq or 0 for e in self._events if e.workspace_id == workspace_id), default=0)
