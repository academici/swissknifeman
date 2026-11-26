"""An approval is spent once, for one digest, by one admission (policy §7, §11, ench2; consistency §07).

The attacks here are the ones a reviewer tries first: starting twice (sequentially and at the same time),
starting with other arguments, carrying an approval over to another intent or scope, starting after the
authority behind the approval changed, and replaying the receipt of a start. Each ends with the effect not
admitted a second time and the stored state untouched by the refusal.
"""

import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from contracts.policy.pg_world import PgWorld, build_pg_world
from security.test_blob_access import (
    _memory_tables,
    _pg_state,
    assert_denied_audit,
    assert_private_output,
    audit_snapshot,
    files_under,
)
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, SkmError
from skm.modules.access.public import Role
from skm.modules.policy.domain.approval import ApprovalId
from skm.modules.policy.domain.tool_intent import IntentState
from skm.modules.policy.generated.commands import ApproveIntent, StartIntentExecution
from skm.modules.policy.ports import ApprovalRepository
from support.pg import TestDatabase
from support.pg import clean_test_database as clean_test_database
from support.pg import pg_session as pg_session
from support.pg import test_database as test_database
from unit.policy.application.harness import World, build_world, push_args
from unit.policy.application.test_lifecycle import approve, outcome, propose, refused, start, view


@pytest.fixture
def world() -> World:
    return build_world()


def started_events(world: World) -> int:
    return len(world.events("intent-execution-started"))


def test_two_concurrent_starts_use_the_approval_once(world: World) -> None:
    proposed = propose(world)
    approve(world, proposed.intent_id)
    digest = view(world, proposed.intent_id).args_digest
    gate = threading.Barrier(2)
    results: list[Any] = []

    def attempt() -> None:
        gate.wait()
        try:
            results.append(world.run(StartIntentExecution(intent_id=proposed.intent_id, args_digest=digest)))
        except SkmError as error:
            results.append(error)

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    admitted = [item for item in results if not isinstance(item, SkmError)]
    refused_ones = [item for item in results if isinstance(item, SkmError)]
    assert len(admitted) == 1
    assert len(refused_ones) == 1
    assert refused_ones[0].code is ErrorCode.APPROVAL_MISMATCH
    assert refused_ones[0].details["reason"] == "already_started"
    assert started_events(world) == 1
    (approval,) = view(world, proposed.intent_id).approvals
    assert approval.used_at is not None


