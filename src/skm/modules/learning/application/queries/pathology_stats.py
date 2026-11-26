"""Summarize observed pathologies and their recorded severity."""

from collections import Counter
from typing import Any, cast
from uuid import UUID

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.ids import ProjectId
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.learning.application.commands.extract_candidates import ActivityStorage, project_ref
from skm.modules.learning.generated.queries import PathologyStats
from skm.modules.learning.generated.views import PathologyStatsView, pathology_stats_view_from_json
from skm.modules.learning.ports import ActivityRecordRepository


def handle(cmd: dict[str, Any], _ctx: QueryContext, uow: UnitOfWork) -> PathologyStatsView:
    window = cmd.get("window", 20)
    repo = cast("ActivityStorage", uow.repo(ActivityRecordRepository))
    rows = repo.recent_for_project(ProjectId(UUID(cmd["project_id"])), window=window)
    counts = Counter(code for row in rows for code in set(row.pathology_codes))
    attention = {
        e.detector_version.partition(":")[0]
        for row in rows
        for e in row.detector_evidence
        if e.severity == "attention"
    }
    return pathology_stats_view_from_json(
        {
            "window": window,
            "records": len(rows),
            "codes": [
                {
                    "code": code.value,
                    "count": count,
                    "severity_max": "attention" if f"pathology/{code}" in attention else "info",
                }
                for code, count in sorted(counts.items())
            ],
        }
    )


SPEC = QuerySpec(
    name="learning.pathology_stats",
    dto=cast("type[dict[str, Any]]", PathologyStats),
    result=PathologyStatsView,
    permission="lesson.read",
    scope_of=lambda cmd: project_ref(cmd["project_id"]),
    handler=handle,
)
