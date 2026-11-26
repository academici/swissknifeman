"""PostgreSQL adapters for ``IntegrationSlotRepository`` and ``ReviewRequestRepository``."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row

from skm.adapters.postgres.execution.codecs import review_request_from_row, slot_from_row
from skm.adapters.postgres.execution.codecs_core import as_uuid
from skm.adapters.postgres.execution.mapping import damaged, run
from skm.adapters.postgres.jsonb import require_aware
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, PreconditionFailed
from skm.kernel.ids import HostId, RepositoryId, RunId
from skm.kernel.json_types import JsonObject
from skm.modules.execution.domain.review_request import CommitReviewTarget
from skm.modules.execution.domain.stored_payloads import (
    canonical_bytes,
    invalid_ref,
    not_found,
    schema_invalid,
)

if TYPE_CHECKING:
    from skm.kernel.ids import AttemptId
    from skm.modules.execution.domain.ids import IntegrationSlotId, ReviewRequestId
    from skm.modules.execution.domain.integration import IntegrationSlot
    from skm.modules.execution.domain.review_request import ReviewRequest

__all__ = [
    "PostgresIntegrationSlotRepository",
    "PostgresReviewRequestRepository",
]

_BRANCH_RE: Final = re.compile(r"^[A-Za-z0-9._/-]{1,200}$")
_ATTEMPT_RUN_WS: Final = "SELECT run_id, workspace_id FROM skm_execution.attempts WHERE id = %s"
_REPO_WS: Final = "SELECT workspace_id FROM skm_workspace.repositories WHERE id = %s"
_RUN_HOST_PIN: Final = """
SELECT host_id FROM skm_execution.run_integration_hosts WHERE run_id = %s AND repository_id = %s
"""
_LOCK_SLOT_BY_TARGET: Final = """
SELECT * FROM skm_execution.integration_slots
 WHERE repository_id = %s AND target_branch = %s
   FOR UPDATE
"""
_SELECT_SLOT_BY_TARGET: Final = """
SELECT * FROM skm_execution.integration_slots
 WHERE repository_id = %s AND target_branch = %s
"""
_INSERT_ACQUIRED_SLOT: Final = """
INSERT INTO skm_execution.integration_slots (
    id, workspace_id, repository_id, target_branch, writer_host_id,
    holder_attempt_id, fencing_token, expires_at, row_version
) VALUES (%s, %s, %s, %s, %s, %s, 1, %s, 1)
RETURNING *
"""
_TAKE_SLOT: Final = """
UPDATE skm_execution.integration_slots
   SET holder_attempt_id = %s, fencing_token = fencing_token + 1,
       expires_at = %s, row_version = row_version + 1
 WHERE id = %s
RETURNING *
"""
_PIN_TARGET_SLOT: Final = """
INSERT INTO skm_execution.integration_slots (
    id, workspace_id, repository_id, target_branch, writer_host_id,
    holder_attempt_id, fencing_token, expires_at, row_version
) VALUES (%s, %s, %s, %s, %s, NULL, 0, NULL, 1)
ON CONFLICT (repository_id, target_branch) DO NOTHING
RETURNING writer_host_id
"""
_SELECT_TARGET_HOST: Final = """
SELECT writer_host_id FROM skm_execution.integration_slots
 WHERE repository_id = %s AND target_branch = %s
"""
_SELECT_SLOTS_BY_REPOS: Final = """
SELECT repository_id, target_branch, writer_host_id
  FROM skm_execution.integration_slots
 WHERE repository_id = ANY(%s::uuid[])
"""
_EXTEND_SLOTS: Final = """
UPDATE skm_execution.integration_slots
   SET expires_at = %s, row_version = row_version + 1
 WHERE holder_attempt_id = %s
   AND expires_at IS NOT NULL
   AND expires_at > clock_timestamp()
"""
_LOCK_SLOT_BY_ID: Final = "SELECT * FROM skm_execution.integration_slots WHERE id = %s FOR UPDATE"
_RELEASE_SLOT: Final = """
UPDATE skm_execution.integration_slots
   SET holder_attempt_id = NULL, expires_at = NULL, row_version = row_version + 1
 WHERE id = %s
"""
_RELEASE_FOR_ATTEMPT: Final = """
UPDATE skm_execution.integration_slots
   SET holder_attempt_id = NULL, expires_at = NULL, row_version = row_version + 1
 WHERE holder_attempt_id = %s
