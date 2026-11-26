"""Draft lifecycle, scoped reads and research receipts over the mounted ASGI routes."""

from collections.abc import Iterator
from dataclasses import replace
from typing import Any, cast
from uuid import uuid4

import httpx
import pytest

from contracts.context.harness import MutableBuiltinPacks, core_pack
from contracts.execution.harness import PEPPER, ExecSide
from contracts.execution.harness import exec_side as exec_side
from contracts.extensions.harness import pack_payload
from integration.api.test_adhoc_surfaces import _http as asgi_client
from integration.context.test_research_repository import command, source_setting
from skm.entrypoints.api.app import create_app
from skm.entrypoints.api.routing import build_route_table
from skm.modules.access.public import CreateToken, authenticate_token
from skm.modules.extensions.generated.commands import SyncBuiltinPacks
from skm.modules.extensions.ports import BuiltinPacks
from support.pg import clean_test_database as clean_test_database
from support.pg import pg_session as pg_session
from support.pg import test_database as test_database
from unit.execution.application._support import _shared_side as _shared_side
from unit.execution.application._support import side as side

API = "/api/v1"


@pytest.fixture
def http(exec_side: ExecSide, monkeypatch: pytest.MonkeyPatch) -> Iterator[httpx.Client]:
    with _client(exec_side, monkeypatch) as client:
        yield client


def _client(side: ExecSide, monkeypatch: pytest.MonkeyPatch) -> httpx.Client:
    token = cast("Any", side.client.dispatch(CreateToken(name="surface-test")))

    def authenticate(secret: str):
        with side.uow(readonly=True) as uow:
            return authenticate_token(uow, secret, pepper=PEPPER, now=side.clock.now())

    app = create_app(
        replace(side.app, authenticator=authenticate),
        route_table=build_route_table(("planning", "context", "execution")),
        registry=side.app.bus._registry,
        schema_check=lambda: None,
        no_background=True,
    )
    return asgi_client(app, monkeypatch, headers={"Authorization": f"Bearer {token.secret}"})


def key() -> dict[str, str]:
    return {"Idempotency-Key": str(uuid4())}


