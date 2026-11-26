"""Revision visas belong to exactly one readiness report and are append-only."""

from dataclasses import replace
from datetime import timedelta

import pytest

from contracts.execution.event_helpers import make_readiness
from contracts.execution.harness import ExecSide
from contracts.execution.harness import exec_side as exec_side
from skm.kernel.errors import SkmError
from skm.modules.execution.domain.readiness import ReadinessScope, RevisionVisa, canonical_start_request
from skm.modules.execution.ports import ReadinessRepository


def test_visa_round_trip_and_report_identity_are_shared_by_backends(exec_side: ExecSide) -> None:
    side = exec_side
    selection = {"phases": ["P1"], "task_keys": []}
    request = canonical_start_request({}, selection, mode="progressive_per_phase")
    report = replace(
        make_readiness(side, start_request=request),
        scope=ReadinessScope("selection", ("P1",)),
    )
    visa = RevisionVisa(
        side.new_id(),
        report.workspace_id,
        report.plan_id,
        report.revision_id,
        report.id,
        selection,
        side.owner.principal_id,
        "Scoped approval",
        side.clock.now(),
    )
    latest = replace(visa, id=side.new_id(), signed_at=visa.signed_at + timedelta(seconds=1))
    with side.uow() as uow:
        repo = uow.repo(ReadinessRepository)
        assert repo.latest_visa_for(report.revision_id) is None
        repo.add(report)
        repo.add_visa(latest)
        repo.add_visa(visa)
        uow.commit()

    for wrong in (
        replace(visa, id=side.new_id(), workspace_id=side.ws2),
        replace(visa, id=side.new_id(), plan_id=side.plan2),
        replace(visa, id=side.new_id(), revision_id=side.rev1),
        visa,
    ):
        with side.uow() as uow, pytest.raises(SkmError):
            uow.repo(ReadinessRepository).add_visa(wrong)

    with side.uow(readonly=True) as uow:
        repo = uow.repo(ReadinessRepository)
        assert repo.get(report.id).scope == report.scope
        assert repo.get(report.id).start_request == request
        assert repo.latest_visa_for(report.revision_id) == latest
        assert repo.latest_visa_for(side.rev1) is None
        first = repo.get_visa(visa.id)
        assert first == visa
        assert first.selection is not None
        first.selection["phases"] = ["P2"]
        assert repo.get_visa(visa.id) == visa
