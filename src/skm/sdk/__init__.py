"""Public Python client for campaign control, event observation and run reports.

Use `with connect(profile="hub") as client:`, then `client.ask(GetRun(run_id))`.
Commands use `client.dispatch` and accept a caller-owned idempotency key for retries.
The same operations work with an existing embedded SkmClient.
"""

from skm.application_bus.client import QueryMeta, SkmClient
from skm.bootstrap.sdk import connect
from skm.kernel.errors import SkmError
from skm.modules.execution.public import (
    DrainAutopilot,
    ExplainAutopilot,
    GetAutopilotStatus,
    GetRun,
    GetTaskLiveControl,
    PauseAutopilot,
    StartAutopilot,
    StopAutopilot,
)
from skm.modules.exports.public import RenderRunReport

__all__ = [
    "DrainAutopilot",
    "ExplainAutopilot",
    "GetAutopilotStatus",
    "GetRun",
    "GetTaskLiveControl",
    "PauseAutopilot",
    "QueryMeta",
    "RenderRunReport",
    "SkmClient",
    "SkmError",
    "StartAutopilot",
    "StopAutopilot",
    "connect",
]
