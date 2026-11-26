"""Pure plan and archived-note Markdown projections."""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from .frontmatter import Fields, FrontmatterValue
from .markdown import MarkdownDoc, Row, bounded_table, heading, iso_utc, quote, table, utf8_prefix


@dataclass(frozen=True, slots=True)
class PhaseExportView:
    key: str
    title: str
    goal: str
    items: tuple[tuple[str, str, str, str], ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class PlanExportView:
    plan_id: UUID
    alias: str
    title: str
    status: str
    project: str
    repository: str | None
    revision_id: UUID | None = None
    revision_no: int | None = None
    content_digest: str | None = None
    run_id: UUID | None = None
    goal: str = ""
    phases: tuple[PhaseExportView, ...] = ()
    requirements: tuple[Row, ...] = ()
    decisions: tuple[Row, ...] = ()
    checks: tuple[Row, ...] = ()


def _fields(view: PlanExportView, *, archived: str | None = None) -> Fields:
    def value(text: str) -> str:
        return utf8_prefix(text, 1024) if archived is not None else text

    fields: list[tuple[str, FrontmatterValue]] = [
        ("type", "skm-plan" if archived is None else "plan-archived"),
        ("plan", value(view.alias)),
        ("plan_id", str(view.plan_id)),
    ]
    if view.revision_no is not None:
        fields.append(("revision", view.revision_no))
    fields.append(("status", value(view.status)))
    if archived is not None:
        fields.append(("archived", archived))
    fields.append(("project", value(view.project)))
    if view.repository:
        fields.append(("repository", value(view.repository)))
    return tuple(fields)


def _section(title: str, columns: Row, rows: tuple[Row, ...]) -> str:
    return f"\n{heading(title, 2)}\n\n{table(columns, rows)}" if rows else ""


def render_plan(view: PlanExportView) -> MarkdownDoc:
    header = (
        *_fields(view),
        ("content_digest", view.content_digest or ""),
        ("exported_by", "skm"),
        ("tags", ("skm", "plan")),
    )
    body = heading(view.title) + "\n"
    if view.goal:
        body += f"\n{quote(view.goal)}\n"
    body += _section("Requirements", ("Key", "Priority", "Statement"), view.requirements)
    if view.phases:
        body += "\n## Phases\n"
    for phase in view.phases:
        body += f"\n{heading(f'{phase.key} — {phase.title}', 3)}\n"
        if phase.goal:
            body += f"\n{quote(phase.goal)}\n"
        if phase.items:
            body += "\n" + table(("Item", "Title", "Kind", "Status"), phase.items)
    body += _section("Decisions", ("Key", "Title", "State", "Decision"), view.decisions)
    body += _section("Checks", ("Check", "Category", "Kind", "Required"), view.checks)
    return MarkdownDoc(header, body)


def _phase_status(phase: PhaseExportView) -> str:
    statuses = {item[3] for item in phase.items}
    if not statuses:
        return "—"
    for status in (
        "failed",
        "cancelled",
        "blocked",
        "running",
        "pending",
        "—",
        "accepted with deviations",
        "accepted",
    ):
        if status in statuses:
            return status
    return "skipped" if statuses == {"skipped"} else "—"


def render_plan_note(view: PlanExportView, *, occurred_at: datetime, provenance: Fields) -> MarkdownDoc:
    archived = iso_utc(occurred_at)
    fields = (
        _fields(view, archived=archived) + provenance + (("source", "skm"), ("tags", ("plan", "archived")))
    )
    body = heading(utf8_prefix(view.title, 1024)) + "\n"
    if view.goal:
        body += "\n" + quote(utf8_prefix(view.goal, 4096)) + "\n"
    counts = Counter(item[3] for phase in view.phases for item in phase.items)
    summary = (
        f"Counts: items {counts.total()}, accepted {counts['accepted']}, "
        f"accepted with deviations {counts['accepted with deviations']}, failed {counts['failed']}, "
        f"skipped {counts['skipped']}.\n\nArchived {archived}.\n"
    )
    if not view.phases:
        return MarkdownDoc(fields, body + "\n" + summary)
    return bounded_table(
        MarkdownDoc(fields, body + "\n"),
        ("Phase", "Title", "Status"),
        ((phase.key, phase.title, _phase_status(phase)) for phase in view.phases),
        total=len(view.phases),
        ref=str(view.plan_id),
        tail="\n" + summary,
    )
