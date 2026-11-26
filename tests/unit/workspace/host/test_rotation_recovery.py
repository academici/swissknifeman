"""Unit tests for ``workspace.host.rotate_worker_token`` rotation and recovery (ACCESS-03)."""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

import pytest

from skm.application_bus.client import QueryMeta, SkmClient, StagedBlobRef
from skm.application_bus.host import HostContext
from skm.kernel.cancel import CancelSource
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, PreconditionFailed
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import HostId, PrincipalId, WorkerId
from skm.modules.access import public as access
from skm.modules.access.generated.views import PrincipalKind as ViewPrincipalKind
from skm.modules.access.generated.views import TokenKind as ViewTokenKind
from skm.modules.workspace.host.rotate_worker_token import (
    RotateWorkerTokenRequest,
    WorkerRotationState,
    rotate_worker_token,
)

HOST_ID = HostId(UUID("0195f1c2-0000-7000-8000-000000000040"))
WORKER_ID = WorkerId(UUID("0195f1c2-0000-7000-8000-000000000060"))
PRINCIPAL_ID = PrincipalId(UUID("0195f1c2-0000-7000-8000-000000000070"))
TOKEN_1 = UUID("0195f1c2-0000-7000-8000-000000000081")
TOKEN_2 = UUID("0195f1c2-0000-7000-8000-000000000082")
TOKEN_3 = UUID("0195f1c2-0000-7000-8000-000000000083")
SECRET_2 = "skm_wk222222_secret_two_never_leak"
SECRET_3 = "skm_wk333333_secret_three_recovered"
FIXED_NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)


class _StreamLogger:
    def __init__(self, stream: io.StringIO) -> None:
        self._stream = stream

    def info(self, event: str, **fields: object) -> None:
        self._stream.write(f"INFO {event} {fields}\n")

    def warning(self, event: str, **fields: object) -> None:
        self._stream.write(f"WARN {event} {fields}\n")


class RotationSimClient:
    """Simulates server-side token rotation chain and optional lost-response transport failure."""

    def __init__(self, *, rotation_due: bool = True, fail_in_transit: bool = False) -> None:
        now = FIXED_NOW
        self.rotation_due = rotation_due
        self.fail_in_transit = fail_in_transit
        self.rotate_calls: list[access.RotateToken] = []
        self.idempotency_keys: list[str | None] = []
        self._seq = 0
        self.principal_kind: ViewPrincipalKind = ViewPrincipalKind.WORKER
        self.paginate_tokens: bool = False
        self.tokens: dict[UUID, access.TokenSummaryView] = {
            TOKEN_1: access.TokenSummaryView(
                token_id=TOKEN_1,
                kind=ViewTokenKind.WORKER,
                name=f"worker:{WORKER_ID}",
                prefix="wk111111",
                scope_id=UUID("0195f1c2-0000-7000-8000-000000000010"),
                permissions=None,
                state="active",
                expires_at=now + (timedelta(hours=12) if rotation_due else timedelta(days=7)),
                last_used_at=now,
                created_at=now - timedelta(days=6),
                superseded_by=None,
                assignment_id=None,
                step_id=None,
            )
        }

    def new_idempotency_key(self) -> str:
        self._seq += 1
        return f"rot-idem-{self._seq}"

    def dispatch(self, command: object, *, idempotency_key: str | None = None) -> Any:
        self.idempotency_keys.append(idempotency_key)
        assert isinstance(command, access.RotateToken)
        self.rotate_calls.append(command)
        old_uuid = UUID(str(command.token_id))
        old = self.tokens[old_uuid]
        if old.state != "active" or old.superseded_by is not None:
            raise PreconditionFailed(
                ErrorCode.INVALID_TRANSITION,
                "token is already superseded or revoked",
                details={"reason": "token_not_rotatable"},
            )
        now = FIXED_NOW
        grace_mins = 5 if command.grace_minutes is None else command.grace_minutes
        new_id = TOKEN_2 if old_uuid == TOKEN_1 else TOKEN_3
        secret = SECRET_2 if new_id == TOKEN_2 else SECRET_3
        prefix = "wk222222" if new_id == TOKEN_2 else "wk333333"

        self.tokens[old_uuid] = access.TokenSummaryView(
            token_id=old.token_id,
            kind=old.kind,
            name=old.name,
            prefix=old.prefix,
            scope_id=old.scope_id,
            permissions=old.permissions,
            state="active" if grace_mins > 0 else "expired",
            expires_at=now + timedelta(minutes=grace_mins),
            last_used_at=old.last_used_at,
            created_at=old.created_at,
            superseded_by=new_id,
            assignment_id=None,
            step_id=None,
        )
        self.tokens[new_id] = access.TokenSummaryView(
            token_id=new_id,
            kind=old.kind,
            name=old.name,
            prefix=prefix,
            scope_id=old.scope_id,
            permissions=old.permissions,
            state="active",
            expires_at=now + timedelta(days=7),
            last_used_at=None,
            created_at=now,
            superseded_by=None,
            assignment_id=None,
            step_id=None,
        )
        if self.fail_in_transit:
            raise ConnectionError("simulated network drop after server commit")

        return access.RotateTokenResult(
            token_id=new_id,
            prefix=prefix,
            secret=secret,
            expires_at=now + timedelta(days=7),
            previous_token_id=old.token_id,
            previous_expires_at=now + timedelta(minutes=grace_mins),
        )

    def ask(self, query: object, *, meta: QueryMeta | None = None) -> Any:
        del meta
        now = FIXED_NOW
        if isinstance(query, access.WhoAmI):
            t1 = self.tokens[TOKEN_1]
            return access.WhoAmIView(
                principal=access.PrincipalView(
                    principal_id=PRINCIPAL_ID,
                    kind=self.principal_kind,
                    display_name="w1",
                    state="active",
                    created_at=now,
                    row_version=1,
                    identities=(),
                ),
                token=t1,
                memberships=(),
                effective_permissions=(),
                modules={},
                permissions_by_scope={},
                events_cursor=None,
            )
        if isinstance(query, access.ListPrincipals):
            return access.ListPrincipalsView(
                items=(
                    access.PrincipalSummaryView(
                        principal_id=PRINCIPAL_ID,
                        kind=ViewPrincipalKind.WORKER,
                        display_name="w1",
                        state="active",
                    ),
                ),
                next=None,
            )
        if isinstance(query, access.ListTokens):
            items = tuple(t for t in self.tokens.values() if query.include_inactive or t.state == "active")
            if self.paginate_tokens and len(items) > 1:
                if query.after is None:
                    return access.ListTokensView(items=items[:1], next="page-2")
                return access.ListTokensView(items=items[1:], next=None)
            return access.ListTokensView(items=items, next=None)
        raise AssertionError(f"unexpected query: {query!r}")

    def upload_blob(self, data: bytes, *, media_type: str) -> StagedBlobRef:
        raise NotImplementedError

    def download_blob(self, blob_id: Any) -> bytes:
        raise NotImplementedError


