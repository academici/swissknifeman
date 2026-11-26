"""PostgreSQL ``DraftRepository`` adapter (planning §6, §11; DDL ``0008``)."""

from typing import Final, cast

import psycopg

from skm.adapters.postgres.jsonb import require_aware, to_jsonb
from skm.adapters.postgres.planning.mapping import (
    already_exists,
    draft_from_row,
    field_owned,
    not_found,
    require_unchanged,
    run,
)
from skm.kernel.ids import PlanId
from skm.modules.planning.domain.draft import Draft, DraftId, DraftState, require_edit_version, require_open
from skm.modules.planning.domain.revision import SCHEMA_VERSION

__all__ = ["PostgresDraftRepository"]

_DRAFT_OWNED: Final = ("plan_id", "workspace_id", "created_by", "created_at")

_SELECT: Final = """
SELECT id, plan_id, workspace_id, base_revision_id, edit_version, document,
       state, published_revision_id, created_by, created_at, updated_by, updated_at, closed_at
  FROM skm_planning.plan_drafts
"""
_GET: Final = _SELECT + " WHERE id = %s"
_LOCK: Final = _GET + " FOR UPDATE"
_INSERT: Final = """
INSERT INTO skm_planning.plan_drafts (
    workspace_id, plan_id, id, base_revision_id, edit_version, schema_version,
    document, state, published_revision_id, created_by, created_at, updated_by, updated_at, closed_at
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (id) DO NOTHING
RETURNING id
"""
_UPDATE: Final = """
UPDATE skm_planning.plan_drafts
   SET base_revision_id = %s,
       edit_version = %s,
       document = %s,
       state = %s,
       published_revision_id = %s,
       updated_by = %s,
       updated_at = %s,
       closed_at = %s
 WHERE id = %s AND edit_version = %s
"""
_LIST_FOR_PLAN: Final = (
    _SELECT
    + """
 WHERE plan_id = %s
   AND (%s::text IS NULL OR state = %s::text)
 ORDER BY created_at ASC, id::text COLLATE "C" ASC
"""
)
_LOCK_OPEN_FOR_PLAN: Final = (
    _SELECT
    + """
 WHERE plan_id = %s AND state = 'open'
 ORDER BY id::text COLLATE "C" ASC
 FOR UPDATE
"""
)
_COUNT_OPEN: Final = """
SELECT count(*)
  FROM skm_planning.plan_drafts
 WHERE plan_id = %s AND state = 'open'
"""


class PostgresDraftRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def get(self, draft_id: DraftId) -> Draft:
        row = run(lambda: self._conn.execute(_GET, (draft_id,)).fetchone())
        if row is None:
            raise not_found("draft", draft_id)
        return draft_from_row(row)

    def lock(self, draft_id: DraftId) -> Draft:
        row = run(lambda: self._conn.execute(_LOCK, (draft_id,)).fetchone())
        if row is None:
            raise not_found("draft", draft_id)
        return draft_from_row(row)

    def add(self, draft: Draft) -> None:
        created_at = require_aware(draft.created_at)
        updated_at = require_aware(draft.updated_at)
        closed_at = None if draft.closed_at is None else require_aware(draft.closed_at)
        inserted = run(
            lambda: self._conn.execute(
                _INSERT,
                (
                    draft.workspace_id,
                    draft.plan_id,
                    draft.id,
                    draft.base_revision_id,
                    draft.edit_version,
                    SCHEMA_VERSION,
                    to_jsonb(draft.document),
                    draft.state.value,
                    draft.published_revision_id,
                    draft.created_by,
                    created_at,
                    draft.updated_by,
                    updated_at,
                    closed_at,
                ),
            ).fetchone()
        )
        if inserted is None:
            raise already_exists("draft", ref=str(draft.id))

    def save(self, draft: Draft, *, expected_edit_version: int) -> None:
        stored = self.lock(draft.id)
        require_open(stored)
        require_edit_version(stored, expected_edit_version)
        require_unchanged("draft", stored, draft, _DRAFT_OWNED)
        if draft.document.get("schema") != stored.document.get("schema"):
            raise field_owned("draft", "schema")
        updated_at = require_aware(draft.updated_at)
        closed_at = None if draft.closed_at is None else require_aware(draft.closed_at)
        run(
            lambda: self._conn.execute(
                _UPDATE,
                (
                    draft.base_revision_id,
                    draft.edit_version,
                    to_jsonb(draft.document),
                    draft.state.value,
                    draft.published_revision_id,
                    draft.updated_by,
                    updated_at,
                    closed_at,
                    draft.id,
                    expected_edit_version,
                ),
            )
        )

    def list_for_plan(self, plan_id: PlanId, *, state: DraftState | None) -> tuple[Draft, ...]:
        state_val = None if state is None else state.value
        rows = run(lambda: self._conn.execute(_LIST_FOR_PLAN, (plan_id, state_val, state_val)).fetchall())
        return tuple(draft_from_row(row) for row in rows)

    def lock_open_for_plan(self, plan_id: PlanId) -> tuple[Draft, ...]:
        rows = run(lambda: self._conn.execute(_LOCK_OPEN_FOR_PLAN, (plan_id,)).fetchall())
        return tuple(draft_from_row(row) for row in rows)

    def count_open(self, plan_id: PlanId) -> int:
        row = run(lambda: self._conn.execute(_COUNT_OPEN, (plan_id,)).fetchone())
        return 0 if row is None else cast("int", row[0])
