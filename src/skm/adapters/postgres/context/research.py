"""Transactional, append-only PostgreSQL research ledger (DDL 0019)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from skm.adapters.postgres.errors import translate_pg_error
from skm.adapters.postgres.jsonb import to_jsonb
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, NotFound
from skm.kernel.ids import ProjectId, WorkspaceId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.context.domain.research import ResearchDocument, document_from_json, result_from_json
from skm.modules.context.domain.research_rules import invalid, validate_result

__all__ = ["PostgresResearchRepository"]

_INSERT_QUERY = """
INSERT INTO skm_context.research_queries (
 id, workspace_id, project_id, step_ref, requested_by, source_id, source_kind, tier,
 query_text, query_digest, depth, max_documents, cache_key, source_config_digest,
 status, error_code, error_message, citations, claims, limitations, usage, usage_complete,
 retrieved_at, expires_at, created_at
) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
"""
_INSERT_DOC = """
INSERT INTO skm_context.external_sources (
 id, workspace_id, project_id, query_id, ordinal, origin, url, title, retrieved_at,
 content_digest, size_bytes, locator, excerpt, trust_class, classification, provenance,
 captured_file_version_id, created_at
) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
"""
_CACHED = """
SELECT id FROM skm_context.research_queries
WHERE workspace_id=%s AND project_id=%s AND cache_key=%s
  AND status <> 'error' AND expires_at > %s
ORDER BY retrieved_at DESC, id DESC LIMIT 1
"""
_LIST = """
SELECT * FROM skm_context.external_sources
WHERE workspace_id=%s AND project_id=%s
 AND (%s::uuid IS NULL OR query_id=%s)
 AND (%s::text IS NULL OR starts_with(origin, %s))
 AND (%s::uuid IS NULL OR id > %s)
