"""ENCH4 authoring while a worker holds an immutable execution contract."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from hashlib import sha256
from threading import Event
from typing import Any
from uuid import UUID

import pytest

from contracts.execution._client_execution import (
    AgentExecution,
    ClientWorker,
    ExecutedChecks,
    begin_command,
    configure_execution,
    finish_agent_and_run_checks,
    prepare_agent_request,
    register_worker,
    schedule,
    start_run_command,
)
from contracts.planning._authoring_support import (
    BASE_GUIDE,
    BASE_TEXT,
    EDITED_TEXT,
    NEW_GUIDE,
    A,
    add_guide,
    add_version,
    base_draft,
    merge_edits,
    revisions,
)
from contracts.planning.test_client_planning import preview, publication
from integration.artifacts.test_upload_flow import dispatch_new
from skm.application_bus.client import SkmClient
from skm.application_bus.ports import EventReader
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.ids import AttemptId, RunId
from skm.kernel.json_types import JsonObject
from skm.modules.context import public as context
from skm.modules.execution import public as execution
from skm.modules.execution.domain.contract_digest import task_contract_digest
from skm.modules.execution.ports import BundleRepository, RunRepository, StageRepository, TaskRepository
from skm.modules.planning import public as planning
from skm.modules.runtimes import public as runtimes
from support.backend import ClientBackend, client_backend
from support.pg import clean_test_database, pg_session, test_database

__all__ = ["clean_test_database", "client_backend", "pg_session", "test_database"]


def _published_events(side: ClientBackend, plan: UUID) -> list[Any]:
    with side.uow() as uow:
        envelopes = uow.repo(EventReader).after_workspace_seq(
            side.seed.workspace_id, 0, types=None, limit=500
        )
    return [
        envelope
        for envelope in envelopes
        if envelope.type == "urn:skm:planning:event:plan-revision-published:v1" and envelope.stream_id == plan
    ]


def _publish_with_material_race(
    side: ClientBackend,
    owner: SkmClient,
    plan: UUID,
    editor: SkmClient,
    draft: Any,
    added: Any,
) -> tuple[Any, Any]:
    stale = preview(editor, plan, draft)
    assert stale.publishable
    assert stale.pinned_materials[0].file_version_id == added.file_version_id
    new_version = add_version(side, owner, added)
    with pytest.raises(SkmError) as rejected:
        dispatch_new(editor, publication(plan, draft, stale))
    assert rejected.value.code is ErrorCode.VERSION_CONFLICT
    assert rejected.value.details["reason"] == "candidate_changed"
    fresh = preview(editor, plan, draft)
    assert fresh.publishable
    assert fresh.content_digest != stale.content_digest
    assert fresh.source == stale.source
    assert fresh.pinned_materials[0].file_version_id == new_version.file_version_id
    command = publication(plan, draft, fresh)
    events_before = len(_published_events(side, plan))
    key = "publish-repaired-authoring-draft"
    with side.lose_response(editor) as interrupted:
        interrupted.dispatch(command, idempotency_key=key)
    latest, *prior = revisions(owner, plan)
    assert len(prior) == 2
    published = editor.dispatch(command, idempotency_key=key)
    assert isinstance(published, planning.PublishRevisionResult)
    assert (published.revision_id, published.content_digest) == (latest.revision_id, fresh.content_digest)
    assert len(_published_events(side, plan)) == events_before + 1
    with pytest.raises(SkmError) as changed_key:
        editor.dispatch(replace(command, expected_content_digest=stale.content_digest), idempotency_key=key)
    assert changed_key.value.code is ErrorCode.IDEMPOTENCY_KEY_REUSED

    side.revoke("other-editor")
    with pytest.raises(SkmError) as revoked:
        editor.dispatch(command, idempotency_key=key)
    assert revoked.value.code is ErrorCode.UNAUTHENTICATED
    with pytest.raises(SkmError) as revoked_read:
        preview(editor, plan, draft)
    assert revoked_read.value.code is ErrorCode.UNAUTHENTICATED
    assert len(revisions(owner, plan)) == 3
    return published, new_version


@dataclass(frozen=True)
class AgentContract:
    revision_id: UUID
    entity_id: UUID
    bundle_digest: str
    instruction_digest: str
    task_contract_digest: str
    admission_contract_digest: str
    context_digest: str
    prompt_digest: str
    check_ids: tuple[str, ...]
    review_requirement: JsonObject


def _bound_contract(
    side: ClientBackend,
    owner: SkmClient,
    agent: AgentExecution,
    publication: Any,
    material: UUID,
    guide: bytes,
    text: str,
    model: str,
    route_class: str,
) -> AgentContract:
    stage, request = agent.stage, agent.request
    run_id = RunId(UUID(request.labels["run_id"]))
    run: Any = owner.ask(execution.GetRun(run_id))
    revision = publication.revision_id
    assert run.revision_no == publication.revision_no
    published: Any = owner.ask(planning.GetRevision(run.plan_id, revision_id=revision, include_document=True))
    item = next(item for item in published.document["items"] if item["key"] == A)
    checks = [check for check in published.document["checks"] if check["owner"] == A]
    assert published.document["materials"][0]["file_version_id"] == str(material)
    step: Any = stage.begin["step"]
    assert stage.context is not None
    with side.uow() as uow:
        assert uow.repo(RunRepository).get(run_id).revision_id == revision
        manifest = context.require_final(uow, stage.context.manifest.id)
        bundle = uow.repo(BundleRepository).get(run_id)
        assert bundle.work_policies is not None
        work_policy = bundle.work_policies[A]
        history = uow.repo(StageRepository).history(AttemptId(UUID(request.labels["attempt_id"])))
        (executed,) = history.of_stage("execute")
    assert executed.record.input_digest == stage.instruction.input_digest
    assert manifest.owner_ref == f"step:{request.request_id}"
    assert str(manifest.entity_id) == item["id"] == stage.task["entity_id"]
    assert manifest.revision_id == revision
    assert stage.task["revision_id"] == str(revision)
    assert step["route_snapshot"]["effective_config_digest"] == bundle.config_digest == run.bundle_digest
    assert step["admission"]["min_class"] == route_class == item["route"]["class"]
    assert step["route"]["source"] == "plan_route"
    assert step["route_snapshot"]["resolved"] == {"runtime_id": "fake", "model": model, "effort": "high"}
    assert (request.runtime_id, request.model, request.effort) == ("fake", model, "high")
    assert manifest.model == request.model
    assert (
        manifest.prompt_digest
        == request.prompt_digest
        == "sha256:" + sha256(request.rendered_prompt.encode()).hexdigest()
    )
    assert manifest.prompt_file_version_id is not None
    with owner.open_file_version_content(manifest.prompt_file_version_id) as stream:
        assert stream.read() == request.rendered_prompt.encode()
    assert manifest.task_digest
    assert manifest.task_digest == stage.context.manifest.task_digest
    draft = step["context"]["draft"]
    assert draft["draft_digest"] == manifest.draft_digest
    variables = draft["variables"]["task"]
    assert variables["work_policy_digest"] == work_policy.digest
    assert variables["goal"] == item["summary"] == text
    assert variables["guidance"] == item["guidance_md"]
    assert variables["deliverables"] == item["deliverables"]
    assert f"Goal: {text}" in request.rendered_prompt.splitlines()
    expected_checks = [
        f"- Check [{c['key']}] ({c['kind']}, required={c['required']}): {c['title']}" for c in checks
    ]
    assert [
        line for line in request.rendered_prompt.splitlines() if line.startswith("- Check [")
    ] == expected_checks
    (pin,) = [block for block in manifest.blocks if block.block_type.value == "materials" and block.included]
    assert pin.source_ref == f"file_version:{material}"
    assert pin.source_version == "sha256:" + sha256(guide).hexdigest()
    assert guide.decode().strip() in request.rendered_prompt.splitlines()
    (contract_block,) = [block for block in draft["blocks"] if block["block_type"] == "task_contract"]
    assert contract_block["source_ref"] == f"spec:{revision}/{A}#task_contract"
    assert contract_block["content"] in request.rendered_prompt
    assert (
        contract_block["content_digest"] == "sha256:" + sha256(contract_block["content"].encode()).hexdigest()
    )
    return AgentContract(
        revision,
        UUID(item["id"]),
        run.bundle_digest,
        executed.record.input_digest,
        task_contract_digest(
            {
                "goal": item["summary"],
                "instructions": item["summary"],
                "deliverables": item["deliverables"],
                "declared_write_scope": stage.task["declared_write_scope"],
                "check_specs": checks,
                "review_requirement": item["review"],
            },
            work_policy.digest,
        ),
        str(step["admission"]["contract_digest"]),
        manifest.task_digest,
        request.prompt_digest,
        tuple(check["id"] for check in checks),
        item["review"],
    )


def _admit_fake(worker: ClientWorker, claimed: Any, agent: AgentExecution) -> None:
    heartbeat = dispatch_new(
        worker.client,
        execution.RenewLease(
            claim=worker.fence(claimed),
            progress={
                "phase": "runtime_started",
                "stage_record_id": agent.stage.begin["stage_record_id"],
                "step_id": agent.request.request_id,
            },
        ),
    )
    assert "refusal" not in heartbeat
    assert heartbeat["cancel_requested"] is False


def _assert_checks(
    executed: ExecutedChecks, agent: AgentExecution, contract: AgentContract, titles: tuple[str, ...]
) -> None:
    step: Any = agent.stage.begin["step"]
    task = step["context"]["draft"]["variables"]["task"]
    # Reconstruct the bound task from the worker's two stage payloads and the pinned review requirement.
    observed = task_contract_digest(
        {
            "goal": task["goal"],
            "instructions": task["instructions"],
            "deliverables": task["deliverables"],
            "declared_write_scope": agent.stage.task["declared_write_scope"],
            "check_specs": [
                {"id": row["check_spec_id"], "kind": row["kind"], "definition": row["definition"]}
                for row in executed.definitions
            ],
            "review_requirement": contract.review_requirement,
        },
        task["work_policy_digest"],
    )
    assert observed == contract.task_contract_digest
    assert sorted((row["check_spec_id"], row["summary"], row["state"]) for row in executed.results) == sorted(
        (key, f"MANUAL_PENDING: {title}", "manual_pending")
        for key, title in zip(contract.check_ids, titles, strict=True)
    )


def _assert_rebound(original: AgentContract, latest: AgentContract, new_prompt: str) -> None:
    assert original.entity_id == latest.entity_id
    assert original.revision_id != latest.revision_id
    assert original.task_contract_digest != latest.task_contract_digest
    assert original.admission_contract_digest != latest.admission_contract_digest
    assert original.instruction_digest != latest.instruction_digest
    assert original.context_digest != latest.context_digest
    assert original.prompt_digest != latest.prompt_digest
    assert BASE_TEXT not in new_prompt
    assert BASE_GUIDE.decode().strip() not in new_prompt


def _assert_no_carry_forward(side: ClientBackend, new_id: RunId) -> None:
    with side.uow() as uow:
        selection = uow.repo(BundleRepository).get(new_id).selection
        assert selection is not None
        assert not selection.satisfied
        (new_task,) = uow.repo(TaskRepository).list_for_run(new_id)
        assert new_task.accepted_attempt_id is None
        assert new_task.accepted_output_id is None


def test_ench4_authoring_does_not_rebind_an_active_run(client_backend: ClientBackend) -> None:
    side = client_backend
    owner = side.client()
    repo_id = configure_execution(side, owner)
    worker = register_worker(side, owner, "authoring-worker")
    added = add_guide(side, owner)
    plan, base = base_draft(side, owner, added.file_version_id)
    baseline = dispatch_new(owner, publication(plan, base, preview(owner, plan, base)))

    def start(revision: UUID) -> tuple[Any, AgentExecution]:
        run = dispatch_new(owner, start_run_command(plan, revision, A))
        schedule(side)
        claimed = dispatch_new(worker.client, worker.claim())
        assert claimed["run_id"] == str(run.run_id)
        assert claimed["task"]["revision_id"] == str(revision)
        ready = dispatch_new(worker.client, begin_command(worker, claimed))
        agent = prepare_agent_request(side, worker, claimed, ready, repo_id)
        _admit_fake(worker, claimed, agent)
        return claimed, agent

    old_claim, old = start(baseline.revision_id)

    def old_binding() -> AgentContract:
        return _bound_contract(
            side,
            owner,
            old,
            baseline,
            added.file_version_id,
            BASE_GUIDE,
            BASE_TEXT,
            "fake-b",
            "implementation",
        )

    original = old_binding()
    entered, release = Event(), Event()
    invocations: list[runtimes.AgentRequest] = []

    def fake_executor(request: runtimes.AgentRequest) -> JsonObject:
        invocations.append(request)
        entered.set()
        assert release.wait(60), "Authoring barrier did not release the fake"
        return {
            "schema": request.result_schema_urn,
            "status": "done",
            "summary": "Reviewed the pinned authoring guide.",
            "changed_paths": [],
            "checks_run": [],
            "open_issues": [],
            "self_check": {"performed": True},
        }

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(fake_executor, old.request)
        try:
            assert entered.wait(10)
            editor, draft = merge_edits(side, plan)
            renew = execution.RenewLease(claim=worker.fence(old_claim))
            dispatch_new(worker.client, renew)
            published, new_version = _publish_with_material_race(side, owner, plan, editor, draft, added)
            dispatch_new(worker.client, renew)
            unchanged: Any = owner.ask(execution.GetRun(UUID(old_claim["run_id"])))
            assert unchanged.status == "running"
            assert unchanged.finished_at is None
            assert old_binding() == original
            assert invocations == [old.request]
            assert not pending.done()
        finally:
            release.set()
        result = pending.result(timeout=10)
    _assert_checks(
        finish_agent_and_run_checks(side, worker, old_claim, old, result),
        old,
        original,
        ("Verify original fixture",),
    )

    new_claim, new = start(published.revision_id)
    latest = _bound_contract(
        side, owner, new, published, new_version.file_version_id, NEW_GUIDE, EDITED_TEXT, "fake-a", "frontier"
    )
    _assert_rebound(original, latest, new.request.rendered_prompt)
    _assert_no_carry_forward(side, RunId(UUID(new_claim["run_id"])))
    result = fake_executor(new.request)
    assert invocations == [old.request, new.request]
    _assert_checks(
        finish_agent_and_run_checks(side, worker, new_claim, new, result),
        new,
        latest,
        ("Verify original fixture", "Verify authored output"),
    )
