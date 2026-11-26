"""Canonical trailer ordering, output projection and integration mode validation."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from skm.kernel.errors import SkmError
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.artifacts import public as artifacts
from skm.modules.execution.application._integration_inputs import step_attribution, task_spec_trailers
from skm.modules.execution.application._worker_dtos import digest
from skm.modules.execution.domain.integration import (
    CommitMode,
    IntegrationStrategy,
    commit_plan,
    commit_trailers,
    excluded_paths,
    validate_mode,
)
from skm.modules.execution.domain.output import ChangedPath
from skm.modules.execution.domain.step import RoleId
from skm.modules.planning import public as planning
from unit.execution.domain.test_acceptance import make_output


def identity() -> JsonObject:
    return {
        "run_id": "run",
        "plan_id": "plan",
        "revision_no": 3,
        "task_key": "T1",
        "attempt_id": "attempt",
        "output_id": "output",
        "effect_id": "effect",
    }


def test_canonical_trailers_are_ordered_and_optional_identity_is_absent():
    inputs = identity()
    assert commit_trailers(inputs) == (
        ("SKM-Run", "run"),
        ("SKM-Plan", "plan"),
        ("SKM-Revision", "3"),
        ("SKM-Task", "T1"),
        ("SKM-Attempt", "attempt"),
        ("SKM-Output", "output"),
        ("SKM-Effect", "effect"),
    )
    key = "fk-" + "b" * 16
    trailers = commit_trailers(
        {**inputs, "review_id": "review", "findings": [key, key], "output_no": 2, "review_round": 3}
    )
    assert trailers[-5:] == (
        ("SKM-Review", "review"),
        ("SKM-Findings", key),
        ("SKM-Findings", key),
        ("SKM-Output-No", "2"),
        ("SKM-Review-Round", "3"),
    )


def test_repeated_producers_keep_contributor_order_and_unavailable_evidence_is_omitted():
    shared = "fake/model/high"
    inputs: JsonObject = {
        **identity(),
        "producers": [
            {"plan_role": "executor", "executed_by": shared, "executor_session": "session-one"},
            {"plan_role": "reviewer", "plan_actor": "assigned/model/low"},
            {"plan_role": "executor", "executed_by": shared, "executor_session": "session-two"},
        ],
    }
    assert commit_trailers(inputs)[7:] == (
        ("Plan-Role", "executor"),
        ("Executed-By", shared),
        ("Executor-Session", "session-one"),
        ("Plan-Role", "reviewer"),
        ("Plan-Actor", "assigned/model/low"),
        ("Plan-Role", "executor"),
        ("Executed-By", shared),
        ("Executor-Session", "session-two"),
    )


def test_private_text_cannot_be_serialized_as_task_spec_metadata_or_findings():
    ref = f"skm:revision:{uuid4()}#entity:{uuid4()}"
    digest = "sha256:" + "a" * 64
    secret = "PRIVATE TASK INSTRUCTIONS"
    inputs = {**identity(), "task_spec": secret, "task_spec_ref": ref, "task_spec_digest": digest}
    assert commit_trailers(inputs)[-2:] == (("Task-Spec-Ref", ref), ("Task-Spec-Digest", digest))
    for bad in (
        {**inputs, "task_spec_ref": secret},
        {**inputs, "task_spec_digest": secret},
        {**inputs, "task_spec_digest": None},
    ):
        with pytest.raises(ValueError, match="invalid task specification trailers"):
            commit_trailers(bad)
    with pytest.raises(ValueError, match="invalid integration trailer: SKM-Findings"):
        commit_trailers({**identity(), "findings": [secret]})


def test_task_spec_reference_and_digest_are_derived_from_the_pinned_entity(monkeypatch):
    private = {"title": "private title", "contract": "private implementation request"}
    run = SimpleNamespace(revision_id=uuid4(), inline_spec_file_version_id=None)
    task = SimpleNamespace(spec_entity_id=uuid4())
    uow = Mock(spec=UnitOfWork)

    def specification(actual_uow, revision_id):
        assert actual_uow is uow
        assert revision_id == run.revision_id

        def entity(entity_id):
            assert entity_id == task.spec_entity_id
            return private

        return SimpleNamespace(entity=entity)

    monkeypatch.setattr(planning, "get_revision_specification", specification)
    metadata = task_spec_trailers(uow, run, task)
    assert metadata == {
        "task_spec_ref": f"skm:revision:{run.revision_id}#entity:{task.spec_entity_id}",
        "task_spec_digest": digest(private),
    }


def test_task_spec_metadata_includes_inline_and_generated_tasks(monkeypatch):
    inline_id = uuid4()
    inline = SimpleNamespace(revision_id=None, inline_spec_file_version_id=inline_id)
    private_digest = "sha256:" + "a" * 64
    monkeypatch.setattr(artifacts, "get_file_version", lambda *_: SimpleNamespace(digest=private_digest))
    uow = Mock(spec=UnitOfWork)
    assert task_spec_trailers(uow, inline, SimpleNamespace(spec_entity_id=None)) == {
        "task_spec_ref": f"skm:file-version:{inline_id}",
        "task_spec_digest": private_digest,
    }
    generated = SimpleNamespace(
        id=uuid4(),
        spec_entity_id=None,
        kind="followup",
        origin={"reason": "private origin"},
        declared_write_scope=(),
    )
    assert task_spec_trailers(
        uow, SimpleNamespace(revision_id=uuid4(), inline_spec_file_version_id=None), generated
    ) == {
        "task_spec_ref": f"skm:task:{generated.id}",
        "task_spec_digest": digest({"kind": "followup", "origin": generated.origin, "write_scope": ()}),
    }


def test_attribution_distinguishes_assigned_route_and_verified_provider_evidence():
    route = {"runtime_id": "codex", "model": "planned", "effort": "medium"}
    binding = {
        "runtime_id": "codex",
        "provider_reported_model": "observed",
        "model_source": "provider_stream",
        "observed_effort": "high",
    }
    step = SimpleNamespace(
        role=RoleId.EXECUTOR,
        route_snapshot={"requested_route": route, "resolved": route, "adapter_version": "2"},
        runtime_observation={"binding": {**binding, "adapter_version": "2"}},
        session_ref="real-session",
    )
    expected = {
        "plan_role": "executor",
        "plan_actor": "codex/planned/medium",
        "executed_by": "codex/observed/high",
        "executor_session": "real-session",
    }
    assert step_attribution(step) == expected
    step.session_ref = "/private/local/transcript"
    expected.pop("executor_session")
    assert step_attribution(step) == expected
    step.runtime_observation["binding"]["adapter_version"] = "1"
    expected.pop("executed_by")
    assert step_attribution(step) == expected


@pytest.mark.parametrize("value", ["x\nSKM-Effect: forged", "x\rforged", "\0", ""])
def test_trailer_injection_rejected(value):
    with pytest.raises(ValueError, match="invalid integration trailer"):
        commit_trailers({**identity(), "task_key": value})


def test_missing_effect_is_not_inferred_from_message():
    inputs = identity()
    inputs.pop("effect_id")
    with pytest.raises(ValueError, match="effect_id"):
        commit_trailers(inputs)


def test_commit_plan_orders_outputs_without_mutating_accepted_facts():
    first = make_output(seq=1)
    second = replace(first, id=uuid4(), seq=2)
    supplied = (second, first)
    final = commit_plan(supplied, CommitMode.FINAL_ONLY)
    fixes = commit_plan(supplied, CommitMode.IMPLEMENTATION_AND_FIXES)
    assert commit_plan(supplied, CommitMode.PER_STAGE_ATTRIBUTED)["output_ids"] == fixes["output_ids"]
    assert final["output_ids"] == [str(second.id)]
    assert fixes["output_ids"] == [str(first.id), str(second.id)]
    assert supplied == (second, first)
    with pytest.raises(ValueError, match="one accepted attempt"):
        commit_plan((first, replace(second, attempt_id=uuid4())), CommitMode.FINAL_ONLY)


@pytest.mark.parametrize("strategy", list(IntegrationStrategy))
@pytest.mark.parametrize("mode", list(CommitMode))
def test_cross_key_mode_constraint(strategy, mode):
    if strategy == IntegrationStrategy.SQUASH and mode != CommitMode.FINAL_ONLY:
        with pytest.raises(SkmError) as caught:
            validate_mode(strategy, mode)
        assert caught.value.code.value == "CONFIG_INVALID"
    else:
        validate_mode(strategy, mode)


def test_excluded_paths_include_old_rename_path():
    import base64

    def encoded(value):
        return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")

    path = ChangedPath(
        "main",
        "renamed.txt",
        encoded("renamed.txt"),
        "renamed",
        ".skm/evidence",
        encoded(".skm/evidence"),
        "100644 " + "1" * 40,
    )
    assert excluded_paths((path,), (".skm/**",)) == (path,)
    assert excluded_paths((path,), ("other/**",)) == ()


def test_red_recheck_preserves_acceptance_and_blocks_done_until_owner_retry():
    from skm.modules.execution.domain.stage_record import StageOutcomeKind
    from skm.modules.execution.domain.workflow.actions import Escalate
    from unit.execution.domain.test_advance_table import decide, e, failed_check, integrating, receipt

    state = integrating(
        e("integrate", out={"integration_receipts": [receipt("b", "b")]}),
        e("recheck", StageOutcomeKind.CHECKS_FAILED),
        checks=(failed_check(),),
    )
    original = state.output
    decision = decide(state)
    assert isinstance(decision.action, Escalate)
    assert decision.action.code == "INTEGRATION_RECHECK_FAILED"
    assert decision.action.payload["options"] == ["retry_stage", "fail"]
    assert state.output is original


@pytest.mark.parametrize(
    ("urn", "payload"),
    [
        (
            "urn:skm:execution:result:acquire-integration-slot:v1",
            {"outcome": "waiting", "code": "SLOT_BUSY", "retry_after_seconds": 5},
        ),
        (
            "urn:skm:execution:stage-outcome-integrate:v1",
            {"outcome": "waiting", "error_code": "SLOT_BUSY", "retry_after_seconds": 5},
        ),
    ],
)
def test_waiting_wire_contracts_cannot_claim_success_or_slot_authority(urn, payload):
    from skm.platform.schema.registry import SchemaRegistry

    registry = SchemaRegistry.load_default()
    registry.require_valid(urn, payload)
    mixed = (
        {**payload, "slot_id": str(uuid4()), "fencing_token": 1, "expires_at": "2026-11-16T14:00:00Z"}
        if "result:acquire" in urn
        else {**payload, "commit_shas": ["1" * 40]}
    )
    assert registry.validate(urn, mixed)
