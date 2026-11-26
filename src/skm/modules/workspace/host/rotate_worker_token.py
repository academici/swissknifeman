"""``workspace.host.rotate_worker_token`` (access §6.3, workspace §9, §12): worker token rotation & recovery.

Implements ACCESS-03:
- Worker mode: checks ``WhoAmI.token`` rotation eligibility (unless ``force=True``), calls ``RotateToken``
  once, and writes the new secret via ``save_secret``.
- Operator recovery mode (``operator_mode=True``): lists worker tokens (``include_inactive=True``), follows
  the ``superseded_by`` chain to the active terminal token, rotates it with ``grace_minutes=0`` so the lost
  successor is immediately revoked, and writes the recovered secret locally.
- On an unknown / lost response from ``RotateToken``, ``RotateToken`` is NEVER retried on the old token;
  ``on_rotation_unresolved`` is triggered so the worker stops claiming new assignments or starting new stages
  while finishing in-flight work on the grace token.
- Once ``RotateTokenResult.secret`` is received in memory, local file write failures retry ONLY the local
  write of that in-memory secret without calling ``RotateToken`` again.
- Secrets are registered with the redactor immediately and never logged or serialized into reports.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Protocol, cast
from uuid import UUID

from skm.application_bus.host import HostContext
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, NotFound, PreconditionFailed
from skm.kernel.ids import PrincipalId, WorkerId
from skm.kernel.module_manifest import HostOperationSpec
from skm.modules.access.public import (
    ListPrincipals,
    ListPrincipalsView,
    ListTokens,
    ListTokensView,
    RotateToken,
    RotateTokenResult,
    TokenSummaryView,
    WhoAmI,
    WhoAmIView,
)

if TYPE_CHECKING:
    from skm.kernel.json_types import JsonObject

__all__ = [
    "SPEC",
    "RotateWorkerTokenOperation",
    "RotateWorkerTokenReport",
    "RotateWorkerTokenRequest",
    "WorkerRotationState",
    "follow_superseded_chain",
    "rotate_worker_token",
    "run",
]


def _log_warn(ctx: HostContext, event: str, **fields: Any) -> None:
    warn_fn = getattr(ctx.log, "warning", None) or getattr(ctx.log, "warn", None)
    if callable(warn_fn):
        warn_fn(event, **fields)


def _log_info(ctx: HostContext, event: str, **fields: Any) -> None:
    info_fn = getattr(ctx.log, "info", None)
    if callable(info_fn):
        info_fn(event, **fields)


@dataclass(slots=True)
class WorkerRotationState:
    """Mutable worker loop state tracking whether token rotation is unresolved."""

    rotation_unresolved: bool = False
    accepting_work: bool = True

    def mark_unresolved(self) -> None:
        self.rotation_unresolved = True
        self.accepting_work = False


@dataclass(frozen=True, slots=True)
class RotateWorkerTokenRequest:
    """Parameters for ``workspace.host.rotate_worker_token``."""

    worker_id: WorkerId | None = None
    principal_id: PrincipalId | None = None
    starting_token_id: UUID | None = None
    operator_mode: bool = False
    force: bool = False
    grace_minutes: int | None = None
    max_save_attempts: int = 3
    now: datetime | None = None
    rotate_before_hours: float = 48.0
    validate_target: Callable[[WorkerId | None], None] | None = None
    save_secret: Callable[[WorkerId | None, str], str | None] | None = None
    register_secret: Callable[[str], None] | None = None
    on_rotation_unresolved: Callable[[], None] | None = None
    rotation_state: WorkerRotationState | None = None


@dataclass(frozen=True, slots=True)
class RotateWorkerTokenReport:
    """Outcome of ``workspace.host.rotate_worker_token`` (never carries the token secret)."""

    rotated: bool
    worker_id: WorkerId | None
    principal_id: PrincipalId
    old_token_id: UUID
    new_token_id: UUID | None
    prefix: str | None = None
    expires_at: datetime | None = None
    previous_expires_at: datetime | None = None
    saved_path: str | None = None
    recovery_required: bool = False

    def to_json(self) -> JsonObject:
        return {
            "rotated": self.rotated,
            "worker_id": None if self.worker_id is None else str(self.worker_id),
            "principal_id": str(self.principal_id),
            "old_token_id": str(self.old_token_id),
            "new_token_id": None if self.new_token_id is None else str(self.new_token_id),
            "prefix": self.prefix,
            "expires_at": None if self.expires_at is None else self.expires_at.isoformat(),
            "previous_expires_at": None
            if self.previous_expires_at is None
            else self.previous_expires_at.isoformat(),
            "saved_path": self.saved_path,
            "recovery_required": self.recovery_required,
        }


class RotateWorkerTokenOperation(Protocol):
    def __call__(
        self, ctx: HostContext, request: RotateWorkerTokenRequest | Mapping[str, Any] | None = None
    ) -> RotateWorkerTokenReport: ...


def _is_rotation_due(
    token: TokenSummaryView,
    now: datetime | None,
    rotate_before_hours: float,
) -> bool:
    explicit = getattr(token, "rotation_due", None)
    if isinstance(explicit, bool):
        return explicit
    if token.expires_at is None:
        return False
    ref_now = now or token.last_used_at or token.created_at
    return (token.expires_at - ref_now) <= timedelta(hours=rotate_before_hours)


def _worker_token_names(worker_id: WorkerId) -> tuple[str, str]:
    return (f"worker-{worker_id}", f"worker:{worker_id}")


def _worker_id_from_token_name(name: str) -> WorkerId | None:
    for prefix in ("worker-", "worker:"):
        if name.startswith(prefix):
            try:
                return WorkerId(UUID(name.removeprefix(prefix)))
            except ValueError:
                return None
    return None


def follow_superseded_chain(
    tokens: Sequence[TokenSummaryView],
    *,
    worker_id: WorkerId | None = None,
    starting_token_id: UUID | None = None,
) -> TokenSummaryView:
    """Follow ``superseded_by`` links among a worker's tokens to the active terminal token."""
    by_id: dict[UUID, TokenSummaryView] = {UUID(str(t.token_id)): t for t in tokens}
    candidates = list(tokens)
    if worker_id is not None:
        expected_names = _worker_token_names(worker_id)
        named = [t for t in candidates if t.name in expected_names]
        if named:
            candidates = named

    if not candidates:
        raise NotFound(
            ErrorCode.NOT_FOUND,
            "No worker tokens found for principal",
            details={
                "kind": "token",
                "worker_id": None if worker_id is None else str(worker_id),
            },
        )

    current: TokenSummaryView | None = None
    if starting_token_id is not None and UUID(str(starting_token_id)) in by_id:
        current = by_id[UUID(str(starting_token_id))]
    else:
        superseded_targets = {UUID(str(t.superseded_by)) for t in candidates if t.superseded_by is not None}
        roots = [t for t in candidates if UUID(str(t.token_id)) not in superseded_targets]
        current = roots[0] if roots else candidates[0]

    visited: set[UUID] = set()
    while current.superseded_by is not None:
        next_id = UUID(str(current.superseded_by))
        if next_id in visited or next_id not in by_id:
            break
        visited.add(UUID(str(current.token_id)))
        current = by_id[next_id]

    if current.state != "active":
        active_terminals = [t for t in candidates if t.state == "active" and t.superseded_by is None]
        if len(active_terminals) == 1:
            current = active_terminals[0]
        else:
            raise PreconditionFailed(
                ErrorCode.INVALID_TRANSITION,
                "Terminal worker token in rotation chain is not active",
                details={
                    "reason": "terminal_token_not_active",
                    "token_id": str(current.token_id),
                    "state": current.state,
                },
            )
    return current


