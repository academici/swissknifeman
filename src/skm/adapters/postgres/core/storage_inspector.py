"""Read storage integrity facts in the caller's PostgreSQL transaction."""

import hashlib
import json
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg

from skm.adapters.postgres.errors import translate_pg_error
from skm.adapters.postgres.planning.spec_reader import load_typed_document
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError, NotFound, ValidationFailed
from skm.kernel.ids import RevisionId, ScopeId, WorkspaceId
from skm.kernel.scopes import ScopeKind, ScopeRecord
from skm.modules.planning.domain.canonical import specification_digest
from skm.modules.planning.domain.compile_graph import compile_execution_graph
from skm.modules.planning.domain.specification import from_document
from skm.platform.storage.verify import (
    EvidenceCheck,
    ExpiredStage,
    Finding,
    Level,
    Location,
    ObjectCheck,
    ObjectInventory,
    Reference,
    Target,
    check_scopes,
    checked_digest,
    finding,
    has_cycle,
)

__all__ = ["PostgresStorageInspector"]

# Entity ownership and scope lineage are stored independently.
_OWNERS = """
SELECT 'workspace', id, id, NULL::uuid FROM skm_workspace.workspaces
UNION ALL SELECT 'host', id, NULL, NULL FROM skm_workspace.hosts
UNION ALL SELECT 'project', id, workspace_id, workspace_id FROM skm_workspace.projects
UNION ALL SELECT 'plan', id, workspace_id, project_id FROM skm_planning.plans
UNION ALL SELECT 'run', id, workspace_id, CASE WHEN kind = 'adhoc' THEN project_id ELSE plan_id END
FROM skm_execution.runs
"""
_REVISIONS = """
SELECT r.id, r.workspace_id, r.content_digest, p.document, p.document_digest
FROM skm_planning.plan_revisions r
LEFT JOIN skm_planning.revision_payloads p
  ON (p.workspace_id, p.plan_id, p.revision_id) = (r.workspace_id, r.plan_id, r.id)
"""
_EDGES = """
SELECT revision_id, dependent_entity_id, prerequisite_entity_id FROM skm_planning.dependency_edges
ORDER BY revision_id
"""
_LIVE_LEASES = """
SELECT a.id, a.workspace_id, a.attempt_id
FROM skm_execution.assignment_leases l
JOIN skm_execution.assignments a ON (a.workspace_id, a.id) = (l.workspace_id, l.assignment_id)
LEFT JOIN skm_execution.attempts t ON (t.workspace_id, t.id) = (a.workspace_id, a.attempt_id)
WHERE l.expires_at > %s AND
 (a.state IN ('completed', 'expired', 'cancelled')
  OR t.state IN ('completed', 'ownership_lost', 'abandoned'))
"""
_STAGED_EXPIRED = """
SELECT s.id, s.workspace_id, s.content_digest, s.backend_id, s.storage_key
FROM skm_artifacts.staged_blobs s
WHERE s.consumed_at IS NULL AND s.expires_at <= %(now)s
  AND NOT EXISTS (SELECT 1 FROM skm_artifacts.blobs b
                  WHERE (b.workspace_id, b.content_digest) = (s.workspace_id, s.content_digest))
  AND NOT EXISTS (SELECT 1 FROM skm_artifacts.blob_locations b
                  WHERE (b.backend_id, b.storage_key) = (s.backend_id, s.storage_key))
  AND NOT EXISTS (SELECT 1 FROM skm_artifacts.staged_blobs l
                  WHERE (l.backend_id, l.storage_key) = (s.backend_id, s.storage_key)
                    AND l.consumed_at IS NULL AND l.expires_at > %(now)s)
"""
_EFFECTS = """
SELECT e.id, e.workspace_id FROM skm_execution.external_effects e
WHERE e.state = 'outcome_unknown' OR (e.state = 'executing' AND NOT EXISTS (
    SELECT 1 FROM skm_execution.assignments a JOIN skm_execution.assignment_leases l
      ON (l.workspace_id, l.assignment_id) = (a.workspace_id, a.id)
    JOIN skm_execution.attempts t ON (t.workspace_id, t.id) = (a.workspace_id, a.attempt_id)
    WHERE (a.workspace_id, a.attempt_id) = (e.workspace_id, e.attempt_id)
      AND a.state = 'leased' AND a.last_fencing_token = l.fencing_token AND l.expires_at > %s
      AND t.state NOT IN ('completed', 'ownership_lost', 'abandoned')
))
"""
_CONTEXT_PROMPTS = """
SELECT m.id, m.workspace_id, m.prompt_file_version_id
FROM skm_context.context_manifests m
LEFT JOIN skm_artifacts.file_versions v ON (v.workspace_id, v.id) = (m.workspace_id, m.prompt_file_version_id)
LEFT JOIN skm_artifacts.blobs b ON (b.workspace_id, b.id) = (v.workspace_id, v.blob_id)
WHERE m.state = 'final' AND m.prompt_digest IS DISTINCT FROM ('sha256:' || b.content_digest)
"""
_LOCATIONS = """
SELECT l.blob_id, l.workspace_id, l.backend_id, l.storage_key, l.storage_version, b.content_digest, v.id
FROM skm_artifacts.blob_locations l
LEFT JOIN skm_artifacts.blobs b ON (b.workspace_id, b.id) = (l.workspace_id, l.blob_id)
LEFT JOIN skm_artifacts.file_versions v ON (v.workspace_id, v.blob_id) = (l.workspace_id, l.blob_id)
"""
_STAGED_LOCATIONS = """
SELECT id, workspace_id, backend_id, storage_key, content_digest
FROM skm_artifacts.staged_blobs WHERE consumed_at IS NULL
"""
_ACCEPTED = """
WITH accepted AS (
    SELECT workspace_id, attempt_id, output_id, basis
    FROM skm_execution.acceptance_decisions WHERE decision = 'accepted' AND attempt_id IS NOT NULL
    UNION ALL
    SELECT workspace_id, id, current_output_id, '{}'::jsonb FROM skm_execution.attempts
    WHERE end_reason = 'ACCEPTED'
    UNION ALL
    SELECT workspace_id, accepted_attempt_id, accepted_output_id, '{}'::jsonb
    FROM skm_execution.run_tasks WHERE accepted_attempt_id IS NOT NULL
), wanted_checks AS (
    SELECT a.*, ref.id AS ref_id FROM accepted a
    CROSS JOIN LATERAL jsonb_array_elements_text(
        CASE WHEN jsonb_typeof(a.basis -> 'check_execution_ids') = 'array'
             THEN a.basis -> 'check_execution_ids' ELSE '[]'::jsonb END
    ) ref(id)
), missing AS (
    SELECT a.workspace_id, a.attempt_id, 'attempt' AS kind, a.attempt_id::text AS ref_id
    FROM accepted a LEFT JOIN skm_execution.attempts t
      ON (t.workspace_id, t.id) = (a.workspace_id, a.attempt_id)
    WHERE t.id IS NULL
    UNION
    SELECT a.workspace_id, a.attempt_id, 'attempt_output', a.output_id::text
    FROM accepted a LEFT JOIN skm_execution.attempt_outputs o
      ON (o.workspace_id, o.attempt_id, o.id) = (a.workspace_id, a.attempt_id, a.output_id)
    WHERE a.output_id IS NOT NULL AND o.id IS NULL
    UNION
    SELECT a.workspace_id, a.attempt_id, 'check_execution', a.ref_id
    FROM wanted_checks a LEFT JOIN skm_execution.check_executions c
      ON (c.workspace_id, c.id::text) = (a.workspace_id, a.ref_id)
    WHERE c.id IS NULL
    UNION
    SELECT a.workspace_id, a.attempt_id, 'review', a.basis ->> 'review_id'
    FROM accepted a LEFT JOIN skm_execution.reviews r
      ON (r.workspace_id, r.id::text) = (a.workspace_id, a.basis ->> 'review_id')
    WHERE a.basis ->> 'review_id' IS NOT NULL AND r.id IS NULL
), refs AS (
    SELECT a.workspace_id, a.attempt_id, b.file_version_id FROM accepted a
    JOIN skm_execution.attempt_file_bindings b USING (workspace_id, attempt_id)
    UNION
    SELECT a.workspace_id, a.attempt_id, b.file_version_id FROM accepted a
    JOIN skm_execution.output_file_bindings b USING (workspace_id, attempt_id, output_id)
    UNION
    SELECT a.workspace_id, a.attempt_id, o.patch_file_version_id FROM accepted a
    JOIN skm_execution.attempt_outputs o
      ON (o.workspace_id, o.attempt_id, o.id) = (a.workspace_id, a.attempt_id, a.output_id)
    WHERE o.patch_file_version_id IS NOT NULL
    UNION
    SELECT a.workspace_id, a.attempt_id, b.file_version_id FROM accepted a
    JOIN skm_execution.check_executions c USING (workspace_id, attempt_id, output_id)
    JOIN skm_execution.check_evidence_bindings b
      ON (b.workspace_id, b.check_execution_id) = (c.workspace_id, c.id)
    UNION
    SELECT a.workspace_id, a.attempt_id, b.file_version_id FROM wanted_checks a
    JOIN skm_execution.check_evidence_bindings b ON (b.workspace_id, b.check_execution_id::text) =
        (a.workspace_id, a.ref_id)
    UNION
    SELECT a.workspace_id, a.attempt_id, b.file_version_id FROM accepted a
    JOIN skm_execution.reviews r ON r.workspace_id = a.workspace_id AND
     ((r.attempt_id, r.output_id) = (a.attempt_id, a.output_id) OR r.id::text = a.basis ->> 'review_id')
    JOIN skm_execution.review_evidence_bindings b ON (b.workspace_id, b.review_id) = (r.workspace_id, r.id)
)
SELECT workspace_id, attempt_id, kind, ref_id, NULL::text, NULL::text, NULL::text FROM missing
UNION ALL
SELECT r.workspace_id, r.attempt_id, 'file_version', r.file_version_id::text,
       l.backend_id, l.storage_key, l.storage_version
FROM refs r
LEFT JOIN skm_artifacts.file_versions v ON (v.workspace_id, v.id) = (r.workspace_id, r.file_version_id)
LEFT JOIN skm_artifacts.blobs b ON (b.workspace_id, b.id) = (v.workspace_id, v.blob_id)
LEFT JOIN skm_artifacts.blob_locations l
  ON (l.workspace_id, l.blob_id) = (b.workspace_id, b.id) AND l.state = 'present'
"""
# Owner identities are global UUIDs. Compare workspace ownership independently of the composite
# foreign key, since an integrity check must still find corruption introduced outside normal writes.
_CROSS_LINKS = """
WITH bindings(kind, owner_id, workspace_id, file_version_id) AS (
    SELECT 'attempt', a.id, a.workspace_id, b.file_version_id
    FROM skm_execution.attempt_file_bindings b JOIN skm_execution.attempts a ON a.id = b.attempt_id
    UNION ALL
    SELECT 'attempt_output', o.id, o.workspace_id, b.file_version_id
    FROM skm_execution.output_file_bindings b JOIN skm_execution.attempt_outputs o ON o.id = b.output_id
    UNION ALL
    SELECT 'check_execution', c.id, c.workspace_id, b.file_version_id
    FROM skm_execution.check_evidence_bindings b
    JOIN skm_execution.check_executions c ON c.id = b.check_execution_id
    UNION ALL
    SELECT 'review', r.id, r.workspace_id, b.file_version_id
    FROM skm_execution.review_evidence_bindings b JOIN skm_execution.reviews r ON r.id = b.review_id
)
SELECT 'files', f.id, f.workspace_id, 'projects', p.id
FROM skm_artifacts.files f JOIN skm_workspace.projects p ON f.project_id = p.id
WHERE f.workspace_id <> p.workspace_id
UNION ALL
SELECT 'files', f.id, f.workspace_id, 'file_versions', v.id
FROM skm_artifacts.files f JOIN skm_artifacts.file_versions v ON f.current_version_id = v.id
WHERE f.workspace_id <> v.workspace_id
UNION ALL
SELECT 'file_versions', v.id, v.workspace_id, 'files', f.id
FROM skm_artifacts.file_versions v JOIN skm_artifacts.files f ON v.file_id = f.id
WHERE v.workspace_id <> f.workspace_id
UNION ALL
SELECT 'file_versions', v.id, v.workspace_id, 'blobs', b.id
FROM skm_artifacts.file_versions v JOIN skm_artifacts.blobs b ON v.blob_id = b.id
WHERE v.workspace_id <> b.workspace_id
UNION ALL
SELECT 'plans', p.id, p.workspace_id, 'projects', j.id
FROM skm_planning.plans p JOIN skm_workspace.projects j ON p.project_id = j.id
WHERE p.workspace_id <> j.workspace_id
UNION ALL
SELECT 'plan_revisions', r.id, r.workspace_id, 'plans', p.id
FROM skm_planning.plan_revisions r JOIN skm_planning.plans p ON r.plan_id = p.id
WHERE r.workspace_id <> p.workspace_id
UNION ALL
SELECT 'revision', r.revision_id, r.workspace_id, 'file_version', v.id
FROM skm_planning.revision_file_bindings r JOIN skm_artifacts.file_versions v ON r.file_version_id = v.id
WHERE r.workspace_id <> v.workspace_id
UNION ALL
SELECT 'runs', r.id, r.workspace_id, 'projects', p.id
FROM skm_execution.runs r JOIN skm_workspace.projects p ON r.project_id = p.id
WHERE r.workspace_id <> p.workspace_id
UNION ALL
SELECT 'runs', r.id, r.workspace_id, 'plans', p.id
FROM skm_execution.runs r JOIN skm_planning.plans p ON r.plan_id = p.id
WHERE r.workspace_id <> p.workspace_id
UNION ALL
SELECT 'runs', r.id, r.workspace_id, 'plan_revisions', p.id
FROM skm_execution.runs r JOIN skm_planning.plan_revisions p ON r.revision_id = p.id
WHERE r.workspace_id <> p.workspace_id
UNION ALL
SELECT 'run_tasks', t.id, t.workspace_id, 'runs', r.id
FROM skm_execution.run_tasks t JOIN skm_execution.runs r ON t.run_id = r.id
WHERE t.workspace_id <> r.workspace_id
UNION ALL
SELECT 'attempts', a.id, a.workspace_id, 'runs', r.id
FROM skm_execution.attempts a JOIN skm_execution.runs r ON a.run_id = r.id
WHERE a.workspace_id <> r.workspace_id
UNION ALL
SELECT 'attempts', a.id, a.workspace_id, 'run_tasks', t.id
FROM skm_execution.attempts a JOIN skm_execution.run_tasks t ON a.task_id = t.id
WHERE a.workspace_id <> t.workspace_id
UNION ALL
SELECT 'assignments', a.id, a.workspace_id, 'runs', r.id
FROM skm_execution.assignments a JOIN skm_execution.runs r ON a.run_id = r.id
WHERE a.workspace_id <> r.workspace_id
UNION ALL
SELECT 'assignments', a.id, a.workspace_id, 'attempts', t.id
FROM skm_execution.assignments a JOIN skm_execution.attempts t ON a.attempt_id = t.id
WHERE a.workspace_id <> t.workspace_id
UNION ALL
SELECT 'checkout_bindings', c.id, c.workspace_id, 'repositories', r.id
FROM skm_workspace.checkout_bindings c JOIN skm_workspace.repositories r ON c.repository_id = r.id
WHERE c.workspace_id <> r.workspace_id
UNION ALL
SELECT 'scope', s.id, s.workspace_id, 'scope', p.id
FROM skm_core.scopes s JOIN skm_core.scopes p ON s.parent_id = p.id
WHERE s.workspace_id <> p.workspace_id
UNION ALL
SELECT b.kind, b.owner_id, b.workspace_id, 'file_version', v.id
FROM bindings b JOIN skm_artifacts.file_versions v ON v.id = b.file_version_id
WHERE b.workspace_id <> v.workspace_id
"""


