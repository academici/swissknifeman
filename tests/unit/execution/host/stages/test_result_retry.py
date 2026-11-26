"""K15 and SE8r: real subprocess output, bounded hints and the single session decision table."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from typing import Any

import pytest

from integration.worker._support import build_draft
from integration.worker.test_worker_loop import documents
from skm.bootstrap.host_services import worker_schema_issues
from skm.modules.execution.domain.repair import result_retry_allowed, schema_error_hint
from skm.modules.execution.domain.session import Fresh, Resume, decide_session
from skm.modules.execution.domain.stage_record import StageOutcomeKind
from skm.modules.execution.domain.step import RoleId, StepState
from skm.modules.execution.domain.workflow.stage_inputs import StageMode
from skm.modules.execution.host.context import WorkerServices
from skm.modules.execution.host.worker_loop import run
from skm.modules.runtimes.public import ResumeAllowance
from unit.execution.domain.test_session import facts, fingerprint, make_step
from unit.execution.host.stages.test_roles import exercise


@pytest.mark.parametrize("role", list(documents()))
@pytest.mark.parametrize("text", ["not a result", '```json\n{"a":1}\n```\n```json\n{"b":2}\n```'])
def test_missing_or_ambiguous_final_text_is_invalid_for_every_role(
    tmp_path: Any, monkeypatch: Any, role: str, text: str
) -> None:
    fixture = exercise(tmp_path, monkeypatch, role, documents()[role])
    scenario = tmp_path / f"{role}.toml"
    scenario.write_text('scenario = "success"\n[result]\ntext = ' + json.dumps(text) + "\n")
    run(fixture.ctx, fixture.request)
    outcome = fixture.outcomes[0]
    assert outcome.kind is StageOutcomeKind.RESULT_INVALID
    errors = json.loads(outcome.payload["detail"])["schema_errors"]
    assert errors[0]["path"] == ""
    assert errors[0]["message"] == (
        "no result document" if text == "not a result" else "several different result documents"
    )
    assert outcome.files[0].path.read_text() == text
    schema = "agent-review" if role == "reviewer" else "agent-step"
    assert not worker_schema_issues(f"urn:skm:execution:stage-outcome-{schema}:v1", dict(outcome.payload))


def test_unhealable_executor_keeps_errors_evidence_and_session(tmp_path: Any, monkeypatch: Any) -> None:
    doc = {
        **documents()["executor"],
        "checks_run": [42],
        "status": "blocked",
        "open_issues": [{"kind": "blocker", "text": "Unresolved"}],
    }
    fixture = exercise(tmp_path, monkeypatch, "executor", doc)
    run(fixture.ctx, fixture.request)
    outcome = fixture.outcomes[0]
    assert outcome.kind is StageOutcomeKind.RESULT_INVALID
    assert "role_result" not in outcome.payload
    assert "session_ref" in outcome.payload
    errors = json.loads(outcome.payload["detail"])["schema_errors"]
    assert 0 < len(errors) <= 20
    assert all(len(row["message"]) <= 300 and len(row["expected"]) <= 200 for row in errors)
    assert [row["path"] for row in errors] == sorted(row["path"] for row in errors)
    assert json.loads(outcome.files[0].path.read_text()) == doc
    assert "return the whole result" in schema_error_hint(errors)


def test_healable_report_preserves_raw_and_records_single_repair(tmp_path: Any, monkeypatch: Any) -> None:
    doc = {**documents()["executor"], "status": "Done "}
    fixture = exercise(tmp_path, monkeypatch, "executor", doc)
    run(fixture.ctx, fixture.request)
    outcome = fixture.outcomes[0]
    assert outcome.kind is StageOutcomeKind.SUCCESS
    assert outcome.payload["role_result"]["status"] == "done"
    assert len(outcome.payload["repairs"]) == len(set(outcome.payload["repairs"])) > 0
    assert json.loads(outcome.files[0].path.read_text())["status"] == "Done "


@pytest.mark.parametrize("role", list(documents()))
@pytest.mark.parametrize(("allowed", "ref"), [(True, "same-session"), (False, "same-session"), (True, None)])
def test_same_role_retry_resumes_only_with_allowance_and_ref(
    role: str, allowed: bool, ref: str | None
) -> None:
    fp = fingerprint(role=RoleId(role))
    previous = make_step(
        role=RoleId(role),
        session_fingerprint=fp,
        session_ref=ref,
        state=StepState.FAILED,
        error_code="RESULT_INVALID",
    )
    decision = decide_session(
        fp,
        facts(
            previous=previous,
            stage_mode=StageMode.RETRY,
            retry_of_previous_stage=True,
            previous_error_code="RESULT_INVALID",
            admission_allows_resume=ResumeAllowance(
                allowed, False, ref, "allowed" if allowed else "resume_disabled"
            ),
        ),
    )
    assert isinstance(decision, Resume if allowed and ref else Fresh)
    if isinstance(decision, Resume):
        assert decision.session_ref == ref
    else:
        assert decision.reason == ("ADMISSION_NO_RESUME" if not allowed else "NO_PREVIOUS_SESSION")
    assert result_retry_allowed(0, 1)
    assert not result_retry_allowed(1, 1)


@pytest.mark.parametrize("mutation", ["authority", "route", "scope", "runtime_error"])
def test_result_retry_never_bypasses_other_resume_guards(mutation: str) -> None:
    fp = fingerprint()
    previous = make_step(state=StepState.FAILED, error_code="RESULT_INVALID")
    if mutation == "authority":
        fp = replace(fp, authority_digest="sha256:" + "f" * 64)
    elif mutation == "scope":
        fp = replace(fp, instruction_digest="sha256:" + "f" * 64)
    elif mutation == "route":
        fp = replace(fp, runtime_id="other")
    decision = decide_session(
        fp,
        facts(
            previous=previous,
            stage_mode=StageMode.RETRY,
            retry_of_previous_stage=True,
            previous_error_code="RUNTIME_ERROR" if mutation == "runtime_error" else "RESULT_INVALID",
        ),
    )
    assert isinstance(decision, Fresh)


@pytest.mark.parametrize(("allowed", "has_ref"), [(True, True), (False, True), (True, False)])
def test_two_real_invocations_carry_hint_and_respect_unsupported_resume(
    tmp_path: Any,
    monkeypatch: Any,
    allowed: bool,
    has_ref: bool,
) -> None:
    first_path, second_path = tmp_path / "first", tmp_path / "second"
    first_path.mkdir()
    second_path.mkdir()
    bad = {**documents()["executor"], "checks_run": [42]}
    first = exercise(first_path, monkeypatch, "executor", bad)
    scenario = first_path / "executor.toml"
    if has_ref:
        scenario.write_text(
            scenario.read_text().replace(
                "[result]",
                '[[step]]\naction = "emit"\n'
                'event = {type = "session_started", session_ref = "same-session", model = "fake-model"}\n'
                "[result]",
            )
        )
    run(first.ctx, first.request)
    invalid = first.outcomes[0]
    assert invalid.kind is StageOutcomeKind.RESULT_INVALID
    errors = json.loads(invalid.payload["detail"])["schema_errors"]
    ref = invalid.payload["session_ref"]
    assert ref == ("same-session" if has_ref else None)
    fp = fingerprint()
    decision = decide_session(
        fp,
        facts(
            previous=make_step(session_ref=ref, state=StepState.FAILED, error_code="RESULT_INVALID"),
            runtime_supports_resume=False,  # the real synthetic adapter explicitly refuses session resume
            stage_mode=StageMode.RETRY,
            retry_of_previous_stage=True,
            previous_error_code="RESULT_INVALID",
            admission_allows_resume=ResumeAllowance(
                allowed, False, ref, "allowed" if allowed else "resume_disabled"
            ),
        ),
    )
    hint = schema_error_hint(errors)
    second = exercise(second_path, monkeypatch, "executor", documents()["executor"])
    inputs = second.services.context_inputs
    draft = build_draft(
        {
            "manifest_id": second.ids["stage"],
            "blocks": [
                {
                    "ordinal": 0,
                    "block_type": "result_contract",
                    "budget_class": "core",
                    "mandatory": True,
                    "source_kind": "derived",
                    "source_ref": "step:previous",
                    "trust": "system",
                    "atomic_group": None,
                    "source_version": None,
                    "content": hint,
                    "content_digest": "sha256:" + hashlib.sha256(hint.encode()).hexdigest(),
                    "tokens_estimate": len(hint),
                    "reason": "mandatory",
                }
            ],
        }
    )
    build = second.services.runtime_request

    def retry_request(request: Any, deps: Any) -> Any:
        return replace(
            build(request, deps),
            resume_session_ref=decision.session_ref if isinstance(decision, Resume) else None,
            session_policy="persistent",
        )

    second.services = replace(
        second.services, context_inputs=replace(inputs, decode=lambda _: draft), runtime_request=retry_request
    )
    second.entries[WorkerServices] = second.services
    second.client.response["instruction"]["mode"] = "retry"
    run(second.ctx, second.request)
    request, _ = second.requests[0]
    assert request.runtime_request.role.value == "executor"
    assert hint in request.context.rendered_prompt
    assert isinstance(decision, Fresh)
    assert request.runtime_request.resume_session_ref is None
    assert second.outcomes, second.failures
    assert second.outcomes[0].kind is StageOutcomeKind.SUCCESS
    assert json.loads(invalid.files[0].path.read_text()) == bad


def test_json_text_without_native_terminal_never_becomes_a_role_result(
    tmp_path: Any, monkeypatch: Any
) -> None:
    fixture = exercise(tmp_path, monkeypatch, "executor", documents()["executor"])
    scenario = tmp_path / "executor.toml"
    scenario.write_text(
        'scenario = "success"\n[[step]]\naction = "emit"\nevent = {type = "text_delta", text = '
        + json.dumps(json.dumps(documents()["executor"]))
        + "}\n"
    )
    run(fixture.ctx, fixture.request)
    assert fixture.outcomes[0].kind is StageOutcomeKind.RUNTIME_ERROR
    assert "role_result" not in fixture.outcomes[0].payload
