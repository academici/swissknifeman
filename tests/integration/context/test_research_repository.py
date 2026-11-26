"""Research ledger and real-bus contracts on memory and PostgreSQL (P09.09.a)."""

from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from typing import Literal, cast, overload
from uuid import UUID

import psycopg
import pytest

from contracts.context.harness import ContextSide
from contracts.execution.harness import ExecSide
from integration.artifacts.test_upload_flow import dispatch_new
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, Forbidden, NotFound, SkmError, ValidationFailed
from skm.kernel.ids import PrincipalId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.ports_uow import Surface
from skm.modules.access.domain.membership import Membership
from skm.modules.access.domain.principal import new_principal
from skm.modules.access.ports import MembershipRepository, PrincipalRepository
from skm.modules.access.public import Role
from skm.modules.context import public as context
from skm.modules.context.application.registry import COMMANDS, QUERIES
from skm.modules.context.domain.research import result_to_json
from skm.modules.context.domain.research_rules import query_digest
from skm.modules.context.generated.commands import (
    RecordResearchResult,
    record_research_result_defs_staged_blob_ref_from_json,
    record_research_result_research_result_dto_from_json,
)
from skm.modules.context.generated.results import RecordResearchResultResult
from skm.modules.context.generated.views import ExternalSourcesView, ResearchCacheView, ResearchResultView
from skm.modules.context.ports import ResearchRepository
from skm.modules.settings.generated.commands import SetValue, SetValueDefsScopeRef
from skm.modules.workspace.public import CreateProject
from unit.context.research_support import normalized

SPECS = {s.name: s for s in (*COMMANDS, *QUERIES)}

type ResearchSide = ContextSide | ExecSide


def seed_actor(side, principal_id, kind, role):
    with side.uow() as uow:
        uow.repo(PrincipalRepository).add(
            new_principal(
                principal_id=principal_id,
                kind=kind,
                display_name=kind.value,
                created_by=side.owner.principal_id,
                now=side.clock.now(),
            )
        )
        uow.repo(MembershipRepository).upsert(
            Membership(side.ws, principal_id, role, side.owner.principal_id, side.clock.now())
        )
        uow.commit()
    return Actor(principal_id, kind, kind.value)


def _json_object(value: JsonValue) -> JsonObject:
    assert isinstance(value, dict)
    return value


def _first_document(result: JsonObject) -> JsonObject:
    documents = result["documents"]
    assert isinstance(documents, list)
    return _json_object(documents[0])


def command(side: ResearchSide, *, index: int = 0, documents: int = 1) -> RecordResearchResult:
    raw = record_research_result_research_result_dto_from_json(result_to_json(normalized()))
    raw["query_id"] = str(UUID(int=UUID(raw["query_id"]).int + index * 100))
    raw["retrieved_at"] = side.clock.now().isoformat()
    raw["expires_at"] = (side.clock.now() + timedelta(hours=1)).isoformat()
    doc = deepcopy(raw["documents"][0])
    doc["retrieved_at"] = raw["retrieved_at"]
    raw["documents"] = []
    for i in range(documents):
        current = deepcopy(doc)
        current["document_id"] = str(UUID(int=UUID(doc["document_id"]).int + index * 100 + i))
        current["origin"] = "repo:repo/guide" + str(i)
        raw["documents"].append(current)
    return {
        "workspace_id": str(side.ws),
        "project_id": str(side.proj),
        "query_text": "Café research",
        "query_digest": query_digest("Café research"),
        "depth": "standard",
        "max_documents": 10,
        "results": [raw],
    }


def record(
    side: ResearchSide, payload: RecordResearchResult, *, key: str | None = None
) -> RecordResearchResultResult:
    result = side.client.dispatch(
        SPECS["context.record_research_result"].dto.from_json(payload),
        idempotency_key=key or "research:step:test-research:" + payload["query_digest"],
    )
    return cast("RecordResearchResultResult", result)


@overload
def ask(
    side: ResearchSide, name: Literal["find_research_cache"], **values: JsonValue
) -> ResearchCacheView: ...


@overload
def ask(
    side: ResearchSide, name: Literal["get_research_query"], **values: JsonValue
) -> ResearchResultView: ...


@overload
def ask(
    side: ResearchSide, name: Literal["list_external_sources"], **values: JsonValue
) -> ExternalSourcesView: ...


