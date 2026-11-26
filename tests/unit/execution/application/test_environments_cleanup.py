"""Real repository cleanup decisions, K13 busy state, and host retention/reconcile boundaries."""

from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from typing import cast

import pytest

from contracts.execution._worker_protocol_support import claim, make_case
from contracts.execution.harness import exec_side as exec_side
from skm.application_bus.host import HostContext
from skm.kernel.cancel import CancelSource
from skm.kernel.errors import SkmError
from skm.modules.execution.application.commands import mark_environments_removed as command
from skm.modules.execution.domain.attempt import AttemptState
from skm.modules.execution.domain.environment import (
    BaselineEntry,
    EnvironmentKind,
    EnvironmentState,
    ExecutionEnvironment,
    attempt_branch,
)
from skm.modules.execution.domain.external_effect import EffectKind, EffectState, ExternalEffect
from skm.modules.execution.generated.commands import MarkEnvironmentsRemoved
from skm.modules.execution.generated.results import mark_environments_removed_result_from_json
from skm.modules.execution.host.clean_environments import clean
from skm.modules.execution.ports import (
    AssignmentRepository,
    AttemptRepository,
    EffectRepository,
    EnvironmentRepository,
    ExecutionEnvironmentManager,
)
from support.pg import clean_test_database as clean_test_database
from support.pg import pg_session as pg_session
from support.pg import test_database as test_database
from unit.execution.application._support import context


def terminal(side, uow, attempt):
    repository = uow.repo(AttemptRepository)
    current = repository.get(attempt.id, for_update=True)
    ended = replace(
        current,
        state=AttemptState.COMPLETED,
        finished_at=side.clock.now(),
        end_reason="FAILED",
        continuation=None,
    )
    repository.save(ended, expected_version=repository.version(attempt.id))


@pytest.mark.parametrize("terminal_attempt", [False, True])
def test_only_terminal_attempt_can_be_explicitly_removed(exec_side, monkeypatch, terminal_attempt):
    side = exec_side
    run, _, attempt, _ = make_case(side, env=False)
    monkeypatch.setattr(command, "effective_permissions", lambda *args: frozenset({"run.control"}))
    with side.uow() as uow:
        env = ExecutionEnvironment(
            side.new_id(),
            attempt.id,
            side.host1,
            EnvironmentKind.EXISTING_CHECKOUT,
            (BaselineEntry("repo", side.repo_id, "1" * 40, "1" * 40, None),),
            attempt_branch(attempt.id),
            "/owned/existing",
            EnvironmentState.READY,
            side.clock.now(),
            None,
            None,
        )
        uow.repo(EnvironmentRepository).upsert(env)
        repo = uow.repo(AttemptRepository)
        repo.save(
            replace(attempt, state=AttemptState.RUNNING, environment_id=env.id),
            expected_version=repo.version(attempt.id),
        )
        assert side.repo_id in uow.repo(EnvironmentRepository).busy_existing_checkout_repos(side.proj)
        if terminal_attempt:
            terminal(side, uow, attempt)
        dto = MarkEnvironmentsRemoved(host_id=str(side.host1), environment_ids=[str(env.id)], freed_bytes=17)
        result = command.handle(dto, context(side, uow, run), uow)
        assert result == {"marked": int(terminal_attempt)}
        assert mark_environments_removed_result_from_json(result) == result
        again = command.handle(dto, context(side, uow, run), uow)
        assert again == {"marked": 0}
        busy = uow.repo(EnvironmentRepository).busy_existing_checkout_repos(side.proj)
        assert (side.repo_id in busy) is not terminal_attempt
        uow.commit()


def test_live_lease_blocks_terminal_environment_removal(exec_side, monkeypatch):
    side = exec_side
    run, _, attempt, assignment = make_case(side, env=True)
    claim(side)
    monkeypatch.setattr(command, "effective_permissions", lambda *args: frozenset({"run.control"}))
    with side.uow() as uow:
        terminal(side, uow, attempt)
        env = uow.repo(EnvironmentRepository).for_attempt(attempt.id)
        assert uow.repo(AssignmentRepository).lease(assignment.id) is not None
        result = command.handle(
            MarkEnvironmentsRemoved(host_id=str(side.host1), environment_ids=[str(env.id)]),
            context(side, uow, run),
            uow,
        )
        assert result == {"marked": 0}
        assert uow.repo(EnvironmentRepository).for_attempt(attempt.id).state is EnvironmentState.READY


def test_unresolved_old_effect_preserves_environment_after_transcript_expiry(exec_side, monkeypatch):
    side = exec_side
    run, task, attempt, _ = make_case(side, env=True)
    monkeypatch.setattr(command, "effective_permissions", lambda *args: frozenset({"run.control"}))
    with side.uow() as uow:
        terminal(side, uow, attempt)
        env = uow.repo(EnvironmentRepository).for_attempt(attempt.id)
        effect = ExternalEffect(
            side.new_id(),
            side.ws,
            run.id,
            attempt.id,
            task.id,
            EffectKind.GIT_COMMIT,
            None,
            "sha256:" + "a" * 64,
            {
                "repository_id": str(side.repo_id),
                "target_branch": "main",
                "before_sha": "1" * 40,
                "after_sha": "2" * 40,
                "tree_sha": "3" * 40,
                "baseline_sha": "1" * 40,
                "output_ids": [],
                "output_digests": [],
                "commit_shas": ["2" * 40],
                "assignment_fencing_token": 1,
                "slot_fencing_token": 1,
                "writer_epoch_sha": "4" * 40,
                "journal": "minimum prepared/replay inputs",
            },
            EffectState.OUTCOME_UNKNOWN,
            None,
            side.clock.now() - timedelta(days=365),
            side.clock.now() - timedelta(days=365),
        )
        uow.repo(EffectRepository).add(effect)
        dto = MarkEnvironmentsRemoved(host_id=str(side.host1), environment_ids=[str(env.id)])
        assert command.handle(dto, context(side, uow, run), uow) == {"marked": 0}
        assert uow.repo(EnvironmentRepository).for_attempt(attempt.id).state is EnvironmentState.READY
        uow.repo(EffectRepository).save(
            replace(effect, state=EffectState.SUCCEEDED, receipt={"confirmed": True})
        )
        assert command.handle(dto, context(side, uow, run), uow) == {"marked": 1}


