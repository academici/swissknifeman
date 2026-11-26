"""M4: real context publication and CLI authorization on memory and PostgreSQL."""

import json
from dataclasses import replace
from hashlib import sha256
from typing import Any, cast

import pytest

from contracts.execution._worker_protocol_support import worker_claim
from contracts.execution.harness import exec_side as exec_side
from contracts.execution.seed_helpers import seed_step
from e2e.test_execution_cli import invoke, result
from integration.worker._bus_support import admitted_stage, bus_case, context_draft
from integration.worker._support import make_host
from integration.worker.test_context_publication import setup_prompt
from integration.worker.test_context_scope import set_value
from skm.adapters.knowledge.null_retriever import NullMemoryRetriever
from skm.kernel.gateways import GatewayTable
from skm.kernel.json_types import JsonObject
from skm.modules.access.public import generate_secret
from skm.modules.context import public as context
from skm.modules.execution import public as execution
from skm.modules.execution.application._worker_dtos import document
from skm.modules.execution.application.commands import begin_stage
from skm.modules.execution.host import context_inputs
from skm.modules.execution.host.context import WorkerServices
from skm.modules.execution.host.context_inputs import finalize_stage_context
from skm.modules.execution.host.worker_loop import run
from skm.modules.runtimes.public import SelfLoadedSource
from support.pg import clean_test_database as clean_test_database
from support.pg import pg_session as pg_session
from support.pg import test_database as test_database

pytestmark = pytest.mark.e2e


def published(side, tmp_path, monkeypatch):
    case, stage, step, draft, ctx, env, claim, begin, inputs = setup_prompt(side, tmp_path, monkeypatch)
    assert step is not None
    assert draft is not None
    finalized = finalize_stage_context(
        ctx, claim, cast("JsonObject", begin), env, inputs, workspace_id=side.ws
    )
    return case, stage, step, draft, finalized


def test_prompt_artifact_text_block_explain_and_diff(exec_side, tmp_path, monkeypatch):
    side = exec_side
    _, _, step, draft, finalized = published(side, tmp_path, monkeypatch)
    prompt = result(side, "run", "step-prompt", str(step.id))
    assert prompt == {"text": finalized.rendered_prompt}
    assert "HOST-INSTRUCTIONS" in prompt["text"]
    with side.uow(readonly=True) as uow:
        manifest = context.require_final(uow, draft.manifest_id)
    with side.client.open_file_version_content(manifest.prompt_file_version_id) as stream:
        content = stream.read()
    assert content == finalized.rendered_prompt.encode("utf-8")
    assert manifest.prompt_digest == finalized.prompt_digest == "sha256:" + sha256(content).hexdigest()
    assert manifest.estimator_id == side.estimator.estimator_id
    assert manifest.assembler_version == finalized.manifest.assembler_version
    explained = result(side, "run", "step-context", str(step.id), "--blocks")
    assert explained["state"] == "final"
    position = next(b.position for b in manifest.blocks if b.included and b.content_stored)
    assert result(side, "run", "step-prompt", str(step.id), "--block", str(position))["text"]
    difference = result(side, "run", "step-context", str(step.id), "--diff", str(step.id))
    assert all(b["change"] == "same" for b in difference["blocks"])
    from skm.entrypoints.cli.commands import run as cli_run

    shown = []
    original_show = cli_run.show

    def show(ctx, command, value):
        shown.append(value)
        return original_show(ctx, command, value)

    monkeypatch.setattr(cli_run, "show", show)
    code, out, err = invoke(side, "run", "step-context", str(step.id), "--blocks", human=True)
    assert code == 0, err
    assert "system_constraints" in out
    assert shown[-1]["items"] == explained["rows"]


@pytest.mark.parametrize(
    "permissions", [["run.read"], ["run.read", "context.read"], ["run.read", "file.read"]]
)
@pytest.mark.parametrize("block", [(), ("--block", "0")])
def test_step_prompt_requires_both_context_and_file_authorization(
    exec_side, tmp_path, monkeypatch, permissions, block
):
    side = exec_side
    case, _, step, draft, finalized = published(side, tmp_path, monkeypatch)
    denied = side.restricted_client(permissions, scope_id=case.run.project_id, owner_token=True)
    code, out, err = invoke(side, "run", "step-prompt", str(step.id), *block, client=denied)
    assert code == 5, out + err
    assert json.loads(out)["error"]["code"] == "FORBIDDEN"
    with side.uow(readonly=True) as uow:
        manifest = context.require_final(uow, draft.manifest_id)
    assert str(manifest.prompt_file_version_id) not in out + err
    assert finalized.rendered_prompt not in out + err
    assert "HOST-INSTRUCTIONS" not in out + err


