"""Canonical explain columns, occurrence-based diffs and hidden source suppression."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, cast
from unittest.mock import create_autospec

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.context.application.query_dtos import ContextWireRecord
from skm.modules.context.domain.digests import task_digest
from skm.modules.context.domain.explain import diff_manifests, explain_rows
from skm.modules.context.domain.finalize import finalize
from skm.modules.context.domain.manifest import ContextManifest

from .test_finalize import _EST, _hfacts, _make_draft, _mandatory_six


def manifest():
    mandatory, _ = _mandatory_six()
    return finalize(_make_draft(mandatory), (), _hfacts(), _EST).manifest


def test_explain_columns_and_order_follow_canonical_example():
    value = manifest()
    rows = explain_rows(value)
    assert rows[0]["pos"] == 0
    assert rows[0]["block_type"] == "system_constraints"
    assert rows[0]["trust"] == "system"
    assert rows[0]["reason"] == "mandatory"
    assert len(str(rows[0]["digest"])) == 12
    assert {"pos", "block_type", "source", "tokens", "digest", "trust", "reason"} <= rows[0].keys()
    assert [r["pos"] for r in rows] == list(range(6))
    assert task_digest(value.blocks) == value.task_digest


def test_diff_both_directions_and_duplicate_occurrences():
    value = manifest()
    first = value.blocks[0]
    changed = replace(first, ordinal=7, block_ref="d:7", source_ref="duplicate", content_digest="changed")
    second = replace(first, ordinal=8, block_ref="d:8", source_ref="duplicate", content_digest="same")
    base = replace(value, blocks=(first, replace(changed, content_digest="old"), second))
    target = replace(value, blocks=(changed, second, replace(first, source_ref="added")))
    result = cast("dict[str, Any]", diff_manifests(base, target))
    rows = result["blocks"]
    assert {r["status"] for r in rows} == {"added", "removed", "changed", "same"}
    duplicates = [r for r in rows if r["source"] == "duplicate"]
    assert [r["occurrence"] for r in duplicates] == [0, 1]
    reverse = cast("dict[str, Any]", diff_manifests(target, base))
    assert result["tokens"]["delta"] == -reverse["tokens"]["delta"]
    assert all("base_tokens" in r and "target_tokens" in r for r in rows)
    excluded_in_base = replace(first, ordinal=9, block_ref="x:9", source_ref="budget-skill", included=False)
    included_in_target = replace(first, ordinal=9, block_ref="d:9", source_ref="budget-skill", included=True)
    transition = cast(
        "dict[str, Any]",
        diff_manifests(
            replace(value, blocks=(excluded_in_base,)),
            replace(value, blocks=(included_in_target,)),
        ),
    )
    assert transition["blocks"][0]["status"] == "added"
    assert transition["tokens"]["delta"] == included_in_target.tokens_estimate


def test_hidden_sources_reveal_no_ids_text_counts_or_token_totals():
    base = manifest()
    hidden = replace(
        base.blocks[0],
        ordinal=999,
        block_ref="SECRET-ID",
        source_ref="SECRET-ID",
        tokens_estimate=999999,
        included=False,
        reason="classification_forbidden",
        detail="SECRET-TEXT",
    )
    target = replace(base, blocks=(*base.blocks, hidden), total_tokens_estimate=999999)
    assert explain_rows(base) == explain_rows(target)
    assert diff_manifests(base, base) == diff_manifests(base, target)
    assert "SECRET" not in str(explain_rows(target))


def test_selectors_remain_explicit_in_explain():
    base = manifest()
    selected = replace(base.blocks[0], source_ref="file_version:one#markdown-heading=Security")
    assert explain_rows(replace(base, blocks=(selected,)))[0]["selector"] == "markdown-heading=Security"


def query_uow(
    *manifests: ContextManifest,
    texts: dict[str | None, str] | None = None,
    research: dict[str, JsonObject] | None = None,
) -> tuple[UnitOfWork, list[type]]:
    from types import SimpleNamespace

    from skm.modules.context.ports import ContextRepository, ResearchRepository, TextStore

    values = {str(value.id): value for value in manifests}
    stored_texts = texts or {}
    stored_research = research or {}
    lookups: list[type] = []
    repositories: dict[type, SimpleNamespace] = {
        ContextRepository: SimpleNamespace(get=lambda manifest_id: values[str(manifest_id)]),
        TextStore: SimpleNamespace(
            get_many=lambda digests: {
                digest: stored_texts[digest] for digest in digests if digest in stored_texts
            }
        ),
        ResearchRepository: SimpleNamespace(get=lambda query_id: stored_research[query_id]),
    }

    def repo(port: type) -> SimpleNamespace:
        lookups.append(port)
        return repositories[port]

    uow = create_autospec(UnitOfWork, instance=True)
    uow.repo.side_effect = repo
    return uow, lookups


def run_query[Q: ContextWireRecord, R](spec: QuerySpec[Q, R], payload: JsonObject, uow: UnitOfWork) -> R:
    return spec.handler(spec.dto(payload), create_autospec(QueryContext, instance=True), uow)


def test_queries_register_wire_dtos_views_permission_and_project_scope():
    from skm.kernel.scopes import ScopeKind
    from skm.modules.context.application.query_dtos import (
        ContextDiffResponse,
        ContextExplainResponse,
        ContextTextResponse,
        DiffContextsRequest,
        ExplainContextRequest,
        GetContextTextRequest,
    )
    from skm.modules.context.application.registry import COMMANDS, QUERIES

    value = manifest()
    assert [spec.name for spec in COMMANDS] == [
        "context.assemble_context",
        "context.finalize_manifest",
        "context.record_research_result",
    ]
    assert [spec.name for spec in QUERIES] == [
        "context.explain_context",
        "context.diff_contexts",
        "context.get_context_text",
        "context.check_research_access",
        "context.find_research_cache",
        "context.get_research_query",
        "context.list_external_sources",
    ]
    assert [(spec.name, spec.dto, spec.result) for spec in QUERIES[:3]] == [
        ("context.explain_context", ExplainContextRequest, ContextExplainResponse),
        ("context.diff_contexts", DiffContextsRequest, ContextDiffResponse),
        ("context.get_context_text", GetContextTextRequest, ContextTextResponse),
    ]
    for spec in QUERIES:
        slug = spec.name.split(".")[1].replace("_", "-")
        assert f"urn:skm:context:query:{slug}:v1" == spec.dto.SCHEMA_URN
        expected = "context.research" if spec.name == "context.check_research_access" else "context.read"
        assert spec.permission == expected
        scope = spec.scope_of({"project_id": str(value.project_id)})
        assert scope.kind is ScopeKind.PROJECT
        assert str(scope.id) == str(value.project_id)


def test_query_explain_preserves_exclusions_truncation_and_unknown_evidence():
    from skm.modules.context.application.queries.explain_context import SPEC

    value = manifest()
    statuses = (
        "too_large",
        "no_matching_sections",
        "runtime_self_loaded",
        "host_budget_exceeded",
        "repo_instructions_max_files",
    )
    excluded = tuple(
        replace(
            value.blocks[0],
            ordinal=100 + index,
            block_ref=f"h:{index}",
            position=None,
            source_ref=f"repo:repo/{index}#markdown-heading=Security",
            included=False,
            reason=reason,
            content_digest=None,
            tokens_estimate=None,
            detail="explicit boundary",
        )
        for index, reason in enumerate(statuses)
    )
    value = replace(
        value,
        blocks=(*value.blocks, *excluded),
        host_facts={"work_paths_count": 3, "work_paths_truncated": True},
        route={
            "config_mode": "isolated",
            "self_loads": [{"kind": "repo_instructions", "locator": "AGENTS.md", "active": True}],
        },
    )
    uow, _ = query_uow(value)
    result = run_query(SPEC, {"project_id": str(value.project_id), "manifest_id": str(value.id)}, uow)
    assert {row["reason"] for row in result["excluded"]} == set(statuses)
    assert all(row["detail"] == "explicit boundary" for row in result["excluded"])
    assert result["host_facts"]["work_paths_truncated"] is True
    assert any(d["code"] == "WORK_PATHS_TRUNCATED" for d in result["diagnostics"])
    assert result["route"]["config_mode"] == "isolated"
    assert result["runtime_self_loads"][0]["locator"] == "AGENTS.md"
    assert all(row["backlinks"] == row["dependencies"] == "unknown" for row in result["rows"])


def test_query_explain_and_diff_never_leak_hidden_ids_counts_or_totals():
    from skm.modules.context.application.queries.diff_contexts import SPEC as DIFF
    from skm.modules.context.application.queries.explain_context import SPEC as EXPLAIN

    base = manifest()
    hidden = replace(
        base.blocks[0],
        ordinal=999,
        block_ref="SECRET-ID",
        source_ref="SECRET-ID",
        included=False,
        position=None,
        reason="classification_forbidden",
        tokens_estimate=999999,
        detail="SECRET-TEXT",
    )
    target = replace(base, blocks=(*base.blocks, hidden), total_tokens_estimate=999999)
    query: JsonObject = {"project_id": str(base.project_id), "manifest_id": str(base.id)}
    uow, _ = query_uow(base)
    baseline = run_query(EXPLAIN, query, uow)
    uow, _ = query_uow(target)
    result = run_query(EXPLAIN, query, uow)
    assert result == baseline
    assert "SECRET" not in str(result)
    result = run_query(
        DIFF,
        {
            "project_id": str(base.project_id),
            "base_manifest_id": str(base.id),
            "target_manifest_id": str(target.id),
        },
        uow,
    )
    assert result["tokens"]["delta"] == 0
    assert result["counts"]["same"] == 6


def test_query_diff_has_canonical_counts_digests_and_bidirectional_token_deltas():
    from uuid import UUID

    from skm.modules.context.application.queries.diff_contexts import SPEC

    base = manifest()
    changed = replace(base.blocks[0], content_digest="sha256:changed", tokens_estimate=1)
    target = replace(
        base,
        id=UUID(int=987),
        blocks=(changed, *base.blocks[1:], replace(changed, ordinal=99, source_ref="added")),
    )
    uow, _ = query_uow(base, target)
    query: JsonObject = {
        "project_id": str(base.project_id),
        "base_manifest_id": str(base.id),
        "target_manifest_id": str(target.id),
    }
    result = run_query(SPEC, query, uow)
    assert set(result) == {"blocks", "tokens", "counts"}
    assert result["counts"] == {"added": 1, "removed": 0, "changed": 1, "same": 5}
    row = next(row for row in result["blocks"] if row["change"] == "changed")
    assert row["digest"] == {"from": base.blocks[0].content_digest, "to": "sha256:changed"}
    reverse = run_query(
        SPEC, {**query, "base_manifest_id": str(target.id), "target_manifest_id": str(base.id)}, uow
    )
    assert reverse["tokens"]["delta"] == -result["tokens"]["delta"]


def test_each_query_rejects_manifest_from_another_project_without_reading_text():
    import pytest

    from skm.kernel.errors import NotFound
    from skm.modules.context.application.queries import diff_contexts, explain_context, get_context_text
    from skm.modules.context.ports import TextStore

    base = manifest()
    project = "00000000-0000-0000-0000-000000000999"
    explain: JsonObject = {"project_id": project, "manifest_id": str(base.id)}
    diff: JsonObject = {
        "project_id": project,
        "base_manifest_id": str(base.id),
        "target_manifest_id": str(base.id),
    }
    uow, lookups = query_uow(base)
    with pytest.raises(NotFound):
        run_query(explain_context.SPEC, explain, uow)
    with pytest.raises(NotFound):
        run_query(get_context_text.SPEC, {**explain, "position": 0}, uow)
    with pytest.raises(NotFound):
        run_query(diff_contexts.SPEC, diff, uow)
    assert TextStore not in lookups


def test_diff_rejects_cross_project_target_as_well_as_base():
    from uuid import UUID

    import pytest

    from skm.kernel.errors import NotFound
    from skm.modules.context.application.queries.diff_contexts import SPEC

    base = manifest()
    other = replace(base, id=UUID(int=987), project_id=UUID(int=999))
    uow, _ = query_uow(base, other)
    with pytest.raises(NotFound):
        run_query(
            SPEC,
            {
                "project_id": str(base.project_id),
                "base_manifest_id": str(base.id),
                "target_manifest_id": str(other.id),
            },
            uow,
        )


def test_get_text_returns_prompt_artifact_link_or_digest_checked_captured_block():
    from uuid import UUID

    from skm.modules.context.application.queries.get_context_text import SPEC
    from skm.modules.context.domain.finalize import sha256_text

    value = manifest()
    block = replace(value.blocks[0], content_digest=sha256_text("captured text"), content_stored=True)
    value = replace(value, blocks=(block,), prompt_file_version_id=UUID(int=777))
    uow, _ = query_uow(value, texts={block.content_digest: "captured text"})
    query: JsonObject = {"project_id": str(value.project_id), "manifest_id": str(value.id)}
    assert run_query(SPEC, query, uow) == {
        "text": None,
        "available": True,
        "prompt_file_version_id": str(UUID(int=777)),
    }
    assert run_query(SPEC, {**query, "position": 0}, uow) == {
        "text": "captured text",
        "available": True,
        "prompt_file_version_id": None,
    }
    assert run_query(SPEC, {**query, "position": 99}, uow)["available"] is False
    bad_uow, _ = query_uow(value, texts={block.content_digest: "changed"})
    assert run_query(SPEC, {**query, "position": 0}, bad_uow)["available"] is False


def test_missing_unstored_and_hidden_text_remain_unavailable():
    from skm.modules.context.application.queries.get_context_text import SPEC
    from skm.modules.context.ports import TextStore

    value = manifest()
    query: JsonObject = {"project_id": str(value.project_id), "manifest_id": str(value.id), "position": 0}
    for changes in ({"content_stored": False}, {"reason": "classification_forbidden"}, {}):
        modified = replace(value, blocks=(replace(value.blocks[0], **changes),))
        uow, lookups = query_uow(modified)
        assert run_query(SPEC, query, uow) == {
            "text": None,
            "available": False,
            "prompt_file_version_id": None,
        }
        if changes:
            assert TextStore not in lookups


def test_summary_outline_and_context_map_are_never_full_read_evidence():
    from skm.modules.context.application.queries.explain_context import SPEC
    from skm.modules.context.domain.blocks import BlockType

    value = manifest()
    refs = (
        "file:one#summary",
        "file:one#outline",
        "repo:repo/a#whole",
        "repo:repo/a#markdown-heading=Security",
        "repo:repo/a#markdown-sections=Security",
        "repo:repo/a#line-range=1-3",
    )
    blocks = tuple(
        replace(value.blocks[0], ordinal=index, block_ref=f"d:{index}", position=index, source_ref=ref)
        for index, ref in enumerate(refs)
    )
    blocks += (
        replace(
            blocks[0],
            ordinal=6,
            block_ref="d:6",
            position=6,
            block_type=BlockType.CONTEXT_MAP,
            source_ref="context-map",
        ),
    )
    value = replace(value, blocks=blocks)
    uow, _ = query_uow(value)
    result = run_query(SPEC, {"project_id": str(value.project_id), "manifest_id": str(value.id)}, uow)
    assert [r["selector"] for r in result["rows"]] == [
        "summary",
        "outline",
        "whole",
        "markdown-heading=Security",
        "markdown-sections=Security",
        "line-range=1-3",
        None,
    ]
    assert all(r["backlinks"] == r["dependencies"] == "unknown" for r in result["rows"])
    assert "full_read" not in str(result)


def test_planned_missing_host_input_and_actual_selector_are_visible():
    from skm.modules.context.application.queries.explain_context import SPEC
    from skm.modules.context.domain.host_inputs import HostSelector
    from unit.context.host.test_collect_host_blocks import request

    value = manifest()
    req = request(selector=HostSelector("line_range", line_from=2, line_to=3))
    host = replace(
        value.blocks[0],
        block_ref="h:hi:0",
        source_kind="repository_path",
        source_ref=req.source_ref,
        position=None,
        included=False,
        reason="not_found",
        tokens_estimate=None,
        content_digest=None,
    )
    hidden = replace(host, ordinal=999, block_ref="x:999", source_ref="SECRET-ID")
    value = replace(value, blocks=(host, hidden), host_inputs=(req,))
    uow, _ = query_uow(value)
    result = run_query(SPEC, {"project_id": str(value.project_id), "manifest_id": str(value.id)}, uow)
    assert len(result["excluded"]) == 1
    assert result["excluded"][0]["reason"] == "not_found"
    assert result["rows"][0]["selector"] == "line-range=2-3"
    assert result["rows"][0]["digest"] == ""
    assert result["rows"][0]["backlinks"] == "unknown"
    assert "SECRET" not in str(result)


def test_get_text_rerenders_scoped_stored_research_with_a_matching_digest(monkeypatch):
    from skm.modules.context.application.queries.get_context_text import SPEC
    from skm.modules.context.domain.blocks import BlockType
    from skm.modules.context.domain.finalize import sha256_text

    value = manifest()
    text = "stored research; limitations remain explicit"
    block = replace(
        value.blocks[0],
        block_type=BlockType.RESEARCH,
        content_stored=False,
        research_query_ids=("rq:1",),
        content_digest=sha256_text(text),
    )
    value = replace(value, blocks=(block,))
    result: JsonObject = {
        "query_id": "rq:1",
        "source_id": "docs",
        "kind": "filesystem",
        "tier": "local_docs",
        "retrieved_at": "2026-11-16T00:00:00+00:00",
        "status": "empty",
        "error": None,
        "documents": [],
        "citations": [],
        "claims": [],
        "limitations": ["content_not_retrieved"],
        "usage": None,
        "usage_complete": False,
        "cache_status": "miss",
        "cache_key": "cache",
        "query_digest": "query",
        "source_config_digest": "config",
        "expires_at": None,
    }
    stored: JsonObject = {
        "project_id": str(value.project_id),
        "workspace_id": str(value.workspace_id),
        "query_text": "question",
        "query_digest": "query",
        "result": result,
    }
    batches = []

    def render(batch):
        batches.append(batch)
        return text

    monkeypatch.setattr("skm.modules.context.application.queries.get_context_text.render_research", render)
    query: JsonObject = {"project_id": str(value.project_id), "manifest_id": str(value.id), "position": 0}
    uow, _ = query_uow(value, research={"rq:1": stored})
    assert run_query(SPEC, query, uow)["text"] == text
    assert batches[0].query_text == "question"
    assert batches[0].results[0].limitations == ("content_not_retrieved",)
    uow, _ = query_uow(value, research={"rq:1": {**stored, "project_id": "other"}})
    assert run_query(SPEC, query, uow)["available"] is False
    uow, _ = query_uow(value, research={"rq:1": {**stored, "workspace_id": "other"}})
    assert run_query(SPEC, query, uow)["available"] is False
    assert len(batches) == 1


def test_collect_then_finalize_preserves_selected_host_evidence(tmp_path):
    from skm.modules.context.domain.host_inputs import HostSelector
    from unit.context.host.test_collect_host_blocks import collect, request

    mandatory, _ = _mandatory_six()
    (tmp_path / "guide.md").write_text("# Guide\n## Security\nkeep\n## Other\ndrop\n")
    req = request(selector=HostSelector("markdown_heading", heading="Security"))
    blocks, facts = collect(tmp_path, (req,))
    finalized = finalize(_make_draft(mandatory, host_inputs=(req,)), blocks, facts, _EST)
    host = next(b for b in finalized.manifest.blocks if b.block_ref == "h:hi:0")
    assert host.content_digest == blocks[0].text_digest
    assert host.included is True
    assert "drop" not in finalized.rendered_prompt
