"""Durable replay and worker cache binding against both real persistence backends."""

from dataclasses import replace
from typing import Any, cast

import pytest

from contracts.context.test_owner_guard import owned_draft
from integration.context.test_research_repository import source_setting
from skm.modules.context.domain.research import result_from_json
from skm.modules.context.domain.research_render import render_research
from skm.modules.context.host.research_query import research_query
from skm.modules.context.ports import ResearchRepository

from ._support import host, spec


class CountingClient:
    def __init__(self, client):
        self.client, self.uploads, self.dispatches = client, 0, 0

    def ask(self, request):
        return self.client.ask(request)

    def dispatch(self, request, **kwargs):
        self.dispatches += 1
        return self.client.dispatch(request, **kwargs)

    def upload_blob(self, *args, **kwargs):
        self.uploads += 1
        return self.client.upload_blob(*args, **kwargs)


def test_real_ledger_replays_after_recreation_and_distinguishes_exact_text(exec_side):
    side = exec_side
    case = owned_draft(side)
    counted = CountingClient(side.client)
    ctx = host(client=counted, clock=side.clock)
    sources = ctx.config["context.research.sources"]
    source_setting(side, **sources["docs"])
    options = {
        "workspace_id": side.ws,
        "project_id": side.proj,
        "step_ref": f"step:{case.step.id}",
        "mounts": {},
    }
    first = research_query(ctx, spec("research evidence", use_cache=False, save_as_material=True), **options)
    fresh = host(client=counted, sources=sources, clock=side.clock)
    replay = research_query(
        fresh, spec("research evidence", use_cache=False, save_as_material=True), **options
    )
    assert first.results[0].query_id == replay.results[0].query_id
    assert counted.uploads == counted.dispatches == 1
    changed = research_query(
        fresh, spec("research  evidence", use_cache=False, save_as_material=True), **options
    )
    assert changed.query_digest == first.query_digest
    assert changed.results[0].query_id != first.results[0].query_id
    assert counted.uploads == counted.dispatches == 2


@pytest.mark.parametrize("empty", [False, True])
def test_worker_cache_hit_is_bound_to_current_step_without_new_capture(owned_research, empty):
    from skm.modules.context.domain.research import ResearchBatch

    case = owned_research
    side = case.side
    counted = CountingClient(side.client)
    ctx = host(client=counted, clock=side.clock)
    sources = ctx.config["context.research.sources"]
    if empty:
        import sys

        from ._support import json_script

        sources["docs"]["argv"] = [sys.executable, "-c", json_script({"documents": []})]
    source_setting(side, **sources["docs"])
    options = {"workspace_id": side.ws, "project_id": side.proj, "mounts": {}}
    original = research_query(ctx, spec(save_as_material=True), step_ref=None, **options)
    worker_counted = CountingClient(case.client)
    worker = host(client=worker_counted, sources=sources, clock=side.clock)
    batch = research_query(worker, spec(save_as_material=True), step_ref=f"step:{case.step.id}", **options)
    result = batch.results[0]
    assert result.cache_status == "hit"
    assert result.query_id != original.results[0].query_id
    assert worker_counted.uploads == 0
    assert worker_counted.dispatches == 1
    with side.uow(readonly=True) as uow:
        repo = uow.repo(ResearchRepository)
        row = repo.get(result.query_id)
        previous = repo.get(original.results[0].query_id)
        assert row["step_ref"] == f"step:{case.step.id}"
        assert row["usage"] is None
        if empty:
            assert row["documents"] == []
        else:
            assert (
                row["documents"][0]["captured_file_version_id"]
                == previous["documents"][0]["captured_file_version_id"]
            )
        assert render_research(batch) == render_research(
            ResearchBatch(batch.query_text, batch.query_digest, (result_from_json(row),))
        )


def test_real_begin_stage_shape_supplies_research_project_without_invented_step_fields(
    exec_side, tmp_path, monkeypatch
):
    from contracts.execution._worker_protocol_support import worker_claim
    from integration.worker.test_context_publication import setup_prompt
    from skm.bootstrap.host_services import decode_context_draft
    from skm.modules.access.public import generate_secret
    from skm.modules.context.domain.draft import make_research_request
    from skm.modules.context.domain.research_rules import query_digest
    from skm.modules.execution import public as execution
    from skm.modules.execution.application._worker_dtos import document
    from skm.modules.execution.host.context_inputs import finalize_stage_context

    side = exec_side
    case, stage, step, draft, ctx, env, claim, _, inputs = setup_prompt(side, tmp_path, monkeypatch)
    begin = side.worker1_client.dispatch(
        execution.BeginStage(
            claim=worker_claim(side, case.claimed),
            stage_id=stage.stage_id,
            round_no=stage.round_no,
            input_digest=stage.input_digest,
            runtime_token_secret=str(generate_secret(lambda n: b"r" * n)),
        ),
        idempotency_key=f"begin:{side.new_id()}",
    )
    assert "project_id" not in begin["step"]
    assert "round_no" not in begin["step"]
    # Seeded admission uses the actual server-assembled Phase-A draft, as the worker fixture does.
    begin["step"]["context"]["draft"] = document(draft)
    seen = []

    class ResearchReached(Exception):
        pass

    def decode(raw):
        decoded = decode_context_draft(raw)
        assert decoded.manifest is None
        return replace(
            decoded,
            host_inputs=(
                make_research_request(
                    "r1", query_spec=spec(), query_digest=query_digest("research"), max_bytes=65536
                ),
            ),
        )

    def capture(_ctx, request):
        seen.append(request)
        raise ResearchReached()

    with pytest.raises(ResearchReached):
        finalize_stage_context(
            replace(ctx, config=object()),
            claim,
            begin,
            env,
            replace(inputs, decode=decode, research_query=capture),
            workspace_id=side.ws,
        )
    assert seen[0]["project_id"] == str(side.proj)
    assert step is not None
    assert seen[0]["step_ref"] == f"step:{step.id}"


def test_cache_binding_refuses_changed_evidence_without_creating_another_row(owned_research):
    from skm.kernel.errors import NotFound, ValidationFailed
    from skm.modules.context.domain.research import result_to_json
    from skm.modules.context.public import RecordResearchResult

    side, case = owned_research.side, owned_research
    ctx = host(client=side.client, clock=side.clock)
    source_setting(side, **ctx.config["context.research.sources"]["docs"])
    original = research_query(
        ctx, spec(), workspace_id=side.ws, project_id=side.proj, step_ref=None, mounts={}
    )
    wire = cast("dict[str, Any]", result_to_json(original.results[0]))
    query_id = str(side.new_id())
    wire.update(query_id=query_id, cache_status="hit")
    wire["documents"][0]["title"] = "changed evidence"
    command = RecordResearchResult.from_json(
        {
            "workspace_id": str(side.ws),
            "project_id": str(side.proj),
            "step_ref": f"step:{case.step.id}",
            "query_text": original.query_text,
            "query_digest": original.query_digest,
            "depth": "standard",
            "max_documents": 10,
            "results": [wire],
        }
    )
    with pytest.raises(ValidationFailed, match="cached_result_changed"):
        side.client.dispatch(command, idempotency_key=f"changed-cache:{query_id}")
    with side.uow(readonly=True) as uow, pytest.raises(NotFound):
        uow.repo(ResearchRepository).get(query_id)