def ask(
    side: ResearchSide,
    name: str,
    **values: JsonValue,
) -> ResearchCacheView | ResearchResultView | ExternalSourcesView:
    result = side.client.ask(SPECS["context." + name].dto.from_json({"project_id": str(side.proj), **values}))
    return cast("ResearchCacheView | ResearchResultView | ExternalSourcesView", result)


def cache(side: ResearchSide, payload: RecordResearchResult, **changes: JsonValue) -> ResearchCacheView:
    return ask(
        side,
        "find_research_cache",
        source_id="docs",
        cache_key=payload["results"][0]["cache_key"],
        max_classification=changes.pop("max_classification", "restricted"),
        **changes,
    )


def setting(side, key, value):
    return dispatch_new(
        side.client,
        SetValue(scope=SetValueDefsScopeRef(level="project", scope_id=side.proj), key=key, value=value),
    )


def source_setting(side, *, host_id=None, **overrides):
    return dispatch_new(
        side.client,
        SetValue(
            scope=SetValueDefsScopeRef(level="host", scope_id=host_id)
            if host_id is not None
            else SetValueDefsScopeRef(level="instance"),
            key="context.research.sources",
            confirmed=True,
            value={
                "docs": {
                    "kind": "command",
                    "tier": "local_docs",
                    "capabilities": ["search", "citations"],
                    "trust_cap": "repository",
                    "classification": "internal",
                    **overrides,
                }
            },
        ),
    )


def test_real_bus_record_fetch_cache_idempotency_and_immutable_ledger(ctx_side: ContextSide):
    payload = command(ctx_side)
    saved = record(ctx_side, payload)
    assert record(ctx_side, payload) == saved
    doc_id = payload["results"][0]["documents"][0]["document_id"]
    qid = payload["results"][0]["query_id"]
    assert saved["results"][0]["documents"] == [{"document_id": doc_id}]
    cached = cache(ctx_side, payload)
    assert cached["hit"]
    assert "result" in cached
    assert cached["result"]["cache_status"] == "hit"
    view = ask(ctx_side, "get_research_query", query_id=qid)["result"]
    assert _first_document(view)["document_id"] == doc_id
    assert view["usage"] is None
    assert not view["usage_complete"]
    with ctx_side.uow(readonly=True) as uow:
        repo = uow.repo(ResearchRepository)
        stored = repo.get(qid)
        assert stored["workspace_id"] == str(ctx_side.ws)
        assert stored["project_id"] == str(ctx_side.proj)
        assert _json_object(_first_document(stored)["provenance"])["source_id"] == "docs"
        assert context.research_documents(uow, (doc_id,))[0].document_id == doc_id
        assert stored["step_ref"] is None
        stored["query_text"] = "tampered"
        assert repo.get(qid)["query_text"] == payload["query_text"]
        uow.rollback()
    if ctx_side.dsn:
        with psycopg.connect(ctx_side.dsn) as conn:
            for statement in (
                "UPDATE skm_context.research_queries SET query_text=query_text",
                "UPDATE skm_context.external_sources SET title=title",
                "DELETE FROM skm_context.research_queries",
                "DELETE FROM skm_context.external_sources",
            ):
                with pytest.raises(psycopg.Error), conn.transaction():
                    conn.execute(statement)
    changed = deepcopy(payload)
    changed["query_text"] = "different"
    changed["query_digest"] = query_digest("different")
    with pytest.raises(Conflict) as err:
        record(ctx_side, changed, key="research:step:test-research:" + payload["query_digest"])
    assert err.value.code is ErrorCode.IDEMPOTENCY_KEY_REUSED


def test_repository_atomic_insert_batch_duplicate_ids_and_exact_replay(ctx_side: ContextSide):
    payload = command(ctx_side)
    record(ctx_side, payload)
    qid = payload["results"][0]["query_id"]
    with ctx_side.uow() as uow:
        repo = uow.repo(ResearchRepository)
        stored = repo.get(qid)
        repo.add_results((stored,))
        other = deepcopy(stored)
        other_id = str(UUID(int=UUID(qid).int + 1000))
        other["query_id"] = other_id
        _first_document(other)["query_id"] = other_id
        with pytest.raises(Conflict):
            repo.add_results((other,))
        with pytest.raises(NotFound):
            repo.get(other_id)
        uow.rollback()


