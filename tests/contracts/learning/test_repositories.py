"""Learning intake and signal history through both real adapters."""

from dataclasses import replace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

from contracts.knowledge.harness import KnowledgeSide, knowledge_side
from integration.artifacts.test_upload_flow import dispatch_new
from skm.kernel.actor import SYSTEM_PRINCIPAL_ID, Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, SkmError, ValidationFailed
from skm.kernel.ids import ProjectId, ScopeId, WorkspaceId
from skm.modules.learning import public as learning
from skm.modules.learning.application.commands.extract_candidates import ActivityStorage
from skm.modules.learning.domain.activity import ActivityRecordId
from skm.modules.learning.domain.candidate import CandidateId
from skm.modules.learning.domain.detectors import replay_detector_evidence
from skm.modules.learning.ports import ActivityRecordRepository, CandidateRepository, SignalRepository
from skm.modules.settings.generated.commands import SetValue
from skm.modules.workspace.public import CreateWorkspace
from support.pg import clean_test_database, pg_session, test_database

__all__ = ["clean_test_database", "knowledge_side", "pg_session", "test_database"]


def session(side: KnowledgeSide, key: str, **extras: Any) -> dict[str, Any]:
    return {
        "schema": "urn:skm:learning:activity-summary:v1",
        "source_kind": "client_session",
        "source_key": f"claude_code:{key}",
        "outcome": "unknown",
        "observed_at": side.clock.now().isoformat(),
        "workarounds": ["Use a local cache for connectivity checks"],
        **extras,
    }


def record(side: KnowledgeSide, summary: dict[str, Any], project: ProjectId | None = None) -> Any:
    return side.app.bus.dispatch(
        learning.RecordActivity.from_json({"project_id": str(project or side.project), "summary": summary}),
        actor=side.owner,
        meta=side.meta(),
    )


def ask(side: KnowledgeSide, model: Any, **data: Any) -> Any:
    return side.app.bus.ask(model.from_json(data), actor=side.owner, meta=side.meta())


def test_client_activity_and_retained_detectors(knowledge_side: KnowledgeSide) -> None:
    side = knowledge_side
    summary = session(side, "session-1")
    first, second, third = [record(side, summary) for _ in range(3)]
    assert first["observations"] == 1
    assert second == third == {"activity_record_id": first["activity_record_id"], "observations": 0}
    project = side.new_project("other")
    with pytest.raises(NotFound):
        record(side, summary, project=project)
    scope = {"workspace_id": str(side.workspace)}
    page = ask(side, learning.ListCandidates, **scope, states=["observed"], project_id=str(side.project))
    (item,) = page["items"]
    assert item["display_key"] == "LC-1"
    path = {**scope, "candidate_id": item["candidate_id"]}
    detail = ask(side, learning.GetCandidate, **path)
    assert detail["n_total"] == detail["unknown_outcome_total"] == detail["exposure_unknown_total"] == 1
    assert detail["independent_known_total"] == detail["confidence"] == 0
    (signal,) = ask(side, learning.ListSignals, **path)["items"]
    assert signal["evidence_dependency"] == "unknown"
    assert signal["sessions_known"] == signal["sessions_success"] == 0
    assert signal["activity"]["source_key"] == summary["source_key"]
    with side.uow(readonly=True) as uow:
        repo = cast("ActivityStorage", uow.repo(ActivityRecordRepository))
        row = repo.get(ActivityRecordId(UUID(first["activity_record_id"])))
        evidence = next(
            bundle for bundle in row.detector_evidence if bundle.detector_version == "workaround:v1"
        )
        assert replay_detector_evidence(evidence).decision == "fired"
        assert repo.count_for_project(side.project) == 1
    assert ask(side, learning.PathologyStats, project_id=str(side.project))["records"] == 1


@pytest.mark.parametrize(
    "extras",
    [
        {"outcome": "success"},
        {"task_outcome": "success"},
        {"exposure_coverage": "complete"},
    ],
)
def test_client_cannot_forge_provenance(knowledge_side: KnowledgeSide, extras: dict[str, str]) -> None:
    side = knowledge_side
    with pytest.raises(ValidationFailed) as failure:
        record(side, session(side, "forged", **extras))
    assert failure.value.code is ErrorCode.SCHEMA_INVALID
    with side.uow(readonly=True) as uow:
        assert uow.repo(ActivityRecordRepository).count_for_project(side.project) == 0


