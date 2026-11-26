"""Bus pipeline helpers and restore admission (kernel-platform §4.4 and §5.6).

The fixed request pipeline owns scope resolution, authorization and domain units of work.
Restored compositions consult their activation receipt before admitting operational work.
"""

from __future__ import annotations

import math
import os
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Protocol, cast, override
from uuid import UUID

from skm.application_bus.context import AuthBasis, AuthBasisKind
from skm.application_bus.ports import IdempotencyReceipt
from skm.application_bus.registry import AnyCommandSpec, AnyQuerySpec, IdempotencyMode
from skm.application_bus.subscribers import EventSinkRegistry
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, InternalError, PreconditionFailed, ValidationFailed
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import HostId, RepositoryId, RunId, WorkspaceId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.outcomes import Waiting
from skm.kernel.ports_uow import RequestMeta, Surface, UnitOfWork
from skm.kernel.scopes import ScopeRecord, ScopeRef, ScopeRegistry
from skm.platform.jsonc.canonical import InvalidUnicodeError
from skm.platform.jsonc.digest import digest
from skm.platform.storage.restore import MARKER, RECEIPT, read_document

if TYPE_CHECKING:
    from skm.application_bus.bus import Bus

__all__ = [
    "KIND_NOT_ALLOWED",
    "ROLE_LACKS_PERMISSION",
    "audit_target",
    "bind_meta",
    "dto_json",
    "from_receipt",
    "idempotency_key",
    "is_waiting",
    "kind_allowed",
    "request_digest",
    "required_permissions",
    "scope_ref",
    "workspace_of",
]

KIND_NOT_ALLOWED: Final = "KIND_NOT_ALLOWED"
ROLE_LACKS_PERMISSION: Final = "ROLE_LACKS_PERMISSION"


def bind_meta(meta: RequestMeta) -> RequestMeta:
    """translate_errors: the correlation is bound before any processing; ``None`` -> the request id."""
    return meta if meta.correlation_id is not None else replace(meta, correlation_id=meta.request_id)


def idempotency_key(spec: AnyCommandSpec, meta: RequestMeta) -> str | None:
    """validate_dto: REQUIRED needs a key, FORBIDDEN rejects one, OPTIONAL accepts both (before BEGIN)."""
    if spec.idempotency is IdempotencyMode.REQUIRED and meta.idempotency_key is None:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "Idempotency-Key is required",
            details={"field": "Idempotency-Key", "command": spec.name},
        )
    if spec.idempotency is IdempotencyMode.FORBIDDEN:
        if meta.idempotency_key is not None:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "Idempotency-Key is forbidden",
                details={"field": "Idempotency-Key", "reason": "not_idempotent"},
            )
        return None
    return meta.idempotency_key


def request_digest(spec: AnyCommandSpec, dto: object) -> str:
    """The only request digest form: ``digest({"operation", "dto"})`` over the full validated DTO.

    Memory and PostgreSQL adapters never compute their own. Secrets marked ``x-skm-secret`` are part of the
    digest (redaction is a presentation concern), so a changed secret under the same key is
    ``IDEMPOTENCY_KEY_REUSED``; only the digest is stored, never the body.

    Canonical JSON refuses floats, so the bus normalizes them as their owner (kernel §2.1): each float
    becomes its ``repr`` and its path is listed under ``"floats"``. A float-free DTO keeps the plain form;
    the extra key keeps a float apart from the equal string and from the integer of the same value.

    A string or key that is not valid Unicode text (an unpaired surrogate) cannot be encoded as canonical
    UTF-8: that is the caller's ``SCHEMA_INVALID``; neither the text nor the key is echoed.
    """
    floats: list[JsonValue] = []
    try:
        body = _floats_as_text(dto_json(dto), (), floats)
        if not floats:
            return digest({"operation": spec.name, "dto": body})
        return digest({"operation": spec.name, "dto": body, "floats": floats})
    except InvalidUnicodeError:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "request holds a string that is not valid Unicode text",
            details={"command": spec.name, "reason": "invalid_unicode"},
        ) from None
    except RecursionError:
        # A document nested past the interpreter's recursion limit is a client value, not a defect; the
        # body is never echoed.
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "request is nested too deeply to digest",
            details={"command": spec.name, "reason": "recursion_limit"},
        ) from None


def kind_allowed(spec: AnyCommandSpec | AnyQuerySpec, actor: Actor | AuthBasis) -> bool:
    """authorize, before BEGIN: internal operations refuse humans; ``allowed_kinds`` narrows further."""
    basis = actor if isinstance(actor, AuthBasis) else None
    resolved = basis.actor if basis is not None else actor
    if spec.internal and resolved.kind is PrincipalKind.HUMAN:
        return False
    if (
        basis is not None
        and basis.kind in {AuthBasisKind.SESSION, AuthBasisKind.LOCAL_OWNER}
        and spec.allowed_kinds == frozenset({PrincipalKind.WORKER})
    ):
        return False
    return resolved.kind in spec.allowed_kinds