def test_cache_exact_project_scope_source_and_ttl(ctx_side: ContextSide):
    payload = command(ctx_side)
    record(ctx_side, payload)
    assert cache(ctx_side, payload)["hit"]
    assert not ask(
        ctx_side,
        "find_research_cache",
        source_id="docs",
        cache_key=query_digest("changed checkout head or dirty state"),
        max_classification="restricted",
    )["hit"]
    assert not ask(
        ctx_side,
        "find_research_cache",
        source_id="foreign",
        cache_key=payload["results"][0]["cache_key"],
        max_classification="restricted",
    )["hit"]
    other = dispatch_new(
        ctx_side.client, CreateProject(workspace_id=ctx_side.ws, slug="other", title="Other")
    ).project_id
    query = SPECS["context.find_research_cache"].dto.from_json(
        {
            "project_id": str(other),
            "source_id": "docs",
            "cache_key": payload["results"][0]["cache_key"],
            "max_classification": "restricted",
        }
    )
    assert not cast("ResearchCacheView", ctx_side.client.ask(query))["hit"]
    with pytest.raises(NotFound):
        ctx_side.client.ask(
            SPECS["context.get_research_query"].dto.from_json(
                {"project_id": str(other), "query_id": payload["results"][0]["query_id"]}
            )
        )
    with ctx_side.uow(readonly=True) as uow:
        assert (
            uow.repo(ResearchRepository).find_cached(
                workspace_id=ctx_side.ws,
                project_id=other,
                cache_key=payload["results"][0]["cache_key"],
                now=ctx_side.clock.now(),
            )
            is None
        )
        uow.rollback()
    ctx_side.clock.advance(timedelta(hours=1))
    assert not cache(ctx_side, payload)["hit"]


def test_identical_queries_in_projects_have_separate_ledger_entries(ctx_side: ContextSide):
    first = command(ctx_side)
    record(ctx_side, first)
    other = dispatch_new(
        ctx_side.client, CreateProject(workspace_id=ctx_side.ws, slug="other", title="Other")
    ).project_id
    second = command(ctx_side, index=1)
    second["project_id"] = str(other)
    record(ctx_side, second, key="research:other:" + second["query_digest"])
    for pid, payload in ((ctx_side.proj, first), (other, second)):
        response = ask(
            ctx_side,
            "find_research_cache",
            project_id=str(pid),
            source_id="docs",
            cache_key=first["results"][0]["cache_key"],
            max_classification="restricted",
        )
        assert response["hit"]
        assert "result" in response
        assert response["result"]["query_id"] == payload["results"][0]["query_id"]


@pytest.mark.parametrize("status", ["empty", "error"])
def test_empty_results_can_cache_but_errors_are_audit_only(ctx_side: ContextSide, status):
    payload = command(ctx_side, documents=0)
    raw = payload["results"][0]
    raw["status"] = status
    if status == "error":
        raw["error"] = {"code": "RESEARCH_SOURCE_UNAVAILABLE", "message": "source missing"}
        raw["expires_at"] = None
    record(ctx_side, payload)
    assert cache(ctx_side, payload)["hit"] is (status == "empty")
    stored = ask(ctx_side, "get_research_query", query_id=raw["query_id"])["result"]
    assert stored["status"] == status
    assert stored["usage"] is None
    if status == "error":
        assert stored["expires_at"] is None


def test_unknown_checkout_is_audited_without_cache_expiry(ctx_side: ContextSide):
    source_setting(ctx_side, kind="filesystem")
    payload = command(ctx_side)
    raw = payload["results"][0]
    raw["kind"] = "filesystem"
    raw["expires_at"] = None
    raw["cache_status"] = "bypass"
    record(ctx_side, payload)
    assert not cache(ctx_side, payload)["hit"]
    assert ask(ctx_side, "get_research_query", query_id=raw["query_id"])["result"]["expires_at"] is None