ORDER BY id LIMIT %s
"""


def _document(row: dict[str, Any]) -> JsonObject:
    return {
        "document_id": str(row["id"]),
        "query_id": str(row["query_id"]),
        "origin": row["origin"],
        "url": row["url"],
        "title": row["title"],
        "retrieved_at": row["retrieved_at"].isoformat(),
        "content_digest": row["content_digest"],
        "locator": row["locator"],
        "excerpt": row["excerpt"],
        "trust_class": row["trust_class"],
        "classification": row["classification"],
        "staged_blob": None,
        "captured_file_version_id": str(row["captured_file_version_id"])
        if row["captured_file_version_id"]
        else None,
        "provenance": row["provenance"],
    }


class PostgresResearchRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def add_results(self, results: Sequence[JsonObject]) -> None:
        try:
            with self._conn.transaction():
                for result in results:
                    raw = cast("dict[str, Any]", result)
                    parsed = result_from_json(raw)
                    problems = validate_result(
                        parsed, max_documents=raw["max_documents"], excerpt_max_chars=20000
                    )
                    if problems:
                        raise invalid(problems[0])
                    try:
                        old = self.get(parsed.query_id)
                    except NotFound:
                        old = None
                    if old is not None:
                        if old == result:
                            continue
                        raise Conflict(ErrorCode.IDEMPOTENCY_KEY_REUSED, "research query id already used")
                    self._insert(raw)
        except psycopg.errors.UniqueViolation as exc:
            raise Conflict(ErrorCode.IDEMPOTENCY_KEY_REUSED, "research identifiers already used") from exc
        except psycopg.Error as exc:
            raise translate_pg_error(exc) from exc

    def _insert(self, raw: dict[str, Any]) -> None:
        error: dict[str, Any] = raw["error"] or {}
        # Versionless legacy rows infer miss/bypass. Cache bindings retain delivery state
        # in reserved storage metadata; public usage remains the exact nullable DTO.
        usage = cast("dict[str, Any] | None", raw["usage"])
        if raw["cache_status"] == "hit":
            usage = {**(usage or {}), "_skm_cache_status": "hit", "_skm_usage_unknown": usage is None}
        with self._conn.cursor() as cur:
            cur.execute(
                _INSERT_QUERY,
                (
                    UUID(raw["query_id"]),
                    UUID(raw["workspace_id"]),
                    UUID(raw["project_id"]),
                    raw.get("step_ref"),
                    UUID(raw["requested_by"]),
                    raw["source_id"],
                    raw["kind"],
                    raw["tier"],
                    raw["query_text"],
                    raw["query_digest"],
                    raw["depth"],
                    raw["max_documents"],
                    raw["cache_key"],
                    raw["source_config_digest"],
                    raw["status"],
                    error.get("code"),
                    error.get("message"),
                    to_jsonb(raw["citations"]),
                    to_jsonb(raw["claims"]),
                    to_jsonb(raw["limitations"]),
                    to_jsonb(usage) if usage is not None else None,
                    raw["usage_complete"],
                    datetime.fromisoformat(raw["retrieved_at"]),
                    datetime.fromisoformat(raw["expires_at"]) if raw["expires_at"] else None,
                    datetime.fromisoformat(raw["created_at"]),
                ),
            )
            for ordinal, doc in enumerate(raw["documents"]):
                cur.execute(
                    _INSERT_DOC,
                    (
                        UUID(doc["document_id"]),
                        UUID(raw["workspace_id"]),
                        UUID(raw["project_id"]),
                        UUID(raw["query_id"]),
                        ordinal,
                        doc["origin"],
                        doc["url"],
                        doc["title"],
                        datetime.fromisoformat(doc["retrieved_at"]),
                        doc["content_digest"],
                        None,
                        to_jsonb(doc["locator"]),
                        doc["excerpt"],
                        doc["trust_class"],
                        doc["classification"],
                        to_jsonb(doc["provenance"]),
                        UUID(doc["captured_file_version_id"])
                        if doc.get("captured_file_version_id")
                        else None,
                        datetime.fromisoformat(raw["created_at"]),
                    ),
                )

    def get(self, query_id: str) -> JsonObject:
        try:
            parsed_id = UUID(query_id)
        except ValueError as exc:
            raise NotFound(ErrorCode.NOT_FOUND, "research query not found") from exc
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM skm_context.research_queries WHERE id=%s", (parsed_id,))
            row = cur.fetchone()
            if row is None:
                raise NotFound(ErrorCode.NOT_FOUND, "research query not found")
            cur.execute(
                "SELECT * FROM skm_context.external_sources WHERE query_id=%s ORDER BY ordinal",
                (UUID(query_id),),
            )
            docs = [_document(d) for d in cur.fetchall()]
        usage = cast("dict[str, Any] | None", row["usage"])
        delivery = usage.get("_skm_cache_status") if usage is not None else None
        if usage is not None and delivery is not None:
            usage = (
                None
                if usage["_skm_usage_unknown"]
                else {key: value for key, value in usage.items() if not key.startswith("_skm_")}
            )
        return {
            "query_id": str(row["id"]),
            "workspace_id": str(row["workspace_id"]),
            "project_id": str(row["project_id"]),
            "step_ref": row["step_ref"],
            "requested_by": str(row["requested_by"]),
            "source_id": row["source_id"],
            "kind": row["source_kind"],
            "tier": row["tier"],
            "query_text": row["query_text"],
            "query_digest": row["query_digest"],
            "depth": row["depth"],
            "max_documents": row["max_documents"],
            "cache_key": row["cache_key"],
            "source_config_digest": row["source_config_digest"],
            "status": row["status"],
            "error": {"code": row["error_code"], "message": row["error_message"]}
            if row["error_code"]
            else None,
            "documents": cast("list[JsonValue]", docs),
            "citations": row["citations"],
            "claims": row["claims"],
            "limitations": row["limitations"],
            "usage": usage,
            "usage_complete": row["usage_complete"],
            "retrieved_at": row["retrieved_at"].isoformat(),
            "expires_at": row["expires_at"].isoformat() if row["expires_at"] else None,
            "cache_status": delivery or ("miss" if row["expires_at"] else "bypass"),
            "created_at": row["created_at"].isoformat(),
        }

    def find_cached(
        self, *, workspace_id: WorkspaceId, project_id: ProjectId, cache_key: str, now: datetime
    ) -> JsonObject | None:
        with self._conn.cursor() as cur:
            cur.execute(_CACHED, (workspace_id, project_id, cache_key, now))
            row = cur.fetchone()
        return self.get(str(row[0])) if row else None

    def documents(self, document_ids: Sequence[str]) -> tuple[ResearchDocument, ...]:
        if not document_ids:
            return ()
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT * FROM skm_context.external_sources WHERE id=ANY(%s::uuid[])",
                ([UUID(d) for d in document_ids],),
            )
            rows = {str(r["id"]): r for r in cur.fetchall()}
        return tuple(
            document_from_json(cast("dict[str, Any]", _document(rows[d]))) for d in document_ids if d in rows
        )

    def results_for_step(self, step_ref: str) -> tuple[JsonObject, ...]:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM skm_context.research_queries WHERE step_ref=%s ORDER BY retrieved_at,id",
                (step_ref,),
            )
            ids = [str(row[0]) for row in cur.fetchall()]
        return tuple(self.get(qid) for qid in ids)

    def list_documents(
        self,
        *,
        workspace_id: WorkspaceId,
        project_id: ProjectId,
        query_id: str | None,
        origin_prefix: str | None,
        after: str | None,
        limit: int,
    ) -> JsonObject:
        if not 1 <= limit <= 200:
            raise invalid("invalid_limit")
        try:
            qid, cursor = UUID(query_id) if query_id else None, UUID(after) if after else None
        except ValueError as exc:
            raise invalid("invalid_cursor") from exc
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                _LIST,
                (workspace_id, project_id, qid, qid, origin_prefix, origin_prefix, cursor, cursor, limit + 1),
            )
            rows = cur.fetchall()
        return {
            "items": cast("list[JsonValue]", [_document(row) for row in rows[:limit]]),
            "next_after": str(rows[limit - 1]["id"]) if len(rows) > limit else None,
        }