def required_permissions(spec: AnyCommandSpec, dto: object) -> tuple[str, ...]:
    """Base permission and AND requirements; the bus expands declared alternatives for the base."""
    extra = () if spec.permissions_of is None else spec.permissions_of(dto)
    if not _is_names(extra):
        raise InternalError(
            ErrorCode.INTERNAL_ERROR,
            "permissions_of must return a tuple of permission names",
            details={"command": spec.name},
        )
    return tuple(dict.fromkeys((spec.permission, *extra)))


def workspace_of(chain: tuple[ScopeRecord, ...]) -> WorkspaceId | None:
    """The nearest workspace of a resolved chain; ``None`` for instance, principal and host scopes."""
    return next((record.workspace_id for record in reversed(chain) if record.workspace_id is not None), None)


def from_receipt(spec: AnyCommandSpec, receipt: IdempotencyReceipt, digest_value: str) -> object:
    """idempotency: same digest -> the stored result without the handler; another -> KEY_REUSED."""
    if receipt.request_digest != digest_value:
        raise Conflict(
            ErrorCode.IDEMPOTENCY_KEY_REUSED,
            "idempotency key reused with another request",
            details={"operation": spec.name},
        )
    return spec.result.from_json(receipt.result)


def is_waiting(result: object) -> bool:
    """receipt: a result that is or holds ``Waiting`` is an expected wait, not a stored outcome."""
    if isinstance(result, Waiting):
        return True
    names: tuple[str, ...] = getattr(type(result), "__slots__", ())
    return any(isinstance(getattr(result, name, None), Waiting) for name in names)


def scope_ref(record: ScopeRecord) -> ScopeRef:
    return ScopeRef(kind=record.kind, id=record.id)


def audit_target(scope: ScopeRef | None, permission: str | None) -> JsonObject:
    """Target of an audit record; ``None`` scope = refused before the chain was resolved (instance)."""
    scope_json: JsonObject | None = None if scope is None else {"kind": scope.kind.value, "id": str(scope.id)}
    return {"scope": scope_json, "permission": permission}


def _is_names(value: object) -> bool:
    if not isinstance(value, tuple):
        return False
    return all(isinstance(item, str) for item in cast("tuple[object, ...]", value))


def _floats_as_text(value: JsonValue, path: tuple[str | int, ...], floats: list[JsonValue]) -> JsonValue:
    """Replace every float by its exact ``repr`` and record its path (keys as str, indexes as int).

    Object keys are walked in canonical order (``jsonc.canonical``), so the path list does not depend on the
    insertion order of an equal object; array items keep their own order.
    """
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "non-finite number is not JSON",
                details={"path": list(path)},
            )
        floats.append(list(path))
        return repr(value)
    if isinstance(value, list):
        return [_floats_as_text(item, (*path, index), floats) for index, item in enumerate(value)]
    if isinstance(value, dict):
        return {key: _floats_as_text(item, (*path, key), floats) for key, item in sorted(value.items())}
    return value


def dto_json(dto: object) -> JsonObject:
    """``to_json()`` of a generated DTO; anything else is a registration defect, not a client error."""
    to_json = getattr(dto, "to_json", None)
    value: object = to_json() if callable(to_json) else None
    if not isinstance(value, dict):
        raise InternalError(
            ErrorCode.INTERNAL_ERROR, "bus DTO has no JSON form", details={"dto": type(dto).__name__}
        )
    return cast("JsonObject", value)


def require_restore_admission(allowed: bool, operation: str) -> None:
    if not allowed:
        raise PreconditionFailed(
            ErrorCode.INVALID_TRANSITION,
            "Operation is blocked by restore recovery",
            details={"reason": "restore_quarantine", "operation": operation},
        )


_ADMIN = frozenset(
    {
        "access.revoke_token",
        "workspace.register_host",
    }
)
_EXTERNAL = ("exports.", "integrations.", "plugins.")


class RecoveryGuard:
    def __init__(
        self,
        state: Path,
        identity: UUID,
        digest: str,
        committed: Callable[[], JsonObject | None],
        allowed: Callable[[str, str], bool],
        *,
        recovery_token_id: Callable[[], UUID | None] | None = None,
    ) -> None:
        self.state, self.identity, self.digest = state, identity, digest
        self._committed = committed
        self.allowed = allowed
        self._recovery_token_id = recovery_token_id
        self._accepted: JsonObject | None = None

    def expected_recovery_token_id(self) -> UUID | None:
        return None if self._recovery_token_id is None else self._recovery_token_id()

    def receipt(self) -> JsonObject | None:
        if os.path.lexists(self.state / MARKER):
            return None
        if not (self.state / RECEIPT).is_file():
            return None
        receipt = read_document(self.state, RECEIPT)
        if (
            receipt.get("restore_id") != str(self.identity)
            or receipt.get("manifest_digest") != self.digest
            or receipt.get("state") != "activated"
        ):
            return None
        saved = self._accepted if self._accepted is not None else self._committed()
        if saved is None or any(receipt.get(key) != value for key, value in saved.items()):
            return None
        self._accepted = saved
        return saved

    def host(self, operation: str | None, surface: Surface) -> None:
        allowed = (
            self.receipt() is not None
            and surface is Surface.WORKER
            and operation
            in {
                None,
                "execution.host.worker_loop",
            }
        )
        require_restore_admission(allowed, operation or "host.context")


