"""Admit vault deliveries using current scope, host binding and source permissions."""

from __future__ import annotations

import base64
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from struct import Struct
from typing import TYPE_CHECKING
from uuid import UUID

from skm.application_bus.registry import QuerySpec
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, NotFound, ValidationFailed
from skm.kernel.ids import HostId, ProjectId, ScopeId, WorkspaceId
from skm.kernel.ports_uow import Surface
from skm.kernel.scopes import ScopeKind, ScopeRef, ScopeRegistry
from skm.modules.exports.domain.frontmatter import FrontmatterValue, read
from skm.modules.exports.domain.markdown import NOTE_BODY_MAX_BYTES
from skm.modules.exports.domain.note import NoteKind, VaultNote
from skm.modules.exports.generated.queries import ListPendingNotes
from skm.modules.exports.generated.settings import ExportsNotesSettings, ExportsSettings
from skm.modules.exports.generated.views import PendingNotesView, PendingNoteView
from skm.modules.exports.ports import (
    PENDING_SCAN_LIMIT,
    Cursor,
    NoteKey,
    VaultNoteRepository,
    VaultRequestMeta,
    note_key,
)
from skm.modules.workspace import public as workspace

if TYPE_CHECKING:
    from skm.application_bus.context import CommandContext, QueryContext
    from skm.kernel.ports_uow import UnitOfWork
    from skm.platform.config.effective import EffectiveConfig

_MAX_PAGE_BYTES = 2 * 1024 * 1024
_TTL_VALIDATOR = "exports.notes_ttl_order"
_PENDING = "exports.notes.pending_ttl_days"
_RETENTION = "exports.notes.retention_days"

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_MICROSECOND = timedelta(microseconds=1)
_ROW_KEY = Struct("!q16s")
_NONCE_SIZE = 16
_TAG_SIZE = 32
_TOKEN_SIZE = _NONCE_SIZE + _ROW_KEY.size + _TAG_SIZE
_TOKEN_LENGTH = (_TOKEN_SIZE + 2) // 3 * 4
# Continuations belong to a serving process. Both keys are independent and never leave it.
_CURSOR_PAD_KEY = secrets.token_bytes(32)
_CURSOR_TAG_KEY = secrets.token_bytes(32)


def _cursor_tag(scope: tuple[UUID, ...], sealed: bytes) -> bytes:
    context = b"skm.exports.notes.v1\x00" + b"".join(identifier.bytes for identifier in scope)
    return hmac.digest(_CURSOR_TAG_KEY, context + sealed, "sha256")


def _mask_row_key(nonce: bytes, value: bytes) -> bytes:
    # The fixed-size row key fits in a single HMAC block. A fresh nonce gives it a fresh pad.
    pad = hmac.digest(_CURSOR_PAD_KEY, nonce, "sha256")[: _ROW_KEY.size]
    return bytes(left ^ right for left, right in zip(value, pad, strict=True))


def page_start(after: Cursor | None, scope: tuple[UUID, ...]) -> NoteKey | None:
    if after is None:
        return None
    try:
        if len(after) != _TOKEN_LENGTH:
            raise ValueError
        token = base64.b64decode(after, altchars=b"-_", validate=True)
        if len(token) != _TOKEN_SIZE or base64.urlsafe_b64encode(token).decode("ascii") != after:
            raise ValueError
        sealed, tag = token[:-_TAG_SIZE], token[-_TAG_SIZE:]
        if not hmac.compare_digest(tag, _cursor_tag(scope, sealed)):
            raise ValueError
    except ValueError:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Invalid vault notes cursor") from None
    nonce, encrypted = sealed[:_NONCE_SIZE], sealed[_NONCE_SIZE:]
    micros, identifier = _ROW_KEY.unpack(_mask_row_key(nonce, encrypted))
    return _EPOCH + micros * _MICROSECOND, UUID(bytes=identifier)


def page_cursor(note: VaultNote, scope: tuple[UUID, ...]) -> Cursor:
    stamp, identifier = note_key(note)
    payload = _ROW_KEY.pack((stamp - _EPOCH) // _MICROSECOND, identifier.bytes)
    nonce = secrets.token_bytes(_NONCE_SIZE)
    sealed = nonce + _mask_row_key(nonce, payload)
    return base64.urlsafe_b64encode(sealed + _cursor_tag(scope, sealed)).decode("ascii")


def load_note_settings(config: EffectiveConfig) -> ExportsNotesSettings:
    invalid = config.invalid_keys().get(_PENDING)
    if invalid is not None and invalid.validator == _TTL_VALIDATOR and not invalid.blocked_by:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            invalid.message,
            details={"validator": _TTL_VALIDATOR, "keys": [_PENDING, _RETENTION]},
        )
    return config.section(ExportsSettings).notes


def holds(
    ctx: QueryContext | CommandContext,
    uow: UnitOfWork,
    permission: str,
    kind: ScopeKind,
    identifier: UUID,
    *,
    project_id: ProjectId | None = None,
) -> bool:
    try:
        chain = uow.repo(ScopeRegistry).ancestors(ScopeId(identifier))
    except NotFound:
        return False
    if not chain or chain[-1].kind != kind:
        return False
    if project_id is not None and not any(
        record.id == project_id and record.kind == ScopeKind.PROJECT for record in chain
    ):
        return False
    return ctx.allows is not None and ctx.allows(permission, chain)


