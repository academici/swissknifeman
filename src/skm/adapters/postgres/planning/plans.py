"""PostgreSQL ``PlanRepository`` adapter (planning §6, §11; DDL ``0008``, ``0009``)."""

from collections.abc import Mapping
from typing import Final, cast
from uuid import UUID

import psycopg

from skm.adapters.postgres.jsonb import require_aware
from skm.adapters.postgres.planning.mapping import (
    already_exists,
    not_found,
    plan_from_row,
    require_unchanged,
    run,
)
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, InternalError
from skm.kernel.ids import FileVersionId, PlanId, PrincipalId, ProjectId, WorkspaceId
from skm.modules.planning.domain.brief import DesignBrief, ResearchReference
from skm.modules.planning.domain.plan import Plan, PlanPurpose
from skm.modules.planning.ports import AliasKind

__all__ = ["PostgresPlanRepository"]

_PLAN_OWNED: Final = ("workspace_id", "project_id", "alias", "purpose", "created_by", "created_at")
_ADDED_ALIASES: Final = frozenset({AliasKind.LEGACY, AliasKind.EXTERNAL})

_SELECT: Final = """
SELECT p.id, p.workspace_id, p.project_id, a.alias, p.purpose, p.title, p.lifecycle_state,
       p.current_revision_id, p.next_revision_no, p.row_version, p.created_by,
       p.created_at, p.updated_at, p.archived_at
  FROM skm_planning.plans p
  JOIN skm_planning.plan_aliases a
    ON a.workspace_id = p.workspace_id
   AND a.project_id = p.project_id
   AND a.plan_id = p.id
   AND a.alias_kind IN ('short', 'system')
"""
_GET: Final = _SELECT + " WHERE p.id = %s"
_LOCK: Final = _GET + " FOR UPDATE OF p"
_LOCK_SHARED: Final = _GET + " FOR SHARE OF p"
_BY_ALIAS: Final = """
SELECT p.id, p.workspace_id, p.project_id, a.alias, p.purpose, p.title, p.lifecycle_state,
       p.current_revision_id, p.next_revision_no, p.row_version, p.created_by,
       p.created_at, p.updated_at, p.archived_at
  FROM skm_workspace.projects proj
  JOIN skm_planning.plan_aliases x
    ON x.workspace_id = proj.workspace_id
   AND x.project_id = proj.id
  JOIN skm_planning.plans p
    ON p.workspace_id = x.workspace_id
   AND p.project_id = x.project_id
   AND p.id = x.plan_id
  JOIN skm_planning.plan_aliases a
    ON a.workspace_id = p.workspace_id
   AND a.project_id = p.project_id
   AND a.plan_id = p.id
   AND a.alias_kind IN ('short', 'system')
 WHERE proj.id = %s
   AND x.alias = %s
"""
_BY_PREFIX: Final = """
SELECT p.id, p.workspace_id, p.project_id, a.alias, p.purpose, p.title, p.lifecycle_state,
       p.current_revision_id, p.next_revision_no, p.row_version, p.created_by,
       p.created_at, p.updated_at, p.archived_at
  FROM skm_workspace.projects proj
  JOIN skm_planning.plans p
    ON p.workspace_id = proj.workspace_id
   AND p.project_id = proj.id
  JOIN skm_planning.plan_aliases a
    ON a.workspace_id = p.workspace_id
   AND a.project_id = p.project_id
   AND a.plan_id = p.id
   AND a.alias_kind IN ('short', 'system')
 WHERE proj.id = %s
   AND p.id::text LIKE %s ESCAPE '\\'
 ORDER BY p.id::text COLLATE "C" ASC
 LIMIT %s
"""
_REVIEW_REQUESTS: Final = (
    _SELECT + " WHERE p.project_id = %s AND p.purpose = 'review_requests' FOR UPDATE OF p"
)

_EXISTS_PLAN: Final = "SELECT 1 FROM skm_planning.plans WHERE id = %s"
_INSERT_PLAN: Final = """
INSERT INTO skm_planning.plans (
    workspace_id, project_id, id, title, lifecycle_state, purpose,
    current_revision_id, next_revision_no, row_version,
    created_by, created_at, updated_at, archived_at
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (id) DO NOTHING
RETURNING id
"""
_INSERT_ALIAS: Final = """
INSERT INTO skm_planning.plan_aliases (workspace_id, project_id, plan_id, alias, alias_kind, created_at)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (workspace_id, project_id, alias) DO NOTHING
RETURNING alias
"""
_UPDATE_PLAN: Final = """
UPDATE skm_planning.plans
   SET title = %s,
       lifecycle_state = %s,
       current_revision_id = %s,
       next_revision_no = %s,
       row_version = %s,
       updated_at = %s,
       archived_at = %s
 WHERE id = %s AND row_version = %s
"""
_PROJECT_ALIASES: Final = """
SELECT a.alias, a.plan_id
  FROM skm_workspace.projects proj
  JOIN skm_planning.plan_aliases a
    ON a.workspace_id = proj.workspace_id
   AND a.project_id = proj.id
 WHERE proj.id = %s
"""
_PROJECT_PLANS: Final = """
SELECT p.id
  FROM skm_workspace.projects proj
  JOIN skm_planning.plans p
    ON p.workspace_id = proj.workspace_id
   AND p.project_id = proj.id
 WHERE proj.id = %s
"""
_SUPERSEDED_BY: Final = """
SELECT DISTINCT p.id, p.id::text COLLATE "C" AS id_sort
  FROM skm_planning.plans p
  JOIN skm_planning.plan_relations r
    ON r.workspace_id = p.workspace_id
   AND r.plan_id = p.id
   AND r.revision_id = p.current_revision_id
 WHERE r.kind = 'supersedes'
   AND r.target_plan_id = %s
 ORDER BY id_sort ASC
"""
_PLAN_ALIASES: Final = """
SELECT alias, alias_kind
  FROM skm_planning.plan_aliases
 WHERE plan_id = %s
"""