def test_null_retriever_proves_only_empty_skm_memory_exposure(exec_side):
    retriever = NullMemoryRetriever()
    assert (
        retriever.search(workspace_id=exec_side.ws, project_id=exec_side.proj, query="lesson", top_k=10) == ()
    )


@pytest.mark.parametrize("store_content", [False, True])
def test_host_text_storage_uses_pinned_run_setting(exec_side, tmp_path, monkeypatch, store_content):
    side = exec_side
    set_value(side, "context.store_host_block_content", store_content)
    case, stage, _, draft, ctx, env, claim, _, inputs = setup_prompt(side, tmp_path, monkeypatch)
    assert draft is not None
    # A live setting change cannot alter the already assembled draft's disclosure policy.
    set_value(side, "context.store_host_block_content", not store_content, version=1)
    begin = side.worker1_client.dispatch(
        execution.BeginStage(
            claim=worker_claim(side, case.claimed),
            stage_id=stage.stage_id,
            round_no=stage.round_no,
            input_digest=stage.input_digest,
            runtime_token_secret=str(generate_secret(lambda n: b"s" * n)),
        ),
        idempotency_key=f"begin-storage:{side.new_id()}",
    )
    assert begin["step"]["context"]["store_host_content"] is store_content
    begin["step"]["context"]["draft"] = document(draft)
    commands = []

    def capture(raw):
        commands.append(raw)
        return inputs.finalize_dto(raw)

    finalize_stage_context(
        ctx,
        claim,
        cast("JsonObject", begin),
        env,
        replace(inputs, finalize_dto=capture),
        workspace_id=side.ws,
    )
    assert commands[0]["host_blocks"]
    assert any("text" in b for b in commands[0]["host_blocks"]) is store_content
    with side.uow(readonly=True) as uow:
        saved = context.require_final(uow, draft.manifest_id)
    hosts = [b for b in saved.blocks if b.block_ref.startswith("h:") and b.included]
    assert hosts
    assert all(b.content_stored is store_content for b in hosts)


@pytest.mark.parametrize("mutation", ["crlf", "newline", "unicode"])
def test_phase_b_rejects_changed_prompt_bytes_before_publication(exec_side, tmp_path, monkeypatch, mutation):
    side = exec_side
    _, _, _, draft, ctx, env, claim, begin, inputs = setup_prompt(side, tmp_path, monkeypatch)
    assert draft is not None

    def corrupt(*args):
        final = context.finalize(*args)
        text = final.rendered_prompt
        text = (
            text.replace("\n", "\r\n")
            if mutation == "crlf"
            else text + ("\n" if mutation == "newline" else "\u0435\u0308")
        )
        return replace(final, rendered_prompt=text)

    uploads = []
    monkeypatch.setattr(context_inputs, "finalize", corrupt)
    with pytest.raises(ValueError, match="final context bytes"):
        finalize_stage_context(
            ctx,
            claim,
            cast("JsonObject", begin),
            env,
            replace(inputs, publish_prompt=lambda *args: uploads.append(args)),
            workspace_id=side.ws,
        )
    assert uploads == []
    with side.uow(readonly=True) as uow:
        assert context.get_manifest(uow, draft.manifest_id).state is context.ManifestState.DRAFT


def test_remote_begin_payload_cannot_claim_observed_runtime_self_loads(exec_side, tmp_path, monkeypatch):
    side = exec_side
    _, _, _, draft, ctx, env, claim, begin, inputs = setup_prompt(side, tmp_path, monkeypatch)
    assert draft is not None
    step_payload = begin["step"]
    assert isinstance(step_payload, dict)
    context_payload = step_payload["context"]
    assert isinstance(context_payload, dict)
    context_payload["runtime_self_loaded"] = [{"kind": "forged", "files": ["forged.md"]}]
    finalized = finalize_stage_context(
        ctx, claim, cast("JsonObject", begin), env, inputs, workspace_id=side.ws
    )
    assert finalized.prompt_digest
    with side.uow(readonly=True) as uow:
        saved = context.require_final(uow, draft.manifest_id)
    assert saved.route["self_loads_observed"] == []