def _list_all_worker_tokens(ctx: HostContext, principal_id: PrincipalId) -> list[TokenSummaryView]:
    items: list[TokenSummaryView] = []
    after: str | None = None
    while True:
        payload: dict[str, Any] = {
            "principal_id": str(principal_id),
            "kind": "worker",
            "include_inactive": True,
        }
        if after is not None:
            payload["after"] = after
        tokens_view = cast(
            "ListTokensView",
            ctx.client.ask(ListTokens.from_json(payload)),
        )
        items.extend(tokens_view.items)
        if not tokens_view.next:
            break
        after = tokens_view.next
    return items


def _resolve_operator_target(
    ctx: HostContext, req: RotateWorkerTokenRequest
) -> tuple[PrincipalId, TokenSummaryView]:
    if req.principal_id is not None:
        all_tokens = _list_all_worker_tokens(ctx, req.principal_id)
        terminal = follow_superseded_chain(
            all_tokens,
            worker_id=req.worker_id,
            starting_token_id=req.starting_token_id,
        )
        return req.principal_id, terminal

    if req.worker_id is None:
        raise PreconditionFailed(
            ErrorCode.SCHEMA_INVALID,
            "operator_mode requires worker_id or principal_id",
            details={"reason": "worker_or_principal_required"},
        )

    expected_token_names = _worker_token_names(req.worker_id)
    after: str | None = None
    while True:
        payload: dict[str, Any] = {"kind": "worker", "limit": 100}
        if after is not None:
            payload["after"] = after
        principals_view = cast(
            "ListPrincipalsView",
            ctx.client.ask(ListPrincipals.from_json(payload)),
        )
        for principal in principals_view.items:
            p_id = PrincipalId(principal.principal_id)
            all_tokens = _list_all_worker_tokens(ctx, p_id)
            matching = [t for t in all_tokens if t.name in expected_token_names]
            if matching:
                terminal = follow_superseded_chain(
                    matching,
                    worker_id=req.worker_id,
                    starting_token_id=req.starting_token_id,
                )
                return p_id, terminal
        if principals_view.next is None:
            break
        after = principals_view.next

    raise NotFound(
        ErrorCode.NOT_FOUND,
        f"No worker principal found for worker {req.worker_id}",
        details={"kind": "worker", "worker_id": str(req.worker_id)},
    )


