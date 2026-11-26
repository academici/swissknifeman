"""Planning commands, queries and authorization through each SkmClient transport."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import Any
from uuid import UUID

import pytest

from integration.artifacts.test_upload_flow import dispatch_new
from skm.application_bus.client import SkmClient
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.modules.access import public as access
from skm.modules.planning import public as planning
from skm.modules.planning.domain.canonical import document_bytes
from skm.modules.settings import public as settings
from support.backend import ClientBackend, client_backend
from support.pg import clean_test_database, pg_session, test_database

__all__ = ["clean_test_database", "client_backend", "pg_session", "test_database"]


def preview(client: SkmClient, plan_id: UUID, draft: Any) -> Any:
    return client.ask(planning.PreviewPublication(plan_id, draft.draft_id, draft.edit_version))


def publication(plan_id: UUID, draft: Any, candidate: Any) -> planning.PublishRevision:
    return planning.PublishRevision(
        plan_id, draft.draft_id, draft.edit_version, candidate.content_digest, "Publish verified candidate"
    )


def _create_after_lost_response(
    side: ClientBackend,
    owner: SkmClient,
    viewer: SkmClient,
) -> planning.CreatePlanResult:
    identity: Any = viewer.ask(access.WhoAmI())
    assert identity.principal.principal_id == side.seed.principals["viewer"]

    create = planning.CreatePlan(side.seed.project_id, "Client contract")
    key = "create-plan-response-lost"
    with side.lose_response(owner) as interrupted:
        interrupted.dispatch(create, idempotency_key=key)
    plans: Any = owner.ask(planning.ListPlans(side.seed.project_id))
    assert len(plans.items) == 1
    plan = owner.dispatch(create, idempotency_key=key)
    assert isinstance(plan, planning.CreatePlanResult)
    assert plan.plan_id == plans.items[0].plan_id
    with pytest.raises(SkmError) as denied:
        viewer.dispatch(create, idempotency_key=key)
    assert denied.value.code is ErrorCode.FORBIDDEN
    audits = side.audit_records("planning.create_plan")
    target = {"scope": {"kind": "project", "id": str(side.seed.project_id)}, "permission": "plan.create"}
    assert [(a.actor_id, a.workspace_id, a.decision, a.target) for a in audits] == [
        (side.seed.principals["owner"], side.seed.workspace_id, "allowed", target),
        (side.seed.principals["viewer"], side.seed.workspace_id, "denied", target),
    ]
    assert audits[0].reason_code is None
    assert audits[1].reason_code is not None
    assert audits[0].request_id != audits[1].request_id
    assert all(a.request_id != key for a in audits)
    with pytest.raises(SkmError) as foreign:
        side.client("foreign").ask(planning.GetPlan(plan.plan_id))
    assert foreign.value.code is ErrorCode.FORBIDDEN

    return plan


def test_planning_cas_audit_and_replay_after_commit(client_backend: ClientBackend) -> None:
    side = client_backend
    owner, viewer = side.client(), side.client("viewer")
    plan = _create_after_lost_response(side, owner, viewer)
    draft = dispatch_new(owner, planning.OpenDraft(plan.plan_id, base="empty"))
    saved = owner.dispatch(
        planning.SaveDraft(plan.plan_id, draft.draft_id, draft.edit_version, merge_patch={"goal": "Baseline"})
    )
    assert isinstance(saved, planning.SaveDraftResult)
    candidate = preview(owner, plan.plan_id, saved)
    assert candidate.publishable, candidate.validation
    baseline = dispatch_new(owner, publication(plan.plan_id, saved, candidate))

    draft = dispatch_new(owner, planning.OpenDraft(plan.plan_id, base="current"))
    start = Barrier(2, timeout=10)
    clients = (owner, side.client())

    def save(index: int) -> tuple[str, int | ErrorCode]:
        goal = f"Concurrent goal {index}"
        command = planning.SaveDraft(
            plan.plan_id, draft.draft_id, draft.edit_version, merge_patch={"goal": goal}
        )
        start.wait()
        try:
            result = clients[index].dispatch(command)
        except SkmError as error:
            return goal, error.code
        assert isinstance(result, planning.SaveDraftResult)
        return goal, result.edit_version

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = dict(pool.map(save, range(2)))
    assert set(outcomes.values()) == {draft.edit_version + 1, ErrorCode.VERSION_CONFLICT}
    winning_goal = next(goal for goal, outcome in outcomes.items() if outcome == draft.edit_version + 1)
    current_draft: Any = owner.ask(planning.GetDraft(plan.plan_id, draft.draft_id))
    assert current_draft.document["goal"] == winning_goal
    candidate = preview(owner, plan.plan_id, current_draft)
    revision = dispatch_new(owner, publication(plan.plan_id, current_draft, candidate))

    head: Any = viewer.ask(planning.GetPlan(plan.plan_id))
    assert head.current_revision_id == revision.revision_id
    current: Any = viewer.ask(
        planning.GetRevision(plan.plan_id, revision_id=head.current_revision_id, include_document=True)
    )
    assert (current.revision_id, current.parent_revision_id, current.document["goal"]) == (
        revision.revision_id,
        baseline.revision_id,
        winning_goal,
    )
    page: Any = viewer.ask(planning.ListRevisions(plan.plan_id))
    assert [row.revision_id for row in page.items] == [revision.revision_id, baseline.revision_id]
    diff: Any = viewer.ask(planning.DiffRevisions(plan.plan_id, to_revision_id=revision.revision_id))
    assert diff.to_json()["from"]["revision_id"] == str(baseline.revision_id)
    assert diff.to_json()["to"]["id"] == str(revision.revision_id)


def test_draft_document_limit_is_a_domain_precondition(client_backend: ClientBackend) -> None:
    owner = client_backend.client()
    limit = 65536
    owner.dispatch(
        settings.SetValue.from_json(
            {
                "scope": {"level": "instance"},
                "key": "planning.drafts.max_document_bytes",
                "value": limit,
                "expected_row_version": 0,
                "reason": "Contract size boundary",
            }
        )
    )
    plan = dispatch_new(owner, planning.CreatePlan(client_backend.seed.project_id, "Draft sizing"))
    draft = dispatch_new(owner, planning.OpenDraft(plan.plan_id, base="empty"))
    snapshot: Any = owner.ask(planning.GetDraft(plan.plan_id, draft.draft_id))
    document = dict(snapshot.document)
    document["rules"] = ["x" * 18000] * 3 + ["x"]
    overhead = document_bytes(document)
    document["rules"][-1] += "x" * (limit - overhead)
    assert document_bytes(document) == limit
    save = planning.SaveDraft.from_json(
        {
            "plan_id": str(plan.plan_id),
            "draft_id": str(draft.draft_id),
            "expected_edit_version": draft.edit_version,
            "document": document,
        }
    )
    saved: Any = owner.dispatch(save)
    assert saved.edit_version == draft.edit_version + 1
    document["rules"][-1] += "x"
    oversized = planning.SaveDraft.from_json(
        {
            **save.to_json(),
            "expected_edit_version": saved.edit_version,
            "document": document,
        }
    )
    with pytest.raises(SkmError) as caught:
        owner.dispatch(oversized)
    assert caught.value.code is ErrorCode.SCHEMA_INVALID
    persisted: Any = owner.ask(planning.GetDraft(plan.plan_id, draft.draft_id))
    assert persisted.edit_version == saved.edit_version
    assert persisted.document_digest == saved.document_digest
