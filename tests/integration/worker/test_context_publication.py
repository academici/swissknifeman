"""Real host reads and atomic worker-scoped prompt publication on both persistence backends."""

from dataclasses import replace
from uuid import UUID

import pytest

from contracts.execution._worker_protocol_support import worker_claim
from integration.artifacts.test_upload_flow import add_file_dto
from skm.application_bus.client import StagedBlobRef
from skm.bootstrap.host_services import build_context_inputs
from skm.kernel.errors import SkmError
from skm.kernel.ids import AttemptId, WorkerId
from skm.kernel.json_types import JsonObject
from skm.modules.artifacts import public as artifacts
from skm.modules.context.application.commands.finalize_manifest import FinalizeManifest
from skm.modules.context.domain.manifest import ManifestState
from skm.modules.context.ports import ContextRepository
from skm.modules.execution.application._stage_preparation import context_host_limits
from skm.modules.execution.domain.ids import AssignmentId
from skm.modules.execution.domain.lease import WorkerClaim
from skm.modules.execution.generated.commands import CancelRun
from skm.modules.execution.host.context_inputs import finalize_stage_context
from skm.modules.execution.host.environment import PreparedEnvironment

from ._bus_support import admitted_stage, bus_case
from ._support import make_host


def setup_prompt(exec_side, tmp_path, monkeypatch):
    case = bus_case(exec_side, tmp_path / "repo")
    stage, step, draft = admitted_stage(case, "executor", real_draft=True)
    assert step is not None
    assert draft is not None
    fixture = make_host(tmp_path / "host", monkeypatch)
    ctx = replace(fixture.ctx, client=exec_side.worker1_client)
    env = PreparedEnvironment(
        case.environment.id, str(case.root), {"repo": case.root}, case.environment.baseline, "main"
    )
    wire_claim = worker_claim(exec_side, case.claimed)
    claim = WorkerClaim(
        AssignmentId(UUID(wire_claim["assignment_id"])),
        AttemptId(UUID(wire_claim["attempt_id"])),
        WorkerId(UUID(wire_claim["worker_id"])),
        wire_claim["fencing_token"],
    )
    with exec_side.uow(readonly=True) as uow:
        host_limits = context_host_limits(uow, case.run.id)
    begin: JsonObject = {
        "step": {
            "step_id": str(step.id),
            "context": {
                "draft": {},
                "estimator_id": exec_side.estimator.estimator_id,
                "host_limits": host_limits,
            },
        }
    }
    inputs = replace(
        build_context_inputs(),
        decode=lambda _: draft,
    )
    return case, stage, step, draft, ctx, env, claim, begin, inputs


def test_worker_publishes_real_rendered_prompt_and_replays_without_reconsuming(
    exec_side, tmp_path, monkeypatch
):
    case, _, step, draft, ctx, env, claim, begin, inputs = setup_prompt(exec_side, tmp_path, monkeypatch)
    payloads = []

    def dto(raw):
        payloads.append(raw)
        return FinalizeManifest.from_json(raw)

    finalized = finalize_stage_context(
        ctx,
        claim,
        begin,
        env,
        replace(inputs, finalize_dto=dto),
        workspace_id=exec_side.ws,
        path_patterns=(("repo", "src/**"),),
    )
    assert "HOST-INSTRUCTIONS: check the real answer." in finalized.rendered_prompt
    assert ["repo", "src/app.py"] in payloads[0]["host_facts"]["work_paths"]
    assert "prompt_file_version_id" not in payloads[0]
    ctx.client.dispatch(FinalizeManifest.from_json(payloads[0]))
    ref = payloads[0]["prompt_staged_blob"]
    staged = StagedBlobRef(
        UUID(ref["staged_blob_id"]), exec_side.ws, ref["digest"], ref["size"], ref["media_type"]
    )
    with pytest.raises(SkmError) as rejected:
        ctx.client.dispatch(
            add_file_dto(exec_side.ws, exec_side.proj, staged),
            idempotency_key=f"forbidden-prompt-mutation:{exec_side.new_id()}",
        )
    assert rejected.value.code.value == "FORBIDDEN"
    with exec_side.uow(readonly=True) as uow:
        saved = uow.repo(ContextRepository).get(draft.manifest_id)
        assert saved.state is ManifestState.FINAL
        assert saved.owner_ref == f"step:{step.id}"
        assert (
            artifacts.read_text_content(uow, saved.prompt_file_version_id, max_bytes=2_000_000)
            == finalized.rendered_prompt
        )
    exec_side.client.dispatch(CancelRun(case.run.id, "late prompt replay"))
    with pytest.raises(SkmError) as caught:
        ctx.client.dispatch(FinalizeManifest.from_json(payloads[0]))
    assert caught.value.code.value == "LEASE_LOST"


@pytest.mark.parametrize("bad_source", ["foreign_workspace", "wrong_digest", "tampered_selection"])
def test_worker_prompt_publication_rolls_back_untrusted_inputs(exec_side, tmp_path, monkeypatch, bad_source):
    _case, _, _, draft, ctx, env, claim, begin, inputs = setup_prompt(exec_side, tmp_path, monkeypatch)
    payloads = []

    def dto(raw):
        payloads.append(raw)
        if bad_source == "foreign_workspace":
            raw["prompt_staged_blob"]["workspace_id"] = str(exec_side.new_id())
        elif bad_source == "wrong_digest":
            raw["rendered_prompt_digest"] = "sha256:" + "0" * 64
        else:
            raw["selection"]["total_tokens"] += 1
        return FinalizeManifest.from_json(raw)

    with pytest.raises(SkmError):
        finalize_stage_context(
            ctx, claim, begin, env, replace(inputs, finalize_dto=dto), workspace_id=exec_side.ws
        )
    with exec_side.uow(readonly=True) as uow:
        assert uow.repo(ContextRepository).get(draft.manifest_id).state is ManifestState.DRAFT
    # The identical staged upload remains usable after a rejected transaction.
    raw = payloads[0]
    raw["prompt_staged_blob"]["workspace_id"] = str(exec_side.ws)
    raw["rendered_prompt_digest"] = raw["prompt_staged_blob"]["digest"]
    if bad_source == "tampered_selection":
        raw["selection"]["total_tokens"] -= 1
    ctx.client.dispatch(FinalizeManifest.from_json(raw))
