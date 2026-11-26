"""Deliver immutable notes to the bound local vault and attest durable observations."""

from __future__ import annotations

import errno
import json
from collections.abc import Iterator, Mapping
from dataclasses import fields
from hashlib import sha256
from typing import TYPE_CHECKING, Literal, NotRequired, TypedDict, cast
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable, Conflict, PreconditionFailed, SkmError, ValidationFailed
from skm.modules.exports.domain.frontmatter import read
from skm.modules.exports.domain.markdown import NOTE_BODY_MAX_BYTES
from skm.modules.exports.domain.note import validate_component, validate_relative_path
from skm.modules.exports.generated.settings import ExportsNotesSettings
from skm.modules.exports.public import (
    ListPendingNotes,
    PendingNotesView,
    PendingNoteView,
    RecordNoteWritten,
    RecordNoteWrittenResult,
)

from .locate_vault import Budget, Catalog, HostSettings, discover, vault_settings

if TYPE_CHECKING:
    from skm.application_bus.host import HostContext
    from skm.kernel.json_types import JsonObject, JsonValue

    from .locate_vault import VaultBackend

__all__ = ["run"]

_JOURNAL_MAX_BYTES = 10 << 20
_JOURNAL_MAX_ROWS = 10_000
_LIMIT = 100
_HEAD = 8192
_RESULTS = ("created", "verified_existing", "modified_existing", "blocked", "expired", "errors", "preview")


type Outcome = Literal["created", "verified_existing", "modified_existing"]
type Classification = Literal["available", "verified_existing", "modified_existing", "foreign"]


class Entry(TypedDict):
    note_id: str
    vault_id: str
    workspace_id: str
    generation: int
    body_digest: str
    frozen_path: str | None
    outcome_unknown: bool
    attempts: int
    next_attempt_at: float
    reason: str | None
    blocked_until_input_change: bool
    blocked_input: NotRequired[str]
    blocked_code: NotRequired[str]
    blocked_path: NotRequired[str | None]
    ack: JsonObject | None
    ack_key: str | None


class Journal:
    def __init__(self, fs: VaultBackend, vault_id: UUID, workspace: str, *, dry_run: bool) -> None:
        self.fs, self.name, self.dry_run = fs.state(), f"vault-{vault_id}.journal", dry_run
        self.progress = f"vault-{vault_id}-{workspace}.cursor"
        raw = self.fs.read_bounded(self.name, max_bytes=_JOURNAL_MAX_BYTES)
        try:
            data: dict[str, object] = json.loads(raw) if raw is not None else {"entries": {}}
            entries, cursors, resume = data["entries"], data.get("cursors", {}), data.get("resume", {})
            if not all(isinstance(part, dict) for part in (entries, cursors, resume)):
                raise ValueError
            self.entries = cast("dict[str, Entry]", entries)
            self.cursors = cast("dict[str, str]", cursors)
            self.resume = cast("dict[str, str]", resume)
            if len(self.entries) > _JOURNAL_MAX_ROWS:
                raise ValueError
            self.cursor, self.restart = self.cursors.get(workspace), self.resume.get(workspace)
            checkpoint = None if dry_run else self.fs.read_bounded(self.progress, max_bytes=4096)
            if checkpoint is not None:
                position = json.loads(checkpoint)
                if not isinstance(position, list):
                    raise ValueError
                cursor, restart = cast("list[object]", position)
                if not all(item is None or isinstance(item, str) for item in (cursor, restart)):
                    raise ValueError
                self.cursor, self.restart = cast("str | None", cursor), cast("str | None", restart)
                self.cursors.pop(workspace, None)
                self.resume.pop(workspace, None)
        except (ValueError, KeyError, TypeError, RecursionError):
            raise BackendUnavailable(ErrorCode.BACKEND_UNAVAILABLE, "Vault journal is invalid") from None

    def checkpoint(self, cursor: str | None, resume: str | None = None) -> None:
        # Full retry journals must still be able to advance past unjournaled failures.
        self.fs.write_atomic(self.progress, json.dumps((cursor, resume)).encode(), replace=True)

    def save(self) -> None:
        if self.dry_run:
            return
        body = json.dumps(
            {"entries": self.entries, "cursors": self.cursors, "resume": self.resume}, separators=(",", ":")
        ).encode()
        if len(self.entries) > _JOURNAL_MAX_ROWS or len(body) > _JOURNAL_MAX_BYTES:
            raise BackendUnavailable(
                ErrorCode.BACKEND_UNAVAILABLE, "Vault journal is full", details={"reason": "journal_full"}
            )
        self.fs.write_atomic(self.name, body, replace=True)

    def put(self, key: str, entry: Entry | None) -> None:
        previous = self.entries.pop(key, None)
        if entry is not None:
            self.entries[key] = entry
        try:
            self.save()
        except (SkmError, OSError):
            if previous is None:
                self.entries.pop(key, None)
            else:
                self.entries[key] = previous
            raise


