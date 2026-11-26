"""PostgreSQL ``PlanningQueries`` adapter and query helpers (planning §6, §8, §11; DDL ``0008``, ``0009``)."""

from collections.abc import Sequence
from datetime import datetime
from typing import Final, cast
from uuid import UUID

import psycopg

from skm.adapters.postgres.pagination import decode_cursor, page_of, query_digest, validate_limit
from skm.adapters.postgres.planning.mapping import (
    Row,
    damaged,
    member_ref_from_row,
    not_found,
    run,
)
from skm.adapters.postgres.planning.spec_reader import (
    load_revision_materials,
    load_revision_pins,
    revisions_for_file_version,
)
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.ids import EntityId, PlanId, ProjectId, RevisionId
from skm.kernel.pagination import Cursor, Page
from skm.modules.planning.domain.material import MaterialRef
from skm.modules.planning.domain.member import EntityLinks, MemberRef
from skm.modules.planning.domain.reads import format_timestamp
from skm.modules.planning.ports import MaterialPin, PlanListState, PlanSummary

__all__ = [
    "PostgresPlanningQueries",
    "entity_links",
    "find_member",
    "find_member_by_id",
    "list_plans",
    "plan_summary",
    "revision_materials",
    "revision_pins",
    "revisions_pinning_file_version",
]

_SUMMARY_SELECT: Final = """
SELECT p.id,
       a.alias,
       p.title,
       p.purpose,
       p.lifecycle_state,
       p.current_revision_id,
       r.revision_no,
       (
           SELECT count(*)
             FROM skm_planning.plan_drafts d
            WHERE d.plan_id = p.id AND d.state = 'open'
       ) AS open_drafts,
       p.updated_at
  FROM skm_planning.plans p
  JOIN skm_planning.plan_aliases a
    ON a.workspace_id = p.workspace_id
   AND a.project_id = p.project_id
   AND a.plan_id = p.id
   AND a.alias_kind IN ('short', 'system')
  LEFT JOIN skm_planning.plan_revisions r
    ON r.workspace_id = p.workspace_id
   AND r.plan_id = p.id
   AND r.id = p.current_revision_id
"""
_GET_SUMMARY: Final = _SUMMARY_SELECT + " WHERE p.id = %s"
_LIST_PLANS: Final = """
SELECT p.id,
       a.alias,
       p.title,
       p.purpose,
       p.lifecycle_state,
       p.current_revision_id,
       r.revision_no,
       (
           SELECT count(*)
             FROM skm_planning.plan_drafts d
            WHERE d.plan_id = p.id AND d.state = 'open'
       ) AS open_drafts,
       p.updated_at
  FROM skm_workspace.projects proj
  JOIN skm_planning.plans p
    ON p.workspace_id = proj.workspace_id
   AND p.project_id = proj.id
  JOIN skm_planning.plan_aliases a
    ON a.workspace_id = p.workspace_id
   AND a.project_id = p.project_id
   AND a.plan_id = p.id
   AND a.alias_kind IN ('short', 'system')
  LEFT JOIN skm_planning.plan_revisions r
    ON r.workspace_id = p.workspace_id
   AND r.plan_id = p.id
   AND r.id = p.current_revision_id
 WHERE proj.id = %(project)s
   AND p.purpose = 'standard'
   AND (%(state)s::text = 'all' OR p.lifecycle_state = %(state)s::text)
   AND (
       %(at)s::timestamptz IS NULL
       OR (p.updated_at, p.id) < (%(at)s::timestamptz, %(id)s::uuid)
   )
 ORDER BY p.updated_at DESC, p.id DESC
 LIMIT %(limit)s
"""

_FIND_MEMBER_BY_KEY: Final = """
SELECT entity_id, entity_kind, display_key, position
  FROM skm_planning.revision_members
 WHERE revision_id = %s AND display_key = %s
"""
_FIND_MEMBER_BY_ID: Final = """
SELECT entity_id, entity_kind, display_key, position
  FROM skm_planning.revision_members
 WHERE revision_id = %s AND entity_id = %s
"""

