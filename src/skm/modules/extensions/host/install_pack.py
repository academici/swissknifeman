"""``extensions.host.install_pack``: read pack via ``PackReader`` and dispatch ``InstallPack``."""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Literal, Protocol, cast

from skm.application_bus.host import HostContext
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.module_manifest import HostOperationSpec
from skm.modules.extensions.generated.commands import InstallPack
from skm.modules.extensions.generated.documents import (
    PackPayload as PayloadDto,
)
from skm.modules.extensions.generated.documents import (
    PackPayloadFilesItem,
)
from skm.modules.extensions.generated.host import InstallPackReport, InstallPackRequest
from skm.modules.extensions.generated.results import InstallPackResult
from skm.modules.extensions.ports import PackReader

if TYPE_CHECKING:
    from skm.kernel.json_types import JsonObject
    from skm.modules.extensions.domain.payload import PackPayload

__all__ = ["SPEC", "InstallPackOperation", "run"]

_ARCHIVE_SUFFIXES = (".tar.gz", ".tgz", ".tar", ".zip")


class InstallPackOperation(Protocol):
    def __call__(self, ctx: HostContext, request: JsonObject) -> JsonObject: ...


def _archive_origin(payload: PackPayload) -> str:
    hasher = hashlib.sha256()
    hasher.update(payload.manifest_text.encode("utf-8"))
    for item in sorted(payload.files, key=lambda f: f.path):
        hasher.update(b"\0")
        hasher.update(item.path.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(item.content)
    return f"archive:{hasher.hexdigest()}"


def _default_allow_quarantine(ctx: HostContext) -> bool:
    getter = getattr(ctx.config, "get", None)
    if callable(getter):
        return getter("extensions.compat.on_incompatible") != "refuse"
    return True


def run(ctx: HostContext, request: InstallPackRequest) -> InstallPackReport:
    """Read a pack directory or archive using ``PackReader`` and dispatch ``extensions.install_pack``."""
    raw_archive = request.get("archive")
    raw_path = request.get("path")
    if isinstance(raw_archive, str) and raw_archive.strip():
        target_path = raw_archive
        is_archive = True
    elif isinstance(raw_path, str) and raw_path.strip():
        target_path = raw_path
        is_archive = target_path.lower().endswith(_ARCHIVE_SUFFIXES)
    else:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "path or archive is required",
            details={"reason": "path_required"},
        )

    trust = cast("Literal['operator', 'third_party']", request.get("trust", "third_party"))
    raw_allow_quarantine = request.get("allow_quarantine")
    allow_quarantine = (
        bool(raw_allow_quarantine) if raw_allow_quarantine is not None else _default_allow_quarantine(ctx)
    )
    dry_run = bool(request.get("dry_run", False))
    reader = ctx.gateways.get(PackReader)

    if is_archive:
        payload = reader.read_archive(target_path)
        default_origin = _archive_origin(payload)
    else:
        payload = reader.read_dir(target_path)
        default_origin = f"path:{target_path}"[:200]

    origin_label = str(request.get("origin_label") or default_origin)
    dto = PayloadDto(
        manifest_text=payload.manifest_text,
        files=tuple(
            PackPayloadFilesItem(
                path=item.path,
                content_b64=base64.b64encode(item.content).decode("ascii"),
            )
            for item in payload.files
        ),
    )
    cmd = InstallPack(
        payload=dto,
        origin_label=origin_label,
        trust=trust,
        allow_quarantine=allow_quarantine,
        dry_run=dry_run,
    )
    raw_result = ctx.client.dispatch(cmd)
    if isinstance(raw_result, InstallPackReport):
        return raw_result
    if isinstance(raw_result, InstallPackResult):
        return InstallPackReport.from_json(raw_result.to_json())
    if isinstance(raw_result, Mapping):
        return InstallPackReport.from_json(cast("Mapping[str, object]", raw_result))
    msg = f"unexpected result type from InstallPack: {type(raw_result)!r}"
    raise TypeError(msg)


SPEC = HostOperationSpec(
    name="extensions.host.install_pack",
    run=run,
    request=cast("type[object]", dict),
    result=InstallPackReport,
    surfaces=cast("frozenset[Any]", frozenset({"cli"})),
)
