"""Runtime capability and skill conflict checks over validated source metadata."""

from __future__ import annotations

from typing import TYPE_CHECKING

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed
from skm.kernel.json_types import JsonValue
from skm.modules.context.domain.candidates import metadata, objects, strings
from skm.modules.context.domain.validation import preserve_groups

if TYPE_CHECKING:
    from skm.modules.context.domain.contracts import Compatible, Selected
    from skm.modules.context.domain.request import RuntimeTarget


def check_compatibility(selected: Selected, runtime: RuntimeTarget) -> Compatible:
    accepted: list[JsonValue] = []
    conditional: list[JsonValue] = []
    excluded: list[JsonValue] = list(objects(selected.get("excluded")))
    for candidate in objects(selected.get("included")):
        if not set(strings(metadata(candidate).get("required_capabilities"))) <= runtime.capabilities:
            if candidate.get("mandatory"):
                raise PreconditionFailed(
                    ErrorCode.CONTEXT_CONFLICT, "mandatory skill requires unavailable capability"
                )
            excluded.append(
                {
                    "block_type": candidate["block_type"],
                    "source_ref": candidate["source_ref"],
                    "reason": "capability_missing",
                }
            )
        else:
            accepted.append(candidate)
    skills = [c for c in objects(accepted) if c["block_type"] == "skills"]
    for i, first in enumerate(skills):
        if any(_conflicts(first, other) for other in skills[i + 1 :]):
            raise PreconditionFailed(ErrorCode.CONTEXT_CONFLICT, "selected skills conflict")
    for candidate in objects(selected.get("conditional")):
        failure = (
            "capability_missing"
            if not set(strings(metadata(candidate).get("required_capabilities"))) <= runtime.capabilities
            else "conflict_lower_priority"
            if any(_conflicts(candidate, other) for other in skills)
            else None
        )
        if failure:
            excluded.append(
                {
                    "block_type": candidate["block_type"],
                    "source_ref": candidate["source_ref"],
                    "reason": failure,
                }
            )
        else:
            conditional.append(candidate)
    return preserve_groups(
        {**selected, "included": accepted, "conditional": conditional, "excluded": excluded},
        objects(selected.get("included")) + objects(selected.get("conditional")),
    )


def _conflicts(first: Compatible, second: Compatible) -> bool:
    fm, sm = metadata(first), metadata(second)
    return str(sm.get("key")) in strings(fm.get("conflicts_with")) or str(fm.get("key")) in strings(
        sm.get("conflicts_with")
    )
