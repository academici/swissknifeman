"""Host-side contract of an attempt environment: mounts, specification, prepared and removed states."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from skm.kernel.ids import AttemptId, RepositoryId
    from skm.modules.execution.domain.contracts import RangeSpec
    from skm.modules.execution.domain.environment import BaselineEntry, EnvironmentKind
    from skm.modules.execution.domain.ids import EnvironmentId
    from skm.modules.execution.domain.review_request import ReviewTarget


@dataclass(frozen=True, slots=True)
class EnvironmentMount:
    mount: str
    repository_id: RepositoryId
    checkout_locator: str
    baseline_ref: str


@dataclass(frozen=True, slots=True)
class EnvironmentSpec:
    attempt_id: AttemptId
    kind: EnvironmentKind
    mounts: tuple[EnvironmentMount, ...]
    branch: str
    root: Path
    range: RangeSpec | None
    review_target: ReviewTarget | None


@dataclass(frozen=True, slots=True)
class PreparedEnvironment:
    environment_id: EnvironmentId
    locator: str
    mounts: Mapping[str, Path]
    baseline: tuple[BaselineEntry, ...]
    branch: str


@dataclass(frozen=True, slots=True)
class RemovedEnvironment:
    locator: str
    freed_bytes: int
