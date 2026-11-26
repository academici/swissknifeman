"""Contract declarations; behavior is implemented by the owning leaf."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from skm.kernel.ids import HostId, PrincipalId
    from skm.modules.runtimes.domain.capability import CapabilityRecord, VerificationContext
    from skm.modules.runtimes.domain.ids import RuntimeId


@dataclass(frozen=True, slots=True)
class DetectProbe:
    host_id: HostId
    binary: str | None
    env_allowlist: tuple[str, ...]
    timeout_seconds: int


@dataclass(frozen=True, slots=True)
class CancellationResult:
    stopped: bool
    signal_used: str | None
    ignored: bool


@dataclass(frozen=True, slots=True)
class VerificationRecord:
    runtime_id: RuntimeId
    runtime_version: str | None
    verification_context: VerificationContext | None
    verification_key: str | None
    record: CapabilityRecord
    recorded_by: PrincipalId
