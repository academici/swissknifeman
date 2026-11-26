"""Artifacts row codecs, cursor decoding and PostgreSQL write guards.

Repositories use ``file_from_row(row)`` for checked storage decoding and
``in_savepoint(connection, write)`` to preserve the surrounding UoW on conflicts.
Connection lifecycle and commits remain with the caller.
"""

from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Final, Literal, cast
from uuid import UUID

import psycopg

from skm.adapters.postgres.errors import translate_pg_error
from skm.adapters.postgres.jsonb import require_aware
from skm.adapters.postgres.pagination import decode_cursor
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, InternalError, NotFound, ValidationFailed
from skm.kernel.ids import FileVersionId, PrincipalId, ProjectId, WorkspaceId
from skm.kernel.json_types import JsonValue
from skm.modules.artifacts.domain.access_grant import AccessGrant, AccessGrantId, GrantReason
from skm.modules.artifacts.domain.blob import (
    Blob,
    BlobAvailability,
    BlobId,
    BlobLocation,
    ContentDigest,
    LocationState,
)
from skm.modules.artifacts.domain.classification import Classification
from skm.modules.artifacts.domain.content_safety import (
    SafetyFinding,
    SafetyLevel,
    SafetyReport,
    SafetyRule,
    is_safety_rule,
)
from skm.modules.artifacts.domain.file import File, FileId, FileOrigin, FileState
from skm.modules.artifacts.domain.file_version import FileVersion, VersionSource
from skm.modules.artifacts.domain.staged_blob import StagedBlob, StagedBlobId

__all__ = [
    "access_grant_from_row",
    "bad_cursor",
    "blob_from_row",
    "blob_location_from_row",
    "ensure_kept",
    "exists",
    "file_from_row",
    "file_keyset",
    "file_version_from_row",
    "hex_of",
    "in_savepoint",
    "not_found",
    "opt_aware",
    "run",
    "safety_to_json",
    "source_to_json",
    "staged_blob_from_row",
    "version_keyset",
]

type _Row = tuple[object, ...]
type _SourceKind = Literal["upload", "evidence", "import", "capture", "generated"]

_SOURCE_KINDS: Final[frozenset[str]] = frozenset({"upload", "evidence", "import", "capture", "generated"})
_SAVEPOINT: Final = "SAVEPOINT skm_artifacts_sp"
_ROLLBACK_SP: Final = "ROLLBACK TO SAVEPOINT skm_artifacts_sp"
_RELEASE_SP: Final = "RELEASE SAVEPOINT skm_artifacts_sp"


def run[T](call: Callable[[], T]) -> T:
    """Translate driver errors while preserving the original exception as the cause."""
    try:
        return call()
    except psycopg.Error as exc:
        raise translate_pg_error(exc) from exc


def in_savepoint[T](conn: psycopg.Connection, call: Callable[[], T]) -> T:
    """Run a write in the caller's transaction, rolling back only its savepoint on failure."""
    run(lambda: conn.execute(_SAVEPOINT))
    try:
        value = call()
    except BaseException:
        try:
            conn.execute(_ROLLBACK_SP)
            conn.execute(_RELEASE_SP)
        except psycopg.Error:
            pass
        raise
    run(lambda: conn.execute(_RELEASE_SP))
    return value


def not_found(kind: str, ref: object) -> NotFound:
    return NotFound(ErrorCode.NOT_FOUND, f"{kind} not found", details={"kind": kind, "ref": str(ref)})


def exists(kind: str, **details: str) -> Conflict:
    return Conflict(ErrorCode.ALREADY_EXISTS, f"{kind} already exists", details={"kind": kind, **details})


def bad_cursor() -> ValidationFailed:
    return ValidationFailed(ErrorCode.SCHEMA_INVALID, "invalid page cursor", details={"field": "after"})


def _damaged(table: str, ref: object, exc: Exception) -> InternalError:
    error = InternalError(
        ErrorCode.INTERNAL_ERROR,
        f"skm_artifacts.{table} row is malformed",
        details={"table": f"skm_artifacts.{table}", "id": str(ref)},
    )
    error.__cause__ = exc
    return error


def ensure_kept(kind: str, current: object, after: object, fields: Sequence[str]) -> None:
    changed = [name for name in fields if getattr(current, name) != getattr(after, name)]
    if changed:
        raise ValueError(f"a stored {kind} keeps its {', '.join(changed)}")


