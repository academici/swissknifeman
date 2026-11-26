"""The single execution path of commands and queries (kernel-platform §4.4, golden ``bus.py``).

The order of the steps is ``registry.COMMAND_PIPELINE`` / ``QUERY_PIPELINE``; the steps are plain calls of
``middleware`` functions in that order, not pluggable middleware. Everything that reads the database runs
inside the one UoW of the attempt; a denial leaves that UoW first and only then writes the denied audit in
a separate short UoW, so a request never holds two connections at once.

Handler denials, including chained Forbidden errors, also roll back before their separate audit.
The caller receives the handler's original error.
"""

import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import NoReturn, cast
from uuid import UUID

from skm.application_bus.client import QueryMeta
from skm.application_bus.context import AuthBasis, CommandContext, QueryContext
from skm.application_bus.middleware import (
    KIND_NOT_ALLOWED,
    ROLE_LACKS_PERMISSION,
    audit_target,
    bind_meta,
    dto_json,
    from_receipt,
    idempotency_key,
    is_waiting,
    kind_allowed,
    request_digest,
    required_permissions,
    scope_ref,
    workspace_of,
)
from skm.application_bus.ports import (
    AuditLog,
    AuditRecord,
    Authorizer,
    AuthzDecision,
    EventReader,
    IdempotencyReceipt,
    IdempotencyStore,
    ScopeChainResolver,
)
from skm.application_bus.registry import AnyCommandSpec, AnyQuerySpec, BusRegistry
from skm.kernel.actor import Actor
from skm.kernel.clock import Clock
from skm.kernel.entropy import EntropySource
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import (
    Conflict,
    Forbidden,
    InternalError,
    NotFound,
    PreconditionFailed,
    SkmError,
    ValidationFailed,
)
from skm.kernel.gateways import GatewayTable
from skm.kernel.id_generator import IdGenerator
from skm.kernel.ids import WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import Isolation, RequestMeta, UnitOfWork, UnitOfWorkFactory
from skm.kernel.scopes import ScopeKind, ScopeRecord, ScopeRef
from skm.platform.config.effective import EffectiveConfig
from skm.platform.config.keys import Chain
from skm.platform.config.loader import ConfigLoader
from skm.platform.config.store import ConfigStore, ScopeTree
from skm.platform.logging.envelope import bind
from skm.platform.logging.logger import StructLogger, get_logger
from skm.platform.schema.registry import SchemaRegistry

__all__ = ["Bus", "RetryPolicy"]

_log = get_logger("application_bus.bus")


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """40001/40P01 retries: ``storage.retry.max_attempts``, pause ``min(0.05·2^n, 1.0)`` with ±50 % jitter."""

    max_attempts: int = 3
    base_delay_seconds: float = 0.05
    max_delay_seconds: float = 1.0


