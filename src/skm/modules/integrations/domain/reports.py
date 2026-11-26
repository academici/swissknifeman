"""P00 declarations; behavior is implemented by the owning leaf."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from skm.kernel.ids import ProjectId

from .budget import FirstTurnSource, FirstTurnVerdict
from .target import TargetId


@dataclass(frozen=True, slots=True)
class CheckResult:
    check_id: str
    target: TargetId
    level: str
    title: str
    detail: str
    path: str | None
    hint: str | None


@dataclass(frozen=True, slots=True)
class DoctorReport:
    checks: tuple[CheckResult, ...]
    counts: Mapping[str, int]
    status: str


@dataclass(frozen=True, slots=True)
class FirstTurnReport:
    project_id: ProjectId
    target: TargetId
    thresholds: Mapping[str, int]
    sources: tuple[FirstTurnSource, ...]
    total: int | None
    verdict: FirstTurnVerdict


@dataclass(frozen=True, slots=True)
class TrustReport:
    subscription_id: str
    digest: str
    trusted: bool


@dataclass(frozen=True, slots=True)
class SpoolReport:
    replayed: int
    dead: int
    dropped: int


@dataclass(frozen=True, slots=True)
class CommandResult:
    exit_code: int | None
    stdout: bytes
    stderr: bytes
    duration_ms: int
    timed_out: bool


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    ok: bool
    retryable: bool
    reason: str | None
    status: int | None
    retry_after_ms: int | None
    response_excerpt: str | None
