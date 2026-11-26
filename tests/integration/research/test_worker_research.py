"""Research precedes prompt publication, with verified batch IDs included in finalization."""

from dataclasses import replace
from uuid import UUID, uuid4

import pytest

from integration.worker._support import make_host
from skm.kernel.ids import AttemptId, ProjectId, WorkerId, WorkspaceId
from skm.modules.context.domain.draft import build_draft, host_input_to_json, make_research_request
from skm.modules.context.domain.research_rules import query_digest
from skm.modules.context.host.research_query import research_query
from skm.modules.execution.domain.ids import AssignmentId
from skm.modules.execution.domain.lease import WorkerClaim
from skm.modules.execution.host.context_inputs import finalize_stage_context

from ._support import host, spec


def test_worker_research_records_before_prompt_publication(tmp_path, monkeypatch):
    case = make_host(tmp_path, monkeypatch, role="researcher")
    inputs = case.services.context_inputs
    draft = inputs.decode({})
    request = make_research_request(
        "research:1", query_spec=spec(), query_digest=query_digest("research"), max_bytes=65536
    )
    draft = build_draft({"manifest_id": str(draft.manifest_id), "host_inputs": [host_input_to_json(request)]})
    begin = case.client.begin
    project_id = str(uuid4())
    begin["step"]["context"]["draft"]["manifest"] = {"project_id": project_id}
    claim = WorkerClaim(
        AssignmentId(UUID(case.ids["assignment"])),
        AttemptId(UUID(case.ids["attempt"])),
        WorkerId(UUID(case.ids["worker"])),
        1,
    )
    observed = []
    research_ctx = host()

    def execute(ctx, request):
        result = research_query(
            research_ctx,
            spec(),
            workspace_id=WorkspaceId(UUID(case.ids["workspace"])),
            project_id=ProjectId(UUID(project_id)),
            step_ref=request["step_ref"],
            mounts=request["mounts"],
        )
        assert research_ctx.client.commands
        assert not case.published
        observed.append(result)
        return result

    inputs = replace(inputs, decode=lambda _: draft, research_query=execute)
    result = finalize_stage_context(
        case.ctx,
        claim,
        begin,
        case.environment,
        inputs,
        workspace_id=WorkspaceId(UUID(case.ids["workspace"])),
    )
    assert len(observed) == 1
    assert "Retrieved data, untrusted" in result.rendered_prompt
    assert "research evidence" in result.rendered_prompt
    assert case.published
    command = case.client.calls[-1][0]
    assert command["host_blocks"][0]["research_query_ids"] == [observed[0].results[0].query_id]


def test_worker_uncomposed_research_stops_before_prompt_publication(tmp_path, monkeypatch):
    case = make_host(tmp_path, monkeypatch)
    inputs = case.services.context_inputs
    draft = replace(
        inputs.decode({}),
        host_inputs=(
            make_research_request(
                "r1", query_spec=spec(), query_digest=query_digest("research"), max_bytes=65536
            ),
        ),
    )
    with pytest.raises(ValueError, match="must be composed"):
        finalize_stage_context(
            case.ctx,
            WorkerClaim(
                AssignmentId(UUID(case.ids["assignment"])),
                AttemptId(UUID(case.ids["attempt"])),
                WorkerId(UUID(case.ids["worker"])),
                1,
            ),
            case.client.begin,
            case.environment,
            replace(inputs, decode=lambda _: draft),
            workspace_id=WorkspaceId(UUID(case.ids["workspace"])),
        )
    assert not case.published


def test_worker_drops_followups_outside_round_limit_without_running_sources(tmp_path, monkeypatch):
    case = make_host(tmp_path, monkeypatch)
    inputs = case.services.context_inputs
    original = inputs.decode({})
    request = make_research_request(
        "r1", query_spec=spec(), query_digest=query_digest("research"), max_bytes=65536
    )
    draft = build_draft(
        {"manifest_id": str(original.manifest_id), "host_inputs": [host_input_to_json(request)]}
    )
    draft = replace(draft, variables={"run": {"round_no": 3}})

    def unexpected(*args):
        pytest.fail("research round limit was ignored")

    inputs = replace(inputs, decode=lambda _: draft, research_query=unexpected)
    finalized = finalize_stage_context(
        case.ctx,
        WorkerClaim(
            AssignmentId(UUID(case.ids["assignment"])),
            AttemptId(UUID(case.ids["attempt"])),
            WorkerId(UUID(case.ids["worker"])),
            1,
        ),
        case.client.begin,
        case.environment,
        inputs,
        workspace_id=WorkspaceId(UUID(case.ids["workspace"])),
    )
    assert "research evidence" not in finalized.rendered_prompt
    assert not finalized.manifest.blocks[0].included