class PostgresStorageInspector:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def _scopes(self) -> Iterable[Finding]:
        rows = _rows(
            lambda: self._conn.execute(
                "SELECT id, kind, parent_id, workspace_id, created_at FROM skm_core.scopes"
            )
        )
        scopes = [
            ScopeRecord(ScopeId(i), ScopeKind(k), ScopeId(p) if p else None, WorkspaceId(w) if w else None, t)
            for i, k, p, w, t in rows
        ]
        instance = next((str(row.id) for row in scopes if row.kind is ScopeKind.INSTANCE), None)
        return check_scopes(
            scopes,
            (
                (Target(k, str(i), w), str(p) if p else instance)
                for k, i, w, p in _rows(lambda: self._conn.execute(_OWNERS))
            ),
        )

    def _provenance(self, *, cross_workspace: bool) -> Iterator[Finding]:
        for lesson, workspace, candidate, candidate_workspace in _rows(
            lambda: self._conn.execute("""
            SELECT l.id, l.workspace_id, l.candidate_id, c.workspace_id FROM skm_knowledge.lessons l
            LEFT JOIN skm_learning.candidates c ON c.id = l.candidate_id
            WHERE c.workspace_id IS DISTINCT FROM l.workspace_id
        """)
        ):
            if (candidate_workspace is not None) == cross_workspace:
                code = "CROSS_WORKSPACE_LINK" if cross_workspace else "DANGLING_REFERENCE"
                yield finding(code, "lesson", lesson, workspace, Reference("candidate", str(candidate)))

    def _revisions(self, level: Level) -> Iterator[Finding]:
        for revision, workspace, expected, document, payload_digest in _rows(
            lambda: self._conn.execute(_REVISIONS)
        ):
            digest = checked_digest(specification_digest, document)
            if level == "cryptographic":
                if digest != expected or payload_digest != expected:
                    yield finding("PAYLOAD_DIGEST_MISMATCH", "revision", revision, workspace)
                continue

            try:
                typed = load_typed_document(self._conn, RevisionId(revision))
                spec, _ = from_document(typed)
            except InternalError as error:
                # The typed reader uses this diagnostic for corrupt stored rows, including missing pins.
                if not error.message.startswith("corrupt skm_planning."):
                    raise
                yield finding("TYPED_SPEC_MISMATCH", "revision", revision, workspace)
                continue
            except (NotFound, AttributeError, KeyError, ValueError, TypeError, ValidationFailed):
                yield finding("TYPED_SPEC_MISMATCH", "revision", revision, workspace)
                continue
            if digest is None or checked_digest(specification_digest, typed) != digest:
                yield finding("TYPED_SPEC_MISMATCH", "revision", revision, workspace)
            try:
                compile_execution_graph(spec, RevisionId(revision))
            except ValidationFailed as error:
                if error.code == ErrorCode.DEPENDENCY_CYCLE:
                    yield finding("DEPENDENCY_CYCLE", "revision", revision, workspace)

    def _cycles(self) -> Iterator[Finding]:
        edges: dict[UUID, list[tuple[str, str]]] = defaultdict(list)
        for revision, dependent, prerequisite in _rows(lambda: self._conn.execute(_EDGES)):
            edges[revision].append((str(dependent), str(prerequisite)))
        for revision, workspace in _rows(
            lambda: self._conn.execute("SELECT id, workspace_id FROM skm_planning.plan_revisions")
        ):
            if edges.get(revision) and has_cycle(edges[revision]):
                yield finding("DEPENDENCY_CYCLE", "revision", revision, workspace)

    def _cross_links(self) -> Iterator[Finding]:
        yield from self._provenance(cross_workspace=True)
        for kind, ident, workspace, parent_kind, parent in _rows(lambda: self._conn.execute(_CROSS_LINKS)):
            yield finding("CROSS_WORKSPACE_LINK", kind, ident, workspace, Reference(parent_kind, str(parent)))

    def inspect(self, level: Level, *, now: datetime, recovery_before: datetime) -> Iterator[Finding]:
        match level:
            case "relational":
                yield from self._scopes()
                yield from self._provenance(cross_workspace=False)
            case "specification":
                yield from self._revisions(level)
                yield from self._cycles()
            case "execution":
                for ident, workspace, attempt in _rows(lambda: self._conn.execute(_LIVE_LEASES, (now,))):
                    yield finding(
                        "LEASE_INCONSISTENT",
                        "assignment",
                        ident,
                        workspace,
                        Reference("attempt", str(attempt)),
                    )
            case "files":
                for stage in self.expired_staging(now):
                    yield finding("STAGED_EXPIRED", "staged_blob", stage.id, stage.workspace_id)
            case "cryptographic":
                yield from self._revisions(level)
                yield from self._manifest_digests()
            case "authorization":
                yield from self._cross_links()
            case "recovery":
                yield from self._recovery(now, recovery_before)

    def _manifest_digests(self) -> Iterator[Finding]:
        for ident, workspace, manifest, expected in _rows(
            lambda: self._conn.execute("""
            SELECT id, workspace_id, manifest, manifest_digest FROM skm_execution.attempt_outputs
        """)
        ):
            value = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            if "sha256:" + hashlib.sha256(value.encode()).hexdigest() != expected:
                yield finding("PAYLOAD_DIGEST_MISMATCH", "attempt_output", ident, workspace)
        for ident, workspace, version in _rows(lambda: self._conn.execute(_CONTEXT_PROMPTS)):
            yield finding(
                "PAYLOAD_DIGEST_MISMATCH",
                "context_manifest",
                ident,
                workspace,
                Reference("file_version", str(version)),
            )

    def _recovery(self, now: datetime, before: datetime) -> Iterator[Finding]:
        for ident, workspace, event in _rows(
            lambda: self._conn.execute("""
            SELECT o.id, e.workspace_id, o.event_id FROM skm_core.outbox o
            LEFT JOIN skm_core.domain_events e ON e.id = o.event_id WHERE o.state = 'dead'
        """)
        ):
            yield finding("OUTBOX_DEAD", "outbox", ident, workspace, Reference("event", str(event)))
        for ident, workspace in _rows(lambda: self._conn.execute(_EFFECTS, (now,))):
            yield finding("EFFECT_OUTCOME_UNKNOWN", "external_effect", ident, workspace)
        for ident, workspace in _rows(
            lambda: self._conn.execute(
                """
            SELECT id, workspace_id FROM skm_execution.run_recoveries WHERE finished_at IS NULL AND at < %s
        """,
                (before,),
            )
        ):
            yield finding("RECOVERY_STALLED", "run_recovery", ident, workspace)

    def expired_staging(self, now: datetime) -> Iterator[ExpiredStage]:
        for ident, workspace, digest, backend, key in _rows(
            lambda: self._conn.execute(_STAGED_EXPIRED, {"now": now})
        ):
            yield ExpiredStage(ident, workspace, f"sha256:{digest}", Location(backend, key))

    def has_blob(self, workspace_id: UUID, digest: str) -> bool:
        return bool(
            _rows(
                lambda: self._conn.execute(
                    """
            SELECT 1 FROM skm_artifacts.blobs WHERE workspace_id = %s AND content_digest = %s LIMIT 1
            """,
                    (workspace_id, digest.removeprefix("sha256:")),
                )
            )
        )

    def inventory(self) -> ObjectInventory:
        refs: dict[tuple[Target, Location, str | None], set[Reference]] = defaultdict(set)
        for ident, workspace, backend, key, version, digest, file_version in _rows(
            lambda: self._conn.execute(_LOCATIONS)
        ):
            record = (
                Target("blob", str(ident), workspace),
                Location(backend, key, version),
                f"sha256:{digest}" if digest is not None else None,
            )
            references = refs[record]
            if file_version is not None:
                references.add(Reference("file_version", str(file_version)))
        stages = _rows(lambda: self._conn.execute(_STAGED_LOCATIONS))
        return ObjectInventory(
            tuple(
                row[0] for row in _rows(lambda: self._conn.execute("SELECT id FROM skm_workspace.workspaces"))
            ),
            (
                *(
                    ObjectCheck(*identity, tuple(sorted(refs, key=lambda ref: ref.id)))
                    for identity, refs in refs.items()
                ),
                *(
                    ObjectCheck(
                        Target("staged_blob", str(ident), workspace),
                        Location(backend, key),
                        f"sha256:{digest}",
                    )
                    for ident, workspace, backend, key, digest in stages
                ),
            ),
        )

    def evidence(self) -> Iterable[EvidenceCheck]:
        groups: dict[tuple[Target, Reference], set[Location]] = defaultdict(set)
        for workspace, attempt, kind, ident, backend, key, version in _rows(
            lambda: self._conn.execute(_ACCEPTED)
        ):
            locations = groups[Target("attempt", str(attempt), workspace), Reference(kind, ident)]
            if backend is not None:
                locations.add(Location(backend, key, version))
        return (
            EvidenceCheck(target, reference, tuple(locations))
            for (target, reference), locations in groups.items()
        )


def _rows(execute: Callable[[], psycopg.Cursor[tuple[Any, ...]]]) -> list[tuple[Any, ...]]:
    try:
        return execute().fetchall()
    except psycopg.Error as error:
        raise translate_pg_error(error) from error