def _mark_unresolved(ctx: HostContext, req: RotateWorkerTokenRequest, token_id: UUID, reason: str) -> None:
    if req.rotation_state is not None:
        req.rotation_state.mark_unresolved()
    if req.on_rotation_unresolved is not None:
        req.on_rotation_unresolved()
    _log_warn(
        ctx,
        "worker.token.rotation_unresolved",
        token_id=str(token_id),
        worker_id=None if req.worker_id is None else str(req.worker_id),
        reason=reason,
    )


def _save_secret_with_retries(
    ctx: HostContext,
    req: RotateWorkerTokenRequest,
    secret: str,
    new_token_id: UUID,
) -> str | None:
    if req.save_secret is None:
        return None
    attempts = max(1, req.max_save_attempts)
    last_err: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return req.save_secret(req.worker_id, secret)
        except Exception as err:  # noqa: BLE001
            last_err = err
            _log_warn(
                ctx,
                "worker.token.local_save_retry",
                attempt=attempt,
                max_attempts=attempts,
                token_id=str(new_token_id),
            )
    _mark_unresolved(ctx, req, new_token_id, "local_secret_write_failed")
    assert last_err is not None  # noqa: S101
    raise last_err


def _coerce_request(
    request: RotateWorkerTokenRequest | Mapping[str, Any] | None,
) -> RotateWorkerTokenRequest:
    if request is None:
        return RotateWorkerTokenRequest()
    if isinstance(request, RotateWorkerTokenRequest):
        return request
    w_raw = request.get("worker_id")
    p_raw = request.get("principal_id")
    t_raw = request.get("starting_token_id")
    g_raw = request.get("grace_minutes")
    return RotateWorkerTokenRequest(
        worker_id=None if w_raw is None else WorkerId(w_raw if isinstance(w_raw, UUID) else UUID(str(w_raw))),
        principal_id=None
        if p_raw is None
        else PrincipalId(p_raw if isinstance(p_raw, UUID) else UUID(str(p_raw))),
        starting_token_id=None if t_raw is None else (t_raw if isinstance(t_raw, UUID) else UUID(str(t_raw))),
        operator_mode=bool(request.get("operator_mode", False)),
        force=bool(request.get("force", False)),
        grace_minutes=None if g_raw is None else int(g_raw),
        max_save_attempts=int(request.get("max_save_attempts", 3)),
        now=cast("datetime | None", request.get("now")),
        rotate_before_hours=float(request.get("rotate_before_hours", 48.0)),
        validate_target=cast("Callable[[WorkerId | None], None] | None", request.get("validate_target")),
        save_secret=cast("Callable[[WorkerId | None, str], str | None] | None", request.get("save_secret")),
        register_secret=cast("Callable[[str], None] | None", request.get("register_secret")),
        on_rotation_unresolved=cast("Callable[[], None] | None", request.get("on_rotation_unresolved")),
        rotation_state=cast("WorkerRotationState | None", request.get("rotation_state")),
    )


