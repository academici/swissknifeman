"""Exercise the registered exports routes over both storage backends."""

from dataclasses import replace
from itertools import count
from uuid import uuid4

from contracts.execution.harness import PEPPER, ExecSide, exec_side
from contracts.execution.seed_helpers import seed_bundle, seed_run
from contracts.knowledge.harness import KnowledgeSide
from integration.artifacts.test_upload_flow import dispatch_new
from security.api.harness import BASE, TestClient
from skm.entrypoints.api.app import create_app
from skm.entrypoints.api.routing import build_route_table
from skm.modules.access.public import (
    CreateToken,
    CreateTokenResult,
    RevokeToken,
    authenticate_token,
)
from skm.modules.workspace.public import BindCheckout, RegisterWorker, RegisterWorkerResult
from support.pg import clean_test_database, pg_session, test_database

from .test_vault_ledger import materialize_archive

__all__ = ["clean_test_database", "exec_side", "pg_session", "test_database"]


def test_http_markdown_pending_and_ack_use_live_authorization(exec_side: ExecSide) -> None:
    side = exec_side
    dispatch_new(
        side.client,
        BindCheckout(
            side.repo_id,
            side.host1,
            "/opt/exports-fixture",
            "/opt/exports-fixture",
            ("example.invalid/skm",),
            None,
            False,
            side.clock.now(),
        ),
    )
    worker = side.client.dispatch(
        RegisterWorker.from_json(
            {
                "workspace_id": str(side.ws),
                "host_id": str(side.host1),
                "display_name": "vault delivery",
                "capabilities": {
                    "platform": {"os": "linux", "arch": "x86_64"},
                    "runtimes": [],
                    "isolation_profiles": ["worktree"],
                    "max_concurrency": 1,
                    "labels": [],
                    "skm_version": "2.0.0",
                },
            }
        )
    )
    assert isinstance(worker, RegisterWorkerResult)
    owner = side.client.dispatch(CreateToken("owner-http"))
    assert isinstance(owner, CreateTokenResult)

    def authenticate(secret: str):
        with side.uow(readonly=True) as uow:
            return authenticate_token(uow, secret, pepper=PEPPER, now=side.clock.now())

    registry = side.app.bus._registry
    api = create_app(
        replace(side.app, authenticator=authenticate),
        route_table=build_route_table(("exports",)),
        registry=registry,
        no_background=True,
    )
    auth = {"Authorization": "Bearer " + worker.token_secret}
    human = {"Authorization": "Bearer " + owner.secret}
    ws, project = side.ws, side.proj
    vault = uuid4()
    with side.uow() as uow:
        run = seed_run(side, uow, plan_id=side.plan2, rev_id=side.rev_p2)
        seed_bundle(side, uow, run.id)
        uow.commit()
    with TestClient(api, base_url=BASE) as http:
        plan_path = f"/api/v1/plans/{side.plan1}/export.md"
        for number, goal in ((1, "Verify Phase-A/B/C"), (2, "Verify Exec Plan 1 v2")):
            markdown = http.get(plan_path, params={"revision_no": number}, headers=auth)
            assert markdown.status_code == 200, markdown.text
            assert markdown.headers["content-type"] == "text/markdown; charset=utf-8"
            assert goal in markdown.text
        report = http.get(f"/api/v1/runs/{run.id}/report.md", params={"variant": "summary"}, headers=auth)
        assert report.status_code == 200, report.text
        assert report.headers["content-type"] == "text/markdown; charset=utf-8"
        assert str(run.id) in report.text
        assert "## Summary" in report.text
        spec = http.get("/api/v1/openapi.json").json()
        for template in ("/plans/{plan_id}/export.md", "/runs/{run_id}/report.md"):
            content = spec["paths"][template]["get"]["responses"]["200"]["content"]
            assert content == {"text/markdown": {"schema": {"type": "string"}}}

        note = materialize_archive(
            KnowledgeSide(side.kind, side.app, side.clock, side.owner, ws, project, count()), side.plan1
        )
        pending = f"/api/v1/workspaces/{ws}/vault-notes/pending"
        params = {"vault_id": str(vault), "host_id": str(side.host1)}
        response = http.get(pending, params=params, headers=auth)
        assert response.status_code == 200, response.text
        (item,) = response.json()["items"]
        assert item["note_id"] == str(note.id)
        assert item["body"] == note.body
        assert (
            http.get(pending, params={**params, "host_id": str(side.host2)}, headers=auth).status_code == 403
        )
        assert (
            http.get(pending, params=params, headers={**auth, "SKM-Host-Id": str(side.host2)}).status_code
            == 403
        )
        assert (
            http.get(pending, params=params, headers={**human, "SKM-Host-Id": str(side.host1)}).status_code
            == 200
        )

        writes = f"/api/v1/projects/{project}/vault-notes/{note.id}/writes"
        payload = {
            "vault_id": str(vault),
            "generation": 1,
            "relative_path": "Plans/note.md",
            "outcome": "created",
            "expected_digest": note.body_digest,
            "observed_digest": note.body_digest,
        }
        ack_headers = {**auth, "Idempotency-Key": "vault-write"}
        assert (
            http.post(
                writes, json=payload, headers={**ack_headers, "SKM-Host-Id": str(side.host2)}
            ).status_code
            == 403
        )
        ack = http.post(writes, json=payload, headers=ack_headers)
        assert ack.status_code == 201, ack.text
        assert ack.json()["recorded"] is True
        assert http.get(pending, params=params, headers=auth).json()["items"] == []
        grant = authenticate(worker.token_secret).grant
        assert grant is not None
        dispatch_new(side.client, RevokeToken(grant.token_id))
        assert http.get(pending, params=params, headers=auth).status_code == 401
        assert http.post(writes, json=payload, headers=ack_headers).status_code == 401
