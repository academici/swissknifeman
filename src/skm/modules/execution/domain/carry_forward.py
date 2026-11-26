"""Carry-forward compatibility (execution §4.18, K14).

Reusing an accepted result of another run is allowed only when the full compatibility evidence of the
source and of the target are equal. The evidence binds the semantic entity contract and everything that
was resolved for it: resource/check/profile/template versions and digests, the frozen config
interpretation, the acceptance policy, material bytes, predecessor outputs and the baseline of every
mount. Missing evidence is never equal to anything (``compatibility_digest`` is ``None``); equality of
the spec or of a name alone is not enough. Nothing here changes a source bundle, revision or accepted
output: the comparison only reads immutable facts.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, fields
from typing import TYPE_CHECKING, Final, Literal, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for

if TYPE_CHECKING:
    from datetime import datetime

    from skm.kernel.ids import AttemptId, PrincipalId, RunId, TaskId
    from skm.kernel.json_types import JsonObject, JsonValue
    from skm.modules.execution.domain.ids import CarryForwardId, OutputId

__all__ = [
    "COMPATIBILITY_SCHEMA_VERSION",
    "CarryForward",
    "CompatibilityInputs",
    "CompatibilityResult",
    "compare_compatibility",
    "compatibility_digest",
    "compatibility_inputs_to_json",
]

COMPATIBILITY_SCHEMA_VERSION: Final = 1
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


@dataclass(frozen=True, slots=True)
class CompatibilityInputs:
    """One side of the comparison; ``None`` in any field means the evidence is missing.

    Maps are keyed by semantic identities (resource kind/key, check key, material key, predecessor
    display key, mount), never by run-local UUIDs or times; their values are digests or exact version
    identities. ``entity_contract_digest`` covers goal, instructions, criteria, check specs, material refs,
    write scope and dependencies of the entity.
    """

    entity_contract_digest: str | None
    resolved_resources: Mapping[str, str] | None
    checks: Mapping[str, str] | None
    config_interpretation_digest: str | None
    acceptance_policy_digest: str | None
    materials: Mapping[str, str] | None
    predecessor_outputs: Mapping[str, str] | None
    baseline: Mapping[str, str] | None

    def __post_init__(self) -> None:
        for name in ("entity_contract_digest", "config_interpretation_digest", "acceptance_policy_digest"):
            value = getattr(self, name)
            if value is not None and not _DIGEST.fullmatch(value):
                raise error_for(
                    ErrorCode.SCHEMA_INVALID, f"{name} is sha256:<64 hex>", details={"field": name}
                )

    def missing(self) -> tuple[str, ...]:
        return tuple(field.name for field in fields(self) if getattr(self, field.name) is None)


@dataclass(frozen=True, slots=True)
class CompatibilityResult:
    compatible: bool
    source_digest: str | None
    target_digest: str | None
    differing: tuple[str, ...]
    missing: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CarryForward:
    id: CarryForwardId
    source_run_id: RunId
    source_task_id: TaskId
    source_attempt_id: AttemptId
    source_output_id: OutputId
    target_run_id: RunId
    target_task_id: TaskId
    compatibility_digest: str
    compatibility_inputs: JsonObject
    decision: Literal["accepted", "rejected"]
    approved_by: PrincipalId
    reason: str
    created_at: datetime


def compatibility_inputs_to_json(inputs: CompatibilityInputs) -> JsonObject:
    """The canonical document of one side, as stored in ``compatibility_inputs.source|target``."""
    return {field.name: _plain(getattr(inputs, field.name)) for field in fields(inputs)}


def compatibility_digest(inputs: CompatibilityInputs) -> str | None:
    """``sha256:`` of the canonical complete inputs; ``None`` when any evidence is missing."""
    if inputs.missing():
        return None
    document = {"schema_version": COMPATIBILITY_SCHEMA_VERSION, **compatibility_inputs_to_json(inputs)}
    text = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def compare_compatibility(source: CompatibilityInputs, target: CompatibilityInputs) -> CompatibilityResult:
    """Full equality of complete evidence; the differing and missing field names explain a refusal."""
    missing = tuple(
        sorted(
            {
                *(f"source.{name}" for name in source.missing()),
                *(f"target.{name}" for name in target.missing()),
            }
        )
    )
    differing = tuple(
        field.name
        for field in fields(source)
        if getattr(source, field.name) is not None
        and getattr(target, field.name) is not None
        and _canonical(getattr(source, field.name)) != _canonical(getattr(target, field.name))
    )
    source_digest = compatibility_digest(source)
    target_digest = compatibility_digest(target)
    compatible = source_digest is not None and source_digest == target_digest
    return CompatibilityResult(compatible, source_digest, target_digest, differing, missing)


def _plain(value: object) -> JsonValue:
    if isinstance(value, Mapping):
        items = cast("Mapping[str, str]", value)
        return {key: items[key] for key in sorted(items)}
    return cast("str | None", value)


def _canonical(value: object) -> str:
    return json.dumps(_plain(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
