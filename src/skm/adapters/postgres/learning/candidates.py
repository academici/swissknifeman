"""PostgreSQL candidates, versioned snapshots and bounded reads."""

from dataclasses import asdict, replace
from datetime import datetime
from typing import Any, Final

import psycopg
from psycopg.types.json import Jsonb

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, NotFound, ValidationFailed
from skm.kernel.ids import ProjectId, ScopeId, WorkspaceId
from skm.kernel.pagination import Cursor, Page
from skm.modules.knowledge.ports import page_of
from skm.modules.learning.domain.candidate import Candidate, CandidateId, CandidateState
from skm.modules.learning.domain.contracts import CandidateRef
from skm.modules.learning.domain.review import proposed_update, review_status

from .mapping import Row, candidate_from_row, paging, proposal_view, rows, run
from .repositories import PostgresCandidateProposalRepository, PostgresCandidateReviewRepository

__all__ = ["PostgresCandidateRepository"]

_GET: Final = "SELECT * FROM skm_learning.candidates WHERE id = %s"
_EXACT: Final = "SELECT * FROM skm_learning.candidates WHERE scope_id = %s AND fingerprint = %s"
_KEY: Final = """
SELECT coalesce(max(substring(display_key FROM 4)::numeric), 0) + 1 AS number
FROM skm_learning.candidates WHERE project_id = %s
"""
_SHORTLIST: Final = """
SELECT id::text AS candidate_id, kind, trigger, action, fingerprint, state
FROM skm_learning.candidates WHERE scope_id = %s ORDER BY updated_at DESC, id DESC LIMIT %s
"""
_LIST: Final = """
SELECT * FROM skm_learning.candidates WHERE scope_id = ANY(%s)
AND (%s OR state = ANY(%s))
AND (%s::timestamptz IS NULL OR (updated_at, id) < (%s, %s))
ORDER BY updated_at DESC, id DESC LIMIT %s
"""
_IDS: Final = """
SELECT id FROM skm_learning.candidates WHERE workspace_id = %s AND (%s::uuid IS NULL OR id > %s)
ORDER BY id LIMIT %s
"""
_ADD: Final = """
INSERT INTO skm_learning.candidates (
  id, workspace_id, project_id, scope_id, display_key, detector, pathology_code, kind, trigger, action,
  review_hint, meta, evidence, fingerprint, state, s_total, n_total, known_outcome_total,
  unknown_outcome_total,
  independent_known_total, independent_success_total, exposed_total, exposure_unknown_total,
  tests_total, tests_passed, days_since, support_score, freshness, stale, confidence, confidence_tier,
  curated_ready, conflicts_with_id, lesson_id, recomputed_at, row_version, created_at, updated_at
) VALUES (
  %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
  %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now(),now()
)
"""
_SAVE: Final = """
UPDATE skm_learning.candidates SET
  display_key = %s, detector = %s, pathology_code = %s, kind = %s, trigger = %s, action = %s,
  review_hint = %s, meta = %s, evidence = %s, fingerprint = %s, state = %s, s_total = %s, n_total = %s,
  known_outcome_total = %s, unknown_outcome_total = %s, independent_known_total = %s,
  independent_success_total = %s, exposed_total = %s, exposure_unknown_total = %s, tests_total = %s,
  tests_passed = %s, days_since = %s, support_score = %s, freshness = %s, stale = %s, confidence = %s,
  confidence_tier = %s, curated_ready = %s, conflicts_with_id = %s, lesson_id = %s, recomputed_at = %s,
  row_version = row_version + 1, updated_at = greatest(updated_at, clock_timestamp())
WHERE id = %s AND workspace_id = %s AND project_id = %s AND scope_id = %s AND row_version = %s
"""