def _digest(data: bytes) -> str:
    return "sha256:" + sha256(data).hexdigest()


def _classify(note: PendingNoteView, data: bytes | None) -> tuple[Classification, str | None]:
    if data is None:
        return "available", None
    observed = _digest(data)
    if observed == note.body_digest:
        return "verified_existing", observed
    head = data[:_HEAD].replace(b"\r\n", b"\n")
    if len(data) <= _HEAD and head.endswith(b"\n---"):
        head += b"\n"
    end = head.find(b"\n---\n", 3)
    if head.startswith(b"---\n"):
        try:
            if end >= 0:
                header = head[: end + 5]
            else:
                # A truncated body can leave the identity lines intact.
                lines = head.split(b"\n")[1:]
                if len(data) > _HEAD:
                    lines.pop()
                lines = [line for line in lines if line.startswith((b"type: ", b"event_id: "))]
                header = b"\n".join((b"---", *lines, b"---", b""))
            metadata = dict(read(header.decode(), max_bytes=len(header)) or ())
            identifier = UUID(str(metadata.get("event_id")))
        except ValueError:
            return "foreign", observed
        types = (
            ("run_finished", "run-finished", "skm-run")
            if note.kind == "run_finished"
            else ("plan_archived", "plan-archived")
        )
        if identifier == note.event_id and metadata.get("type") in types:
            return "modified_existing", observed
    return "foreign", observed


def _note_key(note: PendingNoteView) -> str:
    return f"{note.note_id}:{note.generation}"


