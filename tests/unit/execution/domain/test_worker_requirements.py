"""Worker requirements matching (execution §4.9, G16)."""

from __future__ import annotations

import dataclasses
from typing import Any
from uuid import UUID

import pytest

from skm.modules.execution.domain.assignment import (
    WorkerOffer,
    WorkerRequirements,
    requirement_mismatches,
    worker_matches,
)
from skm.modules.execution.domain.environment import EnvironmentKind

HOST: Any = UUID(int=5)
OTHER_HOST: Any = UUID(int=6)

REQUIREMENTS = WorkerRequirements(
    capabilities=frozenset({"runtime:claude_code", "role:executor"}),
    required_host_id=None,
    required_labels=frozenset({"linux", "web"}),
    environment_kind=EnvironmentKind.GIT_WORKTREE,
    isolation_profiles=frozenset({"worktree"}),
)
OFFER = WorkerOffer(
    worker_id=UUID(int=40),  # type: ignore[arg-type]
    host_id=HOST,
    capabilities=frozenset({"runtime:claude_code", "role:executor", "runtime:codex"}),
    labels=frozenset({"linux", "web", "gpu"}),
    environment_kinds=frozenset({EnvironmentKind.GIT_WORKTREE, EnvironmentKind.MANAGED_CLONE}),
    isolation_profiles=frozenset({"worktree", "landlock"}),
    reaped_steps=(),
)


def test_a_superset_offer_fits() -> None:
    assert worker_matches(REQUIREMENTS, OFFER)
    assert requirement_mismatches(REQUIREMENTS, OFFER) == ()
    pinned = dataclasses.replace(REQUIREMENTS, required_host_id=HOST)
    assert worker_matches(pinned, OFFER)
    empty = WorkerRequirements(frozenset(), None, frozenset(), EnvironmentKind.GIT_WORKTREE, frozenset())
    assert worker_matches(empty, OFFER)


@pytest.mark.parametrize(
    ("change", "mismatch"),
    [
        ({"capabilities": frozenset({"runtime:claude_code", "role:reviewer"})}, "capabilities"),
        ({"required_host_id": OTHER_HOST}, "required_host_id"),
        ({"required_labels": frozenset({"linux", "macos"})}, "required_labels"),
        ({"environment_kind": EnvironmentKind.EXISTING_CHECKOUT}, "environment_kind"),
        ({"isolation_profiles": frozenset({"container"})}, "isolation_profiles"),
    ],
)
def test_each_requirement_alone_rejects_the_worker(change: dict[str, Any], mismatch: str) -> None:
    requirements = dataclasses.replace(REQUIREMENTS, **change)
    assert not worker_matches(requirements, OFFER)
    assert requirement_mismatches(requirements, OFFER) == (mismatch,)


def test_all_mismatches_are_reported_together() -> None:
    offer = dataclasses.replace(
        OFFER,
        host_id=OTHER_HOST,
        capabilities=frozenset(),
        labels=frozenset(),
        environment_kinds=frozenset(),
        isolation_profiles=frozenset(),
    )
    requirements = dataclasses.replace(REQUIREMENTS, required_host_id=HOST)
    assert requirement_mismatches(requirements, offer) == (
        "capabilities",
        "required_host_id",
        "required_labels",
        "environment_kind",
        "isolation_profiles",
    )