def test_two_concurrent_starts_with_distinct_keys_still_admit_one(world: World) -> None:
    proposed = propose(world)
    approve(world, proposed.intent_id)
    digest = view(world, proposed.intent_id).args_digest
    gate = threading.Barrier(4)
    results: list[Any] = []

    def attempt(key: str) -> None:
        gate.wait()
        try:
            results.append(
                world.run(StartIntentExecution(intent_id=proposed.intent_id, args_digest=digest), key=key)
            )
        except SkmError as error:
            results.append(error)

    threads = [threading.Thread(target=attempt, args=(f"k{n}",)) for n in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len([item for item in results if not isinstance(item, SkmError)]) == 1
    assert started_events(world) == 1


def test_a_second_start_is_refused_and_a_finished_effect_cannot_be_started_again(world: World) -> None:
    proposed = propose(world)
    approve(world, proposed.intent_id)
    start(world, proposed.intent_id)
    refused(
        world, lambda: start(world, proposed.intent_id), ErrorCode.APPROVAL_MISMATCH, reason="already_started"
    )
    outcome(world, proposed.intent_id, "succeeded")
    refused(
        world, lambda: start(world, proposed.intent_id), ErrorCode.APPROVAL_MISMATCH, reason="already_started"
    )
    assert started_events(world) == 1


def test_an_approval_does_not_follow_the_effect_to_a_new_intent(world: World) -> None:
    first = propose(world)
    approve(world, first.intent_id)
    start(world, first.intent_id)
    outcome(world, first.intent_id, "succeeded")
    again = propose(world)  # the very same effect, proposed again after it ran
    assert again.intent_id != first.intent_id
    assert again.state == "proposed"
    refused(world, lambda: start(world, again.intent_id), ErrorCode.APPROVAL_REQUIRED)
    assert all(item.used_at is not None for item in view(world, first.intent_id).approvals)


def test_changed_arguments_after_the_approval_cannot_reach_the_effect(world: World) -> None:
    proposed = propose(world)
    approve(world, proposed.intent_id)
    other = propose(
        world, args=push_args(after_sha="d" * 40)
    )  # the candidate moved: a new digest, a new intent
    assert other.args_digest != proposed.args_digest
    refused(world, lambda: start(world, other.intent_id), ErrorCode.APPROVAL_REQUIRED)  # nothing approved it
    refused(
        world,
        lambda: start(world, proposed.intent_id, digest=other.args_digest),
        ErrorCode.APPROVAL_MISMATCH,
        reason="digest_changed",
    )
    refused(
        world,
        lambda: start(world, other.intent_id, digest=proposed.args_digest),
        ErrorCode.APPROVAL_REQUIRED,
    )


@pytest.mark.parametrize(
    "changes",
    [
        {
            "endpoint": {
                "transport": "https",
                "hostname": "evil.example",
                "effective_port": 443,
                "repository_path": "acme/app.git",
            }
        },
        {
            "endpoint": {
                "transport": "https",
                "hostname": "github.com",
                "effective_port": 8443,
                "repository_path": "acme/app.git",
            }
        },
        {
            "endpoint": {
                "transport": "ssh",
                "hostname": "github.com",
                "effective_port": 443,
                "repository_path": "acme/app.git",
            }
        },
        {
            "endpoint": {
                "transport": "https",
                "hostname": "github.com",
                "effective_port": 443,
                "repository_path": "evil/app.git",
            }
        },
        {"target_ref": "refs/heads/release"},
        {"refspecs": ["refs/heads/main:refs/heads/release"]},
        {"after_sha": "d" * 40},
    ],
)
def test_the_approval_binds_host_port_path_transport_ref_and_commit(
    world: World, changes: dict[str, Any]
) -> None:
    proposed = propose(world)
    approve(world, proposed.intent_id)
    moved = propose(world, args=push_args(**changes))
    assert moved.args_digest != proposed.args_digest
    refused(world, lambda: start(world, moved.intent_id), ErrorCode.APPROVAL_REQUIRED)


def test_an_approval_of_one_scope_does_not_open_the_same_effect_in_another(world: World) -> None:
    from skm.kernel.ids import ScopeId
    from skm.kernel.scopes import ScopeKind, ScopeRegistry

    sibling = ScopeId(world.ids.new_id())
    with world.uow() as uow:
        registry = uow.repo(ScopeRegistry)
        parent = registry.ancestors(world.scope_id)[-2].id
        registry.create(sibling, ScopeKind.RUN, parent=parent, workspace_id=world.workspace_id)
        uow.commit()
    first = propose(world)
    approve(world, first.intent_id)
    from skm.modules.policy.generated.commands import EffectKind, ProposeIntent

    second = world.run(
        ProposeIntent(
            scope_id=sibling, subject_ref="run:2", kind=EffectKind.GIT_PUSH, args=push_args(), reason="again"
        )
    )
    assert second.intent_id != first.intent_id
    assert second.state == "proposed"
    refused(world, lambda: start(world, second.intent_id), ErrorCode.APPROVAL_REQUIRED)


def test_revoking_the_kind_after_the_approval_blocks_the_effect_until_it_is_permitted_again(
    world: World,
) -> None:
    proposed = propose(world)
    approve(world, proposed.intent_id)
    world.allow_effects("git_commit")
    refused(world, lambda: start(world, proposed.intent_id), ErrorCode.FORBIDDEN, reason="revoked")
    refused(world, lambda: start(world, proposed.intent_id), ErrorCode.FORBIDDEN, reason="revoked")
    assert all(
        item.used_at is None for item in view(world, proposed.intent_id).approvals
    )  # nothing was spent
    world.allow_effects("git_commit", "git_push")
    assert start(world, proposed.intent_id).state == "executing"


def test_the_approval_row_is_spent_once_at_the_repository_too(world: World) -> None:
    proposed = propose(world)
    approved = approve(world, proposed.intent_id)
    with world.uow() as uow:
        approvals = uow.repo(ApprovalRepository)
        approvals.mark_used(ApprovalId(approved.approval_id), world.clock.now())
        with pytest.raises(Forbidden) as caught:
            approvals.mark_used(ApprovalId(approved.approval_id), world.clock.now())
        assert caught.value.code is ErrorCode.APPROVAL_MISMATCH
        uow.commit()


def test_a_refusal_record_never_admits_an_effect(world: World) -> None:
    from skm.modules.policy.generated.commands import DenyIntent

    proposed = propose(world)
    seen = view(world, proposed.intent_id)
    world.run(DenyIntent(intent_id=proposed.intent_id, expected_row_version=seen.row_version, reason="no"))
    with world.uow() as uow:
        (record,) = uow.repo(ApprovalRepository).for_intent(proposed.intent_id)
        with pytest.raises(Forbidden):
            uow.repo(ApprovalRepository).mark_used(
                record.id, world.clock.now()
            )  # a deny row is not spendable
    assert world.intents()[proposed.intent_id].state is IntentState.DENIED


def test_the_approval_made_before_a_membership_loss_is_not_an_open_door(world: World) -> None:
    from skm.modules.access.generated.commands import RevokeMembership

    mine = world.person("maintainer", {world.workspace_id: Role.MAINTAINER})
    proposed = propose(world)
    approve(world, proposed.intent_id, "maintainer")
    world.run(RevokeMembership(scope_id=world.workspace_id, principal_id=mine.principal_id))
    refused(
        world,
        lambda: start(world, proposed.intent_id),
        ErrorCode.FORBIDDEN,
        reason="approval_authority_revoked",
    )


def test_approving_with_a_digest_of_another_intent_fails(world: World) -> None:
    first = propose(world)
    second = propose(world, args=push_args(after_sha="d" * 40))
    seen = view(world, second.intent_id)
    dto = ApproveIntent(
        intent_id=second.intent_id, expected_row_version=seen.row_version, args_digest=first.args_digest
    )
    refused(world, lambda: world.run(dto), ErrorCode.APPROVAL_MISMATCH, reason="digest_changed")


@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.pg)])
def admission_world(request: pytest.FixtureRequest) -> Iterator[World]:
    if request.param == "memory":
        yield build_world()
    else:
        database: TestDatabase = request.getfixturevalue("clean_test_database")
        postgres = build_pg_world(database)
        try:
            yield postgres
        finally:
            postgres.close()


