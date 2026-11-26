"""Consume an exact human approval before a trusted host writes outside the workspace."""

from __future__ import annotations

from typing import TYPE_CHECKING

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, ValidationFailed
from skm.modules.policy.domain.paths import PathScope, ScopeRoots, classify_path, is_protected
from skm.modules.policy.domain.tool_intent import EffectKind, EnforcementMode, args_digest, normalize_args
from skm.modules.policy.generated.commands import RecordIntentOutcome, StartIntentExecution
from skm.modules.policy.ports import ExternalFileWriter
from skm.platform.jsonc.digest import digest_bytes

if TYPE_CHECKING:
    from skm.application_bus.host import HostContext
    from skm.kernel.ids import ToolIntentId

__all__ = ["write_external"]


def write_external(
    ctx: HostContext,
    intent_id: ToolIntentId,
    path: str,
    data: bytes,
    *,
    roots: ScopeRoots,
    mode: EnforcementMode,
) -> str:
    """Write the approved bytes to the approved path on this host and record the outcome."""
    if mode is EnforcementMode.AGENT_UNATTENDED:
        raise Forbidden(ErrorCode.FORBIDDEN, "unattended agents cannot execute external file writes")
    kind = EffectKind.FS_WRITE_EXTERNAL
    content_digest = digest_bytes(data)
    args = normalize_args(kind, {"host_id": str(ctx.host_id), "path": path, "content_digest": content_digest})
    if (
        is_protected(path, roots)
        or classify_path(path, roots).scope in {PathScope.WORKTREE, PathScope.MATERIALS, PathScope.TMP}
        or ".git" in path.split("/")
    ):
        raise Forbidden(ErrorCode.FORBIDDEN, "external write destination is not an external file")
    writer = ctx.gateways.get(ExternalFileWriter)
    ctx.cancel.raise_if_cancelled()
    ctx.client.dispatch(StartIntentExecution(intent_id=intent_id, args_digest=args_digest(kind, args)))
    try:
        writer(path, data)
    except (OSError, ValidationFailed) as error:
        outcome = "failed" if isinstance(error, ValidationFailed) else "outcome_unknown"
        ctx.client.dispatch(
            RecordIntentOutcome(
                intent_id=intent_id, outcome=outcome, receipt={"content_digest": content_digest}
            )
        )
        raise
    ctx.client.dispatch(
        RecordIntentOutcome(
            intent_id=intent_id, outcome="succeeded", receipt={"content_digest": content_digest}
        )
    )
    return content_digest
