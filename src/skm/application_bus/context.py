"""Contexts of control-plane code: bus handlers, subscribers, external consumers (kernel-platform §4.2).

Host operations get ``HostContext`` (``application_bus/host.py``) instead; the two kinds are separate types.
``gateways`` here is always a ``GatewayTable(kind="control_plane_gateway")``. Only the bus (``bus.py``) and
the outbox relay build these contexts; handlers never construct them.

``SubscriberContext.config_for`` reads the work chain of one scope of the event workspace in the delivery
unit of work (``subscribers.py``); ``ExternalConsumerContext.secrets`` resolves the ``SecretRef`` values of a
delivery plan (``platform/config/secrets.py``).
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from skm.kernel.actor import SYSTEM_PRINCIPAL_ID, Actor, PrincipalKind, TokenGrant
from skm.kernel.clock import Clock
from skm.kernel.entropy import EntropySource
from skm.kernel.gateways import Gateways
from skm.kernel.id_generator import IdGenerator
from skm.kernel.ids import PrincipalId
from skm.kernel.ports_uow import RequestMeta
from skm.kernel.scopes import ScopeRecord, ScopeRef
from skm.platform.config.effective import EffectiveConfig
from skm.platform.config.secrets import SecretResolver
from skm.platform.logging.logger import StructLogger

__all__ = [
    "AuthBasis",
    "AuthBasisKind",
    "CommandContext",
    "ExternalConsumerContext",
    "QueryContext",
    "SubscriberContext",
]

type ScopeAuthorizer = Callable[[str, tuple[ScopeRecord, ...]], bool]


class AuthBasisKind(StrEnum):
    """Authenticated credential basis carried across HTTP, bus, SSE, and live streams."""

    BEARER = "bearer"
    SESSION = "session"
    LOCAL_OWNER = "local_owner"
    SYSTEM = "system"


@dataclass(frozen=True, slots=True)
class AuthBasis:
    """Unified authenticated credential basis preserving revocation and ceiling metadata.

    - ``BEARER`` carries the authenticating ``Actor.grant`` ceiling and ``token_id``; when a same-subject
      session cookie was also presented, ``session_id`` / ``session_expires_at`` are retained as metadata
      while the Bearer grant remains authoritative.
    - ``SESSION`` carries ``session_id`` (and optional ``session_expires_at``) for a human web session with
      no token grant ceiling.
    - ``LOCAL_OWNER`` carries the resolved local human owner in loopback-only ``none`` mode or local CLI.
    - ``SYSTEM`` carries internal/system actors without a user credential.
    """

    kind: AuthBasisKind
    actor: Actor
    token_id: UUID | None = None
    session_id: UUID | None = None
    session_expires_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.kind is AuthBasisKind.BEARER:
            self._validate_bearer()
        elif self.kind is AuthBasisKind.SESSION:
            self._validate_session()
        else:
            self._validate_grantless()

    def _validate_bearer(self) -> None:
        if self.actor.grant is None:
            raise ValueError("bearer AuthBasis requires Actor.grant")
        if self.token_id is None:
            object.__setattr__(self, "token_id", self.actor.grant.token_id)
        elif self.token_id != self.actor.grant.token_id:
            raise ValueError("bearer AuthBasis.token_id must match Actor.grant.token_id")

    def _validate_session(self) -> None:
        if self.actor.grant is not None:
            raise ValueError("session AuthBasis cannot carry a TokenGrant")
        if self.actor.kind is not PrincipalKind.HUMAN:
            raise ValueError("session AuthBasis requires a human principal")
        if self.session_id is None:
            raise ValueError("session AuthBasis requires session_id")
        if self.token_id is not None:
            raise ValueError("session AuthBasis cannot carry token_id")

    def _validate_grantless(self) -> None:
        label = self.kind.value
        if self.actor.grant is not None:
            raise ValueError(f"{label} AuthBasis cannot carry a TokenGrant")
        if self.kind is AuthBasisKind.LOCAL_OWNER and self.actor.kind is not PrincipalKind.HUMAN:
            raise ValueError("local_owner AuthBasis requires a human principal")
        if any(value is not None for value in (self.token_id, self.session_id, self.session_expires_at)):
            raise ValueError(f"{label} AuthBasis cannot carry token or session metadata")

    @property
    def grant(self) -> TokenGrant | None:
        return self.actor.grant

    @property
    def principal_id(self) -> PrincipalId:
        return self.actor.principal_id

    @property
    def auth_method(self) -> Literal["bearer", "session", "none"]:
        if self.kind is AuthBasisKind.BEARER:
            return "bearer"
        if self.kind is AuthBasisKind.SESSION:
            return "session"
        return "none"

    @property
    def stream_quota_key(self) -> tuple[str, UUID]:
        """Per-credential key for concurrent SSE and live attempt stream quotas."""
        if self.kind is AuthBasisKind.BEARER and self.token_id is not None:
            return ("token", self.token_id)
        if self.kind is AuthBasisKind.SESSION and self.session_id is not None:
            return ("session", self.session_id)
        return (self.kind.value, UUID(str(self.actor.principal_id)))

    @property
    def is_worker_token(self) -> bool:
        """True only for an authenticated worker principal presenting a worker Bearer token."""
        return (
            self.kind is AuthBasisKind.BEARER
            and self.actor.kind is PrincipalKind.WORKER
            and self.actor.grant is not None
            and self.actor.grant.kind == "worker"
        )

    @classmethod
    def bearer(
        cls,
        actor: Actor,
        *,
        session_id: UUID | None = None,
        session_expires_at: datetime | None = None,
    ) -> "AuthBasis":
        if actor.grant is None:
            raise ValueError("bearer AuthBasis requires Actor.grant")
        return cls(
            kind=AuthBasisKind.BEARER,
            actor=actor,
            token_id=actor.grant.token_id,
            session_id=session_id,
            session_expires_at=session_expires_at,
        )

    @classmethod
    def session(
        cls,
        actor: Actor,
        *,
        session_id: UUID,
        expires_at: datetime | None = None,
    ) -> "AuthBasis":
        return cls(
            kind=AuthBasisKind.SESSION,
            actor=actor,
            session_id=session_id,
            session_expires_at=expires_at,
        )

    @classmethod
    def local_owner(cls, actor: Actor) -> "AuthBasis":
        return cls(kind=AuthBasisKind.LOCAL_OWNER, actor=actor)

    @classmethod
    def system(cls, actor: Actor) -> "AuthBasis":
        return cls(kind=AuthBasisKind.SYSTEM, actor=actor)

    @classmethod
    def from_actor(cls, actor: Actor) -> "AuthBasis":
        """Derive the default credential basis when a caller supplies only an ``Actor``."""
        if actor.grant is not None:
            return cls.bearer(actor)
        if actor.kind is PrincipalKind.HUMAN:
            return cls.local_owner(actor)
        if actor.principal_id == SYSTEM_PRINCIPAL_ID and actor.kind is PrincipalKind.SERVICE:
            return cls.system(actor)
        return cls.system(actor)


@dataclass(frozen=True, slots=True)
class CommandContext:
    actor: Actor
    meta: RequestMeta
    scope: ScopeRef  # resolved command scope (instance when scope_of is None)
    scope_chain: tuple[ScopeRecord, ...]
    clock: Clock
    ids: IdGenerator
    entropy: EntropySource
    config: EffectiveConfig  # of scope_chain, work chain; read in the command UoW
    log: StructLogger  # component "modules.<module>", request_id/actor_id bound
    gateways: Gateways  # control-plane gateways only
    allows: ScopeAuthorizer | None = None  # current actor, within the handler's UoW
    auth_basis: AuthBasis | None = None  # authenticated credential basis for this request

    def __post_init__(self) -> None:
        if self.auth_basis is None:
            object.__setattr__(self, "auth_basis", AuthBasis.from_actor(self.actor))
        elif self.auth_basis.actor != self.actor:
            raise ValueError("CommandContext.auth_basis.actor must match actor")


@dataclass(frozen=True, slots=True)
class QueryContext:
    actor: Actor
    meta: RequestMeta
    scope: ScopeRef
    scope_chain: tuple[ScopeRecord, ...]
    clock: Clock
    config: EffectiveConfig
    log: StructLogger
    gateways: Gateways  # control-plane gateways only
    allows: ScopeAuthorizer | None = None  # current actor, within the handler's UoW
    auth_basis: AuthBasis | None = None  # authenticated credential basis for this request

    def __post_init__(self) -> None:
        if self.auth_basis is None:
            object.__setattr__(self, "auth_basis", AuthBasis.from_actor(self.actor))
        elif self.auth_basis.actor != self.actor:
            raise ValueError("QueryContext.auth_basis.actor must match actor")


@dataclass(frozen=True, slots=True)
class SubscriberContext:
    consumer_id: str
    attempt: int
    clock: Clock
    ids: IdGenerator
    log: StructLogger
    config: EffectiveConfig  # of the event scope (workspace or instance)
    gateways: Gateways  # control-plane gateways only
    config_for: Callable[[ScopeRef], EffectiveConfig]  # any scope of the event workspace, delivery UoW


@dataclass(frozen=True, slots=True)
class ExternalConsumerContext:
    """Process-level dependencies of an external consumer; config is read per delivery."""

    log: StructLogger
    clock: Clock
    secrets: SecretResolver
    gateways: Gateways  # control-plane gateways only