_PREREQUISITES: Final = """
SELECT m.entity_id, m.entity_kind, m.display_key, m.position
  FROM skm_planning.dependency_edges d
  JOIN skm_planning.revision_members m
    ON m.revision_id = d.revision_id AND m.entity_id = d.prerequisite_entity_id
 WHERE d.revision_id = %s AND d.dependent_entity_id = %s
 ORDER BY m.entity_kind, m.position ASC
"""
_DEPENDENTS: Final = """
SELECT m.entity_id, m.entity_kind, m.display_key, m.position
  FROM skm_planning.dependency_edges d
  JOIN skm_planning.revision_members m
    ON m.revision_id = d.revision_id AND m.entity_id = d.dependent_entity_id
 WHERE d.revision_id = %s AND d.prerequisite_entity_id = %s
 ORDER BY m.entity_kind, m.position ASC
"""
_CRITERIA_LINKS: Final = """
SELECT DISTINCT m.entity_id, m.entity_kind, m.display_key, m.position
  FROM skm_planning.revision_members m
 WHERE m.revision_id = %s
   AND (
       EXISTS (
           SELECT 1 FROM skm_planning.acceptance_criteria a
            WHERE a.revision_id = m.revision_id
              AND a.criterion_id = m.entity_id
              AND a.owner_entity_id = %s
       )
       OR EXISTS (
           SELECT 1 FROM skm_planning.criterion_check_bindings cb
            WHERE cb.revision_id = m.revision_id
              AND cb.criterion_id = m.entity_id
              AND cb.check_id = %s
       )
       OR EXISTS (
           SELECT 1 FROM skm_planning.entity_requirement_links rl
            WHERE rl.revision_id = m.revision_id
              AND rl.entity_id = m.entity_id
              AND rl.requirement_id = %s
              AND rl.relation = 'verifies'
       )
   )
 ORDER BY m.position ASC
"""
_CHECK_LINKS: Final = """
SELECT DISTINCT m.entity_id, m.entity_kind, m.display_key, m.position
  FROM skm_planning.revision_members m
 WHERE m.revision_id = %s
   AND (
       EXISTS (
           SELECT 1 FROM skm_planning.check_specs c
            WHERE c.revision_id = m.revision_id
              AND c.check_id = m.entity_id
              AND c.owner_entity_id = %s
       )
       OR EXISTS (
           SELECT 1 FROM skm_planning.entity_check_bindings eb
            WHERE eb.revision_id = m.revision_id
              AND eb.check_id = m.entity_id
              AND eb.entity_id = %s
       )
       OR EXISTS (
           SELECT 1 FROM skm_planning.criterion_check_bindings cb
            WHERE cb.revision_id = m.revision_id
              AND cb.check_id = m.entity_id
              AND cb.criterion_id = %s
       )
   )
 ORDER BY m.position ASC
"""
_DECISION_LINKS: Final = """
SELECT DISTINCT m.entity_id, m.entity_kind, m.display_key, m.position
  FROM skm_planning.decision_bindings b
  JOIN skm_planning.revision_members m
    ON m.revision_id = b.revision_id AND m.entity_id = b.decision_id
 WHERE b.revision_id = %s AND b.entity_id = %s
 ORDER BY m.position ASC
"""
_MATERIAL_LINKS: Final = """
SELECT DISTINCT m.entity_id, m.entity_kind, m.display_key, m.position
  FROM skm_planning.material_bindings b
  JOIN skm_planning.revision_members m
    ON m.revision_id = b.revision_id AND m.entity_id = b.material_id
 WHERE b.revision_id = %s AND b.entity_id = %s
 ORDER BY m.position ASC
"""
_REQUIREMENT_LINKS: Final = """
SELECT DISTINCT m.entity_id, m.entity_kind, m.display_key, m.position
  FROM skm_planning.entity_requirement_links l
  JOIN skm_planning.revision_members m
    ON m.revision_id = l.revision_id AND m.entity_id = l.requirement_id
 WHERE l.revision_id = %s AND l.entity_id = %s
 ORDER BY m.position ASC
"""


def _summary_from_row(row: Row) -> PlanSummary:
    try:
        rev_id = cast("UUID | None", row[5])
        rev_no = cast("int | None", row[6])
        updated_at = cast("datetime", row[8])
        return {
            "plan_id": str(cast("UUID", row[0])),
            "alias": cast("str", row[1]),
            "title": cast("str", row[2]),
            "purpose": cast("str", row[3]),
            "lifecycle_state": cast("str", row[4]),
            "current_revision_id": None if rev_id is None else str(rev_id),
            "current_revision_no": None if rev_no is None else int(rev_no),
            "open_drafts": int(cast("int", row[7])),
            "updated_at": format_timestamp(updated_at),
        }
    except (TypeError, ValueError) as exc:
        raise damaged("plans", row[0], exc) from exc


def _decode_plan_keyset(cursor: Cursor | None, digest: str) -> tuple[datetime | None, UUID | None]:
    if cursor is None:
        return None, None
    decoded = decode_cursor(str(cursor), expected_query_digest=digest)
    if len(decoded.sort_values) != 2 or not all(isinstance(v, str) for v in decoded.sort_values):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID, "cursor is not valid for this query", details={"field": "after"}
        )
    ts_text, id_text = cast("tuple[str, str]", decoded.sort_values)
    try:
        moment = datetime.fromisoformat(ts_text)
        if moment.utcoffset() is None:
            raise ValueError("naive timestamp")
        return moment, UUID(id_text)
    except ValueError as exc:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID, "cursor is not valid for this query", details={"field": "after"}
        ) from exc