def _values(c: Candidate) -> tuple[Any, ...]:
    return (
        c.display_key,
        c.detector,
        c.pathology_code,
        c.kind,
        c.trigger,
        c.action,
        c.review_hint,
        Jsonb(dict(c.meta)),
        Jsonb([asdict(e) for e in c.evidence]),
        c.fingerprint,
        c.state,
        c.s_total,
        c.n_total,
        c.known_outcome_total,
        c.unknown_outcome_total,
        c.independent_known_total,
        c.independent_success_total,
        c.exposed_total,
        c.exposure_unknown_total,
        c.tests_total,
        c.tests_passed,
        c.days_since,
        c.support_score,
        c.freshness,
        c.stale,
        c.confidence,
        c.confidence_tier,
        c.curated_ready,
        c.conflicts_with_id,
        c.lesson_id,
        c.recomputed_at,
    )


class PostgresCandidateRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn
        self._reviews = PostgresCandidateReviewRepository(conn)
        self._proposals = PostgresCandidateProposalRepository(conn)

    def _project(self, row: Row) -> Candidate:
        candidate = candidate_from_row(row)
        pending = proposed_update(
            self._proposals.for_candidate(candidate.id), self._reviews.for_proposals(candidate.id)
        )
        return replace(
            candidate,
            proposed_update=proposal_view(pending) if pending is not None else None,
            review_status=review_status(self._reviews.for_candidate(candidate.id)),
        )

    def _get(self, candidate_id: CandidateId) -> Row:
        found = rows(lambda: self._conn.execute(_GET, (candidate_id,)))
        if not found:
            raise NotFound(ErrorCode.NOT_FOUND, "Candidate not found")
        return found[0]

    def add(self, c: Candidate) -> None:
        params = (c.id, c.workspace_id, c.project_id, c.scope_id, *_values(c), c.row_version)
        run(lambda: self._conn.execute(_ADD, params))

    def get(self, candidate_id: CandidateId) -> Candidate:
        return self._project(self._get(candidate_id))

    def updated_at(self, candidate_id: CandidateId) -> datetime:
        return self._get(candidate_id)["updated_at"]

    def next_display_key(self, project_id: ProjectId) -> str:
        number = rows(lambda: self._conn.execute(_KEY, (project_id,)))[0]["number"]
        return f"LC-{number}"

    def save(self, c: Candidate, *, expected_version: int) -> None:
        identity = (c.workspace_id, c.project_id, c.scope_id)
        params = (*_values(c), c.id, *identity, expected_version)
        if run(lambda: self._conn.execute(_SAVE, params).rowcount) == 1:
            return
        stored = self._get(c.id)
        if stored["row_version"] != expected_version:
            raise Conflict(ErrorCode.VERSION_CONFLICT, "Candidate version changed")
        if identity != (stored["workspace_id"], stored["project_id"], stored["scope_id"]):
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Candidate scope cannot change")
        raise Conflict(ErrorCode.VERSION_CONFLICT, "Candidate version changed")

    def by_fingerprint(self, scope_id: ScopeId, fingerprint: str) -> Candidate | None:
        found = rows(lambda: self._conn.execute(_EXACT, (scope_id, fingerprint)))
        return self._project(found[0]) if found else None

    def shortlist_pool(self, scope_id: ScopeId, *, limit: int) -> tuple[CandidateRef, ...]:
        return tuple(rows(lambda: self._conn.execute(_SHORTLIST, (scope_id, max(0, min(limit, 2000))))))

    def list(
        self,
        scope_ids: tuple[ScopeId, ...],
        *,
        states: frozenset[CandidateState],
        after: Cursor | None,
        limit: int,
    ) -> Page[Candidate]:
        key, when, row_id = paging(
            after, limit, {"scopes": sorted(map(str, scope_ids)), "states": sorted(states)}
        )
        found = rows(
            lambda: self._conn.execute(
                _LIST, (list(scope_ids), not states, list(states), when, when, row_id, limit + 1)
            )
        )
        page = page_of(found, limit, key, lambda r: (r["updated_at"], r["id"]))
        return Page(tuple(self._project(row) for row in page.items), page.next)

    def ids_for_recompute(
        self, workspace_id: WorkspaceId, *, after: CandidateId | None, limit: int
    ) -> tuple[CandidateId, ...]:
        return tuple(
            row["id"] for row in rows(lambda: self._conn.execute(_IDS, (workspace_id, after, after, limit)))
        )
