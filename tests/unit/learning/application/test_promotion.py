"""Application guards for authenticated learning decisions."""

from dataclasses import replace
from unittest.mock import Mock

import pytest

from skm.application_bus.context import CommandContext
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.learning.application.commands import promote_candidate, review_candidate
from skm.modules.learning.ports import CandidateRepository
from unit.learning.domain.test_consolidation import HUMAN, candidate


@pytest.mark.parametrize("kind", [PrincipalKind.SERVICE, PrincipalKind.WORKER])
def test_promotion_rejects_non_human_before_reading_candidate(kind: PrincipalKind) -> None:
    ctx = Mock(spec=CommandContext, actor=replace(HUMAN, kind=kind))
    uow = Mock(spec=UnitOfWork)

    with pytest.raises(Forbidden) as error:
        promote_candidate.handle({}, ctx, uow)

    assert error.value.code is ErrorCode.FORBIDDEN
    assert error.value.details == {"reason": "human_gate"}
    uow.repo.assert_not_called()


@pytest.mark.parametrize("kind", [PrincipalKind.SERVICE, PrincipalKind.WORKER])
@pytest.mark.parametrize("verdict", ["edit", "reject"])
def test_non_human_cannot_edit_or_reject(kind: PrincipalKind, verdict: str) -> None:
    row = candidate("After changes", "Run checks")
    ctx = Mock(spec=CommandContext, actor=replace(HUMAN, kind=kind))
    repo = Mock(spec=CandidateRepository)
    repo.get.return_value = row
    uow = Mock(spec=UnitOfWork)
    uow.repo.return_value = repo

    with pytest.raises(Forbidden) as error:
        review_candidate.handle(
            {
                "workspace_id": str(row.workspace_id),
                "candidate_id": str(row.id),
                "expected_row_version": row.row_version,
                "verdict": verdict,
            },
            ctx,
            uow,
        )

    assert error.value.code is ErrorCode.FORBIDDEN
    assert error.value.details == {"reason": "human_gate"}
    repo.save.assert_not_called()
    uow.record.assert_not_called()