class GuardedBlobStore:
    def __init__(self, delegate: object, guard: RecoveryGuard) -> None:
        self.delegate, self.guard = delegate, guard

    def __getattr__(self, name: str) -> Any:
        if name not in {"open", "inspection", "exists", "verify", "stat", "iter_objects", "backend_id"}:
            require_restore_admission(self.guard.receipt() is not None, "artifacts." + name)
        return getattr(self.delegate, name)


def recovery_bus(guard: RecoveryGuard, **kwargs: Any) -> Bus:
    from skm.application_bus.bus import Bus

    class RecoveryBus(Bus):
        guard: RecoveryGuard

        @override
        def dispatch(
            self,
            cmd: object,
            *,
            actor: Actor,
            meta: RequestMeta,
            auth_basis: AuthBasis | None = None,
        ) -> object:
            name = self._registry.command(type(cmd)).name
            receipt = guard.receipt()
            if receipt is None:
                require_restore_admission(meta.surface is Surface.CLI and name in _ADMIN, name)
            elif name.startswith(_EXTERNAL) or name in {"platform.retry_outbox", "workspace.bind_checkout"}:
                require_restore_admission(False, name)
            elif name == "execution.reconcile_external_effect":
                require_restore_admission(guard.allowed(name, str(dto_json(cmd).get("effect_id"))), name)
            elif name in {"execution.resume_run", "execution.start_autopilot"}:
                data = dto_json(cmd)
                require_restore_admission(
                    actor.kind is PrincipalKind.HUMAN
                    and guard.allowed(name, str(data.get("run_id") or data.get("project_id"))),
                    name,
                )
            return super().dispatch(cmd, actor=actor, meta=meta, auth_basis=auth_basis)

        @override
        def ask_with_meta(
            self,
            query: object,
            *,
            actor: Actor,
            meta: RequestMeta,
            auth_basis: AuthBasis | None = None,
        ) -> Any:
            name = self._registry.query(type(query)).name
            if name in {"settings.get_host_config", "exports.list_pending_notes"}:
                require_restore_admission(guard.receipt() is not None and name.startswith("settings."), name)
            return super().ask_with_meta(query, actor=actor, meta=meta, auth_basis=auth_basis)

    bus = RecoveryBus(**kwargs)
    bus.guard = guard
    return bus


class StoredScopeChain:
    def chain(self, uow: UnitOfWork, scope: ScopeRef | None) -> tuple[ScopeRecord, ...]:
        registry = uow.repo(ScopeRegistry)
        return (registry.instance(),) if scope is None else registry.ancestors(scope.id)


def recovery_wiring(
    guard: RecoveryGuard | None,
    gateways: GatewayTable,
    blob_type: type | None,
    **kwargs: Any,
) -> tuple[Bus, GatewayTable]:
    from skm.application_bus.bus import Bus

    if guard is None:
        return Bus(gateways=gateways, **kwargs), gateways
    entries = dict(gateways.entries)
    entries[EventSinkRegistry] = EventSinkRegistry(())
    if blob_type is not None and blob_type in entries:
        entries[blob_type] = GuardedBlobStore(entries[blob_type], guard)
    gateways = GatewayTable(entries, gateways.kind)
    return recovery_bus(guard, gateways=gateways, **kwargs), gateways


class RecoveryPin(Protocol):
    @property
    def run_id(self) -> RunId: ...
    @property
    def repository_id(self) -> RepositoryId: ...
    @property
    def host_id(self) -> HostId: ...
    @property
    def branch(self) -> str: ...


class RecoveryPins:
    """Project the verified inspection bindings without changing historical writer authority."""

    def __init__(
        self, delegate: Any, guard: RecoveryGuard, current: Callable[[], tuple[RecoveryPin, ...]]
    ) -> None:
        self._delegate, self._guard, self._current = delegate, guard, current

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)

    def _pins(self) -> tuple[RecoveryPin, ...]:
        return () if self._guard.receipt() is None else self._current()

    def hosts_for_run(self, run_id: RunId) -> dict[RepositoryId, HostId]:
        historical = cast("dict[RepositoryId, HostId]", self._delegate.hosts_for_run(run_id))
        return {**historical, **{p.repository_id: p.host_id for p in self._pins() if p.run_id == run_id}}

    def target_hosts(
        self, targets: tuple[tuple[RepositoryId, str], ...]
    ) -> dict[tuple[RepositoryId, str], HostId]:
        historical = cast("dict[tuple[RepositoryId, str], HostId]", self._delegate.target_hosts(targets))
        return {
            **historical,
            **{
                (p.repository_id, p.branch): p.host_id
                for p in self._pins()
                if (p.repository_id, p.branch) in targets
            },
        }