def list_plans(
    conn: psycopg.Connection,
    project_id: ProjectId,
    *,
    state: PlanListState,
    cursor: Cursor | None,
    limit: int,
) -> Page[PlanSummary]:
    page_limit = validate_limit(limit)
    if state not in ("active", "archived", "all"):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID, "invalid plan list state", details={"field": "state"}
        )
    digest = query_digest({"kind": "planning_plans", "project_id": str(project_id), "state": state})
    at, after_id = _decode_plan_keyset(cursor, digest)
    params = {
        "project": project_id,
        "state": state,
        "at": at,
        "id": after_id,
        "limit": page_limit + 1,
    }
    rows = run(lambda: conn.execute(_LIST_PLANS, params).fetchall())
    items = [_summary_from_row(row) for row in rows]
    return page_of(
        items,
        limit=page_limit,
        digest=digest,
        key_of=lambda item: (cast("str", item["updated_at"]), cast("str", item["plan_id"])),
    )


def plan_summary(conn: psycopg.Connection, plan_id: PlanId) -> PlanSummary:
    row = run(lambda: conn.execute(_GET_SUMMARY, (plan_id,)).fetchone())
    if row is None:
        raise not_found("plan", plan_id)
    return _summary_from_row(row)


def find_member(conn: psycopg.Connection, revision_id: RevisionId, display_key: str) -> MemberRef | None:
    row = run(lambda: conn.execute(_FIND_MEMBER_BY_KEY, (revision_id, display_key)).fetchone())
    return None if row is None else member_ref_from_row(row)


def find_member_by_id(
    conn: psycopg.Connection, revision_id: RevisionId, entity_id: EntityId
) -> MemberRef | None:
    row = run(lambda: conn.execute(_FIND_MEMBER_BY_ID, (revision_id, entity_id)).fetchone())
    return None if row is None else member_ref_from_row(row)


def _refs(rows: Sequence[tuple[object, ...]]) -> tuple[MemberRef, ...]:
    return tuple(member_ref_from_row(r) for r in rows)


def entity_links(conn: psycopg.Connection, revision_id: RevisionId, entity_id: EntityId) -> EntityLinks:
    return run(
        lambda: EntityLinks(
            prerequisites=_refs(conn.execute(_PREREQUISITES, (revision_id, entity_id)).fetchall()),
            dependents=_refs(conn.execute(_DEPENDENTS, (revision_id, entity_id)).fetchall()),
            criteria=_refs(
                conn.execute(_CRITERIA_LINKS, (revision_id, entity_id, entity_id, entity_id)).fetchall()
            ),
            checks=_refs(
                conn.execute(_CHECK_LINKS, (revision_id, entity_id, entity_id, entity_id)).fetchall()
            ),
            decisions=_refs(conn.execute(_DECISION_LINKS, (revision_id, entity_id)).fetchall()),
            materials=_refs(conn.execute(_MATERIAL_LINKS, (revision_id, entity_id)).fetchall()),
            requirements=_refs(conn.execute(_REQUIREMENT_LINKS, (revision_id, entity_id)).fetchall()),
        )
    )


class PostgresPlanningQueries:
    """PostgreSQL implementation of ``PlanningQueries``."""

    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def list_plans(
        self, project_id: ProjectId, *, state: PlanListState, cursor: Cursor | None, limit: int
    ) -> Page[PlanSummary]:
        return list_plans(self._conn, project_id, state=state, cursor=cursor, limit=limit)

    def plan_summary(self, plan_id: PlanId) -> PlanSummary:
        return plan_summary(self._conn, plan_id)

    def find_member(self, revision_id: RevisionId, display_key: str) -> MemberRef | None:
        return find_member(self._conn, revision_id, display_key)

    def find_member_by_id(self, revision_id: RevisionId, entity_id: EntityId) -> MemberRef | None:
        return find_member_by_id(self._conn, revision_id, entity_id)

    def entity_links(self, revision_id: RevisionId, entity_id: EntityId) -> EntityLinks:
        return entity_links(self._conn, revision_id, entity_id)

    def revision_pins(self, revision_id: RevisionId) -> tuple[MaterialPin, ...]:
        return revision_pins(self._conn, revision_id)

    def revision_materials(self, revision_id: RevisionId) -> tuple[MaterialRef, ...]:
        return revision_materials(self._conn, revision_id)

    def revisions_pinning_file_version(self, file_version_id: UUID) -> tuple[RevisionId, ...]:
        return revisions_pinning_file_version(self._conn, file_version_id)


def revision_pins(conn: psycopg.Connection, revision_id: RevisionId) -> tuple[MaterialPin, ...]:
    return load_revision_pins(conn, revision_id)


def revision_materials(conn: psycopg.Connection, revision_id: RevisionId) -> tuple[MaterialRef, ...]:
    return load_revision_materials(conn, revision_id)


def revisions_pinning_file_version(conn: psycopg.Connection, file_version_id: UUID) -> tuple[RevisionId, ...]:
    return revisions_for_file_version(conn, file_version_id)
