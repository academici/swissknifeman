"""Immutable fix-brief persistence through the existing SQL repository and caller's transaction."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from skm.adapters.postgres.execution.checks_reviews import PostgresReviewRepository

if TYPE_CHECKING:
    import psycopg

    from skm.modules.execution.domain.fix_brief import FixBrief
    from skm.modules.execution.domain.ids import FixBriefId

__all__ = ["add_fix_brief", "get_fix_brief"]


def add_fix_brief(conn: psycopg.Connection[Any], brief: FixBrief) -> None:
    PostgresReviewRepository(conn).add_fix_brief(brief)


def get_fix_brief(conn: psycopg.Connection[Any], brief_id: FixBriefId) -> FixBrief:
    return PostgresReviewRepository(conn).get_fix_brief(brief_id)