"""
_RUN_WS: Final = "SELECT workspace_id, review_request_id FROM skm_execution.runs WHERE id = %s"
_PIN_RUN_HOST: Final = """
INSERT INTO skm_execution.run_integration_hosts (run_id, workspace_id, repository_id, host_id, pinned_at)
VALUES (%s, %s, %s, %s, %s)
ON CONFLICT (run_id, repository_id) DO NOTHING
"""
_HOSTS_FOR_RUN: Final = """
SELECT repository_id, host_id FROM skm_execution.run_integration_hosts WHERE run_id = %s
"""

_INSERT_REVIEW_REQUEST: Final = """
INSERT INTO skm_execution.review_requests (
    id, workspace_id, project_id, mount, repository_id, target_kind,
    base_commit, head_commit, patch_file_version_id, target_digest,
    profile_key, reason, requested_by, plan_id, revision_id, created_at
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""
_GET_REVIEW_REQUEST: Final = "SELECT * FROM skm_execution.review_requests WHERE id = %s"


def _validate_branch(branch: str) -> None:
    if not _BRANCH_RE.match(branch) or ".." in branch:
        raise schema_invalid("invalid target_branch", field="target_branch")


# A run's reviews are reached through its tasks: reviews are indexed by task, not by run.
_RUN_FOR_RECEIPT: Final = """
SELECT r.id FROM skm_execution.runs r
JOIN skm_execution.review_requests q ON q.id = r.review_request_id
LEFT JOIN LATERAL (
    SELECT o.tree_digest
    FROM skm_execution.attempt_outputs o
    JOIN skm_execution.attempts a ON a.id = o.attempt_id
    WHERE a.run_id = r.id AND (
        NOT EXISTS (SELECT 1 FROM skm_execution.run_tasks t
                      JOIN skm_execution.reviews v ON v.task_id = t.id
                     WHERE t.run_id = r.id)
        OR o.id = (SELECT v.output_id FROM skm_execution.run_tasks t
                     JOIN skm_execution.reviews v ON v.task_id = t.id
                    WHERE t.run_id = r.id
                    ORDER BY v.round_no DESC, v.id::text DESC LIMIT 1)
    ) ORDER BY o.sealed_at DESC, o.seq DESC LIMIT 1
) o ON true
WHERE (%s::uuid IS NOT NULL AND q.id = %s::uuid)
   OR (%s::uuid IS NULL AND q.project_id = %s::uuid AND q.mount = %s)
ORDER BY COALESCE(o.tree_digest = %s, false) DESC, r.created_at DESC, r.id::text DESC
LIMIT 1
"""


class PostgresIntegrationSlotRepository:
    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self._conn = conn

    def current(
        self, repository_id: RepositoryId, branch: str, *, for_update: bool = False
    ) -> IntegrationSlot | None:
        with self._conn.cursor(row_factory=dict_row) as cur:
            if for_update:
                cur.execute(_LOCK_SLOT_BY_TARGET, (repository_id, branch))
            else:
                cur.execute(_SELECT_SLOT_BY_TARGET, (repository_id, branch))
            row = cur.fetchone()
            return None if row is None else slot_from_row(row)

    def acquire(
        self,
        repository_id: RepositoryId,
        branch: str,
        attempt_id: AttemptId,
        host_id: HostId,
        now: datetime,
        expires_at: datetime,
    ) -> IntegrationSlot | None:
        _validate_branch(branch)
        now_aw = require_aware(now)
        exp_aw = require_aware(expires_at)
        if exp_aw <= now_aw:
            raise schema_invalid("expires_at must be > now", field="expires_at")

        def _op() -> IntegrationSlot | None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_ATTEMPT_RUN_WS, (attempt_id,))
                arow = cur.fetchone()
                if arow is None:
                    raise invalid_ref("fk_integration_slots__attempts", attempt_id=str(attempt_id))
                run_id = as_uuid(arow["run_id"])
                ws_id = as_uuid(arow["workspace_id"])
                cur.execute(_REPO_WS, (repository_id,))
                rrow = cur.fetchone()
                if rrow is None or as_uuid(rrow["workspace_id"]) != ws_id:
                    raise invalid_ref("fk_integration_slots__repositories", repository_id=str(repository_id))
                cur.execute(_RUN_HOST_PIN, (run_id, repository_id))
                pin = cur.fetchone()
                if pin is not None and HostId(as_uuid(pin["host_id"])) != host_id:
                    raise PreconditionFailed(
                        ErrorCode.INTEGRATION_HOST_MISMATCH,
                        "run integration host differs from candidate host",
                        details={"expected_host_id": str(pin["host_id"]), "host_id": str(host_id)},
                    )
                cur.execute(_LOCK_SLOT_BY_TARGET, (repository_id, branch))
                existing = cur.fetchone()
                if existing is None:
                    cur.execute(
                        _INSERT_ACQUIRED_SLOT,
                        (uuid4(), ws_id, repository_id, branch, host_id, attempt_id, exp_aw),
                    )
                    ins = cur.fetchone()
                    if ins is None:
                        raise damaged("integration_slots")
                    return slot_from_row(ins)
                slot = slot_from_row(existing)
                if slot.writer_host_id != host_id:
                    raise PreconditionFailed(
                        ErrorCode.INTEGRATION_HOST_MISMATCH,
                        "integration slot writer_host_id differs from candidate host",
                        details={"writer_host_id": str(slot.writer_host_id), "host_id": str(host_id)},
                    )
                free_or_same = (
                    slot.holder_attempt_id is None
                    or slot.holder_attempt_id == attempt_id
                    or (slot.expires_at is not None and slot.expires_at <= now_aw)
                )
                if not free_or_same:
                    return None
                cur.execute(_TAKE_SLOT, (attempt_id, exp_aw, slot.id))
                upd = cur.fetchone()
                if upd is None:
                    raise damaged("integration_slots", slot.id)
                return slot_from_row(upd)

        return run(_op)

    def pin_target_host(
        self, repository_id: RepositoryId, branch: str, host_id: HostId, at: datetime
    ) -> tuple[HostId, bool]:
        del at
        _validate_branch(branch)

        def _op() -> tuple[HostId, bool]:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_REPO_WS, (repository_id,))
                rrow = cur.fetchone()
                if rrow is None:
                    raise invalid_ref("fk_integration_slots__repositories", repository_id=str(repository_id))
                cur.execute(
                    _PIN_TARGET_SLOT, (uuid4(), as_uuid(rrow["workspace_id"]), repository_id, branch, host_id)
                )
                ins = cur.fetchone()
                if ins is not None:
                    return HostId(as_uuid(ins["writer_host_id"])), True
                cur.execute(_SELECT_TARGET_HOST, (repository_id, branch))
                ex = cur.fetchone()
                if ex is None:
                    raise damaged("integration_slots")
                return HostId(as_uuid(ex["writer_host_id"])), False

        return run(_op)

    def target_hosts(
        self, targets: Sequence[tuple[RepositoryId, str]]
    ) -> Mapping[tuple[RepositoryId, str], HostId]:
        if not targets:
            return {}
        wanted = {(RepositoryId(UUID(str(rid))), br) for rid, br in targets}
        repo_uuids = list({UUID(str(rid)) for rid, _br in wanted})

        def _op() -> Mapping[tuple[RepositoryId, str], HostId]:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_SELECT_SLOTS_BY_REPOS, (repo_uuids,))
                out: dict[tuple[RepositoryId, str], HostId] = {}
                for r in cur.fetchall():
                    key = (RepositoryId(as_uuid(r["repository_id"])), str(r["target_branch"]))
                    if key in wanted:
                        out[key] = HostId(as_uuid(r["writer_host_id"]))
                return out

        return run(_op)

    def extend(self, attempt_id: AttemptId, expires_at: datetime) -> int:
        exp_aw = require_aware(expires_at)

        def _op() -> int:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_EXTEND_SLOTS, (exp_aw, attempt_id))
                return cur.rowcount

        return run(_op)

    def release(self, slot_id: IntegrationSlotId, attempt_id: AttemptId, fencing_token: int) -> None:
        def _op() -> None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_LOCK_SLOT_BY_ID, (slot_id,))
                row = cur.fetchone()
                if row is None:
                    raise not_found("integration_slot", slot_id)
                slot = slot_from_row(row)
                if slot.holder_attempt_id != attempt_id or slot.fencing_token != fencing_token:
                    raise Conflict(
                        ErrorCode.LEASE_LOST,
                        "integration slot holder or fencing token does not match",
                        details={"slot_id": str(slot_id), "fencing_token": fencing_token},
                    )
                cur.execute(_RELEASE_SLOT, (slot_id,))

        run(_op)

    def release_for_attempt(self, attempt_id: AttemptId) -> int:
        def _op() -> int:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_RELEASE_FOR_ATTEMPT, (attempt_id,))
                return cur.rowcount

        return run(_op)

    def pin_host(self, run_id: RunId, repository_id: RepositoryId, host_id: HostId, at: datetime) -> HostId:
        at_aw = require_aware(at)

        def _op() -> HostId:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_RUN_WS, (run_id,))
                rw = cur.fetchone()
                if rw is None:
                    raise invalid_ref("fk_run_integration_hosts__runs", run_id=str(run_id))
                cur.execute(
                    _PIN_RUN_HOST, (run_id, as_uuid(rw["workspace_id"]), repository_id, host_id, at_aw)
                )
                cur.execute(_RUN_HOST_PIN, (run_id, repository_id))
                pin = cur.fetchone()
                if pin is None:
                    raise damaged("run_integration_hosts", run_id)
                return HostId(as_uuid(pin["host_id"]))

        return run(_op)

    def hosts_for_run(self, run_id: RunId) -> Mapping[RepositoryId, HostId]:
        def _op() -> Mapping[RepositoryId, HostId]:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_HOSTS_FOR_RUN, (run_id,))
                return {
                    RepositoryId(as_uuid(r["repository_id"])): HostId(as_uuid(r["host_id"]))
                    for r in cur.fetchall()
                }

        return run(_op)


