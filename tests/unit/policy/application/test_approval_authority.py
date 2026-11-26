"""Who may approve, and whether an approval still counts when it is spent (policy §7, §15, ench2).

Approve and deny check the stored kind of the principal (a human) *and* ``intent.approve`` on the scope of the
intent. Consuming an approval repeats the check against the approver as they are now: membership, state and
kind are read afresh, the bearer token of the approval is never consulted. The approval of the system is
valid only while the condition that made it holds.
"""

from typing import Any

import pytest

from skm.kernel.actor import SYSTEM_PRINCIPAL_ID, Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, SkmError, Unauthenticated
from skm.kernel.json_types import JsonValue
from skm.modules.access.domain.principal import new_principal
from skm.modules.access.generated.commands import (
    CreateToken,
    DisablePrincipal,
    GrantMembership,
    RevokeMembership,
    RevokeToken,
)
from skm.modules.access.generated.commands import Role as GrantRole
from skm.modules.access.generated.queries import GetPrincipal
from skm.modules.access.ports import PrincipalRepository
from skm.modules.access.public import SYSTEM_ACTOR, Role, authenticate_token
from skm.modules.policy.generated.commands import ApproveIntent, DenyIntent
from unit.policy.application.harness import ALL_EFFECTS, INSTANCE, PEPPER, World
from unit.policy.application.test_lifecycle import approve, propose, refused, start, view


def maintainer(world: World, name: str = "maintainer") -> Actor:
    return world.person(name, {world.workspace_id: Role.MAINTAINER})


def approval_of(world: World, who: str, **fields: Any) -> Any:
    proposed = propose(world)
    approve(world, proposed.intent_id, who, **fields)
    return proposed


# ------------------------------------------------------------------------------------------ the human gate
def test_a_human_with_the_right_approves_and_is_the_recorded_approver(world: World) -> None:
    mine = maintainer(world)
    proposed = propose(world)
    approve(world, proposed.intent_id, "maintainer")
    (approval,) = view(world, proposed.intent_id).approvals
    assert approval.approver_id == mine.principal_id


@pytest.mark.parametrize("operation", ["approve", "deny"])
@pytest.mark.parametrize("kind", [PrincipalKind.SERVICE, PrincipalKind.WORKER])
def test_a_service_or_a_worker_cannot_pass_the_human_gate_even_as_owner(
    world: World, operation: str, kind: PrincipalKind
) -> None:
    other = world.person("machine", {world.workspace_id: Role.OWNER}, kind=kind)
    proposed = propose(world)
    seen = view(world, proposed.intent_id)
    dto: Any = (
        ApproveIntent(
            intent_id=proposed.intent_id, expected_row_version=seen.row_version, args_digest=seen.args_digest
        )
        if operation == "approve"
        else DenyIntent(intent_id=proposed.intent_id, expected_row_version=seen.row_version, reason="no")
    )
    refused(world, lambda: world.run(dto, other), ErrorCode.FORBIDDEN, reason="human_gate")


def test_a_claimed_human_kind_does_not_make_a_service_a_human(world: World) -> None:
    service = world.person("machine", {world.workspace_id: Role.OWNER}, kind=PrincipalKind.SERVICE)
    spoofed = Actor(principal_id=service.principal_id, kind=PrincipalKind.HUMAN, display_name="machine")
    proposed = propose(world)
    seen = view(world, proposed.intent_id)
    dto = ApproveIntent(
        intent_id=proposed.intent_id, expected_row_version=seen.row_version, args_digest=seen.args_digest
    )
    refused(world, lambda: world.run(dto, spoofed), ErrorCode.UNAUTHENTICATED)


def test_a_human_without_intent_approve_on_the_scope_is_refused(world: World) -> None:
    world.person("watcher", {world.workspace_id: Role.VIEWER})
    world.person("stranger", {})
    member = world.person("member", {world.workspace_id: Role.MEMBER})
    proposed = propose(world)
    for who in ("watcher", "stranger", "member"):
        error = refused(world, lambda who=who: approve(world, proposed.intent_id, who), ErrorCode.FORBIDDEN)
        assert error.details["permission"] == "intent.approve"
    assert member.kind is PrincipalKind.HUMAN


def test_the_right_is_decided_on_the_scope_of_the_intent_not_on_another_workspace(world: World) -> None:
    other = world.person("elsewhere", {})
    proposed = propose(world)
    seen = view(world, proposed.intent_id)
    dto = ApproveIntent(
        intent_id=proposed.intent_id, expected_row_version=seen.row_version, args_digest=seen.args_digest
    )
    refused(world, lambda: world.run(dto, other), ErrorCode.FORBIDDEN)


# ------------------------------------------------------------------------------------------ at consumption
def test_membership_revoked_between_approve_and_start_blocks_the_effect(world: World) -> None:
    mine = maintainer(world)
    proposed = approval_of(world, "maintainer")
    world.run(RevokeMembership(scope_id=world.workspace_id, principal_id=mine.principal_id))
    refused(
        world,
        lambda: start(world, proposed.intent_id),
        ErrorCode.FORBIDDEN,
        reason="approval_authority_revoked",
    )
    assert world.intents()[proposed.intent_id].state.value == "approved"  # nothing was spent
    assert all(item.used_at is None for item in world.approvals().values())


