"""Accept only unverified outcome and exposure for client session summaries."""

from typing import Any, cast

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.learning.generated.commands import RecordActivity
from skm.modules.learning.generated.results import RecordActivityResult

from .extract_candidates import extract, project_ref


def handle(cmd: dict[str, Any], ctx: CommandContext, uow: UnitOfWork) -> RecordActivityResult:
    summary = cmd["summary"]
    if (
        summary["source_kind"] != "client_session"
        or summary["outcome"] != "unknown"
        or summary.get("task_outcome") not in (None, "unknown")
        or summary.get("exposure_coverage", "unknown") != "unknown"
        or summary.get("exposed_lesson_refs")
    ):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID, "Client activity requires unknown outcome and exposure coverage"
        )
    if ctx.config.get("learning.sources.client_sessions") is False:
        return RecordActivityResult(activity_record_id=None, observations=0)
    result: dict[str, Any] = cast("dict[str, Any]", extract(cmd, ctx, uow, config=ctx.config))
    return RecordActivityResult(
        activity_record_id=result["activity_record_id"], observations=len(result["signaled"])
    )


SPEC = CommandSpec(
    name="learning.record_activity",
    dto=cast("type[dict[str, Any]]", RecordActivity),
    result=RecordActivityResult,
    permission="lesson.read",
    scope_of=lambda cmd: project_ref(cmd["project_id"]),
    handler=handle,
    idempotency=IdempotencyMode.OPTIONAL,
)
