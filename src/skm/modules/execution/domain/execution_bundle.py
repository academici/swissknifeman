"""The frozen execution bundle of a run (execution §4.2).

Written once at ``start_run`` and never changed (database trigger). ``reconfigure_run`` adds append-only
overlays of allowed keys; the effective value of a key is the bundle value overlaid by its reconfigurations
in ``RunReconfigured.stream_seq`` order, without rewriting the bundle or reading newer defaults.
``work_policies`` holds the frozen policy of every compiled task plus ``@default``; a historical ``None``
is diagnostic-only and authorizes nothing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.ids import TaskId
from skm.kernel.json_types import JsonObject

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import datetime
    from uuid import UUID

    from skm.kernel.ids import ResourceVersionId, RunId
    from skm.kernel.json_types import JsonValue
    from skm.modules.execution.domain.review_grouping import ReviewGrouping
    from skm.modules.execution.domain.work_policy import EffectiveWorkPolicy

__all__ = [
    "DEFAULT_POLICY_KEY",
    "ExecutionBundle",
    "Reconfiguration",
    "ResourcePin",
    "ResourcePins",
    "RunSelection",
    "SatisfiedTask",
    "effective_value",
    "run_selection_to_json",
]

DEFAULT_POLICY_KEY: Final = "@default"
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


@dataclass(frozen=True, slots=True)
class ResourcePin:
    kind: str
    key: str
    resource_version_id: ResourceVersionId
    digest: str


@dataclass(frozen=True, slots=True)
class ResourcePins:
    resources: tuple[ResourcePin, ...]
    packs: Mapping[str, UUID]


@dataclass(frozen=True, slots=True)
class SatisfiedTask:
    display_key: str
    source_task_id: TaskId


@dataclass(frozen=True, slots=True)
class RunSelection:
    task_keys: tuple[str, ...]
    phases: tuple[str, ...]
    stop_after: str | None
    compiled_keys: tuple[str, ...]
    satisfied: tuple[SatisfiedTask, ...]


@dataclass(frozen=True, slots=True)
class ExecutionBundle:
    run_id: RunId
    config_snapshot: JsonObject
    config_digest: str
    policy_digest: str
    resource_pins: ResourcePins
    selection: RunSelection | None
    work_policies: Mapping[str, EffectiveWorkPolicy] | None
    context_policy: Mapping[str, JsonValue]
    review_grouping: ReviewGrouping
    created_at: datetime

    def __post_init__(self) -> None:
        problems: list[str] = []
        if not _DIGEST.fullmatch(self.config_digest) or not _DIGEST.fullmatch(self.policy_digest):
            problems.append("config_digest and policy_digest are sha256:<64 hex>")
        if self.work_policies is not None and DEFAULT_POLICY_KEY not in self.work_policies:
            problems.append("work_policies include @default")
        if self.selection is not None and self.work_policies is not None:
            unknown = set(self.selection.compiled_keys) - set(self.work_policies)
            if unknown:
                problems.append(f"work_policies cover the compiled tasks (missing {sorted(unknown)})")
        if problems:
            raise error_for(
                ErrorCode.SCHEMA_INVALID,
                "bundle invariants violated: " + "; ".join(problems),
                details={"run_id": str(self.run_id), "violations": list(problems)},
            )
        if self.work_policies is not None:
            object.__setattr__(self, "work_policies", MappingProxyType(dict(self.work_policies)))
        object.__setattr__(self, "context_policy", MappingProxyType(dict(self.context_policy)))


@dataclass(frozen=True, slots=True)
class Reconfiguration:
    """One ``RunReconfigured`` overlay: ``changes`` maps keys to their new values."""

    stream_seq: int
    changes: Mapping[str, JsonValue]


def effective_value(frozen: JsonValue, key: str, reconfigurations: Sequence[Reconfiguration]) -> JsonValue:
    """The bundle value of ``key`` overlaid by the last reconfiguration of that key in stream order."""
    value = frozen
    for overlay in sorted(reconfigurations, key=lambda found: found.stream_seq):
        if key in overlay.changes:
            value = overlay.changes[key]
    return value


def run_selection_to_json(selection: RunSelection) -> JsonObject:
    """``execution_bundles.selection`` (schema ``urn:skm:execution:execution-bundle:v1``)."""
    return {
        "task_keys": list(selection.task_keys),
        "phases": list(selection.phases),
        "stop_after": selection.stop_after,
        "compiled_keys": list(selection.compiled_keys),
        "satisfied": [
            {"display_key": found.display_key, "source_task_id": str(found.source_task_id)}
            for found in selection.satisfied
        ],
    }
