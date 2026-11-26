"""PostgreSQL ``RevisionRepository`` adapter (planning §6, §11; DDL ``0008``..``0029``)."""

from collections.abc import Mapping
from copy import deepcopy
from typing import Final, cast
from uuid import UUID

import psycopg

from skm.adapters.postgres.planning.mapping import (
    damaged,
    not_found,
    revision_meta_from_row,
    run,
)
from skm.adapters.postgres.planning.spec_reader import load_typed_document
from skm.adapters.postgres.planning.spec_writer import write_revision_record
from skm.kernel.ids import EntityId, PlanId, RevisionId
from skm.modules.planning.domain.revision import RevisionMeta
from skm.modules.planning.domain.specification import EntityKind
from skm.modules.planning.ports import RevisionRecord, SpecificationDoc

__all__ = ["PostgresRevisionRepository"]

_SELECT_META: Final = """
SELECT id, plan_id, workspace_id, revision_no, parent_revision_id, schema_version,
       content_digest, canonicalization_version, compiler_version, origin,
       restored_from_revision_id, published_by, published_at, change_reason
  FROM skm_planning.plan_revisions
"""
_GET_META: Final = _SELECT_META + " WHERE id = %s"
_BY_NUMBER: Final = _SELECT_META + " WHERE plan_id = %s AND revision_no = %s"
_LIST_FOR_PLAN: Final = (
    _SELECT_META
    + """
 WHERE plan_id = %s
   AND (%s::integer IS NULL OR revision_no < %s::integer)
 ORDER BY revision_no DESC
 LIMIT %s
"""
)
_GET_PAYLOAD: Final = """
SELECT document
  FROM skm_planning.revision_payloads
 WHERE revision_id = %s
"""
_IDENTITIES: Final = """
SELECT entity_id, entity_kind
  FROM skm_planning.plan_entity_identities
 WHERE plan_id = %s
"""


class PostgresRevisionRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def get_meta(self, revision_id: RevisionId) -> RevisionMeta:
        row = run(lambda: self._conn.execute(_GET_META, (revision_id,)).fetchone())
        if row is None:
            raise not_found("revision", revision_id)
        return revision_meta_from_row(row)

    def find_by_number(self, plan_id: PlanId, revision_no: int) -> RevisionMeta | None:
        row = run(lambda: self._conn.execute(_BY_NUMBER, (plan_id, revision_no)).fetchone())
        return None if row is None else revision_meta_from_row(row)

    def get_document(self, revision_id: RevisionId) -> SpecificationDoc:
        row = run(lambda: self._conn.execute(_GET_PAYLOAD, (revision_id,)).fetchone())
        if row is None:
            raise not_found("revision", revision_id)
        doc = row[0]
        if not isinstance(doc, dict):
            raise damaged("revision_payloads", revision_id, TypeError("document must be a JSON object"))
        return deepcopy(cast("SpecificationDoc", doc))

    def load_typed_document(self, revision_id: RevisionId) -> SpecificationDoc:
        return load_typed_document(self._conn, revision_id)

    def identities(self, plan_id: PlanId) -> Mapping[EntityId, EntityKind]:
        rows = run(lambda: self._conn.execute(_IDENTITIES, (plan_id,)).fetchall())
        return {EntityId(cast("UUID", row[0])): EntityKind(cast("str", row[1])) for row in rows}

    def add(self, record: RevisionRecord) -> None:
        write_revision_record(self._conn, record)

    def list_for_plan(
        self, plan_id: PlanId, *, before_revision_no: int | None, limit: int
    ) -> tuple[RevisionMeta, ...]:
        if limit <= 0:
            return ()
        rows = run(
            lambda: self._conn.execute(
                _LIST_FOR_PLAN,
                (plan_id, before_revision_no, before_revision_no, limit),
            ).fetchall()
        )
        return tuple(revision_meta_from_row(row) for row in rows)