def test_scoped_queries_and_durable_append_only_proposals(knowledge_side: KnowledgeSide) -> None:
    side = knowledge_side
    record(side, session(side, "one", workarounds=["restart service after checks finish"]))
    record(side, session(side, "two", workarounds=["restart service before checks finish"]))
    foreign = WorkspaceId(
        dispatch_new(
            side.app.client(actor=side.owner, surface=side.meta().surface),
            CreateWorkspace(slug="foreign-learning", title="Foreign"),
        ).workspace_id
    )
    with pytest.raises(NotFound):
        ask(side, learning.ListCandidates, workspace_id=str(foreign), project_id=str(side.project))
    page = ask(side, learning.ListCandidates, workspace_id=str(side.workspace), states=["observed"], limit=1)
    assert page["has_more"]
    assert page["next_cursor"]
    nxt = ask(
        side,
        learning.ListCandidates,
        workspace_id=str(side.workspace),
        states=["observed"],
        limit=1,
        after=page["next_cursor"],
    )
    assert not nxt["has_more"]
    path = {"workspace_id": str(side.workspace), "candidate_id": nxt["items"][0]["candidate_id"]}
    detail = ask(side, learning.GetCandidate, **path)
    with pytest.raises(NotFound):
        ask(side, learning.GetCandidate, **{**path, "workspace_id": str(foreign)})
    assert len(detail["proposals"]) == 1
    assert detail["n_total"] == 1
    assert detail["proposals"][0]["relation"] == "update"


def test_exposed_observations_never_open_independent_gate(knowledge_side: KnowledgeSide) -> None:
    side = knowledge_side
    actor = Actor(SYSTEM_PRINCIPAL_ID, PrincipalKind.SERVICE, "system")
    for index in range(10):
        attempt = str(uuid4())
        refs = [{"id": str(UUID(int=23)), "version": "v1", "content_digest": "sha256:" + "a" * 64}]
        summary = session(
            side,
            attempt,
            source_kind="attempt",
            source_key=attempt,
            outcome="success",
            exposure_coverage="complete",
            exposed_lesson_refs=refs,
        )
        command = learning.ExtractCandidates.from_json(
            {
                "project_id": str(side.project),
                "run_id": str(uuid4()),
                "task_id": str(uuid4()),
                "attempt_id": attempt,
                "summary": summary,
            }
        )
        result = cast("dict[str, Any]", side.app.bus.dispatch(command, actor=actor, meta=side.meta()))
        assert len(result["signaled"]) == 1
        cid = CandidateId(UUID(result["signaled"][0]))
        assert index == 0 or result["created"] == []
    with side.uow(readonly=True) as uow:
        candidate = uow.repo(CandidateRepository).get(cid)
        signals = uow.repo(SignalRepository).for_candidate(cid)
        assert all(signal.evidence_dependency == "exposed" for signal in signals)
        assert candidate.known_outcome_total == candidate.exposed_total == 10
        assert candidate.independent_known_total == candidate.independent_success_total == 0
        assert not candidate.curated_ready


def test_adapter_rejects_bad_candidate_counters(knowledge_side: KnowledgeSide) -> None:
    side = knowledge_side
    record(side, session(side, "one"))
    with side.uow(readonly=True) as uow:
        (row,) = (
            uow.repo(CandidateRepository)
            .list((ScopeId(side.project),), states=frozenset(), after=None, limit=3)
            .items
        )
    with side.uow() as uow, pytest.raises(SkmError) as failure:
        uow.repo(CandidateRepository).save(replace(row, n_total=20), expected_version=row.row_version)
    assert failure.value.code is ErrorCode.SCHEMA_INVALID


@pytest.mark.parametrize(
    ("count", "padding", "valid"), [(1486, 10, True), (1486, 11, False), (2200, 0, False)]
)
def test_candidate_meta_uses_jsonb_text_byte_limit(
    knowledge_side: KnowledgeSide, count: int, padding: int, valid: bool
) -> None:
    side = knowledge_side
    record(side, session(side, "meta-boundary"))
    with side.uow() as uow:
        candidates = uow.repo(CandidateRepository)
        (row,) = candidates.list((ScopeId(side.project),), states=frozenset(), after=None, limit=1).items
        # jsonb renders each exponent as 0.0000001. The first two cases use 16,383 and 16,384 bytes.
        updated = replace(row, meta={"values": [1e-7] * count, "padding": "x" * padding})
        if valid:
            candidates.save(updated, expected_version=row.row_version)
            assert candidates.get(row.id).meta == updated.meta
        else:
            with pytest.raises(SkmError) as failure:
                candidates.save(updated, expected_version=row.row_version)
            assert failure.value.code is ErrorCode.SCHEMA_INVALID