@pytest.mark.parametrize("store", [False, True])
@pytest.mark.parametrize("replay", [False, True])
def test_begin_uses_manifest_content_policy_when_run_bundle_differs(
    exec_side, tmp_path, monkeypatch, store, replay
):
    side = exec_side
    set_value(side, "context.store_host_block_content", not store)
    case = bus_case(side, tmp_path / "repo")
    set_value(side, "context.store_host_block_content", store, version=1)
    if replay:
        stage, _, draft = admitted_stage(case, "executor", real_draft=True)
        command = {"stage_id": stage.stage_id, "round_no": stage.round_no, "input_digest": stage.input_digest}
    else:
        step_id = side.new_id()
        draft = context_draft(side, step_id, "execute")

        def prepare(uow, _ctx, fenced, stage, _selected, _secret):
            step = seed_step(side, uow, fenced.attempt, stage, step_id=step_id, manifest_id=draft.manifest_id)
            return step, {"context": {}}

        monkeypatch.setattr(begin_stage, "prepare_agent_step", prepare)
        instruction = case.claimed["instruction"]
        command = {k: instruction[k] for k in ("stage_id", "round_no", "input_digest")}
    assert draft is not None
    with side.uow(readonly=True) as uow:
        saved = context.get_manifest(uow, draft.manifest_id)
        _, values = begin_stage.effective_values(uow, case.run.id)
    assert values["context.store_host_block_content"] is not store
    snapshot = saved.route["render_snapshot"]
    assert isinstance(snapshot, dict)
    assert snapshot["store_host_content"] is store
    result = side.worker1_client.dispatch(
        execution.BeginStage(
            claim=worker_claim(side, case.claimed),
            **command,
            runtime_token_secret=str(generate_secret(lambda n: b"s" * n)),
        ),
        idempotency_key=f"begin-policy:{side.new_id()}",
    )
    assert result["step"]["context"]["store_host_content"] is store


@pytest.mark.parametrize("when", ["factory", "after_finalize"])
@pytest.mark.parametrize("mutation", ["crlf", "newline", "unicode", "digest", "coherent"])
def test_worker_rejects_runtime_handoff_tampering(tmp_path, monkeypatch, when, mutation):
    fixture = make_host(tmp_path, monkeypatch)
    factory, dispatch = fixture.services.runtime_request, fixture.client.dispatch
    prepared = []

    def corrupt(agent):
        text = agent.rendered_prompt + {"crlf": "\r\n", "newline": "\n", "unicode": "\u0435\u0308"}.get(
            mutation, "changed"
        )
        if mutation != "digest":
            object.__setattr__(agent, "rendered_prompt", text)
        if mutation in {"digest", "coherent"}:
            object.__setattr__(agent, "prompt_digest", "sha256:" + sha256(text.encode()).hexdigest())

    def runtime_request(*args):
        agent = factory(*args)
        prepared.append(agent)
        if when == "factory":
            corrupt(agent)
        return agent

    def publish(command, *, idempotency_key=None):
        result = dispatch(command, idempotency_key=idempotency_key)
        if when == "after_finalize" and command["operation"] == "finalize_manifest":
            corrupt(prepared[0])
        return result

    services = replace(fixture.services, runtime_request=runtime_request)
    ctx = replace(
        fixture.ctx, gateways=GatewayTable({**fixture.entries, WorkerServices: services}, "host_gateway")
    )
    monkeypatch.setattr(fixture.client, "dispatch", publish)
    monkeypatch.setattr(services.stages.for_stage("agent_step"), "run", lambda *_: pytest.fail("handler ran"))
    assert run(ctx, fixture.request)["reason"] == "host_failure"
    assert len(prepared) == 1
    finalized = any(c["operation"] == "finalize_manifest" for c, _ in fixture.client.calls)
    assert finalized is (when == "after_finalize")
    assert not any(
        c["operation"] == "renew_lease" and c.get("progress", {}).get("phase") == "runtime_started"
        for c, _ in fixture.client.calls
    )


def test_worker_observes_actual_runtime_request_before_finalization(tmp_path, monkeypatch):
    fixture = make_host(tmp_path, monkeypatch, role="reviewer")
    observed, order = [], []
    dispatch, start = fixture.client.dispatch, fixture.runtime.start

    def observe(agent):
        observed.append(agent)
        order.append("observe")
        return (
            SelfLoadedSource(
                cast("Any", "project_instructions"), agent.workdir, ("AGENTS.md",), "start", "untrusted"
            ),
        )

    def publish(command, *, idempotency_key=None):
        if command["operation"] == "finalize_manifest":
            order.append("finalize")
            assert command["runtime_self_loaded"] == [
                {
                    "kind": "project_instructions",
                    "locator": observed[0].workdir,
                    "files": ["AGENTS.md"],
                    "when": "start",
                }
            ]
        return dispatch(command, idempotency_key=idempotency_key)

    def spawn(agent):
        assert agent is observed[0]
        order.append("start")
        return start(agent)

    monkeypatch.setattr(fixture.runtime, "self_loaded_context", observe, raising=False)
    monkeypatch.setattr(fixture.runtime, "start", spawn)
    monkeypatch.setattr(fixture.client, "dispatch", publish)
    run(fixture.ctx, fixture.request)
    assert order == ["observe", "finalize", "start"]
