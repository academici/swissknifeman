"""Queue one immutable export snapshot per source event and note kind."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from skm.application_bus.registry import SubscriberSpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.ids import PlanId, ProjectId, RunId, ScopeId
from skm.kernel.ports_uow import Isolation
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.execution.public import get_run_summary
from skm.modules.exports.domain.events import VaultNoteQueued
from skm.modules.exports.domain.frontmatter import Fields
from skm.modules.exports.domain.markdown import NOTE_BODY_MAX_BYTES, MarkdownDoc, iso_utc
from skm.modules.exports.domain.note import NoteKind, VaultNote, VaultNoteId, VaultNoteState, note_name
from skm.modules.exports.domain.plan_markdown import render_plan_note
from skm.modules.exports.domain.run_report import render_run_report
from skm.modules.exports.ports import VaultNoteRepository
from skm.modules.planning import public as planning
from skm.modules.workspace import public as workspace

from .queries.list_pending_notes import load_note_settings
from .queries.render_plan_markdown import build_plan_view
from .queries.render_run_report import build_run_view

if TYPE_CHECKING:
    from skm.application_bus.context import SubscriberContext
    from skm.kernel.events import EventEnvelope
    from skm.kernel.ports_uow import UnitOfWork


def _notes(ctx: SubscriberContext, project_id: ProjectId):
    return load_note_settings(ctx.config_for(ScopeRef(ScopeKind.PROJECT, ScopeId(project_id))))


def _queue(  # noqa: PLR0913 - pinned source facts cross the queue boundary together
    event: EventEnvelope,
    ctx: SubscriberContext,
    uow: UnitOfWork,
    *,
    kind: NoteKind,
    project_id: ProjectId,
    alias: str,
    revision_id: UUID | None,
    run_id: UUID | None,
    render: Callable[[Fields], MarkdownDoc],
) -> None:
    workspace_id = workspace.workspace_of_project(uow, project_id)
    if event.workspace_id != workspace_id:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Export source event belongs to another workspace")
    now = ctx.clock.now()
    note_id = VaultNoteId(ctx.ids.new_id())
    provenance = _provenance(
        event, note_id, now, revision_id, run_id if kind == NoteKind.PLAN_ARCHIVED else None
    )
    doc = render(provenance)
    body = doc.text()
    if len(body.encode("utf-8")) > NOTE_BODY_MAX_BYTES:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Vault note projection exceeds the UTF-8 limit")
    repo = uow.repo(VaultNoteRepository)
    run_note = kind == NoteKind.RUN_FINISHED
    try:
        name = note_name(
            kind,
            date_utc=event.occurred_at,
            plan_alias=alias,
            event_id=event.id,
            run_key=event.stream_id.hex[:8] if run_note else "",
        )
    except ValidationFailed:
        # Legacy plan aliases can be unsuitable as Windows components.
        name = note_name(
            kind,
            date_utc=event.occurred_at,
            plan_alias="plan",
            event_id=event.id,
            run_key=event.stream_id.hex[:8] if run_note else "",
        )
    note = VaultNote(
        id=note_id,
        workspace_id=workspace_id,
        project_id=project_id,
        kind=kind,
        event_id=event.id,
        source_id=event.stream_id,
        name=name,
        subfolder="runs" if run_note else "plans",
        body=body,
        body_digest=doc.digest(),
        state=VaultNoteState.PENDING,
        created_at=now,
    )
    if repo.add(note):
        uow.record(VaultNoteQueued(note))
    else:
        repo.by_event(event.id, kind)


def _provenance(
    event: EventEnvelope, note_id: VaultNoteId, now: datetime, revision_id: UUID | None, run_id: UUID | None
) -> Fields:
    fields: Fields = (
        ("note_id", str(note_id)),
        ("event_id", str(event.id)),
        ("occurred_at", iso_utc(event.occurred_at)),
        ("materialized_at", iso_utc(now)),
        ("render_version", 1),
    )
    if revision_id is not None:
        fields += (("revision_id", str(revision_id)),)
    if run_id is not None:
        fields += (("run_id", str(run_id)),)
    return (*fields, ("classification", "restricted"))


def plan_archived_note(event: EventEnvelope, ctx: SubscriberContext, uow: UnitOfWork) -> None:
    kind = NoteKind.PLAN_ARCHIVED
    if uow.repo(VaultNoteRepository).by_event(event.id, kind) is not None:
        return
    plan = planning.get_plan_summary(uow, PlanId(event.stream_id))
    project_id = ProjectId(plan.project_id)
    if not _notes(ctx, project_id).plan_archived:
        return
    view = build_plan_view(uow, plan)
    _queue(
        event,
        ctx,
        uow,
        kind=kind,
        project_id=project_id,
        alias=view.alias,
        revision_id=view.revision_id,
        run_id=view.run_id,
        render=lambda fields: render_plan_note(view, occurred_at=event.occurred_at, provenance=fields),
    )


def run_finished_note(event: EventEnvelope, ctx: SubscriberContext, uow: UnitOfWork) -> None:
    kind = NoteKind.RUN_FINISHED
    if uow.repo(VaultNoteRepository).by_event(event.id, kind) is not None:
        return
    run_id = RunId(event.stream_id)
    summary = get_run_summary(uow, run_id)
    project_id = ProjectId(UUID(str(summary["project_id"])))
    flag = _notes(ctx, project_id).run_finished
    if flag == "off" or (flag == "failed_only" and summary["status"] == "succeeded"):
        return
    view = build_run_view(uow, run_id, summary=summary)
    _queue(
        event,
        ctx,
        uow,
        kind=kind,
        project_id=project_id,
        alias=view.alias,
        revision_id=UUID(str(summary["revision_id"])),
        run_id=run_id,
        render=lambda fields: render_run_report(view, variant="summary", provenance=fields),
    )


SUBSCRIBERS = (
    SubscriberSpec(
        "exports.plan_archived_note",
        frozenset({"urn:skm:planning:event:plan-archived:v1"}),
        plan_archived_note,
        isolation=Isolation.REPEATABLE_READ,
    ),
    SubscriberSpec(
        "exports.run_finished_note",
        frozenset({"urn:skm:execution:event:run-finished:v1"}),
        run_finished_note,
        isolation=Isolation.REPEATABLE_READ,
    ),
)