def test_workspace_recompute_and_candidate_gates_use_project_thresholds(
    knowledge_side: KnowledgeSide,
) -> None:
    side = knowledge_side
    attempt = str(uuid4())
    check = {"command": None, "origin": "check_execution", "check_key": "unit-tests"}
    summary = session(
        side,
        attempt,
        source_key=attempt,
        source_kind="attempt",
        outcome="success",
        exposure_coverage="complete",
        exposed_lesson_refs=[],
        checks=[{**check, "ok": False}, {**check, "ok": True}],
        workarounds=[],
    )
    command = learning.ExtractCandidates.from_json(
        {
            "project_id": str(side.project),
            "run_id": str(uuid4()),
            "task_id": str(uuid4()),
            "attempt_id": attempt,
            "summary": summary,
        }
    )
    actor = Actor(SYSTEM_PRINCIPAL_ID, PrincipalKind.SERVICE, "system")
    extracted = cast("dict[str, Any]", side.app.bus.dispatch(command, actor=actor, meta=side.meta()))
    (candidate_id,) = extracted["created"]
    workspace = {"workspace_id": str(side.workspace)}
    path = {**workspace, "candidate_id": candidate_id}
    assert ask(side, learning.GetCandidate, **path)["state"] == "observed"
    client = side.app.client(actor=side.owner, surface=side.meta().surface)
    for name, value in {"deprecate_conf": 0, "candidate_min_conf": 0.01, "candidate_min_n_floor": 1}.items():
        dispatch_new(
            client,
            SetValue.from_json(
                {
                    "scope": {"level": "project", "scope_id": str(side.project)},
                    "key": f"learning.thresholds.{name}",
                    "value": value,
                }
            ),
        )
    gate = ask(side, learning.GetCandidate, **path)["gates"]["candidate"]
    assert gate["support_min"] == 0.01
    assert gate["adaptive_min_n"] == 1
    result = dispatch_new(client, learning.RecomputeConfidence.from_json(workspace))
    assert result["transitions"]["to_candidate"] == 1
    assert ask(side, learning.GetCandidate, **path)["state"] == "candidate"


def test_background_recompute_and_promotion_preserve_empirical_signals(knowledge_side: KnowledgeSide) -> None:
    from skm.bootstrap.lifecycle import add_background_services
    from skm.modules.learning.ports import CandidateReviewRepository

    side = knowledge_side
    record(side, session(side, "promotion"))
    (item,) = ask(side, learning.ListCandidates, workspace_id=str(side.workspace), states=["observed"])[
        "items"
    ]
    candidate_id = CandidateId(UUID(item["candidate_id"]))
    with side.uow(readonly=True) as uow:
        before = uow.repo(SignalRepository).for_candidate(candidate_id)

    app = add_background_services(side.app)
    service = next(service for service in app.services if service.name == "learning_recompute")
    service.tick()
    path = {"workspace_id": str(side.workspace), "candidate_id": str(candidate_id)}
    detail = ask(side, learning.GetCandidate, **path)
    promoted = cast(
        "dict[str, Any]",
        side.app.bus.dispatch(
            learning.PromoteCandidate.from_json(
                {
                    **path,
                    "expected_row_version": detail["row_version"],
                    "override_low_confidence": True,
                    "override_reason": "Verified manually on staging",
                }
            ),
            actor=side.owner,
            meta=side.meta("learning-test-promote"),
        ),
    )
    with side.uow(readonly=True) as uow:
        row = uow.repo(CandidateRepository).get(candidate_id)
        assert str(row.lesson_id) == promoted["lesson_id"]
        assert row.review_status == "approved"
        assert uow.repo(SignalRepository).for_candidate(candidate_id) == before
        assert len(uow.repo(CandidateReviewRepository).for_candidate(candidate_id)) == 1
