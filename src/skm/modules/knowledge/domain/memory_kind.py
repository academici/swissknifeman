"""Supported memory categories and categories reserved for repository artifacts."""

from __future__ import annotations

from enum import StrEnum


class MemoryKind(StrEnum):
    CONTEXT = "context"
    FACT = "fact"
    BLOCKER = "blocker"
    COORDINATION = "coordination"
    ACTIVE_HANDOFF = "active_handoff"
    HEALTH_PROBE = "health_probe"


REJECTED_JOURNAL_KINDS: frozenset[str] = frozenset(
    {
        "progress",
        "plan_progress",
        "checkpoint",
        "session_log",
        "decision",
        "plan_decision",
        "architecture",
        "release",
        "feature_log",
        "ecosystem_link",
    }
)
