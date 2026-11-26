"""Byte, provenance and escaping contracts for Markdown projections."""

from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest

from skm.kernel.errors import SkmError
from skm.modules.exports.domain.frontmatter import read, render
from skm.modules.exports.domain.markdown import NOTE_BODY_MAX_BYTES, MarkdownDoc, cell
from skm.modules.exports.domain.note import NoteKind, clean_segment, note_name
from skm.modules.exports.domain.plan_markdown import PhaseExportView, PlanExportView, render_plan_note
from skm.modules.exports.domain.run_report import (
    RunReportData,
    RunTask,
    StepUsage,
    compute_metrics,
    render_run_report,
)

RUN = UUID("019a4b00-1111-7222-8333-444455556666")
PLAN = UUID("019a3f00-1a2b-7c3d-8e4f-5a6b7c8d9e0f")
EVENT = UUID("019a4f00-7e8d-7c6b-9a59-483726150a0b")
NOW = datetime(2026, 10, 25, 16, 20, tzinfo=UTC)


def test_flat_frontmatter_round_trip_and_malformed_headers() -> None:
    fields = (
        ("name", " a: [b] #c 'd' \"e\" "),
        ("enabled", True),
        ("items", ("a", "b, c", "true")),
        ("n", 3),
    )
    text = MarkdownDoc(fields, "# Body").text()
    assert read(text) == fields
    assert text.startswith('---\nname: "')
    assert read(text, max_bytes=35) is None
    assert read("---\nname: one\nname: two\n---\n") is None
    assert read('---\nitems: ["a", ]\n---\n') is None
    assert render(()) == ""
    assert cell("first |\n second") == r"first \| second"


def test_note_names_reserve_suffix_and_keep_full_event_identity() -> None:
    for kind in NoteKind:
        name = note_name(
            kind,
            date_utc=NOW.astimezone(timezone(timedelta(hours=10))),
            plan_alias="😀" * 100,
            event_id=EVENT,
            run_key="🔵" * 100,
        )
        assert name.startswith("2026-10-25 ")
        assert name.endswith(f"{EVENT.hex}.md")
        assert len(name.encode("utf-8")) <= 240
        assert len((name[:-3] + " (10000).md").encode("utf-8")) <= 248
    assert clean_segment(" . e\u0301/\\\x00 ") == "é---"
    assert clean_segment(" ... ") == "plan"
    for bad in ("NUL", "AUX.txt", "name?", "dot."):
        with pytest.raises(SkmError):
            note_name(NoteKind.PLAN_ARCHIVED, date_utc=date(2026, 10, 25), plan_alias=bad, event_id=EVENT)


def test_archived_plan_note_matches_the_owned_example() -> None:
    path = Path("tests/fixtures/corpus/examples/exports/plan-note.md")
    expected = path.read_text().replace(r"\\|", r"\|")
    fields = dict(read(expected) or ())
    sizes = (4, 4, 1)
    phase_rows = [
        ("P1", "Tax rates model", ("accepted",) * 4),
        ("P2", "Invoice totals and API", ("accepted",) * 3 + ("accepted with deviations",)),
        ("P3", "Removal of legacy totals | cleanup", ("skipped",)),
    ]
    phases = tuple(
        PhaseExportView(key, title, "", tuple((str(i), "", "", statuses[i]) for i in range(size)))
        for (key, title, statuses), size in zip(phase_rows, sizes, strict=True)
    )
    provenance = tuple(
        (key, fields[key])
        for key in (
            "note_id",
            "event_id",
            "occurred_at",
            "materialized_at",
            "render_version",
            "revision_id",
            "run_id",
            "classification",
        )
    )
    view = PlanExportView(
        plan_id=PLAN,
        alias="billing-v2",
        revision_no=4,
        title="Billing v2: invoices with taxes",
        status="archived",
        project="Demo service",
        repository="github.com/example/demo-service",
        goal=(
            "Invoices compute totals with regional tax rates, and the HTTP API exposes them.\n"
            "Old totals stay readable for one release."
        ),
        phases=phases,
    )
    assert render_plan_note(view, occurred_at=NOW, provenance=provenance).text() == expected


def test_queued_run_is_bounded_after_escaping_and_keeps_whole_rows() -> None:
    tasks = tuple(RunTask(f"P1.{i}", "😀|" * 20_000, "accepted", 1, 1) for i in range(7))
    view = RunReportData(
        run_id=RUN,
        alias="🚀" * 300_000,
        revision_no=15,
        status="succeeded",
        title="🧪" * 300_000,
        project="Proj",
        tasks=tasks,
    )
    doc = render_run_report(view, variant="summary", provenance=(("classification", "restricted"),))
    assert len(doc.text().encode("utf-8")) <= NOTE_BODY_MAX_BYTES
    assert "truncated: true, total: 7, included: 2, omitted: 5" in doc.body
    assert f"Full report: {RUN}." in doc.body
    assert all(line.endswith(" |") for line in doc.body.splitlines() if line.startswith("|"))
    assert read(doc.text()) is not None


def test_integer_cost_and_missing_usage_are_distinct() -> None:
    view = RunReportData(
        run_id=RUN,
        alias="plan",
        revision_no=1,
        status="failed",
        title="Plan",
        project="Project",
        steps=(StepUsage("executor", 30, 7, 3, 5, 14_820_001), StepUsage("checks")),
    )
    metrics = compute_metrics(view)
    assert metrics.usd is None
    assert metrics.known_usd_micros == 14_820_001
    assert metrics.tokens == {"input": 7, "cached": 3, "output": 5, "unknown_steps": 1}
    assert "Cost ≥ 14.820001 USD" in render_run_report(view).body
