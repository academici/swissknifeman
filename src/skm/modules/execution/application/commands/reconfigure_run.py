"""Append a bounded guard amendment at a run-wide claim/stage/recovery checkpoint."""

from dataclasses import replace
from decimal import Decimal
from fnmatch import fnmatchcase
from typing import Any

from skm.application_bus.registry import CommandSpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.execution.application._control import checkpoint, lock_run, run_scope
from skm.modules.execution.application._events import cause, emit
from skm.modules.execution.application._primitives import BUDGET_DIMENSIONS
from skm.modules.execution.application._start_inputs import value
from skm.modules.execution.application._state import effective_values
from skm.modules.execution.domain.budget import BudgetDimension, limit_from_config
from skm.modules.execution.generated.commands import ReconfigureRun
from skm.modules.execution.generated.results import ReconfigureRunResult
from skm.modules.execution.ports import (
    BudgetRepository,
    BundleRepository,
    ReconfigurationRecord,
    RunRepository,
    TaskRepository,
)

FIXED_KEYS = frozenset(
    {
        "execution.parallel.max_units",
        *(
            f"budgets.{scope}.max_{dimension.value}"
            for scope, dimensions in BUDGET_DIMENSIONS.items()
            for dimension in dimensions
        ),
    }
)


def _validate_number(config: Any, key: str, new: Any) -> int | float:
    spec = config.registry.spec(key)
    if isinstance(new, bool) or not isinstance(new, int | float) or not Decimal(str(new)).is_finite():
        raise error_for(ErrorCode.SCHEMA_INVALID, "limit must be a finite number", details={"key": key})
    if spec.value_type == "integer" and not isinstance(new, int):
        raise error_for(ErrorCode.SCHEMA_INVALID, "this limit is an integer", details={"key": key})
    if config.registry.value_issues(key, new):
        raise error_for(
            ErrorCode.SCHEMA_INVALID, "limit does not satisfy its registry schema", details={"key": key}
        )

    return new


def allowed_keys(config: Any) -> frozenset[str]:
    patterns = value(config, "execution.reconfigure.allowed_keys", [])
    return frozenset(key for key in FIXED_KEYS if any(fnmatchcase(key, p) for p in patterns))


def handle(cmd: ReconfigureRun, ctx: Any, uow: UnitOfWork) -> ReconfigureRunResult:
    run = lock_run(uow, cmd.run_id, cmd.expected_row_version)
    checkpoint(uow, run.id)
    if not cmd.reason.strip() or not cmd.changes or len(cmd.changes) > 128:
        raise error_for(ErrorCode.SCHEMA_INVALID, "nonempty reason and bounded changes are required")
    keys = allowed_keys(ctx.config)
    _, current = effective_values(uow, run.id)
    changes: dict[str, Any] = {}
    for key, requested in cmd.changes.items():
        if key not in keys:
            raise error_for(
                ErrorCode.FORBIDDEN, "key is outside the fixed semantic allowlist", details={"key": key}
            )
        new = _validate_number(ctx.config, key, requested)
        ceiling = value(ctx.config, key, 0)
        if (ceiling and (not new or new > ceiling)) or (key == "execution.parallel.max_units" and new < 1):
            raise error_for(ErrorCode.FORBIDDEN, "requested limit exceeds the current ceiling")
        if ctx.config.provenance(key).locked_by is not None and current.get(key) != new:
            raise error_for(ErrorCode.FORBIDDEN, "key is locked")
        changes[key] = {"old": current.get(key), "new": new}
    record = ReconfigurationRecord(
        ctx.ids.new_id(), run.id, changes, cmd.reason, ctx.actor.principal_id, ctx.clock.now()
    )
    uow.repo(BundleRepository).add_reconfiguration(record)
    for key, change in changes.items():
        if not key.startswith("budgets."):
            continue
        _, scope, max_name = key.split(".")
        dim = BudgetDimension(max_name.removeprefix("max_"))
        targets = (
            (None,) if scope == "run" else tuple(t.id for t in uow.repo(TaskRepository).list_for_run(run.id))
        )
        for target in targets:
            uow.repo(BudgetRepository).raise_limit(
                run.id, target, dim, limit_from_config(str(change["new"]), dim)
            )
    loaded, _ = effective_values(uow, run.id)
    updated = replace(run, row_version=run.row_version + 1)
    uow.repo(RunRepository).save(updated, expected_version=run.row_version)
    emit(
        uow,
        run,
        "run-reconfigured",
        {
            "reconfiguration_id": str(record.id),
            "changes": changes,
            "reason": cmd.reason,
            "by": str(ctx.actor.principal_id),
            "effective_config_digest": loaded.effective_config_digest,
            "effective_after": "checkpoint",
        },
        cause("reconfigure"),
    )
    return ReconfigureRunResult(
        run.id, tuple(changes), record.id, loaded.effective_config_digest, updated.row_version
    )


SPEC = CommandSpec(
    name="execution.reconfigure_run",
    dto=ReconfigureRun,
    result=ReconfigureRunResult,
    permission="run.control",
    scope_of=run_scope,
    handler=handle,
)