class Delivery:
    def __init__(
        self,
        ctx: HostContext,
        fs: VaultBackend,
        catalog: Catalog,
        journal: Journal,
        vault_id: UUID,
        workspace_id: UUID,
    ) -> None:
        self.ctx, self.fs, self.catalog, self.journal = ctx, fs, catalog, journal
        self.vault_id, self.workspace_id = vault_id, workspace_id
        self.report: dict[str, list[JsonValue]] = {state: [] for state in _RESULTS}
        self.settings = self._settings("workspace", workspace_id)
        self.project_settings: dict[UUID, ExportsNotesSettings] = {}
        self.candidate_path: str | None = None
        self.saturated = False

    def _settings(self, level: str, identifier: UUID) -> ExportsNotesSettings:
        config = self.ctx.config
        for_scope = getattr(config, "for_scope", None)
        values = cast("HostSettings", for_scope(level, identifier) if for_scope else config)
        keys = (f"exports.notes.{field.name}" for field in fields(ExportsNotesSettings))
        return ExportsNotesSettings.from_settings(
            {key: value for key in keys if (value := values.get(key)) is not None}
        )

    def _read(self, path: str, *, durable: bool) -> bytes | None:
        self.catalog.budget.check(entries=1, size=NOTE_BODY_MAX_BYTES)
        data = self.fs.read_bounded(path, max_bytes=NOTE_BODY_MAX_BYTES, durable=durable)
        self.catalog.budget.check(size=len(data or b"") - NOTE_BODY_MAX_BYTES)
        return data

    def _guard(self, *, check_mapping: bool = False) -> None:
        self.catalog.budget.check()
        if self.fs.require_writer(self.ctx.host_id).vault_id != self.vault_id:
            raise PreconditionFailed(ErrorCode.INVALID_TRANSITION, "Vault identity changed during delivery")
        if check_mapping:
            self.catalog.check_unchanged()

    def _ack(self, key: str, entry: Entry, *, report: bool) -> None:
        payload = entry["ack"]
        if payload is None:
            raise RuntimeError("Receipt was not prepared")
        self._guard()
        command = RecordNoteWritten.from_json(payload)
        result = cast(
            "RecordNoteWrittenResult", self.ctx.client.dispatch(command, idempotency_key=entry["ack_key"])
        )
        if (result.note_id, result.vault_id, result.generation) != (
            command.note_id,
            command.vault_id,
            command.generation,
        ):
            raise BackendUnavailable(ErrorCode.BACKEND_UNAVAILABLE, "Vault receipt identity mismatch")
        self.journal.put(key, None)
        if report:
            self.report[command.outcome].append(
                {
                    "note_id": str(command.note_id),
                    "generation": command.generation,
                    "relative_path": command.relative_path,
                    "observed_digest": command.observed_digest,
                }
            )

    def _record(
        self, note: PendingNoteView, entry: Entry, outcome: Outcome, observed: str, path: str
    ) -> None:
        key = _note_key(note)
        if entry["ack"] is None:
            receipt = RecordNoteWritten(
                note.project_id,
                note.note_id,
                self.vault_id,
                path,
                note.generation,
                outcome,
                note.body_digest,
                observed,
            )
            entry = {
                **entry,
                "ack": receipt.to_json(),
                "ack_key": self.ctx.client.new_idempotency_key(),
                "outcome_unknown": True,
            }
            self.journal.put(key, entry)
        elif observed != entry["ack"]["observed_digest"]:
            raise _frozen_conflict()
        self._ack(key, entry, report=True)

    def _empty_entry(self, note: PendingNoteView) -> Entry:
        return {
            "note_id": str(note.note_id),
            "vault_id": str(self.vault_id),
            "workspace_id": str(self.workspace_id),
            "generation": note.generation,
            "body_digest": note.body_digest,
            "frozen_path": None,
            "outcome_unknown": False,
            "attempts": 0,
            "next_attempt_at": 0,
            "reason": None,
            "blocked_until_input_change": False,
            "ack": None,
            "ack_key": None,
        }

    def _preview(self, note: PendingNoteView, path: str, classification: Classification) -> None:
        self.report["preview"].append(
            {
                "note_id": str(note.note_id),
                "generation": note.generation,
                "project_id": str(note.project_id),
                "source_id": str(note.source_id),
                "kind": note.kind,
                "relative_path": path,
                "classification": note.classification,
                "disposition": classification,
                "nonportable_refs": cast("list[JsonValue]", [dict(item) for item in note.nonportable_refs]),
            }
        )

    def _publish(self, note: PendingNoteView, entry: Entry, path: str, body: bytes) -> bool:
        key = _note_key(note)
        self.catalog.budget.check(size=len(body))
        prepared: Entry = {**entry, "frozen_path": path, "outcome_unknown": True}
        self.journal.put(key, prepared)
        try:
            return self.fs.create_new(path, body)
        except SkmError as exc:
            if exc.details.get("outcome") == "failed_without_effect":
                self.journal.put(key, {**prepared, "outcome_unknown": False})
            raise

    def _candidate(
        self,
        note: PendingNoteView,
        entry: Entry,
        path: str,
        body: bytes,
        *,
        frozen: bool,
    ) -> bool:
        """Return false only for a foreign collision before any possible effect."""
        key = _note_key(note)
        self.candidate_path = path
        existing, observed = _classify(note, self._read(path, durable=frozen and not self.journal.dry_run))
        if existing == "foreign":
            if frozen:
                raise _frozen_conflict()
            return False
        if existing == "available" and frozen and entry["outcome_unknown"]:
            raise _frozen_conflict()
        if self.journal.dry_run:
            self._preview(note, path, existing)
            return True

        if frozen and existing == "available":
            self.catalog.find(note.project_id)
        self._guard(check_mapping=not frozen or existing == "available")
        if existing == "available":
            if self._publish(note, entry, path, body):
                self._record(note, self.journal.entries[key], "created", note.body_digest, path)
                return True
            existing, observed = _classify(note, self._read(path, durable=True))
            if existing == "foreign" and not frozen:
                self.journal.put(key, None)
                return False
        else:
            if not frozen:
                entry = {**entry, "frozen_path": path}
                self.journal.put(key, entry)
                existing, observed = _classify(note, self._read(path, durable=True))

        if existing in ("verified_existing", "modified_existing") and observed is not None:
            self._record(note, self.journal.entries[key], existing, observed, path)
            return True
        raise _frozen_conflict()

    def _attempt(self, note: PendingNoteView, entry: Entry) -> None:
        body = note.body.encode("utf-8")
        if len(body) > NOTE_BODY_MAX_BYTES or _digest(body) != note.body_digest:
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Materialized vault note body is invalid")
        if entry["body_digest"] != note.body_digest:
            raise _frozen_conflict()
        path = entry["frozen_path"]
        if path is not None:
            validate_relative_path(path)
            self._candidate(note, entry, path, body, frozen=True)
            return

        validate_component(note.name)
        if not note.name.endswith(".md"):
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Vault note name must end in .md")
        base = f"{self._folder(note)}/{note.name}"
        for path in self._suffixes(base):
            validate_relative_path(path)
            if self._candidate(note, entry, path, body, frozen=False):
                return
        self.candidate_path = base
        raise Conflict(ErrorCode.EXPORT_NOTE_NO_FREE_NAME, "Vault note name range is exhausted")

    def _folder(self, note: PendingNoteView) -> str:
        match = self.catalog.find(note.project_id)
        if match is None:
            return self.settings.fallback_folder
        if note.project_id not in self.project_settings:
            self.project_settings[note.project_id] = self._settings("project", note.project_id)
        settings = self.project_settings[note.project_id]
        subfolder = settings.plans_folder if note.subfolder == "plans" else settings.runs_folder
        return f"{match.folder}/{subfolder}"

    def _suffixes(self, path: str) -> Iterator[str]:
        for suffix in range(1, self.settings.max_suffix + 1):
            yield path if suffix == 1 else f"{path.removesuffix('.md')} ({suffix}).md"

    def _blocked_input(self, path: str | None, code: str, *, missing: bool = False) -> str:
        if path is None:
            return ""
        paths = self._suffixes(path) if code == ErrorCode.EXPORT_NOTE_NO_FREE_NAME else iter((path,))
        return self.catalog.path_versions(paths, missing=missing)

    def _still_blocked(self, entry: Entry, note: PendingNoteView | None = None) -> bool:
        if self.journal.dry_run or not entry["blocked_until_input_change"]:
            return False
        code = entry.get("blocked_code", "")
        path = entry.get("blocked_path")
        if entry.get("blocked_input") != self._blocked_input(path, code):
            return False
        if note is None:
            return True
        if code == ErrorCode.EXPORT_VAULT_PROJECT_UNKNOWN:
            return not self.catalog.mapping_valid(note.project_id)
        return (
            path is None or entry["frozen_path"] is not None or self._folder(note) == path.rpartition("/")[0]
        )

    def _failed(self, key: str, entry: Entry, exc: SkmError | OSError) -> None:
        code = exc.code if isinstance(exc, SkmError) else ErrorCode.BACKEND_UNAVAILABLE
        details: Mapping[str, JsonValue] = exc.details if isinstance(exc, SkmError) else {}
        reason = str(details.get("reason", code.value))
        if reason == "budget_exceeded":
            raise exc
        outcome = details.get("outcome")
        state = "blocked"
        if code == ErrorCode.INVALID_TRANSITION and "expir" in str(exc).lower():
            state = "expired"
        elif code in (ErrorCode.BACKEND_UNAVAILABLE, ErrorCode.OUTCOME_UNKNOWN) and reason != "journal_full":
            state = "errors"
            if isinstance(exc, OSError) and exc.errno in (errno.EACCES, errno.EPERM, errno.EROFS):
                state = "blocked"
        failure: JsonObject = {
            "note_id": entry["note_id"],
            "generation": entry["generation"],
            "relative_path": entry["frozen_path"],
            "code": code.value,
            "reason": reason,
            "outcome": outcome
            or ("outcome_unknown" if entry["outcome_unknown"] else "failed_without_effect"),
            **({"candidates": details["candidates"]} if "candidates" in details else {}),
        }
        self.report[state].append(failure)
        self.saturated |= reason == "journal_full"
        if self.journal.dry_run or reason == "journal_full":
            return
        attempts = entry["attempts"] + 1
        delay = min(3600.0, 30 * 2 ** min(attempts - 1, 7) * self.fs.retry_jitter())
        retry: Entry = {
            **entry,
            "attempts": attempts,
            "next_attempt_at": self.fs.retry_time() + delay if state == "errors" else 0.0,
            "reason": reason,
            "blocked_until_input_change": state != "errors",
        }
        if state != "errors":
            path = (entry["frozen_path"] or self.candidate_path) if state == "blocked" else None
            missing = entry["frozen_path"] is not None and code == ErrorCode.EXPORT_VAULT_PROJECT_UNKNOWN
            blocked_input = self._blocked_input(path, code, missing=missing)
            retry.update(blocked_path=path, blocked_code=code.value, blocked_input=blocked_input)
        try:
            self.journal.put(key, retry)
        except BackendUnavailable as error:
            if error.details.get("reason") != "journal_full":
                raise
            self.saturated = True
            failure["retry"] = "journal_full"

    def deliver(self, note: PendingNoteView) -> None:
        key = _note_key(note)
        entry = self.journal.entries.get(key) or self._empty_entry(note)
        self.candidate_path = None
        try:
            waiting = not self.journal.dry_run and entry["next_attempt_at"] > self.fs.retry_time()
            if waiting or self._still_blocked(entry, note):
                self.report["blocked"].append(
                    {
                        "note_id": entry["note_id"],
                        "generation": entry["generation"],
                        "code": entry.get("blocked_code") if not waiting else None,
                        "reason": "retry_not_due" if waiting else entry["reason"],
                        "next_attempt_at": entry["next_attempt_at"],
                        "relative_path": entry["frozen_path"],
                        "outcome_unknown": entry["outcome_unknown"],
                    }
                )
                return
            self._attempt(note, entry)
        except (SkmError, OSError) as exc:
            self._failed(key, self.journal.entries.get(key, entry), exc)

    def recover_receipts(self, page: PendingNotesView) -> None:
        """Resolve lost acknowledgements for notes the ledger already excluded."""
        seen = {_note_key(note) for note in page.items}
        count = 0
        self.candidate_path = None
        for key, entry in tuple(self.journal.entries.items()):
            if count >= _LIMIT:
                return
            if (
                key in seen
                or entry["workspace_id"] != str(self.workspace_id)
                or entry["ack"] is None
                or entry["next_attempt_at"] > self.fs.retry_time()
            ):
                continue
            path = entry["frozen_path"]
            try:
                if self._still_blocked(entry):
                    continue
                count += 1
                if path is None:
                    raise _frozen_conflict()
                observed = self._read(path, durable=True)
                if observed is None or _digest(observed) != entry["ack"]["observed_digest"]:
                    raise _frozen_conflict()
                self._ack(key, entry, report=False)
            except (SkmError, OSError) as exc:
                self._failed(key, entry, exc)