def validate_host(
    ctx: QueryContext | CommandContext,
    uow: UnitOfWork,
    workspace_id: WorkspaceId,
    *,
    host_id: HostId | None = None,
    project_id: ProjectId | None = None,
) -> HostId:
    claimed = ctx.meta.host_id if isinstance(ctx.meta, VaultRequestMeta) else None
    if ctx.actor.grant is not None and ctx.actor.grant.kind == "assignment":
        raise Forbidden(ErrorCode.FORBIDDEN, "Vault delivery requires a host credential")
    if ctx.actor.kind == PrincipalKind.WORKER:
        binding = workspace.worker_for_principal(uow, ctx.actor.principal_id)
        if claimed is None and ctx.meta.surface is Surface.API and ctx.actor.grant is not None:
            claimed = binding.host_id if binding is not None else None
        if (
            claimed is None
            or binding is None
            or binding.state == "retired"
            or binding.workspace_id != workspace_id
            or binding.host_id != claimed
            or (host_id is not None and host_id != claimed)
        ):
            raise Forbidden(ErrorCode.FORBIDDEN, "Vault delivery host does not match worker binding")
    elif claimed is None or (host_id is not None and claimed != host_id):
        raise Forbidden(ErrorCode.FORBIDDEN, "Vault delivery requires matching host metadata")
    actual = HostId(claimed)
    if not uow.repo(VaultNoteRepository).active_checkout(workspace_id, actual, project_id):
        raise Forbidden(ErrorCode.FORBIDDEN, "Vault delivery requires an active checkout")
    return actual


def accessible_source(
    ctx: QueryContext | CommandContext,
    uow: UnitOfWork,
    note: VaultNote,
    *,
    delivery: bool,
) -> dict[str, FrontmatterValue] | None:
    if delivery and not holds(ctx, uow, "export.run", ScopeKind.PROJECT, note.project_id):
        return None
    fields = read(note.body, max_bytes=NOTE_BODY_MAX_BYTES)
    if fields is None:
        return None
    provenance = dict(fields)
    if note.kind == NoteKind.RUN_FINISHED:
        return (
            provenance
            if holds(ctx, uow, "run.read", ScopeKind.RUN, note.source_id, project_id=note.project_id)
            else None
        )
    if not holds(ctx, uow, "plan.read", ScopeKind.PLAN, note.source_id, project_id=note.project_id):
        return None
    run_id = provenance.get("run_id")
    if run_id is not None:
        try:
            pinned_run = UUID(str(run_id))
        except ValueError:
            return None
        if not holds(ctx, uow, "run.read", ScopeKind.RUN, pinned_run, project_id=note.project_id):
            return None
    return provenance


def handle(query: ListPendingNotes, ctx: QueryContext, uow: UnitOfWork) -> PendingNotesView:
    workspace_id = WorkspaceId(query.workspace_id)
    workspace.require_active_workspace(uow, workspace_id)
    host_id = validate_host(ctx, uow, workspace_id, host_id=HostId(query.host_id))
    repo = uow.repo(VaultNoteRepository)
    cursor_scope = (workspace_id, host_id, query.vault_id)
    candidates = repo.pending_for_host(
        workspace_id,
        host_id,
        query.vault_id,
        now=ctx.clock.now(),
        after=page_start(query.after, cursor_scope),
        ttl_days=load_note_settings(ctx.config).pending_ttl_days,
        scan_limit=PENDING_SCAN_LIMIT,
    )
    used = 0
    last_scanned = None
    items: list[PendingNoteView] = []
    for note in candidates.items:
        provenance = accessible_source(ctx, uow, note, delivery=True)
        if provenance is not None:
            size = len(note.body.encode("utf-8"))
            if len(items) == query.limit or used + size > _MAX_PAGE_BYTES:
                cursor = page_cursor(last_scanned, cursor_scope) if last_scanned is not None else None
                return PendingNotesView(tuple(items), cursor, True)
            used += size
            refs = tuple(
                {"kind": kind, "id": str(provenance[field])}
                for kind, field in (("revision", "revision_id"), ("run", "run_id"))
                if field in provenance
            )
            items.append(
                PendingNoteView(
                    note.id,
                    note.project_id,
                    note.source_id,
                    note.kind.value,
                    note.name,
                    note.subfolder,
                    note.body,
                    note.body_digest,
                    note.event_id,
                    note.generation,
                    "restricted",
                    refs,
                )
            )
        last_scanned = note
    cursor = page_cursor(last_scanned, cursor_scope) if candidates.has_more and last_scanned else None
    return PendingNotesView(tuple(items), cursor, candidates.has_more)


SPEC = QuerySpec(
    name="exports.list_pending_notes",
    dto=ListPendingNotes,
    result=PendingNotesView,
    permission="export.run",
    scope_of=lambda q: ScopeRef(ScopeKind.WORKSPACE, ScopeId(q.workspace_id)),
    handler=handle,
)