def opt_aware(value: datetime | None) -> datetime | None:
    return None if value is None else require_aware(value)


def hex_of(digest: ContentDigest) -> str:
    return digest.value.removeprefix("sha256:")


def _digest_of(text: str) -> ContentDigest:
    return ContentDigest(f"sha256:{text}")


def staged_blob_from_row(row: _Row) -> StagedBlob:
    try:
        return StagedBlob(
            StagedBlobId(cast("UUID", row[0])),
            WorkspaceId(cast("UUID", row[1])),
            _digest_of(cast("str", row[2])),
            cast("int", row[3]),
            cast("str", row[4]),
            cast("str", row[5]),
            cast("str", row[6]),
            cast("str", row[7]),
            PrincipalId(cast("UUID", row[8])),
            cast("datetime", row[9]),
            cast("datetime", row[10]),
            cast("datetime | None", row[11]),
            cast("str | None", row[12]),
        )
    except (TypeError, ValueError, ValidationFailed) as exc:
        raise _damaged("staged_blobs", row[0], exc) from exc


def blob_from_row(row: _Row) -> Blob:
    try:
        return Blob(
            BlobId(cast("UUID", row[0])),
            WorkspaceId(cast("UUID", row[1])),
            _digest_of(cast("str", row[2])),
            cast("int", row[3]),
            cast("str", row[4]),
            BlobAvailability(cast("str", row[5])),
            cast("datetime", row[6]),
            cast("datetime | None", row[7]),
        )
    except (TypeError, ValueError, ValidationFailed) as exc:
        raise _damaged("blobs", row[0], exc) from exc


def blob_location_from_row(row: _Row) -> BlobLocation:
    try:
        return BlobLocation(
            BlobId(cast("UUID", row[0])),
            cast("str", row[1]),
            cast("str", row[2]),
            cast("str | None", row[3]),
            LocationState(cast("str", row[4])),
            cast("datetime | None", row[5]),
        )
    except (TypeError, ValueError, ValidationFailed) as exc:
        raise _damaged("blob_locations", f"{row[0]}/{row[1]}", exc) from exc


def file_from_row(row: _Row) -> File:
    try:
        return File(
            FileId(cast("UUID", row[0])),
            WorkspaceId(cast("UUID", row[1])),
            None if row[2] is None else ProjectId(cast("UUID", row[2])),
            cast("str", row[3]),
            FileOrigin(cast("str", row[4])),
            Classification(cast("str", row[5])),
            None if row[6] is None else FileVersionId(cast("UUID", row[6])),
            FileState(cast("str", row[7])),
            cast("int", row[8]),
            cast("datetime", row[9]),
            PrincipalId(cast("UUID", row[10])),
        )
    except (TypeError, ValueError, ValidationFailed) as exc:
        raise _damaged("files", row[0], exc) from exc


def source_to_json(source: VersionSource) -> dict[str, JsonValue]:
    captured = opt_aware(source.captured_at)
    return {
        "kind": source.kind,
        "ref": source.ref,
        "captured_at": None if captured is None else captured.isoformat(),
    }


def _source_from_json(raw: object) -> VersionSource:
    if not isinstance(raw, dict):
        raise TypeError("source must be a JSON object")
    body = cast("dict[str, object]", raw)
    kind, ref, captured_raw = body.get("kind"), body.get("ref"), body.get("captured_at")
    if not isinstance(kind, str) or kind not in _SOURCE_KINDS:
        raise ValueError("invalid source.kind")
    if ref is not None and not isinstance(ref, str):
        raise TypeError("invalid source.ref")
    captured_at: datetime | None = None
    if captured_raw is not None:
        if not isinstance(captured_raw, str):
            raise TypeError("invalid source.captured_at")
        captured_at = datetime.fromisoformat(captured_raw)
        if captured_at.utcoffset() is None:
            raise ValueError("naive source.captured_at")
    return VersionSource(kind=cast("_SourceKind", kind), ref=ref, captured_at=captured_at)


def safety_to_json(safety: SafetyReport) -> dict[str, JsonValue]:
    return {
        "findings": [f.to_json() for f in safety.findings],
        "acknowledged": list(safety.acknowledged),
        "binary": safety.binary,
    }


