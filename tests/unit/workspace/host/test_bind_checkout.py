"""Unit tests for ``workspace.host.bind_checkout``."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import pytest

from skm.application_bus.client import QueryMeta, SkmClient, StagedBlobRef
from skm.application_bus.host import HostContext
from skm.kernel.cancel import CancelSource
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, PreconditionFailed, ValidationFailed
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import HostId, ProjectId, RepositoryId, WorkspaceId
from skm.kernel.outcomes import Diagnostic
from skm.modules.workspace.domain.checkout_binding import CheckoutBindingId, ObservedCheckout
from skm.modules.workspace.domain.checkout_marker import CheckoutMarker
from skm.modules.workspace.domain.mount import MountName
from skm.modules.workspace.domain.remote_url import NormalizedRemote
from skm.modules.workspace.generated.commands import (
    AttachRepository,
    BindCheckout,
    RegisterRepository,
)
from skm.modules.workspace.generated.queries import ListProjectRepositories, MatchCheckout
from skm.modules.workspace.generated.results import (
    BindCheckoutResult,
    RegisterRepositoryResult,
)
from skm.modules.workspace.generated.views import (
    AttachDecisionView,
    ListProjectRepositoriesView,
)
from skm.modules.workspace.host.bind_checkout import BindCheckoutRequest, bind_checkout
from skm.modules.workspace.ports import RepositoryInspector

INSTANCE_ID = UUID("0195f1c2-0000-7000-8000-000000000001")
WS_ID = WorkspaceId(UUID("0195f1c2-0000-7000-8000-000000000010"))
PROJ_ID = ProjectId(UUID("0195f1c2-0000-7000-8000-000000000020"))
REPO_ID = RepositoryId(UUID("0195f1c2-0000-7000-8000-000000000030"))
HOST_ID = HostId(UUID("0195f1c2-0000-7000-8000-000000000040"))
BINDING_ID = CheckoutBindingId(UUID("0195f1c2-0000-7000-8000-000000000050"))
FIXED_NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)


class FakeInspector:
    def __init__(self, observed: ObservedCheckout) -> None:
        self.observed = observed
        self.written_markers: list[tuple[str, str, CheckoutMarker]] = []

    def observe(
        self, path: str, *, marker_relpath: str = ".skm/project.json", timeout_seconds: float = 60.0
    ) -> ObservedCheckout:
        del path, marker_relpath, timeout_seconds
        return self.observed

    def observe_with_diagnostics(
        self, path: str, *, marker_relpath: str = ".skm/project.json", timeout_seconds: float = 60.0
    ) -> tuple[ObservedCheckout, tuple[Diagnostic, ...]]:
        return self.observe(path, marker_relpath=marker_relpath, timeout_seconds=timeout_seconds), ()

    def write_marker(self, toplevel: str, *, marker_relpath: str, marker: CheckoutMarker) -> None:
        self.written_markers.append((toplevel, marker_relpath, marker))


class FakeClient:
    def __init__(self, decision: AttachDecisionView) -> None:
        self.decision = decision
        self.dispatched: list[object] = []
        self.idempotency_keys: list[tuple[str, str | None]] = []
        self.fail_once_on: type[object] | None = None
        self._seq = 0

    def new_idempotency_key(self) -> str:
        self._seq += 1
        return f"idem-{self._seq}"

    def dispatch(self, command: object, *, idempotency_key: str | None = None) -> Any:
        self.idempotency_keys.append((type(command).__name__, idempotency_key))
        if self.fail_once_on is not None and isinstance(command, self.fail_once_on):
            self.fail_once_on = None
            raise RuntimeError("simulated transient failure")
        self.dispatched.append(command)
        if isinstance(command, RegisterRepository):
            return RegisterRepositoryResult(
                repository_id=REPO_ID,
                canonical_remote=command.remote_url,
                provider="github",
            )
        if isinstance(command, AttachRepository):
            return None
        if isinstance(command, BindCheckout):
            return BindCheckoutResult(
                binding_id=BINDING_ID,
                state="active",
                reason="ok",
                row_version=1,
            )
        raise AssertionError(f"unexpected command: {command!r}")

    def ask(self, query: object, *, meta: QueryMeta | None = None) -> Any:
        del meta
        if isinstance(query, MatchCheckout):
            return self.decision
        if isinstance(query, ListProjectRepositories):
            return ListProjectRepositoriesView(items=())
        raise AssertionError(f"unexpected query: {query!r}")

    def upload_blob(self, data: bytes, *, media_type: str) -> StagedBlobRef:
        raise NotImplementedError

    def download_blob(self, blob_id: Any) -> bytes:
        raise NotImplementedError


def _make_ctx(inspector: FakeInspector, client: FakeClient) -> HostContext:
    return HostContext(
        client=cast("SkmClient", client),
        gateways=GatewayTable(entries={RepositoryInspector: inspector}, kind="host_gateway"),
        host_id=HOST_ID,
        config=object(),
        log=object(),
        cancel=CancelSource().token,
    )


def _git_observed(marker: CheckoutMarker | None = None) -> ObservedCheckout:
    return ObservedCheckout(
        exists=True,
        toplevel="/work/repo",
        remotes=(NormalizedRemote("github.com/org/repo"),),
        head="a" * 40,
        marker=marker,
        observed_at=FIXED_NOW,
        dirty=False,
    )


def test_bind_checkout_existing_repository_requires_confirmation_then_binds() -> None:
    inspector = FakeInspector(_git_observed())
    decision = AttachDecisionView(
        kind="use_existing_repository",
        project_id=PROJ_ID,
        repository_id=REPO_ID,
        mount_name="primary",
        needs_confirmation=True,
        canonical_remote=None,
        refuse_code=None,
        refuse_details=None,
        diagnostics=(),
    )
    client = FakeClient(decision)
    ctx = _make_ctx(inspector, client)

    with pytest.raises(PreconditionFailed) as exc_info:
        bind_checkout(ctx, BindCheckoutRequest(workspace_id=WS_ID, path="/work/repo"))
    assert exc_info.value.code is ErrorCode.INVALID_TRANSITION
    assert exc_info.value.details.get("reason") == "confirmation_required"

    report = bind_checkout(
        ctx,
        BindCheckoutRequest(
            workspace_id=WS_ID,
            path="/work/repo",
            confirm=lambda _d: True,
        ),
    )
    assert report.binding_id == BINDING_ID
    assert report.repository_id == REPO_ID
    assert any(isinstance(cmd, AttachRepository) for cmd in client.dispatched)
    assert any(isinstance(cmd, BindCheckout) for cmd in client.dispatched)


def test_bind_checkout_registers_new_repository_and_writes_marker() -> None:
    inspector = FakeInspector(_git_observed())
    decision = AttachDecisionView(
        kind="create_repository",
        project_id=PROJ_ID,
        repository_id=None,
        mount_name="primary",
        needs_confirmation=False,
        canonical_remote="github.com/org/repo",
        refuse_code=None,
        refuse_details=None,
        diagnostics=(),
    )
    client = FakeClient(decision)
    ctx = _make_ctx(inspector, client)

    with pytest.raises(NotFound):
        bind_checkout(
            ctx,
            BindCheckoutRequest(workspace_id=WS_ID, project_id=PROJ_ID, register_missing=False),
        )

    report = bind_checkout(
        ctx,
        BindCheckoutRequest(
            workspace_id=WS_ID,
            project_id=PROJ_ID,
            register_missing=True,
            write_marker=True,
            instance_id=INSTANCE_ID,
        ),
    )
    assert report.marker_written is True
    assert len(inspector.written_markers) == 1
    toplevel, relpath, marker = inspector.written_markers[0]
    assert toplevel == "/work/repo"
    assert relpath == ".skm/project.json"
    assert marker == CheckoutMarker(
        instance_id=INSTANCE_ID,
        workspace_id=WS_ID,
        project_id=PROJ_ID,
        repository_id=REPO_ID,
        mount_name=MountName("primary"),
    )


def test_bind_checkout_refuses_ambiguous_or_non_git() -> None:
    non_git = ObservedCheckout(
        exists=True,
        toplevel=None,
        remotes=(),
        head=None,
        marker=None,
        observed_at=FIXED_NOW,
        dirty=None,
    )
    decision = AttachDecisionView(
        kind="refuse",
        project_id=None,
        repository_id=None,
        mount_name=None,
        needs_confirmation=False,
        canonical_remote=None,
        refuse_code=ErrorCode.AMBIGUOUS_REFERENCE.value,
        refuse_details={"reason": "remotes_match_several_repositories", "candidates": []},
        diagnostics=(),
    )
    ctx_non_git = _make_ctx(FakeInspector(non_git), FakeClient(decision))
    with pytest.raises(PreconditionFailed) as exc_non_git:
        bind_checkout(ctx_non_git, BindCheckoutRequest(workspace_id=WS_ID, path="/work/not-git"))
    assert exc_non_git.value.code is ErrorCode.CHECKOUT_MISMATCH

    ctx_ambig = _make_ctx(FakeInspector(_git_observed()), FakeClient(decision))
    with pytest.raises(ValidationFailed) as exc_ambig:
        bind_checkout(ctx_ambig, BindCheckoutRequest(workspace_id=WS_ID, path="/work/repo"))
    assert exc_ambig.value.code is ErrorCode.AMBIGUOUS_REFERENCE


def test_bind_checkout_use_marker_branch_binds_marker_target() -> None:
    existing_marker = CheckoutMarker(
        instance_id=INSTANCE_ID,
        workspace_id=WS_ID,
        project_id=PROJ_ID,
        repository_id=REPO_ID,
        mount_name=MountName("main"),
    )
    inspector = FakeInspector(_git_observed(marker=existing_marker))
    decision = AttachDecisionView(
        kind="use_marker",
        project_id=PROJ_ID,
        repository_id=REPO_ID,
        mount_name="main",
        needs_confirmation=False,
        canonical_remote="github.com/org/repo",
        refuse_code=None,
        refuse_details=None,
        diagnostics=(),
    )
    client = FakeClient(decision)
    ctx = _make_ctx(inspector, client)

    report = bind_checkout(ctx, BindCheckoutRequest(workspace_id=WS_ID, path="/work/repo"))
    assert report.binding_id == BINDING_ID
    assert report.project_id == PROJ_ID
    assert report.repository_id == REPO_ID
    assert report.mount_name == "main"


def test_bind_checkout_idempotent_retry_reuses_idempotency_keys() -> None:
    inspector = FakeInspector(_git_observed())
    decision = AttachDecisionView(
        kind="create_repository",
        project_id=PROJ_ID,
        repository_id=None,
        mount_name="main",
        needs_confirmation=False,
        canonical_remote="github.com/org/repo",
        refuse_code=None,
        refuse_details=None,
        diagnostics=(),
    )
    client = FakeClient(decision)
    client.fail_once_on = BindCheckout
    ctx = _make_ctx(inspector, client)

    req = BindCheckoutRequest(
        workspace_id=WS_ID,
        project_id=PROJ_ID,
        path="/work/repo",
        register_missing=True,
        idempotency_keys={
            "register_repository": "register-key",
            "attach_repository": "attach-key",
            "bind_checkout": "bind-key",
        },
    )
    with pytest.raises(RuntimeError, match="simulated transient failure"):
        bind_checkout(ctx, req)

    first_attempt_keys = dict(client.idempotency_keys)
    assert set(first_attempt_keys) == {"RegisterRepository", "AttachRepository", "BindCheckout"}

    client.idempotency_keys.clear()
    report = bind_checkout(ctx, req)
    assert report.binding_id == BINDING_ID
    second_attempt_keys = dict(client.idempotency_keys)
    assert second_attempt_keys == first_attempt_keys

    # Subsequent successful call after completion gets fresh idempotency keys
    client.idempotency_keys.clear()
    report_next = bind_checkout(ctx, replace(req, idempotency_keys=None))
    assert report_next.binding_id == BINDING_ID
    third_attempt_keys = dict(client.idempotency_keys)
    assert third_attempt_keys != first_attempt_keys


def test_bind_checkout_validates_write_marker_and_repo_compatibility_before_mutations() -> None:
    inspector = FakeInspector(_git_observed())
    decision_create = AttachDecisionView(
        kind="create_repository",
        project_id=None,
        repository_id=None,
        mount_name="main",
        needs_confirmation=False,
        canonical_remote="github.com/org/repo",
        refuse_code=None,
        refuse_details=None,
        diagnostics=(),
    )
    client = FakeClient(decision_create)
    ctx = _make_ctx(inspector, client)

    # write_marker without project fails BEFORE RegisterRepository / AttachRepository / BindCheckout
    with pytest.raises(ValidationFailed) as exc_marker:
        bind_checkout(
            ctx,
            BindCheckoutRequest(
                workspace_id=WS_ID,
                project_id=None,
                repository_id=REPO_ID,
                write_marker=True,
                instance_id=INSTANCE_ID,
            ),
        )
    assert exc_marker.value.code is ErrorCode.SCHEMA_INVALID
    assert client.dispatched == []

    # Explicit repository_id with conflicting remote match fails BEFORE AttachRepository (_ensure_mounted)
    other_repo = RepositoryId(UUID("0195f1c2-0000-7000-8000-000000000099"))
    decision_other = AttachDecisionView(
        kind="use_existing_repository",
        project_id=PROJ_ID,
        repository_id=other_repo,
        mount_name="main",
        needs_confirmation=False,
        canonical_remote="github.com/org/repo",
        refuse_code=None,
        refuse_details=None,
        diagnostics=(),
    )
    client_conflict = FakeClient(decision_other)
    ctx_conflict = _make_ctx(inspector, client_conflict)
    with pytest.raises(PreconditionFailed) as exc_conflict:
        bind_checkout(
            ctx_conflict,
            BindCheckoutRequest(
                workspace_id=WS_ID,
                project_id=PROJ_ID,
                repository_id=REPO_ID,
            ),
        )
    assert exc_conflict.value.code is ErrorCode.CHECKOUT_MISMATCH
    assert client_conflict.dispatched == []
