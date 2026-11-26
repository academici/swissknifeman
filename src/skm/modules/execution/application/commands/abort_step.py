"""Publish the abort step operator command."""

from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.modules.execution.application._control import run_scope
from skm.modules.execution.application._operator_control import handle
from skm.modules.execution.generated.commands import AbortStep
from skm.modules.execution.generated.results import LiveControlResult

SPEC = CommandSpec(
    name="execution.abort_step",
    dto=AbortStep,
    result=LiveControlResult,
    permission="run.control",
    scope_of=run_scope,
    handler=handle,
    idempotency=IdempotencyMode.OPTIONAL,
)
