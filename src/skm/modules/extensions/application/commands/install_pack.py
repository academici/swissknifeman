"""``extensions.install_pack`` (extensions §7.1): a pack from a surface; the bytes came in the DTO, no IO.

The origin and the trust are what the installer declared and they never reach ``builtin``: the label is
refused here and the schema of the DTO does not admit that trust. A manifest that claims ``builtin`` is
``FORBIDDEN`` in ``install_candidate``.
"""

import base64
import binascii
from typing import cast

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.tokens import TokenEstimator
from skm.modules.extensions.application.candidate import build_candidate
from skm.modules.extensions.application.install import install_candidate
from skm.modules.extensions.domain.pack import PackTrust, require_external_origin
from skm.modules.extensions.domain.payload import (
    PackPayload,
    PayloadFile,
    check_payload_limits,
    validate_payload_path,
)
from skm.modules.extensions.generated.commands import InstallPack
from skm.modules.extensions.generated.documents import PackPayload as PayloadDto
from skm.modules.extensions.generated.results import InstallPackResult

__all__ = ["SPEC", "handle"]


def _decoded(dto: PayloadDto, ctx: CommandContext) -> PackPayload:
    """§7.1 step 1: normalized unique paths inside the limits of ``extensions.install.*``."""
    max_files = cast("int", ctx.config.get("extensions.install.max_archive_files"))
    max_bytes = cast("int", ctx.config.get("extensions.install.max_archive_bytes"))
    check_payload_limits(len(dto.files), 0, max_files=max_files, max_bytes=max_bytes)
    files: list[PayloadFile] = []
    total = 0
    for item in dto.files:
        validate_payload_path(item.path)
        try:
            content = base64.b64decode(item.content_b64, validate=True)
        except binascii.Error as exc:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "a file of the pack is not valid base64",
                details={"reason": "content_not_base64", "path": item.path},
            ) from exc
        total += len(content)
        check_payload_limits(len(dto.files), total, max_files=max_files, max_bytes=max_bytes)
        files.append(PayloadFile(item.path, content))
    return PackPayload(dto.manifest_text, tuple(files))


def handle(cmd: InstallPack, ctx: CommandContext, uow: UnitOfWork) -> InstallPackResult:
    origin = require_external_origin(cmd.origin_label)
    allowed_licenses = frozenset(cast("list[str]", ctx.config.get("extensions.compat.allowed_licenses")))
    max_skill_tokens = cast("int", ctx.config.get("extensions.compat.max_skill_tokens"))
    max_steering_tokens = cast("int", ctx.config.get("extensions.compat.max_steering_tokens"))
    extra_known_tools = frozenset(cast("list[str]", ctx.config.get("extensions.compat.extra_known_tools")))
    candidate = build_candidate(
        _decoded(cmd.payload, ctx),
        estimator=ctx.gateways.get(TokenEstimator),
        allowed_licenses=allowed_licenses,
        max_skill_tokens=max_skill_tokens,
        max_steering_tokens=max_steering_tokens,
        extra_known_tools=extra_known_tools,
    )
    on_incompatible = cast("str", ctx.config.get("extensions.compat.on_incompatible"))
    allow_quarantine = cmd.allow_quarantine and (on_incompatible != "refuse")
    return install_candidate(
        candidate,
        origin=origin,
        trust=PackTrust(cmd.trust),
        installed_by=ctx.actor.principal_id,
        clock=ctx.clock,
        ids=ctx.ids,
        config=ctx.config,
        uow=uow,
        allow_quarantine=allow_quarantine,
        dry_run=cmd.dry_run,
    )


SPEC = CommandSpec(
    name="extensions.install_pack",
    dto=InstallPack,
    result=InstallPackResult,
    permission="ext.install",
    scope_of=None,
    idempotency=IdempotencyMode.OPTIONAL,
    handler=handle,
)
