"""Relational model catalog records and host observations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed

from .ids import is_runtime_id, require_utc

if TYPE_CHECKING:
    from datetime import date, datetime
    from uuid import UUID

    from skm.kernel.ids import HostId, ResourceVersionId, WorkerId

    from .catalog import ModelStatus, Pricing
    from .classes import Effort, ModelClass, RoleId
    from .ids import ModelId, RuntimeId
    from .installation import RuntimeInstallation


WORKER_OFFER_TTL = timedelta(minutes=5)


def _check_model_id(value: ModelId, field: str) -> None:
    if not value or "\x00" in value:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "invalid model identifier", details={"field": field})


@dataclass(frozen=True, slots=True)
class CanonicalModel:
    model_id: ModelId

    def __post_init__(self) -> None:
        _check_model_id(self.model_id, "model_id")


@dataclass(frozen=True, slots=True)
class ProviderModelOffering:
    runtime_id: RuntimeId
    model_id: ModelId
    provider_model_id: ModelId
    display_name: str
    context_window_tokens: int
    max_output_tokens: int | None
    patterns: tuple[str, ...]
    status: ModelStatus
    verified_at: date
    source: str
    pricing: Pricing | None

    def __post_init__(self) -> None:
        _check_model_id(self.model_id, "model_id")
        _check_model_id(self.provider_model_id, "provider_model_id")
        if not is_runtime_id(self.runtime_id):
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "invalid runtime identifier")
        if self.context_window_tokens < 1000 or (
            self.max_output_tokens is not None and self.max_output_tokens < 0
        ):
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "invalid offering token limits")


@dataclass(frozen=True, slots=True)
class ModelGuideline:
    resource_version_id: ResourceVersionId
    runtime_id: RuntimeId
    model_id: ModelId
    classes: frozenset[ModelClass]
    suited_roles: frozenset[RoleId]
    notes: str


@dataclass(frozen=True, slots=True)
class HostModelAvailability:
    host_id: HostId
    runtime_id: RuntimeId
    model_id: ModelId
    effort: Effort
    observed_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        _check_model_id(self.model_id, "model_id")
        if not is_runtime_id(self.runtime_id):
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "invalid runtime identifier")
        require_utc(self.observed_at, "observed_at")
        require_utc(self.expires_at, "expires_at")
        if self.expires_at <= self.observed_at:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID, "model availability must expire after observation"
            )


@dataclass(frozen=True, slots=True)
class WorkerModelSnapshot:
    """Complete replaceable observations from one registered worker and credential."""

    worker_id: WorkerId
    publisher_token_id: UUID
    observed_at: datetime
    expires_at: datetime
    installations: tuple[RuntimeInstallation, ...]
    offers: tuple[HostModelAvailability, ...]

    def __post_init__(self) -> None:
        require_utc(self.observed_at, "observed_at")
        require_utc(self.expires_at, "expires_at")
        if self.expires_at <= self.observed_at:
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Worker snapshot must expire after observation")

    def fresh_at(self, now: datetime) -> bool:
        return self.observed_at <= now < self.expires_at

    def supersedes(self, current: WorkerModelSnapshot) -> bool:
        return self.publisher_token_id != current.publisher_token_id or self.observed_at > current.observed_at