def test_a_disabled_approver_blocks_the_effect(world: World) -> None:
    mine = maintainer(world)
    proposed = approval_of(world, "maintainer")
    principal = world.ask(GetPrincipal(principal_id=mine.principal_id))
    world.run(
        DisablePrincipal(
            principal_id=mine.principal_id, expected_row_version=principal.row_version, reason="left"
        )
    )
    refused(
        world,
        lambda: start(world, proposed.intent_id),
        ErrorCode.FORBIDDEN,
        reason="approval_authority_revoked",
    )


def test_a_downgraded_approver_blocks_the_effect(world: World) -> None:
    mine = maintainer(world)
    proposed = approval_of(world, "maintainer")
    world.run(RevokeMembership(scope_id=world.workspace_id, principal_id=mine.principal_id))
    world.run(
        GrantMembership(scope_id=world.workspace_id, principal_id=mine.principal_id, role=GrantRole.VIEWER)
    )
    refused(
        world,
        lambda: start(world, proposed.intent_id),
        ErrorCode.FORBIDDEN,
        reason="approval_authority_revoked",
    )


def test_an_approver_who_still_holds_the_right_is_enough_even_if_the_starter_is_someone_else(
    world: World,
) -> None:
    maintainer(world)
    proposed = approval_of(world, "maintainer")
    assert start(world, proposed.intent_id, "owner").state == "executing"


def test_losing_the_bearer_token_of_the_approver_does_not_erase_the_approval(world: World) -> None:
    mine = maintainer(world)
    created = world.run(
        CreateToken.from_json(
            {
                "name": "laptop",
                "scope_grants": [
                    {"scope_id": str(INSTANCE), "permissions": ["token.own"]},
                    {"scope_id": str(world.workspace_id), "permissions": ["intent.approve"]},
                ],
            }
        ),
        mine,
    )
    with world.uow(readonly=True) as uow:
        bearer = authenticate_token(uow, created.secret, pepper=PEPPER, now=world.clock.now())
    proposed = propose(world)
    seen = view(world, proposed.intent_id)
    world.run(
        ApproveIntent(
            intent_id=proposed.intent_id, expected_row_version=seen.row_version, args_digest=seen.args_digest
        ),
        bearer,
    )
    world.run(RevokeToken(token_id=created.token_id), mine)
    with pytest.raises(Unauthenticated):  # the revoked token itself no longer authenticates
        world.run(
            ApproveIntent(
                intent_id=proposed.intent_id,
                expected_row_version=seen.row_version,
                args_digest=seen.args_digest,
            ),
            bearer,
        )
    assert start(world, proposed.intent_id).state == "executing"  # the durable approval stands


# ----------------------------------------------------------------------------------- the system approval
def test_the_system_approval_is_checked_by_its_own_path_and_never_by_membership(world: World) -> None:
    proposed = propose(world, "git_commit")
    assert proposed.state == "approved"
    assert start(world, proposed.intent_id).state == "executing"  # no human involved, no membership lookup


def test_the_system_approval_dies_when_the_kind_starts_to_need_a_human(world: World) -> None:
    proposed = propose(world, "git_commit")
    world.set_config("policy.approval.required_for", list[JsonValue](ALL_EFFECTS))
    refused(
        world,
        lambda: start(world, proposed.intent_id),
        ErrorCode.APPROVAL_MISMATCH,
        reason="auto_approval_not_current",
    )


def test_a_user_cannot_create_an_approval_signed_by_the_system(world: World) -> None:
    with world.uow() as uow:  # the system principal exists in a running instance (`skm init`)
        uow.repo(PrincipalRepository).add(
            new_principal(
                principal_id=SYSTEM_PRINCIPAL_ID,
                kind=PrincipalKind.SERVICE,
                display_name="system",
                created_by=None,
                now=world.clock.now(),
            )
        )
        uow.commit()
    proposed = propose(world)
    seen = view(world, proposed.intent_id)
    dto = ApproveIntent(
        intent_id=proposed.intent_id, expected_row_version=seen.row_version, args_digest=seen.args_digest
    )
    with pytest.raises(Forbidden) as caught:
        world.run(dto, SYSTEM_ACTOR)  # the service-kind system principal is no human either
    assert caught.value.details["reason"] == "human_gate"
    assert all(item.approver_id != SYSTEM_PRINCIPAL_ID for item in world.approvals().values())


# ------------------------------------------------------------------------------------------ misc
def test_deny_and_approve_are_both_visible_in_the_approval_history(world: World) -> None:
    maintainer(world)
    proposed = propose(world)
    seen = view(world, proposed.intent_id)
    world.run(
        DenyIntent(intent_id=proposed.intent_id, expected_row_version=seen.row_version, reason="x"),
        "maintainer",
    )
    history = view(world, proposed.intent_id).approvals
    assert [(item.decision, item.approver_id) for item in history] == [
        ("deny", world.actor("maintainer").principal_id)
    ]


def test_the_commit_kind_is_not_an_exception_to_the_gate(world: World) -> None:
    # git_commit needs no human *approval*, but a person who denies it still has to be a human with the right
    proposed = propose(world, "git_commit")
    world.person("watcher", {world.workspace_id: Role.VIEWER})
    seen = view(world, proposed.intent_id)
    with pytest.raises(SkmError):
        world.run(
            DenyIntent(intent_id=proposed.intent_id, expected_row_version=seen.row_version, reason="x"),
            "watcher",
        )