def _make_ctx(client: RotationSimClient, log_stream: io.StringIO) -> HostContext:
    return HostContext(
        client=cast("SkmClient", client),
        gateways=GatewayTable(entries={}, kind="host_gateway"),
        host_id=HOST_ID,
        config=object(),
        log=_StreamLogger(log_stream),
        cancel=CancelSource().token,
    )


def test_lost_response_never_retries_rotate_and_operator_recovers_via_superseded_chain() -> None:
    log_stream = io.StringIO()
    client = RotationSimClient(rotation_due=True, fail_in_transit=True)
    ctx = _make_ctx(client, log_stream)
    state = WorkerRotationState()
    saved: list[tuple[WorkerId | None, str]] = []

    with pytest.raises(ConnectionError):
        rotate_worker_token(
            ctx,
            RotateWorkerTokenRequest(
                worker_id=WORKER_ID,
                rotation_state=state,
                save_secret=lambda w, s: (saved.append((w, s)), "/var/state/w.token")[1],
            ),
        )

    assert len(client.rotate_calls) == 1
    assert state.rotation_unresolved is True
    assert state.accepting_work is False
    assert not saved
    assert client.tokens[TOKEN_1].superseded_by == TOKEN_2
    assert client.tokens[TOKEN_2].state == "active"

    client.fail_in_transit = False
    op_report = rotate_worker_token(
        ctx,
        RotateWorkerTokenRequest(
            worker_id=WORKER_ID,
            operator_mode=True,
            save_secret=lambda w, s: (saved.append((w, s)), "/var/state/w.token")[1],
        ),
    )
    assert op_report.rotated is True
    assert op_report.old_token_id == TOKEN_2
    assert op_report.new_token_id == TOKEN_3
    assert client.rotate_calls[-1].token_id == TOKEN_2
    assert client.rotate_calls[-1].grace_minutes == 0
    assert client.tokens[TOKEN_2].state == "expired"
    assert saved == [(WORKER_ID, SECRET_3)]
    assert SECRET_2 not in log_stream.getvalue()
    assert SECRET_3 not in log_stream.getvalue()


def test_local_save_failure_retries_only_file_write_without_calling_rotate_again() -> None:
    log_stream = io.StringIO()
    client = RotationSimClient(rotation_due=True, fail_in_transit=False)
    ctx = _make_ctx(client, log_stream)
    write_attempts = 0
    written_secrets: list[str] = []

    def flaky_save(_worker_id: WorkerId | None, secret: str) -> str:
        nonlocal write_attempts
        write_attempts += 1
        if write_attempts == 1:
            raise OSError("disk temporarily busy")
        written_secrets.append(secret)
        return "/var/state/recovered.token"

    report = rotate_worker_token(
        ctx,
        RotateWorkerTokenRequest(
            worker_id=WORKER_ID,
            save_secret=flaky_save,
            max_save_attempts=3,
        ),
    )
    assert report.rotated is True
    assert report.new_token_id == TOKEN_2
    assert report.saved_path == "/var/state/recovered.token"
    assert len(client.rotate_calls) == 1
    assert write_attempts == 2
    assert written_secrets == [SECRET_2]
    assert SECRET_2 not in log_stream.getvalue()
    assert SECRET_2 not in str(report.to_json())


def test_self_rotation_refuses_human_principal_and_operator_paginates_tokens() -> None:
    log_stream = io.StringIO()
    client = RotationSimClient(rotation_due=True, fail_in_transit=True)
    ctx = _make_ctx(client, log_stream)

    with pytest.raises(ConnectionError):
        rotate_worker_token(ctx, RotateWorkerTokenRequest(worker_id=WORKER_ID))

    client.fail_in_transit = False
    client.principal_kind = ViewPrincipalKind.HUMAN
    with pytest.raises(Forbidden) as exc_human:
        rotate_worker_token(ctx, RotateWorkerTokenRequest(force=True))
    assert exc_human.value.code is ErrorCode.FORBIDDEN

    client.paginate_tokens = True
    op_report = rotate_worker_token(
        ctx,
        RotateWorkerTokenRequest(worker_id=WORKER_ID, operator_mode=True),
    )
    assert op_report.rotated is True
    assert op_report.old_token_id == TOKEN_2
    assert op_report.new_token_id == TOKEN_3
