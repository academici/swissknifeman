"""Project structural execution records without following source artifact references."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from skm.application_bus.registry import QuerySpec
from skm.kernel.ids import ProjectId, RevisionId, RunId, ScopeId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.execution.public import get_run_export_metrics, get_run_summary
from skm.modules.exports.domain.run_report import (
    CheckRun,
    RunReportData,
    RunTask,
    StepUsage,
    compute_metrics,
    render_run_report,
)
from skm.modules.exports.generated.queries import RenderRunReport
from skm.modules.exports.generated.views import RunReportView, RunReportViewDefsRunReportMetrics
from skm.modules.planning import public as planning
from skm.modules.workspace import public as workspace

if TYPE_CHECKING:
    from skm.application_bus.context import QueryContext
    from skm.kernel.ports_uow import UnitOfWork


def _objects(value: JsonValue) -> tuple[JsonObject, ...]:
    return tuple(item for item in value if isinstance(item, dict)) if isinstance(value, list) else ()


def _integer(value: JsonValue) -> int | None:
    return value if type(value) is int else None


def _timestamp(value: JsonValue) -> datetime | None:
    return datetime.fromisoformat(value) if isinstance(value, str) else None


def _task(raw: JsonObject, title: str) -> RunTask:
    checks = tuple(
        CheckRun(
            str(row["check_key"]),
            row["failed"] is True,
            row["reused"] is True,
            float(str(row["seconds"])),
        )
        for row in _objects(raw.get("checks"))
    )
    return RunTask(
        key=str(raw["display_key"]),
        title=title,
        status=str(raw["status"]).replace("_", " "),
        attempts=_integer(raw.get("attempts_count")) or 0,
        accepted_attempt_no=_integer(raw.get("accepted_attempt_no")),
        checks=checks,
        check_fix_rounds=_integer(raw.get("check_fix_rounds")) or 0,
        review_rounds=_integer(raw.get("review_rounds")) or 0,
        rework_rounds=_integer(raw.get("rework_rounds")) or 0,
    )


def _step(row: JsonObject) -> StepUsage:
    seconds = row.get("seconds")
    return StepUsage(
        group=str(row.get("group", "executor")),
        seconds=float(seconds) if isinstance(seconds, (int, float)) else None,
        input_tokens=_integer(row.get("input_tokens")),
        cached_tokens=_integer(row.get("cached_tokens")),
        output_tokens=_integer(row.get("output_tokens")),
        cost_usd_micros=_integer(row.get("cost_usd_micros")),
    )


def build_run_view(uow: UnitOfWork, run_id: RunId, *, summary: JsonObject | None = None) -> RunReportData:
    summary = get_run_summary(uow, run_id) if summary is None else summary
    report = get_run_export_metrics(uow, run_id)
    spec = planning.get_revision_specification(uow, RevisionId(UUID(str(summary["revision_id"]))))
    project = workspace.get_project(uow, ProjectId(UUID(str(summary["project_id"]))))
    titles = {item.key: item.title for item in (*spec.phases, *spec.items, *spec.units)}
    tasks = sorted(
        _objects(report.get("tasks")), key=lambda task: (str(task["display_key"]), str(task["task_id"]))
    )
    return RunReportData(
        run_id=run_id,
        alias=str(summary["plan_alias"]),
        revision_no=int(str(summary["revision_no"])),
        status=str(summary["status"]),
        title=spec.title,
        project=project.title,
        stop_code=str(summary["stop_code"]) if summary.get("stop_code") else None,
        started_at=_timestamp(summary.get("started_at")),
        finished_at=_timestamp(summary.get("finished_at")),
        tasks=tuple(_task(task, titles.get(key := str(task["display_key"]), key)) for task in tasks),
        steps=tuple(_step(step) for task in tasks for step in _objects(task["steps"])),
        findings=tuple(
            (str(row["severity"]), row["state"] == "confirmed") for row in _objects(report.get("findings"))
        ),
        deviations=("Deviation accepted.",) * (_integer(report.get("deviations_accepted")) or 0),
        decisions_asked=_integer(report.get("decisions_asked")) or 0,
        decisions_answered=_integer(report.get("decisions_answered")) or 0,
        source_unavailable=True,
    )


def _metrics_wire(view: RunReportData) -> dict[str, object]:
    metrics = asdict(compute_metrics(view))
    del metrics["known_usd_micros"], metrics["unknown_cost_steps"]
    return metrics


def handle(query: RenderRunReport, _ctx: QueryContext, uow: UnitOfWork) -> RunReportView:
    view = build_run_view(uow, RunId(query.run_id))
    doc = render_run_report(view, variant=query.variant)
    return RunReportView(
        doc.text(),
        f"run-{query.run_id.hex[:8]}.md",
        doc.digest(),
        RunReportViewDefsRunReportMetrics.from_json(_metrics_wire(view)),
    )


SPEC = QuerySpec(
    name="exports.render_run_report",
    dto=RenderRunReport,
    result=RunReportView,
    permission="run.read",
    scope_of=lambda q: ScopeRef(ScopeKind.RUN, ScopeId(q.run_id)),
    handler=handle,
)