def rotate_worker_token(
    ctx: HostContext, request: RotateWorkerTokenRequest | Mapping[str, Any] | None = None
) -> RotateWorkerTokenReport:
    """Rotate a worker token in worker self-rotation mode or operator recovery mode."""
    req = _coerce_request(request)

    if req.operator_mode:
        principal_id, terminal = _resolve_operator_target(ctx, req)
        target_token_id = UUID(str(terminal.token_id))
        grace_minutes = 0 if req.grace_minutes is None else req.grace_minutes
        worker_id = req.worker_id if req.worker_id is not None else _worker_id_from_token_name(terminal.name)
    else:
        whoami = cast("WhoAmIView", ctx.client.ask(WhoAmI()))
        principal_id = PrincipalId(whoami.principal.principal_id)
        principal_kind = getattr(whoami.principal.kind, "value", str(whoami.principal.kind))
        token_kind = (
            None if whoami.token is None else getattr(whoami.token.kind, "value", str(whoami.token.kind))
        )
        if principal_kind != "worker" or whoami.token is None or token_kind != "worker":
            raise Forbidden(
                ErrorCode.FORBIDDEN,
                "Self-rotation requires a worker token; use --operator --worker <ref> for operator recovery",
                details={"reason": "worker_token_required_for_self_rotation"},
            )
        target_token_id = UUID(str(whoami.token.token_id))
        worker_id = (
            req.worker_id if req.worker_id is not None else _worker_id_from_token_name(whoami.token.name)
        )
        if not req.force and not _is_rotation_due(whoami.token, req.now, req.rotate_before_hours):
            return RotateWorkerTokenReport(
                rotated=False,
                worker_id=worker_id,
                principal_id=principal_id,
                old_token_id=target_token_id,
                new_token_id=None,
            )
        grace_minutes = req.grace_minutes

    if req.validate_target is not None:
        req.validate_target(worker_id)

    try:
        # access.rotate_token has IdempotencyMode.FORBIDDEN (secret-bearing command)
        result = cast(
            "RotateTokenResult",
            ctx.client.dispatch(RotateToken(token_id=target_token_id, grace_minutes=grace_minutes)),
        )
    except Exception:
        if not req.operator_mode:
            _mark_unresolved(ctx, req, target_token_id, "rotate_token_call_failed")
        raise

    if req.register_secret is not None:
        req.register_secret(result.secret)

    req_with_worker = RotateWorkerTokenRequest(
        worker_id=worker_id,
        principal_id=principal_id,
        starting_token_id=req.starting_token_id,
        operator_mode=req.operator_mode,
        force=req.force,
        grace_minutes=req.grace_minutes,
        max_save_attempts=req.max_save_attempts,
        now=req.now,
        rotate_before_hours=req.rotate_before_hours,
        validate_target=req.validate_target,
        save_secret=req.save_secret,
        register_secret=req.register_secret,
        on_rotation_unresolved=req.on_rotation_unresolved,
        rotation_state=req.rotation_state,
    )
    saved_path = _save_secret_with_retries(ctx, req_with_worker, result.secret, UUID(str(result.token_id)))

    _log_info(
        ctx,
        "worker.token.rotated",
        worker_id=None if worker_id is None else str(worker_id),
        old_token_id=str(result.previous_token_id),
        new_token_id=str(result.token_id),
        operator_mode=req.operator_mode,
    )

    return RotateWorkerTokenReport(
        rotated=True,
        worker_id=worker_id,
        principal_id=principal_id,
        old_token_id=UUID(str(result.previous_token_id)),
        new_token_id=UUID(str(result.token_id)),
        prefix=result.prefix,
        expires_at=result.expires_at,
        previous_expires_at=result.previous_expires_at,
        saved_path=saved_path,
        recovery_required=False,
    )


def run(
    ctx: HostContext, request: RotateWorkerTokenRequest | Mapping[str, Any] | None = None
) -> RotateWorkerTokenReport:
    return rotate_worker_token(ctx, request)


SPEC = HostOperationSpec(
    name="workspace.host.rotate_worker_token",
    run=run,
    request=cast("type[object]", RotateWorkerTokenRequest),
    result=RotateWorkerTokenReport,
    surfaces=cast("frozenset[Any]", frozenset({"cli", "worker"})),
)
