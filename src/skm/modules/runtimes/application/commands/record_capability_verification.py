"""``runtimes.record_capability_verification`` (runtimes §7.2): append exact capability evidence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Self, cast, get_args
from uuid import UUID

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, ValidationFailed
from skm.kernel.ids import HostId, ScopeId
from skm.kernel.isolation import parse_isolation_profile
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.runtimes.domain.capability import (
    Capability,
    CapabilityRecord,
    CapabilityStatus,
    VerificationContext,
    verification_context_key,
)
from skm.modules.runtimes.domain.detection import VerificationRecord
from skm.modules.runtimes.domain.events import CapabilityVerified
from skm.modules.runtimes.generated.results import Capability as ResultCapability
from skm.modules.runtimes.generated.results import RecordCapabilityVerificationResult
from skm.modules.runtimes.ports import CapabilityCatalog, CapabilityVerificationRepository
from skm.modules.workspace import public as workspace

if TYPE_CHECKING:
    from skm.kernel.json_types import JsonValue

__all__ = ["SPEC", "RecordCapabilityVerification", "handle"]


type _Status = Literal["native", "adapted", "unsupported", "unknown"]


def _status(raw: object) -> _Status:
    for status in get_args(_Status.__value__):
        if raw == status:
            return status
    raise ValueError(f"unknown capability status {raw!r}")


@dataclass(frozen=True, slots=True)
class RecordCapabilityVerification:
    """Bus command DTO for ``urn:skm:runtimes:command:record-capability-verification:v1`` (§7.2)."""

    runtime_id: str
    runtime_version: str | None
    capability: str
    status: _Status
    evidence: str
    limitations: str
    verified_at: date
    verification_context: VerificationContext | Mapping[str, object] | None = None

    SCHEMA_URN: ClassVar[str] = "urn:skm:runtimes:command:record-capability-verification:v1"

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> Self:
        try:
            verified_raw = data["verified_at"]
            verified_at = (
                verified_raw if isinstance(verified_raw, date) else date.fromisoformat(str(verified_raw))
            )
            ctx_raw = data.get("verification_context")
            vctx: VerificationContext | Mapping[str, object] | None
            if ctx_raw is None:
                vctx = None
            elif isinstance(ctx_raw, VerificationContext):
                vctx = ctx_raw
            elif isinstance(ctx_raw, Mapping):
                vctx = {str(k): v for k, v in cast("Mapping[object, object]", ctx_raw).items()}
            else:
                raise ValueError("verification_context must be an object or null")
            return cls(
                runtime_id=str(data["runtime_id"]),
                runtime_version=None if data["runtime_version"] is None else str(data["runtime_version"]),
                capability=str(data["capability"]),
                status=_status(data["status"]),
                evidence=str(data["evidence"]),
                limitations=str(data["limitations"]),
                verified_at=verified_at,
                verification_context=vctx,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "invalid record_capability_verification payload",
                details={"urn": cls.SCHEMA_URN},
            ) from exc

    def to_json(self) -> dict[str, object]:
        ctx_json: dict[str, object] | None
        if self.verification_context is None:
            ctx_json = None
        elif isinstance(self.verification_context, VerificationContext):
            ctx_json = {
                "host_id": str(self.verification_context.host_id),
                "binary_sha256": self.verification_context.binary_sha256,
                "os": self.verification_context.os,
                "kernel": self.verification_context.kernel,
                "adapter_version": self.verification_context.adapter_version,
                "isolation_profile": str(self.verification_context.isolation_profile),
                "launch_config_digest": self.verification_context.launch_config_digest,
            }
        else:
            ctx_json = {str(k): v for k, v in self.verification_context.items()}
            if "host_id" in ctx_json and isinstance(ctx_json["host_id"], UUID):
                ctx_json["host_id"] = str(ctx_json["host_id"])
            if "isolation_profile" in ctx_json and ctx_json["isolation_profile"] is not None:
                ctx_json["isolation_profile"] = str(ctx_json["isolation_profile"])

        cap_val = self.capability.value if isinstance(self.capability, Capability) else self.capability
        status_val = self.status.value if isinstance(self.status, CapabilityStatus) else self.status
        return {
            "runtime_id": str(self.runtime_id),
            "runtime_version": self.runtime_version,
            "capability": str(cap_val),
            "status": str(status_val),
            "evidence": self.evidence,
            "limitations": self.limitations,
            "verified_at": self.verified_at.isoformat(),
            "verification_context": ctx_json,
        }


def _scope_of(cmd: RecordCapabilityVerification) -> ScopeRef | None:
    ctx = cmd.verification_context
    if ctx is None:
        return None
    if isinstance(ctx, VerificationContext):
        return ScopeRef(ScopeKind.HOST, ScopeId(ctx.host_id))
    if ctx.get("host_id") is not None:
        try:
            return ScopeRef(ScopeKind.HOST, ScopeId(UUID(str(ctx["host_id"]))))
        except ValueError:
            return None
    return None


def _parse_context(raw: VerificationContext | Mapping[str, object] | None) -> VerificationContext | None:
    if raw is None:
        return None
    if isinstance(raw, VerificationContext):
        return raw
    if not isinstance(raw, Mapping):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "verification_context must be an object or null",
            details={"field": "verification_context"},
        )
    required = (
        "host_id",
        "binary_sha256",
        "os",
        "kernel",
        "adapter_version",
        "isolation_profile",
        "launch_config_digest",
    )
    missing: list[JsonValue] = [key for key in required if key not in raw or raw[key] is None]
    if missing:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "incomplete verification_context",
            details={"field": "verification_context", "missing": missing},
        )
    if any(key not in required for key in raw):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "unexpected keys in verification_context",
            details={"field": "verification_context"},
        )
    try:
        return VerificationContext(
            host_id=HostId(UUID(str(raw["host_id"]))),
            binary_sha256=str(raw["binary_sha256"]),
            os=str(raw["os"]),
            kernel=str(raw["kernel"]),
            adapter_version=str(raw["adapter_version"]),
            isolation_profile=parse_isolation_profile(str(raw["isolation_profile"])),
            launch_config_digest=str(raw["launch_config_digest"]),
        )
    except (TypeError, ValueError) as exc:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            f"invalid verification_context: {exc}",
            details={"field": "verification_context"},
        ) from exc


def handle(
    cmd: RecordCapabilityVerification,
    ctx: CommandContext,
    uow: UnitOfWork,
) -> RecordCapabilityVerificationResult:
    registered = ctx.gateways.get(CapabilityCatalog).registered()
    if cmd.runtime_id not in registered:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            f"unknown runtime {cmd.runtime_id!r}",
            details={"runtime_id": cmd.runtime_id, "reason": "unknown_runtime"},
        )

    try:
        cap = Capability(cmd.capability)
        status = CapabilityStatus(cmd.status)
    except ValueError as exc:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            f"unknown capability or status: {exc}",
            details={"capability": str(cmd.capability), "status": str(cmd.status)},
        ) from exc

    if cmd.runtime_version is not None and not (1 <= len(cmd.runtime_version) <= 100):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "runtime_version must be 1..100 characters",
            details={"field": "runtime_version"},
        )
    if not (1 <= len(cmd.evidence) <= 500):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "evidence must be 1..500 characters",
            details={"field": "evidence"},
        )
    if len(cmd.limitations) > 2000:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "limitations must be at most 2000 characters",
            details={"field": "limitations"},
        )

    vctx = _parse_context(cmd.verification_context)
    if vctx is None:
        if ctx.actor.kind is PrincipalKind.WORKER:
            raise Forbidden(
                ErrorCode.FORBIDDEN,
                "worker actors must supply a host-bound verification_context",
                details={"reason": "missing_host_context"},
            )
        vkey = None
    else:
        workspace.get_host(uow, vctx.host_id)
        if ctx.actor.kind is PrincipalKind.WORKER:
            worker = workspace.worker_for_principal(uow, ctx.actor.principal_id)
            if worker is None or worker.host_id != vctx.host_id:
                raise Forbidden(
                    ErrorCode.FORBIDDEN,
                    "worker may only record capability verifications for its own host",
                    details={"host_id": str(vctx.host_id), "reason": "foreign_host"},
                )
        vkey = verification_context_key(vctx)

    record = VerificationRecord(
        runtime_id=cmd.runtime_id,
        runtime_version=cmd.runtime_version,
        verification_context=vctx,
        verification_key=vkey,
        record=CapabilityRecord(
            capability=cap,
            status=status,
            evidence=cmd.evidence,
            tested_runtime_version=cmd.runtime_version,
            limitations=cmd.limitations,
            last_verified_at=cmd.verified_at,
            verification_context=vctx,
        ),
        recorded_by=ctx.actor.principal_id,
    )
    uow.repo(CapabilityVerificationRepository).add(record)
    uow.record(
        CapabilityVerified(
            runtime_id=cmd.runtime_id,
            runtime_version=cmd.runtime_version,
            capability=cap,
            status=status,
        )
    )
    return RecordCapabilityVerificationResult(
        runtime_id=cmd.runtime_id,
        capability=ResultCapability(cap.value),
        status=status.value,
    )


SPEC = CommandSpec(
    name="runtimes.record_capability_verification",
    dto=RecordCapabilityVerification,
    result=RecordCapabilityVerificationResult,
    permission="runtime.manage",
    scope_of=_scope_of,
    allowed_kinds=frozenset({PrincipalKind.HUMAN, PrincipalKind.SERVICE, PrincipalKind.WORKER}),
    idempotency=IdempotencyMode.OPTIONAL,
    handler=handle,
)