class Bus:
    def __init__(  # noqa: PLR0913 - the composition root passes every collaborator explicitly
        self,
        *,
        registry: BusRegistry,
        schemas: SchemaRegistry,
        uow_factory: UnitOfWorkFactory,
        authorizer: Authorizer,
        scopes: ScopeChainResolver,
        config: ConfigLoader,
        clock: Clock,
        ids: IdGenerator,
        entropy: EntropySource,
        gateways: GatewayTable,
        retry: RetryPolicy,
        idempotency_ttl: timedelta,
    ) -> None:
        self._registry = registry
        self._schemas = schemas
        self._uow_factory = uow_factory
        self._authorizer = authorizer
        self._scopes = scopes
        self._config = config
        self._clock = clock
        self._ids = ids
        self._entropy = entropy
        self._gateways = gateways
        self._retry = retry
        self._ttl = idempotency_ttl

    @property
    def idempotency_retention(self) -> timedelta:
        return self._ttl

    def safe_retry_deadline(self) -> datetime:
        """Conservative deadline to persist before sending a keyed command."""
        return self._clock.now() + self._ttl

    # ------------------------------------------------------------------ commands
    def dispatch(
        self,
        cmd: object,
        *,
        actor: Actor,
        meta: RequestMeta,
        auth_basis: AuthBasis | None = None,
    ) -> object:
        basis = _resolve_basis(actor, auth_basis)
        meta = bind_meta(meta)  # translate_errors: correlation bound before processing
        started = time.monotonic()
        name: str | None = None
        with bind(
            request_id=meta.request_id,
            correlation_id=meta.correlation_id,
            causation_id=meta.causation_id,
            actor_id=str(actor.principal_id),
            surface=meta.surface.value,
        ):
            try:
                spec = self._registry.command(type(cmd))  # validate_dto: MODULE_DISABLED / unknown
                name = spec.name
                _log.info("bus.command.started", command=name)
                result = self._command(spec, cmd, basis, meta)
            except SkmError as err:
                _log.info("bus.command.failed", command=name, code=err.code.value, duration_ms=_ms(started))
                raise
            except Exception as exc:
                _log.error("bus.command.failed", exc=exc, command=name, code=ErrorCode.INTERNAL_ERROR.value)
                raise InternalError(
                    ErrorCode.INTERNAL_ERROR, "unexpected error", details={"request_id": meta.request_id}
                ) from exc
            _log.info("bus.command.completed", command=name, duration_ms=_ms(started))
            return result

    def _command(self, spec: AnyCommandSpec, cmd: object, basis: AuthBasis, meta: RequestMeta) -> object:
        actor = basis.actor
        self._require_valid_dto(spec.dto.SCHEMA_URN, cmd)  # validate_dto: SCHEMA_INVALID
        key = idempotency_key(spec, meta)  # validate_dto: REQUIRED / FORBIDDEN, before BEGIN
        if meta.idempotency_deadline is not None and key is None:
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "A retry deadline requires an idempotency key")
        digest_value = request_digest(spec, cmd)
        scope = spec.scope_of(cmd) if spec.scope_of is not None else None
        if not kind_allowed(spec, basis):  # refused before BEGIN: no UoW is open
            self._record_denied(actor, spec.name, _kind_denial(spec.permission, scope), meta)

        def attempt() -> object:
            return self._dispatch_once(spec, cmd, basis, meta, key, digest_value)

        try:
            try:
                return self._with_retry(attempt)
            except Conflict as err:
                if key is None or err.code is ErrorCode.SERIALIZATION_FAILURE:
                    raise
                return self._replay_receipt(spec, cmd, basis, meta, key, digest_value, err)  # receipt race
        except _Denied as denied:  # the command UoW is already closed
            self._record_denied(actor, spec.name, denied, meta)

    def _dispatch_once(
        self,
        spec: AnyCommandSpec,
        cmd: object,
        basis: AuthBasis,
        meta: RequestMeta,
        key: str | None,
        digest_value: str,
    ) -> object:
        actor = basis.actor
        with self._uow_factory(meta, readonly=False, isolation=spec.isolation) as uow:  # uow.begin
            chain, resolved = self._chain_of(uow, spec, cmd)
            for permission in required_permissions(spec, cmd):  # authorize (raises _Denied after rollback)
                self._authorize(
                    uow,
                    basis,
                    permission,
                    chain,
                    opaque=resolved,
                    alternatives=spec.permission_alternatives if permission == spec.permission else (),
                )
            effective = self._effective(uow, chain)  # load_config
            record_allowed = spec.audit and self._record_allowed(uow, chain, effective)
            workspace_id = workspace_of(chain)
            ctx = CommandContext(
                actor=actor,
                meta=meta,
                scope=scope_ref(chain[-1]),
                scope_chain=chain,
                clock=self._clock,
                ids=self._ids,
                entropy=self._entropy,
                config=effective,
                log=_module_log(spec.name),
                gateways=self._gateways,
                allows=lambda permission, target: (
                    self._authorize_decision(uow, basis, permission, target).allowed
                ),
                auth_basis=basis,
            )
            if key is not None:  # idempotency
                receipt = uow.repo(IdempotencyStore).get(workspace_id, actor.principal_id, spec.name, key)
                if receipt is not None:
                    if spec.replay_guard is not None:
                        try:
                            spec.replay_guard(cmd, ctx, uow)
                        except SkmError as err:
                            _raise_if_denial(uow, err, spec.permission, chain)
                            raise
                    uow.rollback()
                    return from_receipt(spec, receipt, digest_value)
            if meta.idempotency_deadline is not None and self._clock.now() >= meta.idempotency_deadline:
                raise PreconditionFailed(
                    ErrorCode.INVALID_TRANSITION,
                    "Safe idempotency retry window has closed",
                    details={"reason": "idempotency_window_closed"},
                )
            try:
                result: object = spec.handler(cmd, ctx, uow)  # handler
            except SkmError as err:
                _raise_if_denial(uow, err, spec.permission, chain)
                raise
            result_json = self._valid_result(spec.result, result, spec.name)
            now = self._clock.now()
            if key is not None and not is_waiting(result):  # receipt: Waiting stores none
                urn: str = getattr(spec.result, "SCHEMA_URN", "")
                receipt_json = self._schemas.validator(urn).without_secret_properties(result_json)
                if receipt_json != result_json:
                    try:
                        self._schemas.require_valid(urn, receipt_json)
                    except ValidationFailed as err:
                        raise InternalError(
                            ErrorCode.INTERNAL_ERROR,
                            "command result requires secret fields in replay",
                            details={"operation": spec.name},
                        ) from err
                uow.repo(IdempotencyStore).put(
                    IdempotencyReceipt(
                        workspace_id=workspace_id,
                        principal_id=actor.principal_id,
                        operation=spec.name,
                        key=key,
                        request_digest=digest_value,
                        result=receipt_json,
                        created_at=now,
                        expires_at=now + self._ttl,
                    )
                )
            if record_allowed:  # audit
                uow.repo(AuditLog).append(
                    AuditRecord(
                        id=self._ids.new_id(),
                        workspace_id=workspace_id,
                        actor_id=actor.principal_id,
                        action=spec.name,
                        target=audit_target(scope_ref(chain[-1]), spec.permission),
                        decision="allowed",
                        reason_code=None,
                        request_id=meta.request_id,
                        recorded_at=now,
                    )
                )
            uow.commit()  # commit: state + events + outbox + receipt + audit together
            return result

    def _replay_receipt(
        self,
        spec: AnyCommandSpec,
        cmd: object,
        basis: AuthBasis,
        meta: RequestMeta,
        key: str,
        digest_value: str,
        original: Conflict,
    ) -> object:
        """A concurrent duplicate lost the race; the command UoW is closed, a new one reads the receipt."""
        actor = basis.actor
        with self._uow_factory(meta, readonly=True, isolation=Isolation.REPEATABLE_READ) as uow:
            chain, resolved = self._chain_of(uow, spec, cmd)
            for permission in required_permissions(spec, cmd):  # authorize again before any result
                self._authorize(
                    uow,
                    basis,
                    permission,
                    chain,
                    opaque=resolved,
                    alternatives=spec.permission_alternatives if permission == spec.permission else (),
                )
            receipt = uow.repo(IdempotencyStore).get(workspace_of(chain), actor.principal_id, spec.name, key)
            if receipt is not None and spec.replay_guard is not None:
                ctx = CommandContext(
                    actor=actor,
                    meta=meta,
                    scope=scope_ref(chain[-1]),
                    scope_chain=chain,
                    clock=self._clock,
                    ids=self._ids,
                    entropy=self._entropy,
                    config=self._effective(uow, chain),
                    log=_module_log(spec.name),
                    gateways=self._gateways,
                    allows=lambda permission, target: (
                        self._authorize_decision(uow, basis, permission, target).allowed
                    ),
                    auth_basis=basis,
                )
                try:
                    spec.replay_guard(cmd, ctx, uow)
                except SkmError as err:
                    _raise_if_denial(uow, err, spec.permission, chain)
                    raise
            uow.rollback()
        if receipt is None:
            raise original
        return from_receipt(spec, receipt, digest_value)

    def _with_retry(self, attempt: Callable[[], object]) -> object:
        """40001/40P01: rollback and a new UoW from uow.begin, scope/authz/config included."""
        for n in range(1, self._retry.max_attempts + 1):
            try:
                return attempt()
            except Conflict as err:
                if err.code is not ErrorCode.SERIALIZATION_FAILURE or n >= self._retry.max_attempts:
                    raise
                delay = min(self._retry.base_delay_seconds * 2 ** (n - 1), self._retry.max_delay_seconds)
                _log.info("uow.commit.retry", count=n, duration_ms=int(delay * 1000))
                time.sleep(delay * random.uniform(0.5, 1.5))  # jitter ±50 % (adapters §1.3), not security
        raise InternalError(ErrorCode.INTERNAL_ERROR, "retry policy allows no attempt")

    # ------------------------------------------------------------------ queries
    def ask(
        self,
        query: object,
        *,
        actor: Actor,
        meta: RequestMeta,
        auth_basis: AuthBasis | None = None,
    ) -> object:
        return self.ask_with_meta(query, actor=actor, meta=meta, auth_basis=auth_basis)[0]

    def ask_with_meta(
        self,
        query: object,
        *,
        actor: Actor,
        meta: RequestMeta,
        auth_basis: AuthBasis | None = None,
    ) -> tuple[object, QueryMeta]:
        basis = _resolve_basis(actor, auth_basis)
        meta = bind_meta(meta)
        with bind(
            request_id=meta.request_id,
            correlation_id=meta.correlation_id,
            causation_id=meta.causation_id,
            actor_id=str(actor.principal_id),
            surface=meta.surface.value,
        ):
            try:
                return self._query(query, basis, meta)
            except SkmError:
                raise
            except Exception as exc:
                # The caller sees only INTERNAL_ERROR with the request id; this line is what the id finds.
                _log.error("bus.query.failed", exc=exc, code=ErrorCode.INTERNAL_ERROR.value)
                raise InternalError(
                    ErrorCode.INTERNAL_ERROR, "unexpected error", details={"request_id": meta.request_id}
                ) from exc

    def _query(self, query: object, basis: AuthBasis, meta: RequestMeta) -> tuple[object, QueryMeta]:
        actor = basis.actor
        spec = self._registry.query(type(query))
        self._require_valid_dto(spec.dto.SCHEMA_URN, query)  # validate_dto
        scope = spec.scope_of(query) if spec.scope_of is not None else None
        if not kind_allowed(spec, basis):
            self._record_denied(actor, spec.name, _kind_denial(spec.permission, scope), meta)
        try:
            return self._ask_once(spec, query, basis, meta, scope)
        except _Denied as denied:
            self._record_denied(actor, spec.name, denied, meta)

    def _ask_once(
        self, spec: AnyQuerySpec, query: object, basis: AuthBasis, meta: RequestMeta, scope: ScopeRef | None
    ) -> tuple[object, QueryMeta]:
        actor = basis.actor
        with self._uow_factory(meta, readonly=True, isolation=spec.isolation) as uow:
            chain, resolved = self._chain_of(uow, spec, query, scope)
            self._authorize(
                uow, basis, spec.permission, chain, opaque=resolved, alternatives=spec.permission_alternatives
            )
            effective = self._effective(uow, chain)
            workspace_id = workspace_of(chain)  # events_cursor before the handler: data never older
            cursor = None
            if workspace_id is not None:
                cursor = uow.repo(EventReader).head_workspace_seq(workspace_id)
            ctx = QueryContext(
                actor=actor,
                meta=meta,
                scope=scope_ref(chain[-1]),
                scope_chain=chain,
                clock=self._clock,
                config=effective,
                log=_module_log(spec.name),
                gateways=self._gateways,
                allows=lambda permission, target: (
                    self._authorize_decision(uow, basis, permission, target).allowed
                ),
                auth_basis=basis,
            )
            try:
                result: object = spec.handler(query, ctx, uow)
            except SkmError as err:
                _raise_if_denial(uow, err, spec.permission, chain)
                raise
            self._valid_result(spec.result, result, spec.name)  # validate_result
            if cursor is None and isinstance(res_ws := getattr(result, "workspace_id", None), UUID):
                cursor = uow.repo(EventReader).head_workspace_seq(WorkspaceId(res_ws))
            if cursor is None and isinstance(view_cursor := getattr(result, "events_cursor", None), int):
                cursor = view_cursor
            uow.rollback()
            return result, QueryMeta(events_cursor=cursor)

    # ------------------------------------------------------------------ helpers
    def _chain_of(
        self,
        uow: UnitOfWork,
        spec: AnyCommandSpec | AnyQuerySpec,
        dto: object,
        named: ScopeRef | None = None,
    ) -> tuple[tuple[ScopeRecord, ...], bool]:
        """resolve_scope: the chain the permission is decided on, and whether the server resolved it.

        A scope the request names (``scope_of``) is resolved as before. For an operation that names a stored
        resource by its id the spec's ``scope_resolver`` reads the owner of that resource in this unit of
        work and the bus authorizes on it, never on a claim of the caller. An unknown resource, a scope the
        registry no longer knows and a resolver that answers ``None`` all fail closed on the instance scope.
        A denial on a resolved scope is opaque (``_Denied.opaque``): it tells the caller nothing of the
        resource, only the audit row names the real scope.
        """
        resolver = spec.scope_resolver
        if resolver is None:
            scope = named if named is not None else spec.scope_of(dto) if spec.scope_of is not None else None
            return self._scopes.chain(uow, scope), False
        try:
            resolved = cast("object", resolver(dto, uow))  # a registered spec is not checked at run time
            if resolved is not None and not isinstance(resolved, ScopeRef):
                raise InternalError(
                    ErrorCode.INTERNAL_ERROR,
                    "scope_resolver must return a ScopeRef or None",
                    details={"operation": spec.name},
                )
            return self._scopes.chain(uow, resolved), True
        except NotFound:
            return self._scopes.chain(uow, None), True

    def _require_valid_dto(self, urn: str, dto: object) -> None:
        """A request DTO the generated codec cannot encode (a non-finite number, a value outside its JSON
        types) raises ``ValueError``: that is the caller's ``SCHEMA_INVALID``, not a server defect. The text
        of the codec error is not reported. A DTO without a JSON form stays ``INTERNAL_ERROR`` (``dto_json``).
        """
        try:
            payload = dto_json(dto)
        except ValueError:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                f"instance does not match {urn}: it has no JSON form",
                details={"urn": urn, "reason": "not_json"},
            ) from None
        self._schemas.require_valid(urn, payload)

    def _effective(self, uow: UnitOfWork, chain: tuple[ScopeRecord, ...]) -> EffectiveConfig:
        return self._config.effective(uow.repo(ConfigStore), uow.repo(ScopeTree), scope_ref(chain[-1]))

    def _record_allowed(
        self, uow: UnitOfWork, chain: tuple[ScopeRecord, ...], effective: EffectiveConfig
    ) -> bool:
        """``access.audit.record_allowed`` is a work-chain key (instance/workspace levels, live).

        A host-scoped command gets the host chain as ``ctx.config``, which never resolves the key; its policy
        comes from the instance work chain (a host has no workspace), never from a host chain. A missing value
        records; an invalid or unavailable policy raises, so the command fails instead of skipping audit.
        """
        policy = effective
        if chain[-1].kind is ScopeKind.HOST:
            policy = self._config.effective(uow.repo(ConfigStore), uow.repo(ScopeTree), None, Chain.WORK)
        return policy.get("access.audit.record_allowed") is not False

    def _valid_result(self, model: type[object], result: object, operation: str) -> JsonObject:
        """A result that breaks its own schema is a handler defect: INTERNAL_ERROR, never SCHEMA_INVALID."""
        result_json = dto_json(result)
        try:
            self._schemas.require_valid(getattr(model, "SCHEMA_URN", ""), result_json)
        except (ValidationFailed, InternalError) as err:
            raise InternalError(
                ErrorCode.INTERNAL_ERROR,
                "handler returned an invalid result",
                details={"operation": operation},
            ) from err
        return result_json

    def _authorize_decision(
        self,
        uow: UnitOfWork,
        basis: AuthBasis,
        permission: str,
        chain: tuple[ScopeRecord, ...],
    ) -> AuthzDecision:
        authorize_basis = getattr(self._authorizer, "authorize_basis", None)
        if callable(authorize_basis):
            return cast("AuthzDecision", authorize_basis(uow, basis, permission, chain))
        return self._authorizer.authorize(uow, basis.actor, permission, chain)

    def _authorize(
        self,
        uow: UnitOfWork,
        basis: AuthBasis,
        permission: str | None,
        chain: tuple[ScopeRecord, ...],
        *,
        opaque: bool = False,
        alternatives: tuple[str, ...] = (),
    ) -> None:
        if permission is None:
            admit_basis = getattr(self._authorizer, "admit_basis", None)
            if callable(admit_basis):
                admit_basis(uow, basis)
                return
            admit = getattr(self._authorizer, "admit", None)
            if callable(admit):
                admit(uow, basis.actor)
            return
        decision = self._authorize_decision(uow, basis, permission, chain)
        if decision.allowed:
            return
        for candidate in alternatives:
            decision = self._authorize_decision(uow, basis, candidate, chain)
            if decision.allowed:
                return
        uow.rollback()
        # Leaving the ``with`` block returns the connection; _record_denied writes the denial afterwards.
        raise _Denied(
            scope=scope_ref(chain[-1]),
            workspace_id=workspace_of(chain),
            permission=permission,
            reason_code=decision.reason_code or ROLE_LACKS_PERMISSION,
            opaque=opaque,
        )

    def _record_denied(self, actor: Actor, action: str, denied: "_Denied", meta: RequestMeta) -> NoReturn:
        with self._uow_factory(meta, readonly=False) as audit_uow:
            audit_uow.repo(AuditLog).append(
                AuditRecord(
                    id=self._ids.new_id(),
                    workspace_id=denied.workspace_id,
                    actor_id=actor.principal_id,
                    action=action,
                    target=audit_target(denied.scope, denied.permission),
                    decision="denied",
                    reason_code=denied.reason_code,
                    request_id=meta.request_id,
                    recorded_at=self._clock.now(),
                )
            )
            audit_uow.commit()
        error = denied.error
        if error is not None:  # a denial the handler found: its own error, contract unchanged
            raise error from error.__cause__
        message = f"permission {denied.permission} is required" if denied.permission else "access denied"
        if (
            denied.opaque
        ):  # the scope came from stored state: neither its id nor the reason may reach the caller
            raise Forbidden(
                ErrorCode.FORBIDDEN,
                message,
                details={
                    "permission": denied.permission,
                    "scope": None,
                    "reason_code": ROLE_LACKS_PERMISSION,
                },
            )
        raise Forbidden(
            ErrorCode.FORBIDDEN,
            message,
            details={
                "permission": denied.permission,
                "scope": None if denied.scope is None else str(denied.scope.id),
                "reason_code": denied.reason_code,
            },
        )


