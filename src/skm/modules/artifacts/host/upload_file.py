"""``artifacts.host.upload_file``: symlink-safe host source read, streaming upload and file registration."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Final, Protocol, cast
from uuid import UUID

from skm.application_bus.host import HostContext
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.gateways import host_gateway
from skm.kernel.ids import ProjectId, WorkspaceId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.module_manifest import HostOperationSpec
from skm.modules.artifacts.domain.classification import Classification
from skm.modules.artifacts.domain.content_safety import Reject, SafetyRule, is_safety_rule, symlink_finding
from skm.modules.artifacts.domain.file import FileId, FileOrigin
from skm.modules.artifacts.domain.upload_rules import normalize_media_type, validate_filename
from skm.modules.artifacts.generated import commands as wire
from skm.modules.artifacts.generated.queries import GetFile
from skm.modules.artifacts.generated.results import AddFileResult, AddFileVersionResult
from skm.modules.artifacts.generated.views import GetFileView

__all__ = [
    "SPEC",
    "UploadFileOperation",
    "UploadSourceInfo",
    "UploadSourceReader",
    "run",
]

# Tuple layout: (original_filename, size_bytes, is_symlink, is_regular)
type UploadSourceInfo = tuple[str, int, bool, bool]


@host_gateway
class UploadSourceReader(Protocol):
    """Host gateway reading a local upload candidate without following symbolic links."""

    def open_source(self, path: str) -> AbstractContextManager[tuple[UploadSourceInfo, Iterable[bytes]]]: ...


class UploadFileOperation(Protocol):
    def __call__(self, ctx: HostContext, request: JsonObject) -> JsonObject: ...


@dataclass(frozen=True, slots=True)
class _ParsedUploadRequest:
    path: str
    workspace_id: WorkspaceId | None
    project_id: ProjectId | None
    file_id: FileId | None
    expected_row_version: int | None
    title: str | None
    origin: FileOrigin
    classification: Classification | None
    original_filename: str | None
    declared_media_type: str | None
    description: str
    acknowledge: tuple[SafetyRule, ...]
    expected_digest: str | None
    source: Mapping[str, Any]
    idempotency_key: str | None


def _opt_uuid(raw: object, field_name: str) -> UUID | None:
    if raw is None:
        return None
    if isinstance(raw, UUID):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            return UUID(raw)
        except ValueError:
            pass
    raise ValidationFailed(
        ErrorCode.SCHEMA_INVALID,
        f"{field_name} must be a canonical UUID",
        details={"field": field_name},
    )


def _parse_request(request: Mapping[str, JsonValue]) -> _ParsedUploadRequest:
    raw_path = request.get("path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "upload path is required",
            details={"field": "path", "reason": "path_required"},
        )
    ws_uuid = _opt_uuid(request.get("workspace_id"), "workspace_id")
    proj_uuid = _opt_uuid(request.get("project_id"), "project_id")
    file_uuid = _opt_uuid(request.get("file_id"), "file_id")
    if file_uuid is None and ws_uuid is None:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "workspace_id is required when creating a new file",
            details={"field": "workspace_id"},
        )

    raw_row_version = request.get("expected_row_version")
    expected_row_version: int | None = None
    if raw_row_version is not None:
        if isinstance(raw_row_version, bool) or not isinstance(raw_row_version, int) or raw_row_version < 1:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "expected_row_version must be a positive integer",
                details={"field": "expected_row_version"},
            )
        expected_row_version = raw_row_version

    raw_origin = request.get("origin", "upload")
    try:
        origin = FileOrigin(str(raw_origin))
    except ValueError:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            f"invalid file origin: {raw_origin!r}",
            details={"field": "origin"},
        ) from None

    raw_cls = request.get("classification")
    classification: Classification | None = None
    if raw_cls is not None:
        try:
            classification = Classification(str(raw_cls))
        except ValueError:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                f"invalid classification: {raw_cls!r}",
                details={"field": "classification"},
            ) from None

    raw_ack = request.get("acknowledge", ())
    if not isinstance(raw_ack, Sequence) or isinstance(raw_ack, str | bytes):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "acknowledge must be a sequence of safety rule identifiers",
            details={"field": "acknowledge"},
        )
    ack: list[SafetyRule] = []
    for item in cast("Sequence[object]", raw_ack):
        if not is_safety_rule(item):
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                f"unknown safety rule: {item!r}",
                details={"field": "acknowledge"},
            )
        ack.append(item)

    raw_source = request.get("source")
    source: Mapping[str, Any] = (
        cast("Mapping[str, Any]", raw_source) if isinstance(raw_source, Mapping) else {"kind": "upload"}
    )

    raw_media = request.get("declared_media_type")
    media_type = normalize_media_type(str(raw_media)) if isinstance(raw_media, str) and raw_media else None
    raw_title = request.get("title")
    title = str(raw_title) if isinstance(raw_title, str) and raw_title else None
    raw_orig_name = request.get("original_filename")
    orig_name = str(raw_orig_name) if isinstance(raw_orig_name, str) and raw_orig_name else None
    raw_digest = request.get("expected_digest")
    expected_digest = str(raw_digest) if isinstance(raw_digest, str) and raw_digest else None
    raw_idem = request.get("idempotency_key")
    idem_key = str(raw_idem) if isinstance(raw_idem, str) and raw_idem else None

    return _ParsedUploadRequest(
        path=raw_path,
        workspace_id=WorkspaceId(ws_uuid) if ws_uuid is not None else None,
        project_id=ProjectId(proj_uuid) if proj_uuid is not None else None,
        file_id=FileId(file_uuid) if file_uuid is not None else None,
        expected_row_version=expected_row_version,
        title=title,
        origin=origin,
        classification=classification,
        original_filename=orig_name,
        declared_media_type=media_type,
        description=str(request.get("description") or ""),
        acknowledge=tuple(ack),
        expected_digest=expected_digest,
        source=source,
        idempotency_key=idem_key,
    )


def run(ctx: HostContext, request: JsonObject) -> JsonObject:
    """Read a host file via ``UploadSourceReader``, stream-upload it and register the file or version."""
    ctx.cancel.raise_if_cancelled()
    if not isinstance(request, Mapping):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "upload request must be an object",
            details={"reason": "not_object"},
        )
    parsed = _parse_request(request)
    target_file_id = parsed.file_id
    reader = ctx.gateways.get(UploadSourceReader)

    with reader.open_source(parsed.path) as (info, chunks):
        source_filename, size_bytes, is_symlink, is_regular = info
        if is_symlink:
            raise Reject((symlink_finding(),), "not_acknowledged").error()
        if not is_regular:
            raise ValidationFailed(
                ErrorCode.INVALID_REFERENCE,
                "upload source must be a regular file",
                details={"reason": "not_regular", "path": parsed.path},
            )
        original_filename = validate_filename(parsed.original_filename or source_filename)

        workspace_id = parsed.workspace_id
        row_version = parsed.expected_row_version
        if target_file_id is not None and (workspace_id is None or row_version is None):
            existing = ctx.client.ask(GetFile(file_id=target_file_id))
            assert isinstance(existing, GetFileView)  # noqa: S101
            workspace_id = workspace_id or WorkspaceId(existing.workspace_id)
            row_version = row_version if row_version is not None else existing.row_version

        assert workspace_id is not None  # noqa: S101
        staged = ctx.client.upload_blob(
            workspace_id,
            chunks,
            size=size_bytes,
            expected_digest=parsed.expected_digest,
            media_type=parsed.declared_media_type,
        )

    idem = parsed.idempotency_key or ctx.client.new_idempotency_key()
    if target_file_id is None:
        add_cmd = wire.AddFile(
            workspace_id=workspace_id,
            project_id=parsed.project_id,
            title=parsed.title or original_filename,
            origin=wire.FileOrigin(parsed.origin.value),
            classification=(
                wire.Classification(parsed.classification.value)
                if parsed.classification is not None
                else None
            ),
            blob=wire.AddFileDefsStagedBlobRef(
                staged_blob_id=staged.staged_blob_id,
                workspace_id=staged.workspace_id,
                digest=staged.digest,
                size=staged.size,
                media_type=staged.media_type,
            ),
            original_filename=original_filename,
            declared_media_type=parsed.declared_media_type,
            description=parsed.description,
            source=wire.AddFileDefsVersionSource.from_json(dict(parsed.source)),
            acknowledge=parsed.acknowledge,
        )
        added = ctx.client.dispatch(add_cmd, idempotency_key=idem)
        assert isinstance(added, AddFileResult)  # noqa: S101
        out = dict(added.to_json())
    else:
        assert row_version is not None  # noqa: S101
        ver_cmd = wire.AddFileVersion(
            file_id=target_file_id,
            expected_row_version=row_version,
            blob=wire.AddFileVersionDefsStagedBlobRef(
                staged_blob_id=staged.staged_blob_id,
                workspace_id=staged.workspace_id,
                digest=staged.digest,
                size=staged.size,
                media_type=staged.media_type,
            ),
            original_filename=original_filename,
            declared_media_type=parsed.declared_media_type,
            description=parsed.description,
            source=wire.AddFileVersionDefsVersionSource.from_json(dict(parsed.source)),
            acknowledge=parsed.acknowledge,
        )
        ver_added = ctx.client.dispatch(ver_cmd, idempotency_key=idem)
        assert isinstance(ver_added, AddFileVersionResult)  # noqa: S101
        out = dict(ver_added.to_json())

    out["digest"] = staged.digest
    out["size_bytes"] = staged.size
    out["original_filename"] = original_filename
    return cast("JsonObject", out)


SPEC: Final = HostOperationSpec(
    name="artifacts.host.upload_file",
    run=run,
    request=cast("type[object]", dict),
    result=cast("type[object]", dict),
    surfaces=cast("frozenset[Any]", frozenset({"cli", "worker"})),
)
