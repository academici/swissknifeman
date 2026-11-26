"""PostgreSQL ``PlanCounters`` adapter (planning §6, §11; DDL ``0008``)."""

from typing import Final, cast

import psycopg

from skm.adapters.postgres.planning.mapping import damaged, run
from skm.kernel.ids import ProjectId, WorkspaceId

__all__ = ["PostgresPlanCounters"]

_ALLOCATE: Final = """
INSERT INTO skm_planning.project_plan_counters (workspace_id, project_id, next_plan_no)
VALUES (%s, %s, 2)
ON CONFLICT (project_id) DO UPDATE
   SET workspace_id = EXCLUDED.workspace_id,
       next_plan_no = skm_planning.project_plan_counters.next_plan_no + 1
RETURNING next_plan_no - 1
"""


class PostgresPlanCounters:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def allocate_plan_no(self, workspace_id: WorkspaceId, project_id: ProjectId) -> int:
        row = run(lambda: self._conn.execute(_ALLOCATE, (workspace_id, project_id)).fetchone())
        if row is None:
            raise damaged("project_plan_counters", project_id)
        return cast("int", row[0])
