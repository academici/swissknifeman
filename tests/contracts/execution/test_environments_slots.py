"""Durable writer-host pins and project-scoped existing-checkout exclusion (K6/K13)."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from typing import TYPE_CHECKING

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, PreconditionFailed
from skm.modules.execution.domain.environment import (
    BaselineEntry,
    EnvironmentKind,
    EnvironmentState,
    ExecutionEnvironment,
    attempt_branch,
)
from skm.modules.execution.domain.ids import EnvironmentId
from skm.modules.execution.ports import EnvironmentRepository, IntegrationSlotRepository

from .seed_helpers import COMMIT_1, seed_attempt, seed_run, seed_task

if TYPE_CHECKING:
    from .harness import ExecSide


def test_environment_busy_repositories_and_durable_integration_hosts(exec_side: ExecSide) -> None:
    with exec_side.uow() as uow:
        run = seed_run(exec_side, uow)
        task = seed_task(exec_side, uow, run.id)
        att = seed_attempt(exec_side, uow, run.id, task.id)
        env = ExecutionEnvironment(
            EnvironmentId(exec_side.new_id()),
            att.id,
            exec_side.host1,
            EnvironmentKind.EXISTING_CHECKOUT,
            (BaselineEntry("repo", exec_side.repo_id, COMMIT_1, COMMIT_1, None),),
            attempt_branch(att.id),
            "owned-checkout-locator",
            EnvironmentState.READY,
            exec_side.clock.now(),
            None,
            None,
        )
        envs = uow.repo(EnvironmentRepository)
        envs.upsert(env)
        assert envs.for_attempt(att.id) == env
        assert envs.busy_existing_checkout_repos(exec_side.proj) == frozenset({exec_side.repo_id})
        assert envs.busy_existing_checkout_repos(exec_side.proj2) == frozenset()
        envs.upsert(replace(env, state=EnvironmentState.DISCARDED, discarded_at=exec_side.clock.now()))
        assert envs.busy_existing_checkout_repos(exec_side.proj) == frozenset()
        slots = uow.repo(IntegrationSlotRepository)
        assert slots.pin_target_host(exec_side.repo_id, "main", exec_side.host1, exec_side.clock.now()) == (
            exec_side.host1,
            True,
        )
        assert slots.pin_target_host(exec_side.repo_id, "main", exec_side.host2, exec_side.clock.now()) == (
            exec_side.host1,
            False,
        )
        assert (
            slots.pin_host(run.id, exec_side.repo_id, exec_side.host1, exec_side.clock.now())
            == exec_side.host1
        )
        assert (
            slots.pin_host(run.id, exec_side.repo_id, exec_side.host2, exec_side.clock.now())
            == exec_side.host1
        )
        acquired = slots.acquire(
            exec_side.repo_id,
            "main",
            att.id,
            exec_side.host1,
            exec_side.clock.now(),
            exec_side.clock.now() + timedelta(days=1),
        )
        assert acquired is not None
        slots.release(acquired.id, att.id, acquired.fencing_token)
        assert slots.target_hosts(((exec_side.repo_id, "main"),)) == {
            (exec_side.repo_id, "main"): exec_side.host1
        }
        assert slots.hosts_for_run(run.id) == {exec_side.repo_id: exec_side.host1}
        uow.commit()
    with exec_side.uow() as uow:
        with pytest.raises(PreconditionFailed) as exc:
            uow.repo(IntegrationSlotRepository).acquire(
                exec_side.repo_id,
                "main",
                att.id,
                exec_side.host2,
                exec_side.clock.now(),
                exec_side.clock.now() + timedelta(days=1),
            )
        assert exc.value.code is ErrorCode.INTEGRATION_HOST_MISMATCH
        uow.rollback()
    with exec_side.uow() as uow:
        with pytest.raises(Conflict) as exc:
            uow.repo(IntegrationSlotRepository).release(acquired.id, att.id, acquired.fencing_token)
        assert exc.value.code is ErrorCode.LEASE_LOST
        uow.rollback()