@dataclass(eq=False)
class _Denied(Exception):  # internal control flow; never leaves Bus (FORBIDDEN after the denied audit)
    scope: ScopeRef | None  # None: instance scope, refused before the chain was resolved
    workspace_id: WorkspaceId | None
    permission: str | None
    reason_code: str
    error: SkmError | None = None  # the handler's error to raise after the audit; None: the bus's FORBIDDEN
    opaque: bool = False  # the scope was resolved from stored state: the FORBIDDEN names neither it nor why


def _kind_denial(permission: str | None, scope: ScopeRef | None) -> _Denied:
    # Refused before BEGIN: the scope is not resolved (None = instance); the audit row still names it.
    return _Denied(scope=scope, workspace_id=None, permission=permission, reason_code=KIND_NOT_ALLOWED)


def _raise_if_denial(
    uow: UnitOfWork, err: SkmError, permission: str | None, chain: tuple[ScopeRecord, ...]
) -> None:
    """A denial the handler found leaves the UoW rolled back as ``_Denied``; any other error returns.

    The audit takes the reason the handler's ``Forbidden`` reports, the one of the decision that refused
    (settings ``Rights`` keeps each ``AuthzDecision`` and R13/R16 report its ``reason_code``). The bus never
    asks the ``Authorizer`` again for it: a later decision may see other facts and proves nothing about the
    refusal. Without a reported reason (a decision that gave none, a handler's own guard) the row keeps the
    bus default ``ROLE_LACKS_PERMISSION`` (a denied audit row always carries one); that fallback is not
    evidence of a role gap and stays an open gap until an agreed representation of an unknown reason exists.
    """
    forbidden = _handler_denial(err)
    if forbidden is None:
        return
    uow.rollback()  # nothing of the handler stays; the denied audit follows in its own UoW
    raise _Denied(
        scope=scope_ref(chain[-1]),
        workspace_id=workspace_of(chain),
        permission=_detail(forbidden, "permission") or permission,
        reason_code=_detail(forbidden, "reason_code") or ROLE_LACKS_PERMISSION,
        error=err,
    ) from err


def _handler_denial(err: SkmError) -> Forbidden | None:
    """The ``Forbidden`` of a denial a handler found: the error itself or the first one in its explicit
    ``from`` chain, at any depth. An implicit ``__context__`` is not followed and a cyclic chain ends at its
    first repeated error. Any other error, a validation error included, is not a denial."""
    seen: set[int] = set()
    found: BaseException | None = err
    while found is not None and id(found) not in seen:
        if isinstance(found, Forbidden):
            return found
        seen.add(id(found))
        found = found.__cause__
    return None


def _detail(err: SkmError, name: str) -> str | None:
    value = err.details.get(name)
    return value if isinstance(value, str) and value else None


def _module_log(operation: str) -> StructLogger:
    return get_logger(f"modules.{operation.split('.', 1)[0]}")


def _resolve_basis(actor: Actor, auth_basis: AuthBasis | None) -> AuthBasis:
    if auth_basis is None:
        return AuthBasis.from_actor(actor)
    if auth_basis.actor != actor:
        raise ValueError("auth_basis.actor must match actor")
    return auth_basis


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
