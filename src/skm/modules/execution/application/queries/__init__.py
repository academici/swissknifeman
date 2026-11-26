"""Shared query helpers and result wrappers of the execution module (execution §§8, 8.1)."""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Final, Self, cast
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.ids import ScopeId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.pagination import CURSOR_MAX_LENGTH
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.execution.domain.work_policy import work_policy_to_json

if TYPE_CHECKING:
    from skm.modules.execution.domain.readiness import ReadinessReport

__all__ = [
    "MAX_LIMIT",
    "MAX_TIMELINE_LIMIT",
    "RunHistoryResult",
    "bad_cursor",
    "check_limit",
    "decode_token",
    "encode_token",
    "parse_inbox_scope",
    "readiness_report_to_json",
]

MAX_LIMIT: Final = 200
MAX_TIMELINE_LIMIT: Final = 500


@dataclass(frozen=True, slots=True)
class RunHistoryResult:
    """Typed bus result wrapper for ``urn:skm:execution:view:get-run-history:v1``."""

    run_id: UUID
    through_seq: int
    builder_version: int
    scanned_through_seq: int
    entries: tuple[JsonObject, ...]
    next_after: str | None
    coverage: str
    SCHEMA_URN: ClassVar[str] = "urn:skm:execution:view:get-run-history:v1"

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> Self:
        entries_raw = data.get("entries", ())
        entries = tuple(
            dict(cast("Mapping[str, JsonValue]", item)) for item in cast("Sequence[Any]", entries_raw)
        )
        nxt = data.get("next_after")
        return cls(
            run_id=UUID(str(data["run_id"])),
            through_seq=int(data["through_seq"]),
            builder_version=int(data["builder_version"]),
            scanned_through_seq=int(data["scanned_through_seq"]),
            entries=entries,
            next_after=None if nxt is None else str(nxt),
            coverage=str(data["coverage"]),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "run_id": str(self.run_id),
            "through_seq": self.through_seq,
            "builder_version": self.builder_version,
            "scanned_through_seq": self.scanned_through_seq,
            "entries": [deepcopy(dict(e)) for e in self.entries],
            "next_after": self.next_after,
            "coverage": self.coverage,
        }


def bad_cursor(msg: str = "cursor is not valid for this query") -> ValidationFailed:
    return ValidationFailed(ErrorCode.SCHEMA_INVALID, msg, details={"field": "after"})


def encode_token(doc: Mapping[str, JsonValue]) -> str:
    raw = json.dumps(doc, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_token(after: str) -> Mapping[str, Any]:
    if not 1 <= len(after) <= CURSOR_MAX_LENGTH or not after.isascii():
        raise bad_cursor()
    try:
        raw = base64.urlsafe_b64decode(after + "=" * (-len(after) % 4))
        parsed: object = json.loads(raw.decode("utf-8"))
    except (binascii.Error, UnicodeDecodeError, ValueError, TypeError):
        raise bad_cursor() from None
    if not isinstance(parsed, dict):
        raise bad_cursor()
    return cast("Mapping[str, Any]", parsed)


def check_limit(limit: int | None, *, default: int = 50, maximum: int = MAX_LIMIT) -> int:
    if limit is None:
        return default
    if isinstance(limit, bool) or not 1 <= limit <= maximum:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID, f"limit must be 1..{maximum}", details={"field": "limit"}
        )
    return limit


def parse_inbox_scope(scope: Mapping[str, Any]) -> ScopeRef:
    kind_raw = scope.get("kind")
    id_raw = scope.get("id")
    if kind_raw is None and "project_id" in scope and len(scope) == 1:
        kind_raw, id_raw = "project", scope.get("project_id")
    elif kind_raw is None and "run_id" in scope and len(scope) == 1:
        kind_raw, id_raw = "run", scope.get("run_id")
    if kind_raw not in ("project", "run") or not isinstance(id_raw, str):
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "invalid inbox scope", details={"field": "scope"})
    try:
        uid = UUID(id_raw)
    except ValueError:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID, "invalid inbox scope id", details={"field": "scope"}
        ) from None
    return ScopeRef(ScopeKind.PROJECT if kind_raw == "project" else ScopeKind.RUN, ScopeId(uid))


def readiness_report_to_json(rep: ReadinessReport) -> JsonObject:
    work_policies_doc: JsonObject | None = None
    if rep.work_policies is not None:
        work_policies_doc = {k: work_policy_to_json(v) for k, v in rep.work_policies.items()}
    scope_kind = "phase" if rep.scope.kind == "phases" else rep.scope.kind
    return {
        "schema": "urn:skm:execution:readiness-report:v1",
        "id": str(rep.id),
        "workspace_id": str(rep.workspace_id),
        "project_id": str(rep.project_id),
        "plan_id": str(rep.plan_id),
        "revision_id": str(rep.revision_id),
        "revision_digest": rep.revision_digest,
        "status": rep.status.value,
        "scope": {"kind": scope_kind, "phase_keys": list[JsonValue](rep.scope.phase_keys)},
        "inputs": {
            "requirements": rep.inputs.requirements,
            "dependencies": rep.inputs.dependencies,
            "write_scopes": rep.inputs.write_scopes,
            "criteria": rep.inputs.criteria,
            "capability_requirements": rep.inputs.capability_requirements,
            "policy": rep.inputs.policy,
            "config": rep.inputs.config,
            "resources": rep.inputs.resources,
            "materials": rep.inputs.materials,
        },
        "inputs_digest": rep.inputs_digest,
        "policy_digest": rep.policy_digest,
        "results": [
            {"rule_id": r.rule_id, "outcome": r.outcome, "findings_count": r.findings_count}
            for r in rep.results
        ],
        "findings": [
            {
                "code": f.code,
                "severity": f.severity,
                "entity_id": None if f.entity_id is None else str(f.entity_id),
                "message": f.message,
                "rule_id": f.rule_id,
            }
            for f in rep.findings
        ],
        "assumptions": list[JsonValue](rep.assumptions),
        "structural_counts": dict[str, JsonValue](rep.structural_counts),
        "start_request": None if rep.start_request is None else deepcopy(dict(rep.start_request)),
        "work_policies": work_policies_doc,
        "estimate": deepcopy(dict(rep.estimate)),
        "audit": None if rep.audit is None else deepcopy(dict(rep.audit)),
        "supersedes_report_id": None if rep.supersedes_report_id is None else str(rep.supersedes_report_id),
        "validator_version": rep.validator_version,
        "created_by": str(rep.created_by),
        "created_at": rep.created_at.isoformat(),
    }
