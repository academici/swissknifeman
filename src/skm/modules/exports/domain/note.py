"""Vault note identity, delivery windows and receipt invariants."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from typing import Literal, NewType
from unicodedata import normalize
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, PreconditionFailed, ValidationFailed
from skm.kernel.ids import EventId, HostId, ProjectId, WorkspaceId

from .markdown import utf8_prefix

VaultNoteId = NewType("VaultNoteId", UUID)


class NoteKind(StrEnum):
    PLAN_ARCHIVED = "plan_archived"
    RUN_FINISHED = "run_finished"


class VaultNoteState(StrEnum):
    PENDING = "pending"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True, kw_only=True)
class VaultNote:
    id: VaultNoteId
    workspace_id: WorkspaceId
    project_id: ProjectId
    kind: NoteKind
    event_id: EventId
    source_id: UUID
    name: str
    subfolder: Literal["plans", "runs"]
    body: str
    body_digest: str
    state: VaultNoteState
    generation: int = 1
    created_at: datetime
    requeued_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class VaultNoteWrite:
    note_id: VaultNoteId
    vault_id: UUID
    generation: int
    host_id: HostId
    relative_path: str
    outcome: Literal["created", "verified_existing", "modified_existing"]
    expected_digest: str
    observed_digest: str
    written_at: datetime


def clean_segment(text: str) -> str:
    cleaned = "".join("-" if char in "/\\\x7f" or ord(char) < 32 else char for char in text)
    return normalize("NFC", cleaned.strip().lstrip(".").strip())[:100].rstrip() or "plan"


def validate_component(value: str) -> None:
    stem = value.partition(".")[0].rstrip().upper()
    reserved = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
    reserved.update(f"{prefix}{n}" for prefix in ("COM", "LPT") for n in "123456789¹²³")
    if (
        not value
        or value.endswith((".", " "))
        or stem in reserved
        or any(c in '/\\<>:"|?*' or ord(c) < 32 or ord(c) == 127 for c in value)
    ):
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Invalid vault path component")


def note_name(kind: NoteKind, *, date_utc: date, plan_alias: str, event_id: UUID, run_key: str = "") -> str:
    date_utc = date_utc.astimezone(UTC).date() if isinstance(date_utc, datetime) else date_utc
    start = f"{date_utc.isoformat()} "
    end = f" {event_id.hex}.md"
    alias = clean_segment(plan_alias)
    if kind == NoteKind.PLAN_ARCHIVED:
        end = " archived" + end
    else:
        run = clean_segment(run_key)
        validate_component(run)
        run = utf8_prefix(run, 80).rstrip()
        end = f" run {run}" + end
    validate_component(alias)
    alias = utf8_prefix(alias, 240 - len((start + end).encode("utf-8"))).rstrip()
    name = start + alias + end
    validate_component(name)
    return name


def validate_relative_path(value: str) -> None:
    if not 1 <= len(value) <= 1024 or any(part in {"", ".", ".."} for part in value.split("/")):
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Expected a vault-relative path")
    for part in value.split("/"):
        validate_component(part)


def delivery_deadline(note: VaultNote, ttl_days: int) -> datetime:
    return (note.requeued_at or note.created_at) + timedelta(days=ttl_days)


def check_generation(note: VaultNote, expected: int) -> None:
    if note.generation != expected:
        raise Conflict(
            ErrorCode.VERSION_CONFLICT,
            "Vault note generation changed",
            details={"expected": expected, "actual": note.generation},
        )


def check_write(note: VaultNote, write: VaultNoteWrite, *, now: datetime, ttl_days: int) -> None:
    check_generation(note, write.generation)
    same_bytes = write.expected_digest == write.observed_digest
    if (
        note.state != VaultNoteState.PENDING
        or now >= delivery_deadline(note, ttl_days)
        or write.expected_digest != note.body_digest
        or same_bytes == (write.outcome == "modified_existing")
    ):
        raise PreconditionFailed(
            ErrorCode.INVALID_TRANSITION, "Vault note receipt conflicts with delivery state"
        )


def check_existing_write(existing: VaultNoteWrite, attempted: VaultNoteWrite) -> None:
    if existing != replace(attempted, written_at=existing.written_at):
        raise PreconditionFailed(
            ErrorCode.INVALID_TRANSITION, "Vault note receipt already recorded differently"
        )
