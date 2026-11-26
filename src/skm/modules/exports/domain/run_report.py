"""Pure run metrics and Markdown projection of structural execution facts."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from skm.kernel.json_types import JsonObject

from .frontmatter import Fields
from .markdown import MarkdownDoc, bounded_table, heading, iso_utc, one_line, table, utf8_prefix


@dataclass(frozen=True, slots=True)
class CheckRun:
    key: str
    failed: bool
    reused: bool = False
    seconds: float = 0


@dataclass(frozen=True, slots=True)
class StepUsage:
    group: str
    seconds: float | None = None
    input_tokens: int | None = None
    cached_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd_micros: int | None = None
    step_count: int = 1


@dataclass(frozen=True, slots=True)
class RunTask:
    key: str
    title: str
    status: str
    attempts: int = 0
    accepted_attempt_no: int | None = None
    checks: tuple[CheckRun, ...] = ()
    check_fix_rounds: int = 0
    review_rounds: int = 0
    rework_rounds: int = 0


@dataclass(frozen=True, slots=True, kw_only=True)
class RunReportData:
    run_id: UUID
    alias: str
    revision_no: int
    status: str
    title: str
    project: str
    stop_code: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    tasks: tuple[RunTask, ...] = ()
    steps: tuple[StepUsage, ...] = ()
    findings: tuple[tuple[str, bool], ...] = ()
    deviations: tuple[str, ...] = ()
    decisions_asked: int = 0
    decisions_answered: int = 0
    source_unavailable: bool = False


@dataclass(frozen=True, slots=True)
class RunReportMetrics:
    tasks_total: int
    tasks_accepted: int
    tasks_failed: int
    tasks_skipped: int
    first_pass_rate: float
    attempts_per_task: float
    check_fix_rounds: int
    review_rounds: int
    rework_rounds: int
    checks: JsonObject
    findings: JsonObject
    deviations_accepted: int
    decisions: JsonObject
    tokens: JsonObject
    usd: int | None
    known_usd_micros: int
    unknown_cost_steps: int
    active_seconds_by_group: Mapping[str, float]
    wall_seconds: float


def _usage(steps: tuple[StepUsage, ...]) -> tuple[JsonObject, int, int, dict[str, float]]:
    groups: dict[str, float] = {}
    for step in steps:
        if step.seconds is not None:
            groups[step.group] = groups.get(step.group, 0) + step.seconds
    tokens: JsonObject = {
        "input": sum(step.input_tokens or 0 for step in steps),
        "cached": sum(step.cached_tokens or 0 for step in steps),
        "output": sum(step.output_tokens or 0 for step in steps),
        "unknown_steps": sum(
            step.step_count
            for step in steps
            if step.input_tokens is None
            and step.cached_tokens is None
            and step.output_tokens is None
            and step.cost_usd_micros is None
        ),
    }
    return (
        tokens,
        sum(s.cost_usd_micros or 0 for s in steps),
        sum(s.step_count for s in steps if s.cost_usd_micros is None),
        groups,
    )


def _checks(tasks: tuple[RunTask, ...]) -> JsonObject:
    grouped: dict[str, Counter[str]] = {}
    seconds: dict[str, float] = {}
    for task in tasks:
        for check in task.checks:
            grouped.setdefault(check.key, Counter()).update(
                {"runs": 1, "red": int(check.failed), "reused": int(check.reused)}
            )
            seconds[check.key] = seconds.get(check.key, 0) + check.seconds
    return {key: {**dict(counts), "seconds": seconds[key]} for key, counts in sorted(grouped.items())}


def compute_metrics(view: RunReportData) -> RunReportMetrics:
    counts = Counter(task.status for task in view.tasks)
    accepted = counts["accepted"] + counts["accepted with deviations"]
    first_pass = sum(
        t.accepted_attempt_no == 1 for t in view.tasks if t.status in ("accepted", "accepted with deviations")
    )
    attempted = [task.attempts for task in view.tasks if task.attempts > 0]
    tokens, known_cost, unknown_cost, groups = _usage(view.steps)
    if check_seconds := sum(check.seconds for task in view.tasks for check in task.checks):
        groups["checks"] = groups.get("checks", 0) + check_seconds
    confirmed = Counter(severity for severity, confirmed in view.findings if confirmed)
    wall = (view.finished_at - view.started_at).total_seconds() if view.started_at and view.finished_at else 0
    return RunReportMetrics(
        tasks_total=len(view.tasks),
        tasks_accepted=accepted,
        tasks_failed=counts["failed"],
        tasks_skipped=counts["skipped"],
        first_pass_rate=first_pass / accepted if accepted else 0,
        attempts_per_task=sum(attempted) / len(attempted) if attempted else 0,
        check_fix_rounds=sum(t.check_fix_rounds for t in view.tasks),
        review_rounds=sum(t.review_rounds for t in view.tasks),
        rework_rounds=sum(t.rework_rounds for t in view.tasks),
        checks=_checks(view.tasks),
        findings={
            "confirmed": confirmed.total(),
            "rejected": len(view.findings) - confirmed.total(),
            "by_severity": {key: confirmed[key] for key in ("blocker", "major", "minor", "nit")},
        },
        deviations_accepted=len(view.deviations),
        decisions={
            "asked": view.decisions_asked,
            "answered": view.decisions_answered,
            "open": max(0, view.decisions_asked - view.decisions_answered),
        },
        tokens=tokens,
        usd=None if unknown_cost else known_cost,
        known_usd_micros=known_cost,
        unknown_cost_steps=unknown_cost,
        active_seconds_by_group=groups,
        wall_seconds=wall,
    )


def _duration(seconds: float) -> str:
    hours, rem = divmod(int(seconds), 3600)
    minutes, sec = divmod(rem, 60)
    return f"{hours} h {minutes} min" if hours else f"{minutes} min" if minutes else f"{sec} s"


def _money(micros: int) -> str:
    whole, fraction = divmod(micros, 1_000_000)
    return f"{whole}.{fraction:06d}".rstrip("0").rstrip(".")


def _details(view: RunReportData, metrics: RunReportMetrics) -> str:
    parts: list[str] = []
    if metrics.checks:
        parts.append(
            "\n## Checks\n\n"
            + table(
                ("Check", "Runs", "Red", "Reused", "Seconds"),
                (
                    (key, counts["runs"], counts["red"], counts["reused"], counts["seconds"])
                    for key, counts in metrics.checks.items()
                    if isinstance(counts, dict)
                ),
            )
        )
    if view.findings:
        severity = metrics.findings["by_severity"]
        breakdown = (
            ", ".join(f"{key} {count}" for key, count in severity.items())
            if isinstance(severity, dict)
            else ""
        )
        parts.append(
            f"\n## Findings\n\nConfirmed {metrics.findings['confirmed']}, "
            f"rejected {metrics.findings['rejected']}. "
            f"By severity: {breakdown}.\n"
        )
    if view.deviations:
        parts.append("\n## Deviations\n\n" + "".join(f"- {one_line(line)}\n" for line in view.deviations))
    if view.decisions_asked or view.decisions_answered:
        parts.append(
            f"\n## Decisions\n\nAsked {metrics.decisions['asked']}, "
            f"answered {metrics.decisions['answered']}, "
            f"open {metrics.decisions['open']}.\n"
        )
    if view.steps:
        usage: list[tuple[object, ...]] = []
        for group in sorted({step.group for step in view.steps}):
            steps = [step for step in view.steps if step.group == group]
            values = (
                tuple(getattr(step, key) for step in steps)
                for key in ("input_tokens", "cached_tokens", "output_tokens")
            )
            usage.append(
                (
                    group,
                    _duration(metrics.active_seconds_by_group[group])
                    if group in metrics.active_seconds_by_group
                    else "—",
                    *(
                        "—"
                        if all(value is None for value in field)
                        else f"{sum(value or 0 for value in field):,}".replace(",", " ")
                        for field in values
                    ),
                )
            )
        parts.append(
            "\n## Usage\n\n"
            + table(("Group", "Active time", "Input tokens", "Cached tokens", "Output tokens"), usage)
        )
        cost = _money(metrics.known_usd_micros)
        price = (
            f"≥ {cost} USD ({metrics.unknown_cost_steps} steps without a known price)"
            if metrics.usd is None
            else f"{cost} USD"
        )
        parts.append(f"\nCost {price}. Steps without usage: {metrics.tokens['unknown_steps']}.\n")
    if view.source_unavailable:
        parts.append("\nSource material and execution traces are unavailable in this projection.\n")
    return "".join(parts)


def render_run_report(
    view: RunReportData, *, variant: Literal["full", "summary"] = "full", provenance: Fields = ()
) -> MarkdownDoc:
    def show(value: str) -> str:
        return utf8_prefix(value, 1024) if provenance else value

    run_key = view.run_id.hex[:8]
    fields: Fields = (
        ("type", "skm-run"),
        ("run", run_key),
        ("run_id", str(view.run_id)),
        ("plan", show(view.alias)),
        ("revision", view.revision_no),
        ("status", show(view.status)),
    )
    if view.started_at:
        fields += (("started", iso_utc(view.started_at)),)
    if view.finished_at:
        fields += (("finished", iso_utc(view.finished_at)),)
    fields = (*fields, ("project", show(view.project)), *provenance, ("tags", ("skm", "run")))
    metrics = compute_metrics(view)
    deviated = sum(task.status == "accepted with deviations" for task in view.tasks)
    pass_count = sum(
        task.accepted_attempt_no == 1
        for task in view.tasks
        if task.status in ("accepted", "accepted with deviations")
    )
    title = heading(f"Run {run_key} — {show(view.title)}")
    body = (
        f"{title}\n\n## Summary\n\nStatus {one_line(show(view.status))} "
        f"(stop code {one_line(show(view.stop_code or '—'))}). Tasks {metrics.tasks_total}: "
        f"accepted {metrics.tasks_accepted - deviated}, accepted with deviations {deviated}, "
        f"failed {metrics.tasks_failed}, skipped {metrics.tasks_skipped}.\n"
        f"First-pass rate {metrics.first_pass_rate:.2f} "
        f"({pass_count} of {metrics.tasks_accepted} accepted on attempt 1). "
        f"Attempts per task {metrics.attempts_per_task:.2f}. Wall time {_duration(metrics.wall_seconds)}.\n"
    )
    if variant == "summary" and view.source_unavailable:
        body += "\nSource material and execution traces are unavailable in this projection.\n"
    if view.tasks:
        body += "\n## Tasks\n\n"
        columns = ("Task", "Title", "Status", "Attempts", "Checks red", "Review rounds")
        rows = (
            (
                task.key,
                task.title,
                task.status,
                task.attempts,
                sum(c.failed for c in task.checks),
                task.review_rounds,
            )
            for task in view.tasks
        )
        if provenance:
            return bounded_table(
                MarkdownDoc(fields, body), columns, rows, total=len(view.tasks), ref=str(view.run_id)
            )
        body += table(columns, rows)
    if variant == "full":
        body += _details(view, metrics)
    return MarkdownDoc(fields, body)