def test_server_caps_exaggerated_classification_and_live_policy_tightening(ctx_side: ContextSide):
    payload = command(ctx_side)
    raw = payload["results"][0]
    raw["documents"][0]["classification"] = "confidential"
    record(ctx_side, payload)
    from dataclasses import replace

    viewer_id = PrincipalId(UUID("01900000-0000-7000-8000-000000008894"))
    viewer = seed_actor(ctx_side, viewer_id, PrincipalKind.HUMAN, Role.VIEWER)
    ctx_side = replace(ctx_side, client=ctx_side.app.client(actor=viewer, surface=Surface.CLI))
    assert not cache(ctx_side, payload, max_classification="restricted")["hit"]
    assert not cache(ctx_side, payload, max_classification="public")["hit"]
    with pytest.raises(NotFound):
        ask(ctx_side, "get_research_query", query_id=raw["query_id"])
    assert ask(ctx_side, "list_external_sources")["items"] == []


@pytest.mark.parametrize("url", [None, "https://example.com/a"])
def test_disabled_source_and_live_url_policy_block_active_cache(ctx_side: ContextSide, url):
    payload = command(ctx_side)
    doc = payload["results"][0]["documents"][0]
    doc.update(origin="https://example.com/a", url=url, trust_class="external")
    record(ctx_side, payload)
    assert cache(ctx_side, payload)["hit"]
    setting(ctx_side, "context.research.url_deny", ["example.com"])
    assert not cache(ctx_side, payload)["hit"]
    with pytest.raises(NotFound):
        ask(ctx_side, "get_research_query", query_id=payload["results"][0]["query_id"])
    assert ask(ctx_side, "list_external_sources")["items"] == []


def test_source_permissions_are_rechecked_even_before_ttl_expires(ctx_side: ContextSide):
    payload = command(ctx_side)
    record(ctx_side, payload)
    assert cache(ctx_side, payload)["hit"]
    setting(ctx_side, "context.research.disabled_sources", ["docs"])
    assert not cache(ctx_side, payload)["hit"]
    with pytest.raises(NotFound):
        ask(ctx_side, "get_research_query", query_id=payload["results"][0]["query_id"])
    assert ask(ctx_side, "list_external_sources")["items"] == []


def test_server_limits_ttl_and_cache_enabled_policy(ctx_side: ContextSide):
    payload = command(ctx_side)
    raw = payload["results"][0]
    raw["expires_at"] = (ctx_side.clock.now() + timedelta(days=365)).isoformat()
    record(ctx_side, payload)
    stored = ask(ctx_side, "get_research_query", query_id=raw["query_id"])["result"]
    assert stored["expires_at"] == (ctx_side.clock.now() + timedelta(days=7)).isoformat()
    setting(ctx_side, "context.research.cache.enabled", False)
    assert not cache(ctx_side, payload)["hit"]


def test_cursor_pages_query_and_literal_origin_prefix(ctx_side: ContextSide):
    payload = command(ctx_side, documents=3)
    record(ctx_side, payload)
    qid = payload["results"][0]["query_id"]
    first = ask(ctx_side, "list_external_sources", query_id=qid, limit=2)
    second = ask(ctx_side, "list_external_sources", query_id=qid, limit=2, after=first["next_after"])
    assert len(first["items"]) == 2
    assert len(second["items"]) == 1
    assert second["next_after"] is None
    assert {d["document_id"] for d in first["items"] + second["items"]} == {
        d["document_id"] for d in payload["results"][0]["documents"]
    }
    assert (
        ask(ctx_side, "list_external_sources", origin_prefix="repo:repo/guide0")["items"]
        == first["items"][:1]
    )
    assert ask(ctx_side, "list_external_sources", origin_prefix="repo:%")["items"] == []


@pytest.mark.parametrize("invalid_case", ["claim", "citation", "trust", "excerpt", "query", "workspace"])
def test_server_rejects_invalid_provenance_before_writing(ctx_side: ContextSide, invalid_case):
    payload = command(ctx_side)
    raw = payload["results"][0]
    if invalid_case == "claim":
        raw["claims"] = [{"text": "foreign", "document_ids": ["01900000-0000-7000-8000-00000000ffff"]}]
    elif invalid_case == "citation":
        raw["citations"] = [
            {"claim_index": 0, "document_id": "01900000-0000-7000-8000-00000000ffff", "quote": None}
        ]
    elif invalid_case == "trust":
        raw["documents"][0].update(origin="https://example.com", url="https://example.com")
    elif invalid_case == "excerpt":
        raw["documents"][0]["excerpt"] = "x" * 2001
    elif invalid_case == "query":
        payload["query_digest"] = query_digest("foreign")
    else:
        payload["workspace_id"] = "01900000-0000-7000-8000-00000000ffff"
    with pytest.raises((ValidationFailed, NotFound)):
        record(ctx_side, payload)
    with ctx_side.uow(readonly=True) as uow:
        with pytest.raises(NotFound):
            uow.repo(ResearchRepository).get(raw["query_id"])
        uow.rollback()


