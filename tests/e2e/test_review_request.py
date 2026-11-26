"""P09.10: transactional review requests through the real bus and both stores."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest

from contracts.context.harness import _profile_toml, core_pack
from contracts.execution.conftest import clean_test_database as clean_test_database
from contracts.execution.conftest import pg_session as pg_session
from contracts.execution.conftest import test_database as test_database
from contracts.execution.harness import exec_side as exec_side
from contracts.extensions.harness import pack_payload
from e2e.test_execution_cli import invoke
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.ids import RunId
from skm.modules.execution.application.commands.request_review import RequestReview
from skm.modules.execution.application.queries.get_review_receipt import GetReviewReceipt
from skm.modules.execution.domain.budget import BudgetDimension
from skm.modules.execution.domain.review_request import ReviewReceipt
from skm.modules.execution.domain.run import RunKind
from skm.modules.execution.ports import (
    BudgetRepository,
    BundleRepository,
    ReviewRequestRepository,
    RunRepository,
    TaskRepository,
)
from skm.modules.extensions.generated.commands import SyncBuiltinPacks
from skm.modules.extensions.ports import BuiltinPacks
from skm.modules.planning import public as planning
from skm.modules.planning.generated.queries import ListPlans

pytestmark = pytest.mark.e2e
ROOT = Path(__file__).resolve().parents[2]
BASE, HEAD = "1" * 40, "2" * 40


@pytest.fixture
def review_side(exec_side: Any):
    side = exec_side
    payload = core_pack("1.1.0")
    files = {f.path: f.content.decode() for f in payload.files}
    files["workflows/review-only.toml"] = (
        ROOT / "resources/packs/core/workflows/review-only.toml"
    ).read_text()
    for role in ("reviewer", "triager"):
        files[f"agent-profiles/{role}.toml"] = _profile_toml(role, "1.1.0")
    files["agent-profiles/security.toml"] = _profile_toml("reviewer", "1.1.0").replace(
        'key = "reviewer"', 'key = "security"'
    )
    side.app.gateways.get(BuiltinPacks).current = (pack_payload("core", "1.1.0", files=files),)
    side.client.dispatch(SyncBuiltinPacks())
    return side


def command(side: Any, **values: Any) -> RequestReview:
    return RequestReview(
        project_id=str(side.proj),
        mount="repo",
        target={"kind": "commits", "base_commit": BASE, "head_commit": HEAD},
        reason="Owner requested range review",
        **values,
    )


def request(side: Any, cmd: Any = None, *, key: str | None = None) -> Any:
    return side.client.dispatch(
        cmd or command(side), idempotency_key=key or side.client.new_idempotency_key()
    )


def test_atomic_service_revision_run_and_required_idempotency(review_side: Any) -> None:
    side = review_side
    key = side.client.new_idempotency_key()
    with pytest.raises(SkmError):
        side.client.dispatch(command(side))
    result = request(side, key=key)
    assert request(side, key=key) == result
    with side.uow(readonly=True) as uow:
        run = uow.repo(RunRepository).get(UUID(result["run_id"]))
        req = uow.repo(ReviewRequestRepository).for_run(run.id)
        assert req is not None
        assert run.kind is RunKind.REVIEW_REQUEST
        assert run.review_request_id == req.id
        assert run.readiness_report_id is None
        assert not run.autopilot
        assert run.revision_id == req.revision_id
        assert req.target_digest.startswith("sha256:")
        plan = planning.get_plan_ref(uow, run.plan_id)
        assert plan.purpose.value == "review_requests"
        assert plan.alias == "review-requests"
        tasks = uow.repo(TaskRepository).list_for_run(run.id)
        assert len(tasks) == 1
        assert not tasks[0].declared_write_scope
        assert tasks[0].review_profile == "reviewer"
        bundle = uow.repo(BundleRepository).get(run.id)
        assert next(p for p in bundle.resource_pins.resources if p.kind == "workflow").key == "review-only"
        assert uow.repo(BudgetRepository).accounts_for(run.id, None, BudgetDimension.USD)
    listed = side.client.ask(ListPlans(project_id=side.proj))
    assert all(str(row.plan_id) != str(run.plan_id) for row in listed.items)
    receipt = side.client.ask(GetReviewReceipt(run_id=result["run_id"]))
    assert receipt.request_id == UUID(result["request_id"])
    assert receipt == side.client.ask(GetReviewReceipt(request_id=result["request_id"]))
    assert receipt == side.client.ask(
        GetReviewReceipt(project_id=str(side.proj), mount="repo", tree_digest="sha256:" + "f" * 64)
    )
    code, out, err = invoke(side, "review", "show", result["run_id"])
    assert code == 0, (out, err)


def test_rejects_mutable_commits_mount_and_permissions(review_side: Any) -> None:
    side = review_side
    for mutation, code in (
        ({"mount": "missing"}, ErrorCode.NOT_FOUND),
        (
            {"target": {"kind": "commits", "base_commit": "main", "head_commit": "HEAD"}},
            ErrorCode.SCHEMA_INVALID,
        ),
    ):
        cmd = command(side)
        cmd.update(mutation)
        with pytest.raises(SkmError) as caught:
            request(side, cmd)
        assert caught.value.code is code
    restricted = side.restricted_client(["run.read"], scope_id=side.proj)
    with pytest.raises(SkmError) as caught:
        restricted.dispatch(command(side), idempotency_key=restricted.new_idempotency_key())
    assert caught.value.code is ErrorCode.FORBIDDEN
    result = request(side)
    restricted = side.restricted_client(["run.start"], scope_id=side.proj, owner_token=True)
    with pytest.raises(SkmError) as caught:
        restricted.ask(GetReviewReceipt(run_id=result["run_id"]))
    assert caught.value.code is ErrorCode.FORBIDDEN


def test_receipt_freshness_tracks_exact_tree() -> None:
    receipt = ReviewReceipt(
        UUID(int=1), UUID(int=2), "succeeded", "green", (), UUID(int=3), "sha256:" + "a" * 64, BASE, HEAD
    )
    assert receipt.fresh_for("sha256:" + "a" * 64)
    assert not receipt.fresh_for("sha256:" + "b" * 64)
    assert replace(receipt, head_commit="3" * 40).fresh_for(receipt.tree_digest)


def test_emergency_stop_and_archived_project_are_rejected(review_side: Any) -> None:
    from skm.modules.execution.domain.autopilot import AutopilotState, AutopilotStateKind
    from skm.modules.execution.ports import AutopilotRepository
    from skm.modules.workspace.public import ArchiveProject

    side = review_side
    with side.uow() as uow:
        uow.repo(AutopilotRepository).save(
            AutopilotState(
                side.proj,
                side.ws,
                AutopilotStateKind.STOPPED,
                True,
                None,
                None,
                {},
                {},
                "AUTOPILOT_EMERGENCY_STOP",
                "Owner stop",
                side.owner.principal_id,
                side.clock.now(),
                1,
            ),
            expected_version=None,
        )
        uow.commit()
    with pytest.raises(SkmError) as caught:
        request(side)
    assert caught.value.code is ErrorCode.EMERGENCY_STOPPED
    side.client.dispatch(
        ArchiveProject(project_id=side.proj, expected_row_version=1, reason="Archived by owner")
    )
    with pytest.raises(SkmError) as caught:
        request(side)
    assert caught.value.code is ErrorCode.PROJECT_ARCHIVED


def test_patch_must_be_ready_in_the_project_workspace(review_side: Any) -> None:
    from skm.modules.artifacts import public as artifacts

    side = review_side
    cmd = command(side)
    cmd["target"] = {"kind": "working_tree", "base_commit": BASE, "patch_file_version_id": str(side.fv1)}
    result = request(side, cmd)
    assert result["request_id"]
    from contracts.execution.seed_helpers import seed_attempt, seed_output

    with side.uow() as uow:
        rid = UUID(result["run_id"])
        task = uow.repo(TaskRepository).list_for_run(rid)[0]
        attempt = seed_attempt(side, uow, RunId(rid), task.id)
        output = seed_output(side, uow, attempt)
        uow.commit()
    receipt = side.client.ask(GetReviewReceipt(run_id=result["run_id"]))
    assert receipt.head_commit == output.manifest.mounts[0].head_commit
    assert receipt.head_commit != BASE
    with side.uow(readonly=True) as uow:
        fid = artifacts.file_id_of_version(uow, side.ws, side.fv1)
    side.client.dispatch(
        artifacts.TrashFile(
            file_id=fid,
            expected_row_version=side.client.ask(artifacts.GetFile(file_id=fid)).row_version,
            reason="Unavailable patch",
        )
    )
    with pytest.raises(SkmError) as caught:
        request(side, cmd)
    assert caught.value.code is ErrorCode.FILE_VERSION_NOT_READY
    cmd["project_id"] = str(side.proj2)
    with pytest.raises(SkmError) as caught:
        request(side, cmd)
    assert caught.value.code is ErrorCode.NOT_FOUND


def test_newest_matching_receipt_precedes_newest_stale(review_side: Any) -> None:
    from contracts.execution.seed_helpers import DIGEST_A, DIGEST_B, seed_attempt, seed_output
    from skm.modules.execution.domain.output import manifest_digest
    from skm.modules.execution.domain.review import Freshness, Review, ReviewerKind, ReviewState, Verdict
    from skm.modules.execution.ports import ExecutionQueries, OutputRepository, ReviewRepository

    side = review_side
    old, new = request(side), request(side)
    with side.uow() as uow:
        for index, result in enumerate((old, new)):
            run = uow.repo(RunRepository).get(UUID(result["run_id"]))
            task = uow.repo(TaskRepository).list_for_run(run.id)[0]
            attempt = seed_attempt(side, uow, run.id, task.id)
            out = seed_output(side, uow, attempt)
            if not index:
                pins = uow.repo(BundleRepository).get(run.id).resource_pins.resources
                profile = next(p for p in pins if p.kind == "agent_profile" and p.key == "reviewer")
                uow.repo(ReviewRepository).add(
                    Review(
                        side.new_id(),
                        side.ws,
                        run.id,
                        task.id,
                        attempt.id,
                        out.id,
                        1,
                        ReviewerKind.HUMAN,
                        {"principal_id": str(side.owner.principal_id)},
                        "reviewer",
                        profile.resource_version_id,
                        "range",
                        ReviewState.COMPLETED,
                        Verdict.GREEN,
                        Freshness.FRESH,
                        None,
                        "",
                        side.clock.now(),
                    )
                )
            manifest = replace(out.manifest, tree_digest=DIGEST_B)
            uow.repo(OutputRepository).add(
                replace(
                    out,
                    id=side.new_id(),
                    seq=2,
                    manifest=manifest,
                    manifest_digest=manifest_digest(manifest),
                )
            )
        assert uow.repo(ExecutionQueries).latest_run_id(side.proj) is None
        uow.commit()
    exact = side.client.ask(GetReviewReceipt(project_id=str(side.proj), mount="repo", tree_digest=DIGEST_A))
    assert str(exact.run_id) == old["run_id"]
    assert exact.fresh_for(DIGEST_A)
    assert exact.verdict == "green"
    newest = side.client.ask(GetReviewReceipt(project_id=str(side.proj), mount="repo", tree_digest=DIGEST_B))
    assert str(newest.run_id) == new["run_id"]
    stale = side.client.ask(
        GetReviewReceipt(project_id=str(side.proj), mount="repo", tree_digest="sha256:" + "f" * 64)
    )
    assert str(stale.run_id) == new["run_id"]
    assert not stale.fresh_for("sha256:" + "f" * 64)
    for payload in ({}, {"run_id": old["run_id"], "request_id": old["request_id"]}):
        with pytest.raises(SkmError) as caught:
            side.client.ask(GetReviewReceipt(payload))
        assert caught.value.code is ErrorCode.SCHEMA_INVALID
    with pytest.raises(SkmError) as caught:
        side.client.ask(GetReviewReceipt(project_id=str(side.proj), mount="missing", tree_digest=DIGEST_A))
    assert caught.value.code is ErrorCode.NOT_FOUND


@pytest.mark.parametrize("working_tree", [False, True])
def test_host_request_with_real_git_keeps_source_branch(
    review_side: Any, tmp_path: Path, working_tree: bool
) -> None:
    import json
    from types import SimpleNamespace

    from skm.adapters.git.commit import git_vcs
    from skm.adapters.git.repo_inspect import GitRepositoryInspector
    from skm.application_bus.host import HostContext
    from skm.kernel.cancel import CancelSource
    from skm.kernel.gateways import GatewayTable
    from skm.modules.execution.ports import Vcs
    from skm.modules.workspace.ports import RepositoryInspector
    from skm.modules.workspace.public import ResolveCheckout
    from support.git_repo import init_git_repo

    side = review_side
    repo = init_git_repo(tmp_path / "review-source")
    base = repo.commit_file(content="base\n")
    repo.create_branch("review-base", start_point=base)
    head = repo.commit_file(content="changed\n", message="requested range")
    if working_tree:
        (repo.path / "README.md").write_text("dirty\n")
        (repo.path / "new.txt").write_text("untracked\n")
    branch = repo.runner.run(repo.path, ["symbolic-ref", "HEAD"]).stdout

    class LocatedClient:
        """Only checkout location is supplied at the host boundary; bus and Git are real."""

        def __getattr__(self, name: str) -> Any:
            return getattr(side.client, name)

        def ask(self, query: Any) -> Any:
            if isinstance(query, ResolveCheckout):
                return SimpleNamespace(local_locator=str(repo.path))
            return side.client.ask(query)

    host = HostContext(
        cast("Any", LocatedClient()),
        GatewayTable(
            {
                Vcs: git_vcs(repo.runner, state_dir=tmp_path / "snapshots"),
                RepositoryInspector: GitRepositoryInspector(repo.runner),
            },
            "host_gateway",
        ),
        side.host1,
        None,
        None,
        CancelSource().token,
    )
    target = ["--working-tree"] if working_tree else ["--head", "main"]
    code, out, err = invoke(
        side,
        "review",
        "request",
        "--project",
        str(side.proj),
        "--mount",
        "repo",
        "--base",
        "review-base",
        *target,
        host=lambda: host,
    )
    assert code == 0, (out, err)
    result = json.loads(out)["result"]
    with side.uow(readonly=True) as uow:
        req = uow.repo(ReviewRequestRepository).for_run(UUID(result["run_id"]))
        assert req is not None
        assert req.target.base_commit == base
        assert req.target.kind == ("working_tree" if working_tree else "commits")
    from skm.modules.execution.host.request_review import run as request_host

    payload: Any = {
        "project_id": str(side.proj),
        "mount": "repo",
        "integration_branch": "review-base",
        "working_tree": working_tree,
        "idempotency_key": side.client.new_idempotency_key(),
    }
    first = request_host(host, payload)
    assert request_host(host, payload) == first
    assert repo.runner.run(repo.path, ["rev-parse", "HEAD"]).stdout.strip() == head
    assert repo.runner.run(repo.path, ["symbolic-ref", "HEAD"]).stdout == branch


def test_requested_profile_is_pinned_and_unknown_profile_rolls_back(review_side: Any) -> None:
    side = review_side
    result = request(side, command(side, profile_key="security"))
    with side.uow(readonly=True) as uow:
        rid = UUID(result["run_id"])
        bundle = uow.repo(BundleRepository).get(rid)
        assert any(
            pin.kind == "agent_profile" and pin.key == "security" for pin in bundle.resource_pins.resources
        )
        task = uow.repo(TaskRepository).list_for_run(rid)[0]
        assert task.review_profile == "security"
        from types import SimpleNamespace

        from skm.modules.execution.application._stage_agent_helpers import profile_and_permissions
        from skm.modules.execution.domain.step import RoleId
        from unit.execution.application._support import context

        run = uow.repo(RunRepository).get(rid)
        actual, _, _ = profile_and_permissions(
            uow,
            context(side, uow, run),
            SimpleNamespace(run=run, task=task),
            SimpleNamespace(params={"profile": "reviewer"}),
            RoleId.REVIEWER,
        )
        assert actual.key == "security"
    with pytest.raises(SkmError):
        request(side, command(side, profile_key="missing-profile"))
    with side.uow(readonly=True) as uow:
        run = uow.repo(RunRepository).get(rid)
        assert str(planning.get_plan_ref(uow, run.plan_id).current_revision_id) == result["revision_id"]
