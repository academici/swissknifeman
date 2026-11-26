"""Immutable fix-brief persistence using the existing memory review store and transaction."""

from __future__ import annotations

from typing import TYPE_CHECKING

from skm.adapters.memory.execution.checks_reviews import MemoryReviewRepository

if TYPE_CHECKING:
    from skm.adapters.memory.core.state import MemoryBackendState
    from skm.modules.execution.domain.fix_brief import FixBrief
    from skm.modules.execution.domain.ids import FixBriefId

__all__ = ["add_fix_brief", "get_fix_brief"]


def add_fix_brief(state: MemoryBackendState, brief: FixBrief) -> None:
    MemoryReviewRepository(state).add_fix_brief(brief)


def get_fix_brief(state: MemoryBackendState, brief_id: FixBriefId) -> FixBrief:
    return MemoryReviewRepository(state).get_fix_brief(brief_id)