def test_safe_staged_material_is_captured_and_linked(ctx_side: ContextSide):
    payload = command(ctx_side)
    doc = payload["results"][0]["documents"][0]
    staged = ctx_side.client.upload_blob(ctx_side.ws, [b"body"], size=4, media_type="text/markdown")
    doc["staged_blob"] = record_research_result_defs_staged_blob_ref_from_json(staged.to_json())
    saved = record(ctx_side, payload)
    vid = saved["results"][0]["documents"][0]["captured_file_version_id"]
    assert vid is not None
    assert record(ctx_side, payload) == saved
    from skm.kernel.ids import FileVersionId
    from skm.modules.artifacts import public as artifacts
    from skm.modules.artifacts.ports import FileRepository, FileVersionRepository

    with ctx_side.uow(readonly=True) as uow:
        version = artifacts.get_file_version(uow, FileVersionId(UUID(vid)))
        persisted = uow.repo(FileVersionRepository).get(FileVersionId(UUID(vid)))
        file = uow.repo(FileRepository).get(persisted.file_id)
        assert persisted.source.kind == "capture"
        assert file.origin.value == "capture"
        assert file.classification.value == doc["classification"]
        assert version.digest == doc["content_digest"]
        persisted_result = uow.repo(ResearchRepository).get(payload["results"][0]["query_id"])
        assert _first_document(persisted_result)["captured_file_version_id"] == vid
        uow.rollback()


def test_unsafe_staged_material_blocks_and_rolls_back_entire_ledger(ctx_side: ContextSide):
    payload = command(ctx_side)
    data = b"password=very-secret-value"
    staged = ctx_side.client.upload_blob(ctx_side.ws, [data], size=len(data), media_type="text/markdown")
    doc = payload["results"][0]["documents"][0]
    doc["staged_blob"] = record_research_result_defs_staged_blob_ref_from_json(staged.to_json())
    doc["content_digest"] = staged.digest
    with pytest.raises(SkmError) as err:
        record(ctx_side, payload)
    assert err.value.code is ErrorCode.CONTENT_UNSAFE
    with ctx_side.uow(readonly=True) as uow:
        with pytest.raises(NotFound):
            uow.repo(ResearchRepository).get(payload["results"][0]["query_id"])
        uow.rollback()
    from skm.modules.artifacts import public as artifacts

    with ctx_side.uow() as uow:
        reusable = artifacts.consume_staged_blob(
            uow,
            ref=staged.to_json(),
            workspace_id=ctx_side.ws,
            request_id="req_" + "R" * 26,
            now=ctx_side.clock.now(),
        )
        assert reusable.digest.value == staged.digest
        uow.rollback()


def test_record_requires_current_research_permission(ctx_side: ContextSide):
    viewer_id = PrincipalId(UUID("01900000-0000-7000-8000-000000008888"))
    viewer = seed_actor(ctx_side, viewer_id, PrincipalKind.HUMAN, Role.VIEWER)
    client = ctx_side.app.client(actor=viewer, surface=Surface.CLI)
    with pytest.raises(Forbidden):
        client.dispatch(
            SPECS["context.record_research_result"].dto.from_json(command(ctx_side)),
            idempotency_key="research:forbidden",
        )


def test_worker_without_assignment_cannot_read_or_record(ctx_side: ContextSide):
    payload = command(ctx_side)
    record(ctx_side, payload)
    worker_id = PrincipalId(UUID("01900000-0000-7000-8000-000000008889"))
    worker = seed_actor(ctx_side, worker_id, PrincipalKind.WORKER, Role.WORKER)
    client = ctx_side.app.client(actor=worker, surface=Surface.CLI)
    with pytest.raises(Forbidden):
        client.ask(
            SPECS["context.find_research_cache"].dto.from_json(
                {
                    "project_id": str(ctx_side.proj),
                    "source_id": "docs",
                    "cache_key": payload["results"][0]["cache_key"],
                    "max_classification": "restricted",
                }
            )
        )
    with pytest.raises(Forbidden):
        client.dispatch(
            SPECS["context.record_research_result"].dto.from_json(command(ctx_side, index=2)),
            idempotency_key="research:worker-without-assignment",
        )


