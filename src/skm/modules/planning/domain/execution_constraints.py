"""Execution constraints: typed record and document form (planning §4.2)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from skm.modules.planning.domain.phase import Strategy
from skm.modules.planning.domain.reads import compact

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Literal

    from skm.kernel.json_types import JsonObject, JsonValue


@dataclass(frozen=True, slots=True)
class PathRule:
    mount: str
    pattern: str


@dataclass(frozen=True, slots=True)
class ExecutionConstraints:
    strategy: Strategy
    forbidden_paths: tuple[PathRule, ...]
    required_isolation: Literal["worktree", "container"] | None
    max_parallel_units: int | None


def constraints_from_doc(doc: Mapping[str, JsonValue] | None) -> ExecutionConstraints:
    doc = doc or {}
    isolation, parallel = doc.get("required_isolation"), doc.get("max_parallel_units")
    return ExecutionConstraints(
        strategy=Strategy(str(doc.get("strategy", "dag"))),
        forbidden_paths=tuple(
            PathRule(str(rule["mount"]), str(rule["pattern"]))
            for rule in cast("list[Mapping[str, JsonValue]]", doc.get("forbidden_paths", []))
        ),
        required_isolation=cast("Literal['worktree', 'container'] | None", isolation),
        max_parallel_units=None if parallel is None else int(cast("int", parallel)),
    )


def constraints_to_doc(constraints: ExecutionConstraints) -> JsonObject:
    return compact(
        {
            "strategy": constraints.strategy.value,
            "forbidden_paths": [
                {"mount": r.mount, "pattern": r.pattern} for r in constraints.forbidden_paths
            ],
            "required_isolation": constraints.required_isolation,
            "max_parallel_units": constraints.max_parallel_units,
        }
    )
