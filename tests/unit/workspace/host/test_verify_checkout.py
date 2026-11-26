"""Unit tests for ``workspace.host.verify_checkout`` and ``register_this_host``."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal, cast
from uuid import UUID

import pytest

from skm.application_bus.client import QueryMeta, SkmClient, StagedBlobRef
from skm.application_bus.host import HostContext
from skm.kernel.cancel import CancelSource
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, PreconditionFailed, Unauthenticated
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import HostId, ProjectId, RepositoryId, WorkspaceId
from skm.modules.access.generated.views import PrincipalKind
from skm.modules.access.public import PrincipalView, WhoAmI, WhoAmIView
from skm.modules.workspace.domain.checkout_binding import CheckoutBindingId, ObservedCheckout
from skm.modules.workspace.domain.checkout_marker import CheckoutMarker
from skm.modules.workspace.domain.remote_url import NormalizedRemote
from skm.modules.workspace.generated.commands import (
    RecordCheckoutVerification,
    RegisterHost,
)
from skm.modules.workspace.generated.queries import ListProjectRepositories
from skm.modules.workspace.generated.results import (
    RecordCheckoutVerificationResult,
    RegisterHostResult,
)
from skm.modules.workspace.generated.views import (
    ListProjectRepositoriesView,
    MountView,
    MountViewBindingVariant1,
    RepositoryView,
)
from skm.modules.workspace.host.register_this_host import (
    RegisterThisHostRequest,
    register_this_host,
)
from skm.modules.workspace.host.verify_checkout import (
    VerifyCheckoutRequest,
    verify_checkout,
)
from skm.modules.workspace.ports import RepositoryInspector

FIXED_NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)

WS_ID = WorkspaceId(UUID("0195f1c2-0000-7000-8000-000000000010"))
PROJ_ID = ProjectId(UUID("0195f1c2-0000-7000-8000-000000000020"))
REPO_ID = RepositoryId(UUID("0195f1c2-0000-7000-8000-000000000030"))
HOST_ID = HostId(UUID("0195f1c2-0000-7000-8000-000000000040"))
BINDING_ID = CheckoutBindingId(UUID("0195f1c2-0000-7000-8000-000000000050"))


class StubInspector:
    def __init__(self, observed: ObservedCheckout) -> None:
        self.observed = observed

    def observe(
        self, path: str, *, marker_relpath: str = ".skm/project.json", timeout_seconds: float = 60.0
    ) -> ObservedCheckout:
        del path, marker_relpath, timeout_seconds
        return self.observed

    def write_marker(self, toplevel: str, *, marker_relpath: str, marker: CheckoutMarker) -> None:
        raise NotImplementedError


class StubVerifyClient:
    def __init__(
        self,
        next_state: Literal["active", "missing", "mismatched", "removed"] = "mismatched",
        reason: str = "remote_mismatch",
    ) -> None:
        self.next_state: Literal["active", "missing", "mismatched", "removed"] = next_state
        self.reason = reason
        self.dispatched: list[RecordCheckoutVerification] = []
        self.registered: list[RegisterHost] = []
        self.whoami: WhoAmIView | Exception | None = None
        self._seq = 0

    def new_idempotency_key(self) -> str:
        self._seq += 1
        return f"idem-{self._seq}"

    def dispatch(self, command: object, *, idempotency_key: str | None = None) -> Any:
        del idempotency_key
        if isinstance(command, RecordCheckoutVerification):
            self.dispatched.append(command)
            return RecordCheckoutVerificationResult(
                binding_id=command.binding_id,
                state=self.next_state,
                reason=self.reason,
                row_version=command.expected_row_version + 1,
            )
        if isinstance(command, RegisterHost):
            self.registered.append(command)
            return RegisterHostResult(host_id=HOST_ID, name=command.name)
        raise AssertionError(f"unexpected command: {command!r}")

    def ask(self, query: object, *, meta: QueryMeta | None = None) -> Any:
        del meta
        if isinstance(query, WhoAmI):
            if isinstance(self.whoami, Exception):
                raise self.whoami
            return self.whoami
        if isinstance(query, ListProjectRepositories):
            return ListProjectRepositoriesView(
                items=(
                    MountView(
                        mount_name="primary",
                        role="primary",
                        repository=RepositoryView(
                            repository_id=REPO_ID,
                            workspace_id=WS_ID,
                            title="repo",
                            canonical_remote="github.com/org/repo",
                            provider="github",
                            external_id=None,
                            row_version=1,
                            created_at=FIXED_NOW,
                        ),
                        binding=MountViewBindingVariant1(
                            binding_id=BINDING_ID,
                            state="active",
                            is_stale=False,
                            row_version=2,
                            local_locator="/work/repo",
                        ),
                    ),
                )
            )
        raise AssertionError(f"unexpected query: {query!r}")

    def upload_blob(self, data: bytes, *, media_type: str) -> StagedBlobRef:
        raise NotImplementedError

    def download_blob(self, blob_id: Any) -> bytes:
        raise NotImplementedError


def _ctx(inspector: StubInspector, client: StubVerifyClient) -> HostContext:
    return HostContext(
        client=cast("SkmClient", client),
        gateways=GatewayTable(entries={RepositoryInspector: inspector}, kind="host_gateway"),
        host_id=HOST_ID,
        config=object(),
        log=object(),
        cancel=CancelSource().token,
    )


def test_verify_checkout_dispatches_verification_and_records_state_transition() -> None:
    observed = ObservedCheckout(
        exists=True,
        toplevel="/work/repo",
        remotes=(NormalizedRemote("github.com/other/fork"),),
        head="b" * 40,
        marker=None,
        observed_at=FIXED_NOW,
        dirty=True,
    )
    client = StubVerifyClient(next_state="mismatched", reason="remote_mismatch")
    ctx = _ctx(StubInspector(observed), client)

    report = verify_checkout(ctx, VerifyCheckoutRequest(project_id=PROJ_ID))
    assert len(report.items) == 1
    item = report.items[0]
    assert item.binding_id == BINDING_ID
    assert item.state == "mismatched"
    assert item.reason == "remote_mismatch"
    assert item.row_version == 3
    assert len(client.dispatched) == 1
    assert client.dispatched[0].expected_row_version == 2
    assert client.dispatched[0].observed_dirty is True


def test_register_this_host_persists_host_id_and_blocks_worker_auto() -> None:
    observed = ObservedCheckout(
        exists=False,
        toplevel=None,
        remotes=(),
        head=None,
        marker=None,
        observed_at=FIXED_NOW,
        dirty=None,
    )
    client = StubVerifyClient()
    ctx = _ctx(StubInspector(observed), client)
    persisted: list[HostId] = []

    report = register_this_host(
        ctx,
        RegisterThisHostRequest(
            name="devbox",
            os="linux",
            arch="x86_64",
            persist_host_id=persisted.append,
        ),
    )
    assert report.host_id == HOST_ID
    assert report.persisted is True
    assert persisted == [HOST_ID]

    with pytest.raises(PreconditionFailed) as exc_auto:
        register_this_host(
            ctx,
            RegisterThisHostRequest(is_worker=True, host_id_setting="auto"),
        )
    assert exc_auto.value.code is ErrorCode.INVALID_TRANSITION
    assert exc_auto.value.details.get("reason") == "host_not_registered"
    assert exc_auto.value.details.get("hint") == "skm host register"

    with pytest.raises(Forbidden):
        register_this_host(
            ctx,
            RegisterThisHostRequest(is_worker=True, host_id_setting=str(HOST_ID)),
        )

    with pytest.raises(Forbidden):
        register_this_host(
            ctx,
            RegisterThisHostRequest(is_worker=True, host_id_setting=None),
        )


def _whoami(kind: PrincipalKind) -> WhoAmIView:
    return WhoAmIView(
        principal=PrincipalView(
            principal_id=UUID("0195f1c2-0000-7000-8000-000000000060"),
            kind=kind,
            display_name=kind,
            state="active",
            created_at=FIXED_NOW,
            row_version=1,
            identities=(),
        ),
        token=None,
        memberships=(),
        effective_permissions=(),
        modules={},
        permissions_by_scope={},
        events_cursor=None,
    )


def _no_checkout() -> StubInspector:
    return StubInspector(
        ObservedCheckout(
            exists=False, toplevel=None, remotes=(), head=None, marker=None, observed_at=FIXED_NOW, dirty=None
        )
    )


def test_register_this_host_refuses_a_worker_token_it_learns_of_from_whoami() -> None:
    client = StubVerifyClient()
    client.whoami = _whoami(PrincipalKind.WORKER)

    with pytest.raises(Forbidden):
        register_this_host(_ctx(_no_checkout(), client), RegisterThisHostRequest(name="devbox"))
    assert client.registered == []


def test_register_this_host_reports_a_failing_whoami_instead_of_registering_blind() -> None:
    client = StubVerifyClient()
    client.whoami = Unauthenticated(ErrorCode.UNAUTHENTICATED, "token expired")

    with pytest.raises(Unauthenticated):
        register_this_host(_ctx(_no_checkout(), client), RegisterThisHostRequest(name="devbox"))
    assert client.registered == []


def test_reusing_a_recorded_host_requires_instance_host_management() -> None:
    client = StubVerifyClient()
    client.whoami = _whoami(PrincipalKind.HUMAN)
    with pytest.raises(Forbidden):
        register_this_host(
            _ctx(_no_checkout(), client), RegisterThisHostRequest(recorded_host_id=HOST_ID, replace=True)
        )
    assert client.registered == []