def _safety_from_json(raw: object) -> SafetyReport:
    if not isinstance(raw, dict):
        raise TypeError("safety must be a JSON object")
    body = cast("dict[str, object]", raw)
    findings_raw, ack_raw, binary = body.get("findings"), body.get("acknowledged"), body.get("binary")
    if not isinstance(findings_raw, list) or not isinstance(ack_raw, list) or not isinstance(binary, bool):
        raise TypeError("invalid safety shape")
    findings: list[SafetyFinding] = []
    for item in cast("list[object]", findings_raw):
        if not isinstance(item, dict):
            raise TypeError("finding must be an object")
        entry = cast("dict[str, object]", item)
        rule, level, detail = entry.get("rule"), entry.get("level"), entry.get("detail")
        line, pointer = entry.get("line"), entry.get("pointer")
        if not is_safety_rule(rule) or not isinstance(level, str) or not isinstance(detail, str):
            raise TypeError("invalid finding fields")
        if line is not None and (isinstance(line, bool) or not isinstance(line, int)):
            raise TypeError("invalid finding.line")
        if pointer is not None and not isinstance(pointer, str):
            raise TypeError("invalid finding.pointer")
        findings.append(SafetyFinding(rule, SafetyLevel(level), detail, line, pointer))
    acknowledged: list[SafetyRule] = []
    for ack in cast("list[object]", ack_raw):
        if not is_safety_rule(ack):
            raise TypeError("invalid safety.acknowledged")
        acknowledged.append(ack)
    return SafetyReport(tuple(findings), tuple(acknowledged), binary)


def file_version_from_row(row: _Row) -> FileVersion:
    try:
        return FileVersion(
            FileVersionId(cast("UUID", row[0])),
            WorkspaceId(cast("UUID", row[1])),
            FileId(cast("UUID", row[2])),
            cast("int", row[3]),
            BlobId(cast("UUID", row[4])),
            cast("str", row[5]),
            cast("str | None", row[6]),
            cast("str", row[7]),
            _source_from_json(row[8]),
            _safety_from_json(row[9]),
            PrincipalId(cast("UUID", row[10])),
            cast("datetime", row[11]),
        )
    except (TypeError, ValueError, ValidationFailed) as exc:
        raise _damaged("file_versions", row[0], exc) from exc


def access_grant_from_row(row: _Row) -> AccessGrant:
    try:
        return AccessGrant(
            AccessGrantId(cast("UUID", row[0])),
            WorkspaceId(cast("UUID", row[1])),
            PrincipalId(cast("UUID", row[2])),
            FileVersionId(cast("UUID", row[3])),
            GrantReason(cast("str", row[4])),
            cast("str", row[5]),
            cast("datetime", row[6]),
            cast("datetime", row[7]),
            cast("datetime | None", row[8]),
        )
    except (TypeError, ValueError, ValidationFailed) as exc:
        raise _damaged("access_grants", row[0], exc) from exc


def file_keyset(after: str | None, *, digest: str) -> tuple[datetime | None, UUID | None]:
    """Decode the created-at/id keyset of a filter-bound file listing."""
    after_at: datetime | None = None
    after_id: UUID | None = None
    if after is not None:
        values = decode_cursor(after, expected_query_digest=digest).sort_values
        if len(values) != 2 or not all(isinstance(v, str) for v in values):
            raise bad_cursor()
        texts = cast("tuple[str, str]", values)
        try:
            parsed = datetime.fromisoformat(texts[0])
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise bad_cursor()
            after_at, after_id = parsed, UUID(texts[1])
        except ValueError:
            raise bad_cursor() from None
    return after_at, after_id


def version_keyset(after: str | None, *, digest: str) -> int | None:
    """Decode the positive version number of a file-bound version listing."""
    after_no: int | None = None
    if after is not None:
        values = decode_cursor(after, expected_query_digest=digest).sort_values
        if len(values) != 1:
            raise bad_cursor()
        raw = values[0]
        if isinstance(raw, int) and not isinstance(raw, bool):
            after_no = raw
        elif isinstance(raw, str) and raw.isdecimal():
            after_no = int(raw)
        else:
            raise bad_cursor()
        if after_no < 1:
            raise bad_cursor()
    return after_no