def _escape_like(prefix: str) -> str:
    return prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


class PostgresPlanRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def add_design_brief(self, brief: DesignBrief) -> None:
        scope = (brief.workspace_id, brief.plan_id, brief.id)

        def insert() -> None:
            self._conn.execute(
                """INSERT INTO skm_planning.plan_design_briefs
                   (workspace_id, plan_id, id, goal, context_md, constraints, created_by, created_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    *scope,
                    brief.goal,
                    brief.context_md,
                    # Authored constraints are strings. A NULL separator leaves legacy arrays
                    # intact and distinguishes storage metadata from any user-supplied text.
                    [*brief.constraints, None, "visa_policy=required"]
                    if brief.visa_policy == "required"
                    else list(brief.constraints),
                    brief.created_by,
                    require_aware(brief.created_at),
                ),
            )
            with self._conn.cursor() as cur:
                cur.executemany(
                    """INSERT INTO skm_planning.plan_design_brief_rag_bindings
                       (workspace_id, plan_id, design_brief_id, file_version_id) VALUES (%s, %s, %s, %s)""",
                    [(*scope, version) for version in brief.rag_file_version_ids],
                )
                cur.executemany(
                    """INSERT INTO skm_planning.plan_design_brief_research_references
                       (workspace_id, plan_id, design_brief_id, reference, content_digest)
                       VALUES (%s, %s, %s, %s, %s)""",
                    [(*scope, ref.reference, ref.content_digest) for ref in brief.research_references],
                )

        run(insert)

    def get_design_brief(self, plan_id: PlanId, brief_id: UUID) -> DesignBrief:
        def read() -> DesignBrief:
            row = self._conn.execute(
                """SELECT workspace_id, goal, context_md, constraints, created_by, created_at
                     FROM skm_planning.plan_design_briefs WHERE plan_id = %s AND id = %s""",
                (plan_id, brief_id),
            ).fetchone()
            if row is None:
                raise not_found("design_brief", brief_id)
            versions = self._conn.execute(
                """SELECT file_version_id FROM skm_planning.plan_design_brief_rag_bindings
                    WHERE plan_id = %s AND design_brief_id = %s ORDER BY file_version_id""",
                (plan_id, brief_id),
            ).fetchall()
            references = self._conn.execute(
                """SELECT reference, content_digest FROM skm_planning.plan_design_brief_research_references
                    WHERE plan_id = %s AND design_brief_id = %s ORDER BY reference COLLATE "C" """,
                (plan_id, brief_id),
            ).fetchall()
            required_visa = row[3][-2:] == [None, "visa_policy=required"]
            return DesignBrief(
                brief_id,
                WorkspaceId(row[0]),
                plan_id,
                row[1],
                row[2],
                tuple(row[3][:-2] if required_visa else row[3]),
                tuple(FileVersionId(item[0]) for item in versions),
                tuple(ResearchReference(*item) for item in references),
                PrincipalId(row[4]),
                row[5],
                "required" if required_visa else "optional",
            )

        return run(read)

    def get(self, plan_id: PlanId) -> Plan:
        row = run(lambda: self._conn.execute(_GET, (plan_id,)).fetchone())
        if row is None:
            raise not_found("plan", plan_id)
        return plan_from_row(row)

    def lock(self, plan_id: PlanId) -> Plan:
        row = run(lambda: self._conn.execute(_LOCK, (plan_id,)).fetchone())
        if row is None:
            raise not_found("plan", plan_id)
        return plan_from_row(row)

    def lock_shared(self, plan_id: PlanId) -> Plan:
        row = run(lambda: self._conn.execute(_LOCK_SHARED, (plan_id,)).fetchone())
        if row is None:
            raise not_found("plan", plan_id)
        return plan_from_row(row)

    def add(self, plan: Plan) -> None:
        if run(lambda: self._conn.execute(_EXISTS_PLAN, (plan.id,)).fetchone()) is not None:
            raise already_exists("plan", ref=str(plan.id))
        system = plan.purpose is PlanPurpose.REVIEW_REQUESTS
        if system and self.find_review_requests_plan(plan.project_id) is not None:
            raise already_exists("plan", alias=plan.alias)
        if self.find_by_alias(plan.project_id, plan.alias) is not None:
            raise already_exists("alias", alias=plan.alias)
        created_at = require_aware(plan.created_at)
        updated_at = require_aware(plan.updated_at)
        archived_at = None if plan.archived_at is None else require_aware(plan.archived_at)
        inserted = run(
            lambda: self._conn.execute(
                _INSERT_PLAN,
                (
                    plan.workspace_id,
                    plan.project_id,
                    plan.id,
                    plan.title,
                    plan.lifecycle.value,
                    plan.purpose.value,
                    plan.current_revision_id,
                    plan.next_revision_no,
                    plan.row_version,
                    plan.created_by,
                    created_at,
                    updated_at,
                    archived_at,
                ),
            ).fetchone()
        )
        if inserted is None:
            raise already_exists("plan", ref=str(plan.id))
        alias_kind = AliasKind.SYSTEM if system else AliasKind.SHORT
        bound = run(
            lambda: self._conn.execute(
                _INSERT_ALIAS,
                (plan.workspace_id, plan.project_id, plan.id, plan.alias, alias_kind.value, created_at),
            ).fetchone()
        )
        if bound is None:
            raise already_exists("alias", alias=plan.alias)

    def save(self, plan: Plan, *, expected_version: int) -> None:
        stored = self.lock(plan.id)
        if stored.row_version != expected_version:
            raise Conflict(
                ErrorCode.VERSION_CONFLICT,
                "the plan was changed by another command",
                details={"expected": expected_version, "actual": stored.row_version},
            )
        require_unchanged("plan", stored, plan, _PLAN_OWNED)
        updated_at = require_aware(plan.updated_at)
        archived_at = None if plan.archived_at is None else require_aware(plan.archived_at)
        run(
            lambda: self._conn.execute(
                _UPDATE_PLAN,
                (
                    plan.title,
                    plan.lifecycle.value,
                    plan.current_revision_id,
                    plan.next_revision_no,
                    plan.row_version,
                    updated_at,
                    archived_at,
                    plan.id,
                    expected_version,
                ),
            )
        )

    def find_by_alias(self, project_id: ProjectId, alias: str) -> Plan | None:
        row = run(lambda: self._conn.execute(_BY_ALIAS, (project_id, alias)).fetchone())
        return None if row is None else plan_from_row(row)

    def find_by_id_prefix(self, project_id: ProjectId, prefix: str, *, limit: int) -> tuple[Plan, ...]:
        if limit <= 0:
            return ()
        rows = run(
            lambda: self._conn.execute(_BY_PREFIX, (project_id, _escape_like(prefix), limit)).fetchall()
        )
        return tuple(plan_from_row(row) for row in rows)

    def project_plan_refs(self, project_id: ProjectId) -> Mapping[str, PlanId]:
        alias_rows = run(lambda: self._conn.execute(_PROJECT_ALIASES, (project_id,)).fetchall())
        plan_rows = run(lambda: self._conn.execute(_PROJECT_PLANS, (project_id,)).fetchall())
        refs: dict[str, PlanId] = {cast("str", row[0]): PlanId(cast("UUID", row[1])) for row in alias_rows}
        for row in plan_rows:
            pid = PlanId(cast("UUID", row[0]))
            refs[f"plan:{pid}"] = pid
        return refs

    def find_review_requests_plan(self, project_id: ProjectId) -> Plan | None:
        row = run(lambda: self._conn.execute(_REVIEW_REQUESTS, (project_id,)).fetchone())
        return None if row is None else plan_from_row(row)

    def superseded_by(self, plan_id: PlanId) -> tuple[PlanId, ...]:
        rows = run(lambda: self._conn.execute(_SUPERSEDED_BY, (plan_id,)).fetchall())
        return tuple(PlanId(cast("UUID", row[0])) for row in rows)

    def add_alias(self, plan_id: PlanId, alias: str, kind: AliasKind) -> None:
        if kind not in _ADDED_ALIASES:
            raise InternalError(
                ErrorCode.INTERNAL_ERROR,
                "only a legacy or external alias is added to an existing plan",
                details={"alias_kind": kind.value},
            )
        plan = self.get(plan_id)
        bound = run(
            lambda: self._conn.execute(
                _INSERT_ALIAS,
                (
                    plan.workspace_id,
                    plan.project_id,
                    plan.id,
                    alias,
                    kind.value,
                    require_aware(plan.updated_at),
                ),
            ).fetchone()
        )
        if bound is None:
            raise already_exists("alias", alias=alias)

    def list_aliases(self, plan_id: PlanId) -> tuple[tuple[str, AliasKind], ...]:
        plan = self.get(plan_id)
        rows = run(lambda: self._conn.execute(_PLAN_ALIASES, (plan_id,)).fetchall())
        primary_kind = AliasKind.SYSTEM if plan.purpose is PlanPurpose.REVIEW_REQUESTS else AliasKind.SHORT
        extras = sorted(
            (
                (cast("str", row[0]), AliasKind(cast("str", row[1])))
                for row in rows
                if cast("str", row[0]) != plan.alias
            ),
            key=lambda item: (item[1].value, item[0]),
        )
        return ((plan.alias, primary_kind), *extras)