def test_foreign_host_ids_are_never_marked(exec_side, monkeypatch):
    side = exec_side
    run, _, attempt, _ = make_case(side, env=True)
    monkeypatch.setattr(command, "effective_permissions", lambda *args: frozenset({"run.control"}))
    with side.uow() as uow:
        terminal(side, uow, attempt)
        env = uow.repo(EnvironmentRepository).for_attempt(attempt.id)
        result = command.handle(
            MarkEnvironmentsRemoved(host_id=str(side.host2), environment_ids=[str(env.id)]),
            context(side, uow, run),
            uow,
        )
        assert result == {"marked": 0}
        assert uow.repo(EnvironmentRepository).for_attempt(attempt.id).state is EnvironmentState.READY


def test_worker_cannot_release_other_hosts_checkout(exec_side, monkeypatch):
    side = exec_side
    run, _, attempt, _ = make_case(side, env=True)
    monkeypatch.setattr(command, "effective_permissions", lambda *args: frozenset({"worker.claim"}))
    monkeypatch.setattr(command, "worker_for_principal", lambda *args: SimpleNamespace(host_id=side.host2))
    with side.uow() as uow:
        env = uow.repo(EnvironmentRepository).for_attempt(attempt.id)
        with pytest.raises(SkmError, match="registered host"):
            command.handle(
                MarkEnvironmentsRemoved(host_id=str(side.host1), environment_ids=[str(env.id)]),
                context(side, uow, run, actor=side.worker1_client._actor),
                uow,
            )


@pytest.mark.parametrize(
    ("retain", "eligible", "accepted", "expected"),
    [
        ("always", True, True, 0),
        ("never", False, True, 0),
        ("failed", True, False, 0),
        ("failed", True, True, 1),
        ("never", True, False, 1),
    ],
)
def test_host_retention_needs_independent_terminal_empty_reconcile_proof(
    retain, eligible, accepted, expected
):
    removed, dispatched = [], []
    row = {
        "environment_id": "00000000-0000-0000-0000-000000000001",
        "kind": "git_worktree",
        "attempt_id": "00000000-0000-0000-0000-000000000003",
        "local_locator": "/owned/attempt",
        "attempt_end_reason": "ACCEPTED" if accepted else "FAILED",
    }

    class Client:
        def ask(self, query):
            from skm.modules.execution.generated.queries import GetAttempt

            if isinstance(query, GetAttempt):
                return {"end_reason": row["attempt_end_reason"]}
            return {"items": [row], "next_after": None}

        def dispatch(self, dto, **kwargs):
            dispatched.append(dto)
            return {"marked": 1}

    class Manager:
        def remove(self, locator):
            removed.append(locator)
            return SimpleNamespace(freed_bytes=123)

    ctx = SimpleNamespace(
        client=Client(), host_id="00000000-0000-0000-0000-000000000002", cancel=CancelSource().token
    )
    report = clean(
        cast("HostContext", ctx),
        {"retain": retain},
        managers={"git_worktree": cast("ExecutionEnvironmentManager", Manager())},
        eligible=lambda _: eligible,
        idempotency_key="clean-key",
        command_factory=lambda command: command,
    )
    assert report == {"marked": expected, "freed_bytes": 123 * expected}
    assert len(removed) == len(dispatched) == expected


def test_mark_removed_bus_records_use_exact_generated_codecs():
    from uuid import uuid4

    from skm.modules.execution.generated.commands import mark_environments_removed_from_json

    raw = {"host_id": str(uuid4()), "environment_ids": [str(uuid4())], "freed_bytes": 123}
    dto = command.MarkEnvironmentsRemovedCommand.from_json(raw)
    assert dto.to_json() == mark_environments_removed_from_json(raw)
    receipt = command.MarkEnvironmentsRemovedReceipt.from_json({"marked": 1})
    assert receipt.to_json() == {"marked": 1}
    assert command.SPEC.dto is type(dto)
    assert command.SPEC.result is type(receipt)


def test_registered_cleanup_dispatch_releases_busy_checkout(exec_side):
    side = exec_side
    _, _, attempt, _ = make_case(side, env=True)
    with side.uow() as uow:
        terminal(side, uow, attempt)
        env = uow.repo(EnvironmentRepository).for_attempt(attempt.id)
        uow.commit()
    dto = command.MarkEnvironmentsRemovedCommand.from_json(
        {
            "host_id": str(side.host1),
            "environment_ids": [str(env.id)],
            "freed_bytes": 19,
        }
    )
    result = side.worker1_client.dispatch(dto, idempotency_key=f"remove:{side.new_id()}")
    assert result["marked"] == 1
    with side.uow(readonly=True) as uow:
        assert uow.repo(EnvironmentRepository).for_attempt(attempt.id).state is EnvironmentState.REMOVED
