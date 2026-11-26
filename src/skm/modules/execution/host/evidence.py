"""Stage evidence is uploaded completely before the fenced result command (K8)."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, cast

from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.execution.generated.commands import RecordStageResult, record_stage_result_from_json

if TYPE_CHECKING:
    from pathlib import Path

    from skm.application_bus.host import HostContext
    from skm.kernel.ids import WorkspaceId
    from skm.modules.artifacts.public import StagedBlobRef


class EvidenceOperation(Protocol):
    def __call__(self, ctx: HostContext, request: JsonObject) -> JsonObject: ...


@dataclass(frozen=True, slots=True)
class EvidenceFile:
    path: Path
    owner: str  # '<owner kind>:<UUID>', e.g. check_execution:<check id>
    role: str
    filename: str
    media_type: str


class BlobUploader(Protocol):
    def upload_blob(self, content: bytes) -> StagedBlobRef: ...


class ClientBlobUploader:
    """Bind the real streaming SkmClient upload to one workspace, without changing CheckDeps."""

    def __init__(self, ctx: HostContext, workspace_id: WorkspaceId) -> None:
        self.ctx, self.workspace_id = ctx, workspace_id

    def upload_blob(self, content: bytes) -> StagedBlobRef:
        return self.ctx.client.upload_blob(self.workspace_id, (content,), size=len(content)).to_json()


def upload_evidence(
    files: Iterable[EvidenceFile], uploader: BlobUploader, read: Callable[[Path], bytes]
) -> tuple[JsonObject, ...]:
    staged: list[JsonObject] = []
    for file in files:
        owner, separator, owner_id = file.owner.partition(":")
        if not separator or owner not in {"step", "attempt", "output", "check_execution", "review"}:
            raise ValueError("evidence needs a typed owner identity")
        blob = uploader.upload_blob(read(file.path))
        staged.append(
            {
                "owner": owner,
                "owner_id": owner_id,
                "role": file.role,
                "filename": file.filename,
                "media_type": file.media_type,
                "staged_blob": blob,
            }
        )
    return tuple(staged)


def record_with_evidence(
    ctx: HostContext,
    request: RecordStageResult,
    *,
    files: Iterable[EvidenceFile],
    uploader: BlobUploader,
    read: Callable[[Path], bytes],
    idempotency_key: str,
    command_factory: Callable[[RecordStageResult], object],
) -> object:
    staged = upload_evidence(files, uploader, read)
    raw = cast("JsonObject", dict(request))
    if raw.get("evidence"):
        raise ValueError("stage evidence must be assembled exactly once")
    raw["evidence"] = list[JsonValue](staged)
    command = record_stage_result_from_json(raw)
    return ctx.client.dispatch(command_factory(command), idempotency_key=idempotency_key)
