"""Worker offers, assignments and effect fixtures for execution persistence contracts."""

from __future__ import annotations

from typing import TYPE_CHECKING

from skm.modules.execution.domain.assignment import (
    Assignment,
    AssignmentState,
    WorkerOffer,
    WorkerRequirements,
)
from skm.modules.execution.domain.environment import EnvironmentKind
from skm.modules.execution.domain.external_effect import EffectKind, EffectState, ExternalEffect
from skm.modules.execution.domain.ids import AssignmentId, ExternalEffectId
from skm.modules.execution.ports import AssignmentRepository, EffectRepository

from .seed_helpers import COMMIT_1, COMMIT_2, DIGEST_A, TREE_1

if TYPE_CHECKING:
    from skm.kernel.ports_uow import UnitOfWork
    from skm.modules.execution.domain.attempt import Attempt

    from .harness import ExecSide


def offer(side: ExecSide) -> WorkerOffer:
    return WorkerOffer(
        side.worker1,
        side.host1,
        frozenset(),
        frozenset({"linux"}),
        frozenset({EnvironmentKind.GIT_WORKTREE}),
        frozenset({"landlock"}),
        (),
    )


def assignment(
    side: ExecSide, uow: UnitOfWork, attempt: Attempt, *, effect_id: ExternalEffectId | None = None
) -> Assignment:
    row = Assignment(
        id=AssignmentId(side.new_id()),
        run_id=attempt.run_id,
        task_id=attempt.task_id,
        attempt_id=attempt.id,
        workspace_id=side.ws,
        state=AssignmentState.AVAILABLE,
        available_at=side.clock.now(),
        requirements=WorkerRequirements(
            frozenset(),
            side.host1 if effect_id else None,
            frozenset(),
            EnvironmentKind.GIT_WORKTREE,
            frozenset({"landlock"}),
        ),
        priority=0,
        last_fencing_token=0,
        reconcile_effect_id=effect_id,
        reap_stage_record_id=None,
        reap_step_id=None,
        created_at=side.clock.now(),
        row_version=1,
    )
    uow.repo(AssignmentRepository).add(row)
    return row


def effect(side: ExecSide, uow: UnitOfWork, attempt: Attempt) -> ExternalEffect:
    row = ExternalEffect(
        ExternalEffectId(side.new_id()),
        side.ws,
        attempt.run_id,
        attempt.id,
        attempt.task_id,
        EffectKind.GIT_COMMIT,
        None,
        DIGEST_A,
        {
            "repository_id": str(side.repo_id),
            "target_branch": "main",
            "before_sha": COMMIT_1,
            "after_sha": COMMIT_2,
            "tree_sha": TREE_1,
            "baseline_sha": COMMIT_1,
            "output_ids": [],
            "output_digests": [],
            "commit_shas": [COMMIT_2],
            "assignment_fencing_token": 1,
            "slot_fencing_token": 1,
            "writer_epoch_sha": COMMIT_1,
        },
        EffectState.OUTCOME_UNKNOWN,
        None,
        side.clock.now(),
        side.clock.now(),
    )
    uow.repo(EffectRepository).add(row)
    return row
