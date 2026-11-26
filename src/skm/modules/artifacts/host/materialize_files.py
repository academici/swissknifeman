"""``artifacts.host.materialize_files``: stream pinned file versions into a sealed read-only material root."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final, Protocol, cast

from skm.application_bus.host import HostContext
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed, ValidationFailed
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.module_manifest import HostOperationSpec
from skm.modules.artifacts.domain.materialization import (
    MaterialEntry,
    MaterialSource,
    plan_materialization,
)
from skm.modules.artifacts.generated.host import MaterializeFilesRequest
from skm.modules.artifacts.generated.queries import GetFileVersion
from skm.modules.artifacts.generated.views import GetFileVersionView
from skm.modules.artifacts.ports import MaterialWriter

__all__ = ["SPEC", "MaterializeFilesOperation", "run"]


class MaterializeFilesOperation(Protocol):
    def __call__(self, ctx: HostContext, request: JsonObject) -> tuple[MaterialEntry, ...]: ...


def _coerce_request(request: object) -> MaterializeFilesRequest:
    if isinstance(request, MaterializeFilesRequest):
        return request
    if isinstance(request, Mapping):
        return MaterializeFilesRequest.from_json(dict(cast("Mapping[str, Any]", request)))
    raise ValidationFailed(
        ErrorCode.SCHEMA_INVALID,
        "materialize_files request must be an object",
        details={"reason": "not_object"},
    )


def run(
    ctx: HostContext,
    request: MaterializeFilesRequest | JsonObject,
) -> tuple[MaterialEntry, ...]:
    """Resolve ``file_version_ids``, build a canonical ``MaterialPlan``, stream and seal ``target_dir``."""
    ctx.cancel.raise_if_cancelled()
    req = _coerce_request(request)
    if not req.target_dir or not req.target_dir.strip():
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "target_dir must be a non-empty path",
            details={"field": "target_dir", "reason": "empty_target_dir"},
        )

    sources: list[MaterialSource] = []
    trashed: list[str] = []
    for raw_vid in req.file_version_ids:
        ctx.cancel.raise_if_cancelled()
        view = ctx.client.ask(GetFileVersion(file_version_id=raw_vid))
        assert isinstance(view, GetFileVersionView)  # noqa: S101
        if view.state == "trashed":
            trashed.append(str(view.file_version_id))
            continue
        sources.append(view)
    if trashed:
        raise PreconditionFailed(
            ErrorCode.FILE_VERSION_NOT_READY,
            "cannot materialize versions belonging to a trashed file",
            details={"ids": list[JsonValue](trashed)},
        )

    plan = plan_materialization(sources)
    writer = ctx.gateways.get(MaterialWriter)
    target = req.target_dir
    for entry in plan:
        ctx.cancel.raise_if_cancelled()
        with ctx.client.open_file_version_content(entry.file_version_id) as stream:
            writer.write(target, entry, stream)
    writer.seal(target)
    return plan


SPEC: Final = HostOperationSpec(
    name="artifacts.host.materialize_files",
    run=run,
    request=MaterializeFilesRequest,
    result=tuple,
    surfaces=cast("frozenset[Any]", frozenset({"worker", "cli"})),
)
