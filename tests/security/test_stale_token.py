"""Worker result fencing and credential revalidation precede receipt replay (S1/S6/S23/S25)."""

from datetime import timedelta
from pathlib import Path
from typing import Any, cast

import pytest

from contracts.execution.harness import ExecSide
from contracts.execution.harness import exec_side as exec_side
from contracts.execution.test_step_notes import owned_agent
from contracts.execution.test_worker_protocol import worker_claim
from integration.api.test_worker_protocol import bearer, empty_output, worker_api
from integration.api.test_worker_protocol import worker_side as worker_side
from security.api.harness import BASE, TestClient
from security.test_blob_access import denial_checks
from skm.application_bus.ports import IdempotencyStore
from skm.modules.access import public as access
from skm.modules.access.domain.token import TokenId
from skm.modules.access.ports import TokenRepository
from skm.modules.execution.domain.stage_record import StageOutcomeKind
from skm.modules.execution.ports import OutputRepository, StageRepository, StepRepository
from support.pg import clean_test_database as clean_test_database
from support.pg import pg_session as pg_session
from support.pg import test_database as test_database

SCHEMAS = ("access", "execution", "artifacts")


def test_stale_fence_cannot_submit_worker_result(
    worker_side: tuple[ExecSide, dict[str, str], dict[str, str]],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    side, worker, owner = worker_side
    _, _, attempt, claimed, stage, _, _, _, step_secret = owned_agent(side)
    fence = {**worker_claim(side, claimed), "fencing_token": claimed["fencing_token"] + 1}
    private = "private-stale-result-marker-0739"
    body = {
        "claim": fence,
        "outcome_kind": "result_invalid",
        "outcome": {"error_code": "RESULT_INVALID"},
        "diagnostics": [{"code": "RESULT_INVALID", "message": private}],
    }
    path = f"/api/v1/worker/assignments/{claimed['assignment_id']}/stages/{stage.id}/result"
    with side.uow(readonly=True) as uow:
        before = uow.repo(StageRepository).get(stage.id)
    with (
        TestClient(worker_api(side), base_url=BASE) as api,
        denial_checks(
            side.app,
            tmp_path,
            dsn=side.dsn,
            schemas=SCHEMAS,
            capsys=capsys,
            private=(private, step_secret, worker["Authorization"][7:], owner["Authorization"][7:]),
        ) as check,
    ):
        response = api.post(path, json=body, headers={**worker, "Idempotency-Key": "stale-fence"})
        check((response.text, response.headers))
    assert (response.status_code, response.json()["code"]) == (409, "LEASE_LOST")
    assert not {"next", "task_status"} & response.json().keys()
    with side.uow(readonly=True) as uow:
        assert uow.repo(StageRepository).get(stage.id) == before
        assert uow.repo(OutputRepository).latest(attempt.id) is None


@pytest.mark.parametrize("condition", ["revoked-initial", "revoked-replay", "expired-replay"])
def test_inactive_worker_cannot_submit_result_or_replay_receipt(
    worker_side: tuple[ExecSide, dict[str, str], dict[str, str]],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    condition: str,
) -> None:
    side, worker, owner = worker_side
    run, _, attempt, claimed, stage, step, _, _, step_secret = owned_agent(side)
    with side.uow(readonly=True) as uow:
        actor = access.authenticate_token(
            uow,
            worker["Authorization"][7:],
            pepper=side.app.gateways.get(access.TokenPepperSource).pepper(),
            now=side.clock.now(),
        )
    assert actor.grant is not None
    assert actor.grant.kind == "worker"
    token_id = TokenId(actor.grant.token_id)
    claim = worker_claim(side, claimed)
    assignment = f"/api/v1/worker/assignments/{claimed['assignment_id']}"
    path = f"{assignment}/stages/{stage.id}/result"
    key = "worker-result-receipt"
    headers = {**worker, "Idempotency-Key": key}
    private = "private-worker-result-marker-8932"
    body = {
        "claim": claim,
        "outcome_kind": "result_invalid",
        "outcome": {"error_code": "RESULT_INVALID", "detail": private},
    }

    with TestClient(worker_api(side), base_url=BASE) as api:
        sealed = api.post(
            f"{assignment}/outputs",
            json={
                "claim": claim,
                "stage_record_id": str(stage.id),
                "step_id": str(step.id),
                "source": "executor",
                "manifest": empty_output(side),
            },
            headers={**worker, "Idempotency-Key": "seal-before-result"},
        )
        assert sealed.status_code == 201, sealed.text
        output_id = sealed.json()["output_id"]
        replay = condition.endswith("-replay")
        if replay:
            first = api.post(path, json=body, headers=headers)
            assert first.status_code == 200, first.text
            assert {"task_status", "next"} <= first.json().keys()
            assert api.post(path, json=body, headers=headers).json() == first.json()

        with side.uow(readonly=True) as uow:
            before_stage = uow.repo(StageRepository).get(stage.id)
            before_output = uow.repo(OutputRepository).latest(attempt.id)
            receipt = uow.repo(IdempotencyStore).get(
                run.workspace_id, actor.principal_id, "execution.record_stage_result", key
            )
            expiry = uow.repo(TokenRepository).get(token_id).expires_at
        assert (receipt is not None) is replay
        assert before_stage.outcome_kind is (StageOutcomeKind.RESULT_INVALID if replay else None)
        assert before_output is not None
        assert str(before_output.id) == output_id

        if condition == "expired-replay":
            assert expiry is not None
            assert expiry > side.clock.now()
            side.clock.set(expiry)
        else:
            side.client.dispatch(access.RevokeToken(token_id=token_id))
        with denial_checks(
            side.app,
            tmp_path,
            dsn=side.dsn,
            schemas=SCHEMAS,
            capsys=capsys,
            private=(
                private,
                output_id,
                step_secret,
                worker["Authorization"][7:],
                owner["Authorization"][7:],
            ),
        ) as check:
            denied = api.post(path, json=body, headers=headers)
            check((denied.text, denied.headers))
        assert (denied.status_code, denied.json()["code"]) == (401, "UNAUTHENTICATED")
        assert not {"next", "task_status", "receipt", "output_id"} & denied.json().keys()

    with side.uow(readonly=True) as uow:
        assert uow.repo(StageRepository).get(stage.id) == before_stage
        assert uow.repo(OutputRepository).latest(attempt.id) == before_output


@pytest.mark.parametrize("condition", ["revoked", "expired"])
@pytest.mark.parametrize("credential", ["human", "assignment"])
def test_inactive_bearer_cannot_replay_committed_receipt(
    worker_side: tuple[ExecSide, dict[str, str], dict[str, str]],
    tmp_path: Path,
    condition: str,
    credential: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    side, worker, owner = worker_side
    run, _, _, _, _, step, _, assignment_token, assignment_secret = owned_agent(side)
    if credential == "assignment":
        secret, token_id = assignment_secret, assignment_token.token_id

    with TestClient(worker_api(side), base_url=BASE) as api:
        if credential == "assignment":
            path = f"/api/v1/runs/{run.id}/steps/{step.id}/notes"
            body: dict[str, Any] = {"kind": "progress", "text": "committed-note-body-6417"}
        else:
            # The human bearer can read the run, but step notes require an assignment binding.
            token = cast(
                "access.CreateTokenResult",
                side.client.dispatch(
                    access.CreateToken(
                        name="expiring workspace operator",
                        scope_id=side.ws,
                        permissions=("project.create",),
                        expires_at=side.clock.now() + timedelta(seconds=30),
                    )
                ),
            )
            secret, token_id = token.secret, token.token_id
            path = f"/api/v1/workspaces/{side.ws}/projects"
            body = {"slug": "replay-probe", "title": "committed-project-title-6417"}
        headers = {**bearer(secret), "Idempotency-Key": f"replay-{credential}"}
        first = api.post(path, json=body, headers=headers)
        assert first.is_success, first.text
        assert api.post(path, json=body, headers=headers).json() == first.json()
        receipt_id = first.json()["note_id" if credential == "assignment" else "project_id"]
        if condition == "revoked":
            side.client.dispatch(access.RevokeToken(token_id=token_id))
        else:
            side.clock.advance(timedelta(hours=1))

        for key in (headers["Idempotency-Key"], "fresh-after-revocation"):
            with denial_checks(
                side.app,
                tmp_path,
                dsn=side.dsn,
                schemas=(*SCHEMAS, "workspace"),
                capsys=capsys,
                private=(
                    str(receipt_id),
                    str(body.get("text", body.get("title"))),
                    secret,
                    assignment_secret,
                    worker["Authorization"][7:],
                    owner["Authorization"][7:],
                ),
            ) as check:
                result = api.post(path, json=body, headers={**headers, "Idempotency-Key": key})
                check((result.text, result.headers))
            assert (result.status_code, result.json()["code"]) == (401, "UNAUTHENTICATED")
    with side.uow(readonly=True) as uow:
        assert len(uow.repo(StepRepository).notes_for_step(step.id)) == (credential == "assignment")
