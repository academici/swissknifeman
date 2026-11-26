"""Host cleanup applies retention after terminal/reap/reconcile proof; blobs are untouched."""

from collections.abc import Callable, Mapping
from typing import Any, cast
from uuid import UUID

from skm.application_bus.host import HostContext
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError, error_for
from skm.kernel.json_types import JsonObject
from skm.modules.execution.generated.commands import MarkEnvironmentsRemoved
from skm.modules.execution.generated.queries import GetAttempt, ListExecutionEnvironments
from skm.modules.execution.ports import ExecutionEnvironmentManager

PAGE_SIZE = 200
REMOVAL_BATCH = 500


def clean(
    ctx: HostContext,
    request: JsonObject,
    *,
    managers: Mapping[str, ExecutionEnvironmentManager],
    eligible: Callable[[JsonObject], bool],
    idempotency_key: str,
    command_factory: Callable[[MarkEnvironmentsRemoved], object],
    on_skip: Callable[[JsonObject], None] | None = None,
) -> JsonObject:
    """eligible verifies terminal ownership, empty containment and all retained replay dependencies.

    The manager independently verifies its marker, exact filesystem binding and removal proof before IO.
    Unknown evidence/PermissionError never authorizes deletion or clearing the server's busy state.
    """
    retain = request.get("retain", "failed")
    if retain not in {"never", "failed", "always"}:
        raise ValueError("unknown environment retain policy")
    if retain == "always":
        return {"marked": 0, "freed_bytes": 0}
    removed: list[str] = []
    freed = 0
    after = None
    while True:
        ctx.cancel.raise_if_cancelled()
        query = ListExecutionEnvironments.from_json(
            {
                "host_id": str(ctx.host_id),
                "removable_only": True,
                "limit": PAGE_SIZE,
                **({"after": after} if after else {}),
            }
        )
        result: Any = ctx.client.ask(query)
        page = result.to_json() if hasattr(result, "to_json") else result
        for row in page["items"]:
            if len(removed) == REMOVAL_BATCH:
                break
            if not eligible(row):
                continue
            if retain == "failed":
                try:
                    attempt: Any = ctx.client.ask(GetAttempt(UUID(row["attempt_id"])))
                except (SkmError, KeyError, ValueError):
                    continue
                attempt_doc = attempt.to_json() if hasattr(attempt, "to_json") else attempt
                if attempt_doc.get("end_reason") != "ACCEPTED":
                    continue
            manager = managers.get(row["kind"])
            if manager is None:
                raise error_for(ErrorCode.CAPABILITY_UNAVAILABLE, "environment kind unavailable on host")
            try:
                outcome = manager.remove(row["local_locator"])
            except (OSError, SkmError, ValueError):
                if on_skip is not None:
                    on_skip(row)
                continue  # uncertain cleanup retains state and all recovery inputs
            removed.append(row["environment_id"])
            freed += outcome.freed_bytes
        after = page.get("next_after")
        if after is None or len(removed) == REMOVAL_BATCH:
            break
    if not removed:
        return {"marked": 0, "freed_bytes": 0}
    command = MarkEnvironmentsRemoved(host_id=str(ctx.host_id), environment_ids=removed, freed_bytes=freed)
    result = ctx.client.dispatch(command_factory(command), idempotency_key=idempotency_key)
    marked = (
        cast("dict[str, Any]", result).get("marked", 0)
        if isinstance(result, dict)
        else getattr(result, "marked", 0)
    )
    return {"marked": marked, "freed_bytes": freed}


class CleanEnvironmentsOperation:
    def __init__(
        self,
        *,
        managers: Mapping[str, ExecutionEnvironmentManager],
        eligible: Callable[[JsonObject], bool],
        idempotency_key: Callable[[JsonObject], str],
        command_factory: Callable[[MarkEnvironmentsRemoved], object],
        on_skip: Callable[[JsonObject], None] | None = None,
    ) -> None:
        self.managers, self.eligible, self.key = managers, eligible, idempotency_key
        self.command_factory = command_factory
        self.on_skip = on_skip

    def __call__(self, ctx: HostContext, request: JsonObject) -> JsonObject:
        return clean(
            ctx,
            request,
            managers=self.managers,
            eligible=self.eligible,
            idempotency_key=self.key(request),
            command_factory=self.command_factory,
            on_skip=self.on_skip,
        )