class PostgresReviewRequestRepository:
    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self._conn = conn

    def add(self, request: ReviewRequest) -> None:
        if isinstance(request.target, CommitReviewTarget):
            target_kind = "commits"
            head_commit: str | None = request.target.head_commit
            patch_fvid: UUID | None = None
            target_doc: JsonObject = {
                "kind": "commits",
                "base_commit": request.target.base_commit,
                "head_commit": request.target.head_commit,
            }
        else:
            target_kind = "working_tree"
            head_commit = None
            patch_fvid = UUID(str(request.target.patch_file_version_id))
            target_doc = {
                "kind": "working_tree",
                "base_commit": request.target.base_commit,
                "patch_file_version_id": str(request.target.patch_file_version_id),
            }
        digest = "sha256:" + hashlib.sha256(canonical_bytes(target_doc)).hexdigest()

        def _op() -> None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    _INSERT_REVIEW_REQUEST,
                    (
                        request.id,
                        request.workspace_id,
                        request.project_id,
                        request.mount,
                        request.repository_id,
                        target_kind,
                        request.target.base_commit,
                        head_commit,
                        patch_fvid,
                        digest,
                        request.profile_key,
                        request.reason,
                        request.requested_by,
                        request.plan_id,
                        request.revision_id,
                        require_aware(request.created_at),
                    ),
                )

        run(_op)

    def get(self, request_id: ReviewRequestId) -> ReviewRequest:
        def _op() -> ReviewRequest:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_GET_REVIEW_REQUEST, (request_id,))
                row = cur.fetchone()
                if row is None:
                    raise not_found("review_request", request_id)
                return review_request_from_row(row)

        return run(_op)

    def select_run_id(self, selector: JsonObject) -> RunId:
        request_id = UUID(str(selector["request_id"])) if "request_id" in selector else None
        project_id = UUID(str(selector["project_id"])) if "project_id" in selector else None
        mount, tree_digest = selector.get("mount"), selector.get("tree_digest")

        def _op() -> RunId:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    _RUN_FOR_RECEIPT,
                    (request_id, request_id, request_id, project_id, mount, tree_digest),
                )
                row = cur.fetchone()
                if row is None:
                    raise not_found("review_receipt", request_id or project_id)
                return RunId(as_uuid(row["id"]))

        return run(_op)

    def for_run(self, run_id: RunId) -> ReviewRequest | None:
        def _op() -> ReviewRequest | None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_RUN_WS, (run_id,))
                rw = cur.fetchone()
                if rw is None:
                    raise not_found("run", run_id)
                rr_id = rw["review_request_id"]
                if rr_id is None:
                    return None
                cur.execute(_GET_REVIEW_REQUEST, (rr_id,))
                row = cur.fetchone()
                if row is None:
                    raise not_found("review_request", rr_id)
                return review_request_from_row(row)

        return run(_op)