def test_cache_rechecks_revoked_workspace_membership(ctx_side: ContextSide):
    from skm.modules.access.public import RevokeMembership

    payload = command(ctx_side)
    record(ctx_side, payload)
    reader_id = PrincipalId(UUID("01900000-0000-7000-8000-000000008890"))
    reader = seed_actor(ctx_side, reader_id, PrincipalKind.HUMAN, Role.VIEWER)
    client = ctx_side.app.client(actor=reader, surface=Surface.CLI)
    query = SPECS["context.find_research_cache"].dto.from_json(
        {
            "project_id": str(ctx_side.proj),
            "source_id": "docs",
            "cache_key": payload["results"][0]["cache_key"],
            "max_classification": "restricted",
        }
    )
    assert cast("ResearchCacheView", client.ask(query))["hit"]
    dispatch_new(ctx_side.client, RevokeMembership(scope_id=ctx_side.ws, principal_id=reader_id))
    with pytest.raises(Forbidden):
        client.ask(query)


@pytest.mark.parametrize(
    ("constraints", "reason"),
    [
        ({"trust_cap": "third_party"}, "trust_raised"),
        ({"classification": "confidential"}, "classification_lowered"),
        ({"capabilities": ["search"]}, "answer_without_citations"),
    ],
)
def test_record_validates_trusted_source_constraints(ctx_side, constraints, reason):
    payload = command(ctx_side)
    raw = payload["results"][0]
    did = raw["documents"][0]["document_id"]
    raw["claims"] = [{"text": "supported", "document_ids": [did]}]
    raw["citations"] = [{"claim_index": 0, "document_id": did, "quote": None}]
    source_setting(ctx_side, **constraints)
    with pytest.raises(ValidationFailed) as err:
        record(ctx_side, payload)
    assert err.value.details["reason"] == reason
    with ctx_side.uow(readonly=True) as uow, pytest.raises(NotFound):
        uow.repo(ResearchRepository).get(raw["query_id"])
    source_setting(ctx_side)
    assert record(ctx_side, payload)["results"][0]["query_id"] == raw["query_id"]
    source_setting(ctx_side, **constraints)
    assert not cache(ctx_side, payload)["hit"]
    with pytest.raises(ValidationFailed) as err:
        record(ctx_side, payload)
    assert err.value.details["reason"] == reason


@pytest.mark.parametrize("origin", ["http://localhost/secret", "https://example.com/secret"])
@pytest.mark.parametrize("url", [None, "https://allowed.example/a"])
def test_record_checks_network_origin_even_without_or_with_different_url(ctx_side, origin, url):
    payload = command(ctx_side)
    payload["results"][0]["documents"][0].update(origin=origin, url=url, trust_class="external")
    setting(ctx_side, "context.research.url_deny", ["example.com"])
    with pytest.raises(ValidationFailed) as err:
        record(ctx_side, payload)
    assert err.value.details["reason"] == "url_denied"
    assert not cache(ctx_side, payload)["hit"]


def test_source_url_allow_applies_to_origin_without_url(ctx_side):
    payload = command(ctx_side)
    payload["results"][0]["documents"][0].update(
        origin="https://example.com/a", url=None, trust_class="external"
    )
    record(ctx_side, payload)
    assert cache(ctx_side, payload)["hit"]
    source_setting(ctx_side, url_allow=["other.example"])
    assert not cache(ctx_side, payload)["hit"]
    with pytest.raises(ValidationFailed):
        record(ctx_side, payload)
    with pytest.raises(NotFound):
        ask(ctx_side, "get_research_query", query_id=payload["results"][0]["query_id"])
    other = command(ctx_side, index=1)
    other["results"][0]["documents"] = deepcopy(payload["results"][0]["documents"])
    with pytest.raises(ValidationFailed) as err:
        record(ctx_side, other, key="research:disallowed-origin")
    assert err.value.details["reason"] == "url_denied"
