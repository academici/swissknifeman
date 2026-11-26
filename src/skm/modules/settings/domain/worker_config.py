"""Project settings that may cross the registered worker configuration boundary."""

import re
from collections.abc import Iterable, Mapping
from typing import cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.json_types import JsonObject, JsonValue

__all__ = [
    "PROJECT_WORKER_HOST_KEYS",
    "PROJECT_WORKER_KEYS",
    "PROJECT_WORKER_WORK_KEYS",
    "worker_identifiers",
    "worker_values",
]

_PROJECT_INTEGERS = {
    "api.limits.max_body_bytes": (1024, 67_108_864),
    "api.live.batch_ms": (10, 10_000),
    "exports.vault.push_interval_seconds": (0, 86_400),
    "worker.capacity": (1, 64),
    "worker.claim.poll_ms": (100, 60_000),
    "worker.disk_min_bytes": (0, 17_592_186_044_416),
}
PROJECT_WORKER_WORK_KEYS = frozenset({"runtimes.allowed", "api.limits.max_body_bytes"})
PROJECT_WORKER_HOST_KEYS = frozenset(_PROJECT_INTEGERS) - PROJECT_WORKER_WORK_KEYS
PROJECT_WORKER_KEYS = PROJECT_WORKER_HOST_KEYS | PROJECT_WORKER_WORK_KEYS

_RUNTIME_ID = re.compile(r"[a-z][a-z0-9_-]{1,40}")
_PLUGIN_ID = re.compile(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)?")


def worker_identifiers(value: object, *, key: str) -> tuple[str, ...]:
    pattern = _PLUGIN_ID if key.startswith("plugins.") else _RUNTIME_ID
    if isinstance(value, (list, tuple)):
        items = cast("Iterable[object]", value)
        if all(isinstance(item, str) and pattern.fullmatch(item) for item in items):
            result = tuple(cast("Iterable[str]", items))
            if len(set(result)) == len(result):
                return result
    raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Invalid worker setting", details={"key": key})


def worker_values(values: Mapping[str, JsonValue]) -> JsonObject:
    """Project-side worker values are bounded numbers and runtime identifiers."""
    result: JsonObject = {}
    for key, (minimum, maximum) in _PROJECT_INTEGERS.items():
        if key not in values:
            continue
        value = values[key]
        if type(value) is not int or not minimum <= value <= maximum:
            raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Invalid worker setting", details={"key": key})
        result[key] = value
    if "runtimes.allowed" in values:
        result["runtimes.allowed"] = list[JsonValue](
            worker_identifiers(values["runtimes.allowed"], key="runtimes.allowed")
        )
    return result