def ok(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def problem(response, status, code):
    assert response.status_code == status, response.text
    assert response.json()["code"] == code


def test_publish_replay_nested_identity_and_rebase_conflict(http, exec_side):
    plan = f"{API}/plans/{exec_side.plan1}"
    other = f"{API}/plans/{exec_side.plan2}"
    previous = ok(http.get(plan + "/revisions"))["items"]

    def edit(goal):
        opened = http.post(plan + "/drafts", json={"base": "current"}, headers=key())
        draft = ok(opened, 201)
        path = f"{plan}/drafts/{draft['draft_id']}"
        version = opened.headers["ETag"]
        assert version == f'W/"v{draft["edit_version"]}"'
        media = {"Content-Type": "application/merge-patch+json"}
        problem(http.patch(path, headers=media, json={"goal": goal}), 428, "PRECONDITION_REQUIRED")
        saved = http.patch(path, headers={**media, "If-Match": version}, json={"goal": goal})
        edit = ok(saved)["edit_version"]
        assert saved.headers["ETag"] == f'W/"v{edit}"'
        return path, edit

    first, edit_version = edit("Publish the first edit")
    second, other_version = edit("Keep the concurrent edit")
    draft_path = second.replace(plan, other)
    problem(http.get(draft_path), 404, "NOT_FOUND")
    validated = ok(http.post(first + "/validate", json={"expected_edit_version": edit_version}))
    assert validated["edit_version"] == edit_version
    preview = ok(http.post(first + "/publication-preview", json={"expected_edit_version": edit_version}))
    digest = preview["content_digest"]
    headers = {**key(), "If-Match": f'W/"v{edit_version}"'}
    body = {"expected_content_digest": digest, "reason": "publish from API"}
    published = http.post(first + "/publish", headers=headers, json=body)
    revision = ok(published, 201)
    assert published.headers["ETag"] == f'"{digest}"'
    assert ok(http.post(first + "/publish", headers=headers, json=body), 201) == revision
    revisions = ok(http.get(plan + "/revisions"))["items"]
    assert len(revisions) == 1 + len(previous)
    assert revisions[0]["revision_id"] == revision["revision_id"]
    suffix = "/revisions/" + revision["revision_id"]
    problem(http.get(other + suffix), 404, "NOT_FOUND")
    response = http.get(plan + suffix, params={"include": "tree"})
    assert ok(response)["content_digest"] == digest
    assert response.headers["ETag"] == f'"{digest}"'
    assert http.get(plan + suffix, headers={"If-None-Match": f'"{digest}"'}).status_code == 304
    stale = http.post(second + "/rebase", headers={**key(), "If-Match": f'W/"v{other_version}"'}, json={})
    problem(stale, 409, "REBASE_CONFLICTS")
    assert ok(http.get(second))["edit_version"] == other_version

    restored = http.post(
        plan + "/restore",
        headers=key(),
        json={
            "revision_no": 1,
            "reason": "restore baseline",
            "expected_current_revision_id": revision["revision_id"],
        },
    )
    baseline = ok(restored, 201)
    assert restored.headers["ETag"] == f'"{baseline["content_digest"]}"'
    assert baseline["parent_revision_id"] == revision["revision_id"]


def test_document_routes_and_source_bound_queries(http, exec_side):
    plan = f"{API}/plans/{exec_side.plan1}"
    opened = ok(http.post(plan + "/drafts", json={"base": "current"}, headers=key()), 201)
    path = f"{plan}/drafts/{opened['draft_id']}"
    draft = ok(http.get(path))
    document = {**draft["document"], "goal": "A complete HTTP replacement"}
    saved = ok(http.put(path, headers={"If-Match": f'W/"v{draft["edit_version"]}"'}, json=document))
    version = saved["edit_version"]
    problem(
        http.post(path + "/changes", headers={"If-Match": f'W/"v{version}"'}, json={"document": document}),
        422,
        "SCHEMA_INVALID",
    )
    changed = ok(
        http.post(
            path + "/changes",
            headers={"If-Match": f'W/"v{version}"'},
            json={"changes": [{"op": "patch", "target": "P1.1", "merge_patch": {"title": "HTTP edit"}}]},
        )
    )
    assert changed["edit_version"] == version + 1
    version = changed["edit_version"]
    page = ok(
        http.get(
            plan + "/entities",
            params={
                "draft_id": opened["draft_id"],
                "expected_edit_version": version,
                "kinds": "phase,item",
                "limit": 1,
            },
        )
    )
    assert len(page["items"]) == 1
    assert page["source"]["draft_id"] == opened["draft_id"]
    diff = ok(
        http.get(path + "/diff", params={"expected_edit_version": version, "against": str(exec_side.rev2)})
    )
    assert diff["from_digest"] != diff["to_digest"]
    problem(http.get(path + "/stats", params={"expected_edit_version": version - 1}), 409, "VERSION_CONFLICT")
    assert ok(
        http.get(
            API + "/plans/resolve", params={"ref": str(exec_side.plan1), "project_id": str(exec_side.proj)}
        )
    )["plan_id"] == str(exec_side.plan1)


def test_api_records_host_research_and_reads_cache_without_launching_process(http, exec_side, monkeypatch):
    import subprocess

    def unexpected_process(*args, **kwargs):
        pytest.fail("control-plane research route launched a subprocess")

    source_setting(exec_side)
    payload = command(exec_side)
    research = f"{API}/projects/{exec_side.proj}/research-queries"
    cache = {
        "source_id": "docs",
        "cache_key": payload["results"][0]["cache_key"],
        "max_classification": "restricted",
    }
    monkeypatch.setattr(subprocess, "Popen", unexpected_process)
    assert ok(http.get(research, params=cache))["hit"] is False
    receipt = ok(http.post(research, headers=key(), json=payload), 201)
    query_id = payload["results"][0]["query_id"]
    assert receipt["results"][0]["query_id"] == query_id
    assert ok(http.get(research + "/" + query_id))["result"]["query_id"] == query_id
    assert ok(http.get(research, params=cache))["hit"] is True


def test_simulation_http_pins_its_source_and_preserves_unknowns(http, exec_side) -> None:
    plan = f"{API}/plans/{exec_side.plan1}"
    revision = f"/revisions/{exec_side.rev2}/simulate"
    result = ok(http.get(plan + revision, params={"tokens_per_second": 100}))
    assert result["basis"] == "heuristic"
    assert result["source"]["revision_id"] == str(exec_side.rev2)
    assert result["task_count"] > 0
    assert result["tokens_per_second"] == 100
    assert [result[key] for key in ("tokens", "duration_seconds", "cost_usd_micros")] == [None] * 3
    problem(http.get(plan + revision, params={"tokens_per_second": 0}), 422, "SCHEMA_INVALID")
    problem(http.get(f"{API}/plans/{exec_side.plan2}" + revision), 404, "NOT_FOUND")

    opened = ok(http.post(plan + "/drafts", json={"base": "empty"}, headers=key()), 201)
    path = f"{plan}/drafts/{opened['draft_id']}/simulate"
    problem(http.get(path), 422, "SCHEMA_INVALID")
    problem(
        http.get(path, params={"expected_edit_version": opened["edit_version"] + 1}), 409, "VERSION_CONFLICT"
    )
    simulation = ok(http.get(path, params={"expected_edit_version": opened["edit_version"]}))
    assert simulation["source"]["edit_version"] == opened["edit_version"]
    assert simulation["task_count"] == 0
    assert simulation["cost_usd_micros"] == {"min": 0, "max": 0}
    assert ok(http.get(path.removesuffix("/simulate")))["edit_version"] == opened["edit_version"]


def test_design_intake_http_is_idempotent_and_can_pin_the_draft(http, exec_side) -> None:
    plan = f"{API}/plans/{exec_side.plan1}"
    body = {"goal": "Verify intake", "context_md": "Context", "constraints": ["Keep evidence pinned"]}
    headers = key()
    brief = ok(http.post(plan + "/design-briefs", json=body, headers=headers), 201)
    assert ok(http.post(plan + "/design-briefs", json=body, headers=headers), 201) == brief
    assert brief["plan_id"] == str(exec_side.plan1)

    draft = http.post(plan + "/drafts", json={"base": "current"}, headers=key())
    path = f"{plan}/drafts/{ok(draft, 201)['draft_id']}"
    ok(
        http.patch(
            path,
            json={"design_brief_id": brief["design_brief_id"]},
            headers={"Content-Type": "application/merge-patch+json", "If-Match": draft.headers["ETag"]},
        )
    )
    assert ok(http.get(path))["document"]["design_brief_id"] == brief["design_brief_id"]


def test_visa_status_http_is_revision_scoped_and_updates_after_signing(
    side: ExecSide, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _client(side, monkeypatch) as http:
        plan = f"{API}/plans/{side.plan1}"
        revision = f"{plan}/revisions/{side.rev2}"
        assert ok(http.get(revision + "/visa")) == {"latest_signature": None}
        body = {"mode": "progressive_per_phase", "selection": {"phases": ["P1"]}}
        report = ok(http.post(revision + "/readiness", json=body, headers=key()), 201)
        assert report["status"] in {"ready", "ready_with_advisories"}, report["findings"]
        signature = ok(
            http.post(
                plan + "/revision-visas",
                json={"readiness_report_id": report["report_id"], "reason": "Approve P1"},
                headers=key(),
            ),
            201,
        )
        assert ok(http.get(revision + "/visa")) == {"latest_signature": signature}
        assert ok(http.get(f"{plan}/revisions/{side.rev1}/visa")) == {"latest_signature": None}
        other = revision.replace(str(side.plan1), str(side.plan2))
        problem(http.get(other + "/visa"), 404, "NOT_FOUND")


def test_simulation_uses_catalog_model_metrics_and_tariffs(http, exec_side: ExecSide) -> None:
    catalog = """
schema = "urn:skm:runtimes:model-catalog:v1"
catalog_version = "1.1.0"
[runtimes.codex]
class_selectors = {implementation = ["priced"]}
effort_selectors = {low = "low"}
[[runtimes.codex.models]]
id = "priced"
display_name = "Priced model"
classes = ["implementation"]
context_window_tokens = 32000
max_output_tokens = 4096
status = "confirmed"
verified_at = "2026-01-01"
source = "test catalog"
[runtimes.codex.models.pricing]
input_per_mtok_usd = "1.50"
output_per_mtok_usd = "2.50"
currency = "USD"
verified_at = "2026-01-01"
source = "test catalog"
[[runtimes.codex.models]]
id = "unpriced"
display_name = "Model with unknown tariff"
classes = ["implementation"]
context_window_tokens = 32000
max_output_tokens = 4096
status = "confirmed"
verified_at = "2026-01-01"
source = "test catalog"
"""
    builtin = exec_side.app.gateways.get(BuiltinPacks)
    assert isinstance(builtin, MutableBuiltinPacks)
    files = {file.path: file.content.decode() for file in core_pack("1.1.0").files}
    builtin.current = (pack_payload("core", "1.1.0", files={**files, "runtimes/models.toml": catalog}),)
    exec_side.client.dispatch(SyncBuiltinPacks())

    plan = f"{API}/plans/{exec_side.plan1}"
    draft = http.post(plan + "/drafts", json={"base": "current"}, headers=key())
    path = f"{plan}/drafts/{ok(draft, 201)['draft_id']}"
    snapshot = ok(http.get(path))
    items = snapshot["document"]["items"]
    for model in ("priced", "unpriced"):
        for item in items:
            item["route"] = {"runtime": "codex", "model": model, "class": "implementation", "effort": "low"}
        saved = http.patch(
            path,
            json={"items": items},
            headers={
                "Content-Type": "application/merge-patch+json",
                "If-Match": f'W/"v{snapshot["edit_version"]}"',
            },
        )
        snapshot = ok(saved)
        result = ok(
            http.get(
                path + "/simulate",
                params={
                    "expected_edit_version": snapshot["edit_version"],
                    "tokens_per_second": 100,
                },
            )
        )
        count = result["task_count"]
        assert count > 0
        assert result["tokens"] == {"min": 1280 * count, "max": 5120 * count}
        assert result["duration_seconds"] == {"min": 1280 * count // 100, "max": (5120 * count + 99) // 100}
        assert result["cost_usd_micros"] == (
            {"min": 2176 * count, "max": 8704 * count} if model == "priced" else None
        )
