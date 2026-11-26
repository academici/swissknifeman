"""Assignment reads are pinned, extended without revival and revoked with release."""

from datetime import timedelta
from typing import Any

from contracts.execution.test_worker_protocol import claim, make_case, worker_claim
from skm.modules.artifacts import public as artifacts
from skm.modules.execution import public as execution
from unit.execution.application._support import _shared_side as _shared_side
from unit.execution.application._support import side as side


def test_claim_grants_only_revision_pinned_versions_and_release_revokes(side: Any) -> None:
    make_case(side)
    claimed = claim(side)
    principal = side.worker1_client._actor.principal_id
    with side.uow(readonly=True) as uow:
        assert uow.repo(artifacts.AccessGrantRepository).active_for(principal, side.fv1, side.clock.now())
        assert not uow.repo(artifacts.AccessGrantRepository).active_for(principal, side.fv2, side.clock.now())
    side.clock.advance(timedelta(seconds=15))
    side.worker1_client.dispatch(
        execution.RenewLease(claim=worker_claim(side, claimed)), idempotency_key=f"renew:{side.new_id()}"
    )
    side.worker1_client.dispatch(
        execution.ReleaseAssignment(
            claim=worker_claim(side, claimed), reason="retry_later", retain_environment=True
        ),
        idempotency_key=f"release:{side.new_id()}",
    )
    with side.uow(readonly=True) as uow:
        assert not uow.repo(artifacts.AccessGrantRepository).active_for(principal, side.fv1, side.clock.now())


def test_revoked_grant_is_not_revived_by_extend(side: Any) -> None:
    make_case(side)
    claimed = claim(side)
    with side.uow() as uow:
        artifacts.revoke_grants(
            uow, reason=artifacts.GrantReason.ASSIGNMENT, ref=claimed["assignment_id"], now=side.clock.now()
        )
        assert (
            artifacts.extend_grants(
                uow,
                reason=artifacts.GrantReason.ASSIGNMENT,
                ref=claimed["assignment_id"],
                expires_at=side.clock.now() + timedelta(hours=1),
                now=side.clock.now(),
            )
            == 0
        )
        uow.commit()
