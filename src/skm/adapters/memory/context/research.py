"""Append-only research ledger over the transaction's private memory snapshot."""

from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from skm.adapters.memory.core.state import MemoryBackendState
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, NotFound
from skm.kernel.ids import ProjectId, WorkspaceId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.context.domain.research import ResearchDocument, document_from_json, result_from_json
from skm.modules.context.domain.research_rules import invalid, validate_result

__all__ = ["MemoryResearchRepository"]


@dataclass
class _State:
    results: dict[str, JsonObject] = field(default_factory=dict[str, JsonObject])
    documents: dict[str, JsonObject] = field(default_factory=dict[str, JsonObject])


class MemoryResearchRepository:
    def __init__(self, state: MemoryBackendState) -> None:
        self._state = state

    def _tables(self) -> _State:
        found = self._state.modules.setdefault("context_research", _State())
        return cast("_State", found)

    def add_results(self, results: Sequence[JsonObject]) -> None:
        self._state.core.require_writable()
        staged = deepcopy(self._tables())
        for result in results:
            raw = cast("dict[str, Any]", result)
            parsed = result_from_json(raw)
            problems = validate_result(parsed, max_documents=raw["max_documents"], excerpt_max_chars=20000)
            if problems:
                raise invalid(problems[0])
            qid = parsed.query_id
            existing = staged.results.get(qid)
            if existing is not None:
                if existing == result:
                    continue
                raise Conflict(ErrorCode.IDEMPOTENCY_KEY_REUSED, "research query id already used")
            for doc in raw["documents"]:
                if doc["document_id"] in staged.documents:
                    raise Conflict(ErrorCode.IDEMPOTENCY_KEY_REUSED, "research document id already used")
                staged.documents[doc["document_id"]] = deepcopy(doc)
            staged.results[qid] = deepcopy(result)
        self._state.modules["context_research"] = staged

    def find_cached(
        self, *, workspace_id: WorkspaceId, project_id: ProjectId, cache_key: str, now: datetime
    ) -> JsonObject | None:
        rows = [
            r
            for r in self._tables().results.values()
            if r["workspace_id"] == str(workspace_id)
            and r["project_id"] == str(project_id)
            and r["cache_key"] == cache_key
            and r["status"] in {"ok", "empty"}
            and r["expires_at"] is not None
            and datetime.fromisoformat(str(r["expires_at"])) > now
        ]
        return (
            deepcopy(
                max(rows, key=lambda r: (datetime.fromisoformat(str(r["retrieved_at"])), str(r["query_id"])))
            )
            if rows
            else None
        )

    def get(self, query_id: str) -> JsonObject:
        row = self._tables().results.get(query_id)
        if row is None:
            raise NotFound(ErrorCode.NOT_FOUND, "research query not found")
        return deepcopy(row)

    def documents(self, document_ids: Sequence[str]) -> tuple[ResearchDocument, ...]:
        rows = self._tables().documents
        return tuple(
            document_from_json(cast("dict[str, Any]", deepcopy(rows[key])))
            for key in document_ids
            if key in rows
        )

    def results_for_step(self, step_ref: str) -> tuple[JsonObject, ...]:
        return tuple(
            deepcopy(r)
            for r in sorted(
                self._tables().results.values(),
                key=lambda r: (datetime.fromisoformat(str(r["retrieved_at"])), str(r["query_id"])),
            )
            if r.get("step_ref") == step_ref
        )

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
        if after is not None:
            try:
                UUID(after)
            except ValueError as exc:
                raise invalid("invalid_cursor") from exc
        rows: list[JsonObject] = []
        for result in self._tables().results.values():
            if result["workspace_id"] != str(workspace_id) or result["project_id"] != str(project_id):
                continue
            if query_id is not None and result["query_id"] != query_id:
                continue
            rows.extend(
                doc
                for doc in cast("list[JsonObject]", result["documents"])
                if (after is None or str(doc["document_id"]) > after)
                and (origin_prefix is None or str(doc["origin"]).startswith(origin_prefix))
            )
        rows.sort(key=lambda d: str(d["document_id"]))
        return {
            "items": cast("list[JsonValue]", deepcopy(rows[:limit])),
            "next_after": str(rows[limit - 1]["document_id"]) if len(rows) > limit else None,
        }
