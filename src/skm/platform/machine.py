"""Typed storage contract for one machine installation."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal, Protocol
from uuid import UUID

from skm.kernel.json_types import JsonObject, JsonValue
from skm.platform.config.secrets import SecretRef

__all__ = [
    "MachineBinding",
    "MachineCheckout",
    "MachineCheckoutKey",
    "MachinePrincipal",
    "MachineProfile",
    "MachineRetry",
    "MachineRetryKey",
    "MachineSession",
    "MachineStore",
]


@dataclass(frozen=True, slots=True)
class MachinePrincipal:
    installation_id: UUID
    instance_id: UUID
    principal_id: UUID


@dataclass(frozen=True, slots=True)
class MachineProfile:
    installation_id: UUID
    name: str
    instance_id: UUID
    origin: str
    endpoint: str | None
    credential_ref: SecretRef | None = field(default=None, repr=False)
    ca_bundle: Path | None = None
    revision: UUID | None = None


@dataclass(frozen=True, slots=True)
class MachineSession:
    profile: MachineProfile
    principal_id: UUID
    handle_hash: str = field(repr=False)
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class MachineCheckoutKey:
    installation_id: UUID
    instance_id: UUID
    host_id: UUID
    checkout_id: UUID


@dataclass(frozen=True, slots=True)
class MachineCheckout:
    key: MachineCheckoutKey
    root: Path


@dataclass(frozen=True, slots=True)
class MachineBinding:
    scope: MachinePrincipal
    checkout: MachineCheckoutKey
    workspace_id: UUID
    project_id: UUID
    repository_id: UUID


@dataclass(frozen=True, slots=True)
class MachineRetryKey:
    scope: MachinePrincipal
    checkout: MachineCheckoutKey
    operation: Literal["bind", "verify"]
    request_id: UUID
    step: str


@dataclass(frozen=True, slots=True)
class MachineRetry:
    key: MachineRetryKey
    idempotency_key: str
    payload: JsonObject
    safe_until: datetime
    receipt: JsonObject | None = None

    def state(self, now: datetime) -> Literal["pending", "expired", "confirmed"]:
        if self.receipt is not None:
            return "confirmed"
        return "pending" if now < self.safe_until else "expired"


class MachineStore(Protocol):
    """Machine IO used by trusted local gateways after their authorization checks."""

    def get_installation_id(self) -> UUID | None: ...
    def initialize_installation(self, installation_id: UUID) -> None: ...
    def get_operator_setting(self, installation_id: UUID, key: str) -> JsonValue: ...
    def set_operator_setting(self, installation_id: UUID, key: str, value: JsonValue) -> None: ...
    def get_user_setting(self, scope: MachinePrincipal, key: str) -> JsonValue: ...
    def set_user_setting(self, scope: MachinePrincipal, key: str, value: JsonValue) -> None: ...
    def get_profile(self, installation_id: UUID, name: str) -> MachineProfile | None: ...
    def list_profiles(self, installation_id: UUID) -> tuple[MachineProfile, ...]: ...
    def put_profile(self, profile: MachineProfile, *, expected: MachineProfile | None = None) -> bool:
        """Create, or atomically replace the expected profile and invalidate its sessions."""
        ...

    def delete_profile(self, profile: MachineProfile) -> bool: ...
    def get_session(
        self, installation_id: UUID, handle_hash: str, now: datetime
    ) -> MachinePrincipal | None: ...
    def put_session(self, session: MachineSession) -> bool:
        """Persist a handle after live authentication against the stored profile, for up to 15 minutes."""
        ...

    def delete_session(self, installation_id: UUID, handle_hash: str) -> None: ...
    def revoke_sessions(self, scope: MachinePrincipal) -> None: ...
    def get_checkout(self, key: MachineCheckoutKey) -> MachineCheckout | None: ...
    def reserve_checkout(self, checkout: MachineCheckout) -> MachineCheckout:
        """Return the stable ID of the canonical root supplied by the local caller."""
        ...

    def get_binding(self, scope: MachinePrincipal, checkout: MachineCheckoutKey) -> MachineBinding | None: ...
    def put_binding(self, binding: MachineBinding) -> None: ...
    def get_retry(self, key: MachineRetryKey) -> MachineRetry | None: ...
    def begin_retry(self, retry: MachineRetry) -> MachineRetry:
        """Persist before sending. Return the existing exact payload and safe window on retry."""
        ...

    def confirm_retry(self, key: MachineRetryKey, receipt: JsonObject) -> MachineRetry:
        """Persist the confirmed response. Repeated confirmation must agree with the original."""
        ...
