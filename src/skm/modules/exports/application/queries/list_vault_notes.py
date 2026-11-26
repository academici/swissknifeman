"""Read project queue metadata and delivery receipts after live source admission."""

from __future__ import annotations

from typing import TYPE_CHECKING

from skm.application_bus.registry import QuerySpec
from skm.kernel.ids import ProjectId, ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.exports.domain.markdown import iso_utc
from skm.modules.exports.domain.note import delivery_deadline
from skm.modules.exports.generated.queries import ListVaultNotes
from skm.modules.exports.generated.views import VaultNoteListItemView, VaultNotesView
from skm.modules.exports.ports import VaultNoteRepository

from .list_pending_notes import accessible_source, load_note_settings, page_cursor, page_start

if TYPE_CHECKING:
    from skm.application_bus.context import QueryContext
    from skm.kernel.ports_uow import UnitOfWork


def handle(query: ListVaultNotes, ctx: QueryContext, uow: UnitOfWork) -> VaultNotesView:
    repo = uow.repo(VaultNoteRepository)
    cursor_scope = (query.project_id,)
    page = repo.list(
        ProjectId(query.project_id), after=page_start(query.after, cursor_scope), limit=query.limit or 50
    )
    ttl = load_note_settings(ctx.config).pending_ttl_days
    items = tuple(
        VaultNoteListItemView.from_json(
            {
                "note_id": str(note.id),
                "kind": note.kind.value,
                "name": note.name,
                "state": note.state.value,
                "generation": note.generation,
                "created_at": iso_utc(note.created_at),
                "requeued_at": iso_utc(note.requeued_at) if note.requeued_at is not None else None,
                "delivery_deadline": iso_utc(delivery_deadline(note, ttl)),
                "writes": [
                    {
                        "note_id": str(note.id),
                        "vault_id": str(w.vault_id),
                        "generation": w.generation,
                        "host_id": str(w.host_id),
                        "relative_path": w.relative_path,
                        "outcome": w.outcome,
                        "expected_digest": w.expected_digest,
                        "observed_digest": w.observed_digest,
                        "written_at": iso_utc(w.written_at),
                    }
                    for w in repo.writes(note.id)
                ],
            }
        )
        for note in page.items
        if accessible_source(ctx, uow, note, delivery=False) is not None
    )
    cursor = page_cursor(page.items[-1], cursor_scope) if page.has_more else None
    return VaultNotesView(items, cursor, page.has_more)


SPEC = QuerySpec(
    name="exports.list_vault_notes",
    dto=ListVaultNotes,
    result=VaultNotesView,
    permission="plan.read",
    scope_of=lambda q: ScopeRef(ScopeKind.PROJECT, ScopeId(q.project_id)),
    handler=handle,
)