def _admission_state(world: World) -> object:
    if isinstance(world, PgWorld):
        return _pg_state(world.pg.database.dsn, ("access", "policy"))
    return _memory_tables(world.backend)


@pytest.mark.parametrize(
    ("probe", "expected", "reason"),
    [
        ("replay", ErrorCode.APPROVAL_MISMATCH, "already_started"),
        ("digest", ErrorCode.APPROVAL_MISMATCH, "digest_changed"),
        ("expired", ErrorCode.APPROVAL_MISMATCH, "no_valid_approval"),
        ("revoked", ErrorCode.FORBIDDEN, "revoked"),
    ],
)
def test_failed_effect_admission_never_changes_approval_or_emits_another_output(
    admission_world: World,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    probe: str,
    expected: ErrorCode,
    reason: str,
) -> None:
    world = admission_world
    private = "private-approval-arguments-0196"
    proposed = propose(
        world,
        args=push_args(
            target_ref=f"refs/heads/{private}", refspecs=[f"refs/heads/main:refs/heads/{private}"]
        ),
    )
    approved = approve(world, proposed.intent_id, ttl_seconds=60)
    digest = proposed.args_digest
    if probe == "replay":
        assert start(world, proposed.intent_id).approval_id == approved.approval_id
    elif probe == "digest":
        digest = propose(world, args=push_args(after_sha="e" * 40)).args_digest
    elif probe == "expired":
        (approval,) = view(world, proposed.intent_id).approvals
        world.clock.set(approval.expires_at)
    else:
        world.allow_effects("git_commit")

    dsn = world.pg.database.dsn if isinstance(world, PgWorld) else None
    backend = None if isinstance(world, PgWorld) else world.backend
    audits = audit_snapshot(dsn, backend)
    before = _admission_state(world)
    outside = tmp_path / "effect-output"
    outside.write_text("untouched")
    fs = files_under(tmp_path)
    original = view(world, proposed.intent_id)
    capsys.readouterr()
    with pytest.raises(SkmError) as rejected:
        world.run(
            StartIntentExecution(intent_id=proposed.intent_id, args_digest=digest), key=f"admission-{probe}"
        )
    assert rejected.value.code is expected
    assert rejected.value.details["reason"] == reason
    assert _admission_state(world) == before
    markers = (private, str(approved.approval_id))
    assert_denied_audit(audits, audit_snapshot(dsn, backend), ("policy.start_intent_execution",), *markers)
    assert_private_output((rejected.value, rejected.value.details, capsys.readouterr()), *markers)
    assert files_under(tmp_path) == fs
    assert view(world, proposed.intent_id) == original
    events = world.started_events() if isinstance(world, PgWorld) else started_events(world)
    assert events == (probe == "replay")