def _frozen_conflict() -> PreconditionFailed:
    return PreconditionFailed(
        ErrorCode.INVALID_TRANSITION,
        "Frozen vault path requires reconciliation",
        details={"reason": "frozen_path_conflict"},
    )


def _drain(
    ctx: HostContext,
    request: JsonObject,
    fs: VaultBackend,
    catalog: Catalog,
    vault_id: UUID,
) -> JsonObject:
    try:
        workspace_id = UUID(str(request["workspace_id"]))
        limit = request.get("limit", _LIMIT)
        dry_run = request.get("dry_run", False)
        if type(limit) is not int or not 1 <= limit <= _LIMIT or type(dry_run) is not bool:
            raise ValueError
    except (KeyError, ValueError):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID, "Expected a workspace and a note limit from 1 to 100"
        ) from None

    journal = Journal(fs, vault_id, str(workspace_id), dry_run=dry_run)
    delivery = Delivery(ctx, fs, catalog, journal, vault_id, workspace_id)
    cursor = None if dry_run else journal.cursor
    try:
        page = cast(
            "PendingNotesView",
            ctx.client.ask(ListPendingNotes(workspace_id, ctx.host_id, vault_id, cursor, limit)),
        )
    except ValidationFailed as exc:
        if cursor is None or exc.code != ErrorCode.SCHEMA_INVALID:
            raise
        journal.checkpoint(None)
        return {**delivery.report, "partial": True, "reason": "cursor_reset", "has_more": True}

    reason = None
    items = page.items
    resume = journal.restart
    if resume is not None and not dry_run:
        index = next((i for i, note in enumerate(items) if _note_key(note) == resume), 0)
        items = items[index:] + items[:index]
    completed_page = False
    _position = 0
    try:
        for _position, note in enumerate(items):
            catalog.budget.check()
            delivery.deliver(note)
        completed_page = True
        if not dry_run:
            if cursor != page.next_cursor or resume is not None:
                journal.checkpoint(page.next_cursor)
            delivery.recover_receipts(page)
    except BackendUnavailable as exc:
        if exc.details.get("reason") != "budget_exceeded":
            raise
        reason = "budget_exceeded"
        if not dry_run and not completed_page and items:
            # Resume within the same page when one note uses up the whole tick.
            journal.checkpoint(cursor, _note_key(items[(_position + 1) % len(items)]))
    partial = bool(
        reason or any(delivery.report[key] for key in ("blocked", "expired", "errors", "modified_existing"))
    )
    return {
        **delivery.report,
        "partial": partial,
        "reason": reason or ("journal_full" if delivery.saturated else None),
        "has_more": page.next_cursor is not None or not completed_page,
        "dry_run": dry_run,
    }


def run(ctx: HostContext, request: JsonObject) -> JsonObject:
    settings = vault_settings(ctx.config)
    _, fs = discover(ctx, settings)
    budget = Budget(ctx, fs)
    identity = fs.require_writer(ctx.host_id)
    catalog = Catalog(fs, settings.projects_dir, budget)
    if request.get("dry_run") is True:
        return _drain(ctx, request, fs, catalog, identity.vault_id)
    with fs.lock(identity.vault_id, deadline_seconds=settings.lock_deadline_seconds):
        if fs.require_writer(ctx.host_id) != identity:
            raise PreconditionFailed(ErrorCode.INVALID_TRANSITION, "Vault identity changed before delivery")
        return _drain(ctx, request, fs, catalog, identity.vault_id)
