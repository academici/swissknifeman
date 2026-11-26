"""Rank live memory, enforce per-scope quotas, and select digest text."""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import UTC, datetime
from heapq import nlargest
from typing import Protocol

from .memory_entry import MemoryEntry
from .memory_kind import MemoryKind
from .memory_policy import MemoryPolicySettings, is_live
from .memory_scope import MemoryScope, require_project_scope

_TOKEN = re.compile(r"\w{2,}")
_WORD = re.compile(r"\S+")
_PRIORITY_KINDS = frozenset({MemoryKind.BLOCKER, MemoryKind.ACTIVE_HANDOFF})


class RecallSettings(MemoryPolicySettings, Protocol):
    @property
    def recall_limit(self) -> int: ...

    @property
    def recall_shared_limit(self) -> int: ...


def _tokens(text: str) -> set[str]:
    return {token.casefold() for token in _TOKEN.findall(text)}


def rank_entries(
    entries: Iterable[MemoryEntry],
    query: str | None,
    now: datetime,
    settings: MemoryPolicySettings,
    *,
    limit: int | None = None,
) -> tuple[MemoryEntry, ...]:
    query_tokens = _tokens(query or "")

    def rank(entry: MemoryEntry) -> tuple[int, datetime]:
        score = 2 * len(query_tokens.intersection(_tokens(entry.body))) + (entry.kind in _PRIORITY_KINDS)
        return score, entry.created_at.astimezone(UTC)

    live = (entry for entry in entries if is_live(entry, now, settings))
    if limit is not None:
        return tuple(nlargest(limit, live, key=rank))
    return tuple(sorted(live, key=rank, reverse=True))


def partition_recall(
    ranked: Iterable[MemoryEntry], scopes: tuple[MemoryScope, ...], settings: RecallSettings
) -> tuple[MemoryEntry, ...]:
    """Take each authorized scope's quota, with the requesting project first."""
    if not scopes:
        return ()
    project = require_project_scope(scopes[0])
    by_scope: dict[MemoryScope, list[MemoryEntry]] = {scope: [] for scope in scopes}
    for entry in ranked:
        bucket = by_scope.get(entry.scope)
        if bucket is not None:
            limit = settings.recall_limit if entry.scope == project else settings.recall_shared_limit
            if len(bucket) < limit:
                bucket.append(entry)
    return tuple(entry for bucket in by_scope.values() for entry in bucket)


def _trim_at_word_boundary(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    end = 0
    for word in _WORD.finditer(text):
        if word.end() > max_chars:
            break
        end = word.end()
    return text[: end or max_chars]


def select_for_budget(
    entries: Iterable[MemoryEntry], budget_chars: int = 4000, item_max_chars: int = 500
) -> tuple[str, ...]:
    items: list[str] = []
    remaining = budget_chars
    for entry in entries:
        limit = min(remaining, item_max_chars)
        if limit <= 0:
            break
        item = _trim_at_word_boundary(entry.body, limit)
        items.append(item)
        remaining -= len(item)
    return tuple(items)
