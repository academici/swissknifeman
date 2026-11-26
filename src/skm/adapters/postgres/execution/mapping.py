"""Shared PostgreSQL helpers, error translation, and payload validators for ``skm_execution``."""

from __future__ import annotations

import functools
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final, cast

import psycopg
import psycopg_pool

from skm.adapters.postgres.errors import translate_pg_error
from skm.adapters.postgres.jsonb import require_aware, to_jsonb
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import (
    InternalError,
    PreconditionFailed,
    ValidationFailed,
)
from skm.kernel.json_types import JsonObject
from skm.modules.execution.domain import stored_payloads as stored
from skm.modules.execution.domain.attempt import (
    Attempt,
)
from skm.modules.execution.domain.frozen_json import thaw_json
from skm.modules.execution.domain.lease import ProcessIdentity
from skm.modules.execution.domain.step import AttemptStep
from skm.modules.execution.domain.stored_payloads import (
    field_owned,
)
from skm.modules.runtimes.domain.usage import usage_to_json as runtime_usage_to_json
from skm.modules.runtimes.public import SubagentUsage, UsageReport, UsageStatus
from skm.platform.schema.registry import SchemaRegistry

if TYPE_CHECKING:
    from skm.modules.execution.domain.readiness import ReadinessReport

__all__: list[str] = []

FIX_BRIEF_URN: Final = "urn:skm:execution:fix-brief:v1"

type DictRow = dict[str, Any]


@functools.cache
def schema_registry() -> SchemaRegistry:
    return SchemaRegistry.load_default()


def validate_step_payloads(step: AttemptStep, old_step: AttemptStep | None) -> None:
    stored.validate_step_payloads(step, old_step, require_valid=schema_registry().require_valid)


def validate_continuation_payload(attempt: Attempt, old_attempt: Attempt | None) -> None:
    stored.validate_continuation_payload(attempt, old_attempt, require_valid=schema_registry().require_valid)


def run[T](call: Callable[[], T]) -> T:
    """Execute ``call`` and translate ``psycopg`` driver exceptions, including ``23001`` triggers."""
    try:
        return call()
    except (psycopg.Error, psycopg_pool.PoolTimeout) as exc:
        if exc.sqlstate == "23001":
            msg = exc.diag.message_primary or str(exc)
            lower = msg.lower()
            if (
                "late observation" in lower
                or "only applied -> superseded" in lower
                or "finished recovery" in lower
            ):
                err = PreconditionFailed(ErrorCode.INVALID_TRANSITION, msg)
                err.__cause__ = exc
                raise err from exc
            if "immutable" in lower or "forbidden" in lower:
                err = ValidationFailed(ErrorCode.FIELD_OWNED, msg)
                err.__cause__ = exc
                raise err from exc
        raise translate_pg_error(exc) from exc


def opt_aware(value: datetime | None) -> datetime | None:
    return None if value is None else require_aware(value)


def opt_jsonb(value: object | None) -> object | None:
    return None if value is None else to_jsonb(thaw_json(value))


def damaged(table: str, row_id: object = None, cause: Exception | None = None) -> InternalError:
    suffix = "" if row_id is None else f" {row_id}"
    err = InternalError(ErrorCode.INTERNAL_ERROR, f"corrupt skm_execution.{table} row{suffix}")
    if cause is not None:
        err.__cause__ = cause
    return err


def require_unchanged(kind: str, current: object, incoming: object, fields: Sequence[str]) -> None:
    for name in fields:
        if getattr(current, name) != getattr(incoming, name):
            raise field_owned(kind, name)


def validate_readiness_report(report: ReadinessReport) -> tuple[JsonObject | None, JsonObject | None]:
    require_aware(report.created_at)
    return stored.validate_readiness_report(report, require_valid=schema_registry().require_valid)


def usage_to_json(usage: UsageReport | None) -> JsonObject | None:
    return None if usage is None else runtime_usage_to_json(usage)


def usage_from_json(raw: object) -> UsageReport | None:
    if raw is None:
        return None
    doc = cast("Mapping[str, Any]", raw)
    sub = cast("Mapping[str, Any]", doc.get("subagents") or {})
    return UsageReport(
        input_tokens=doc.get("input_tokens"),
        output_tokens=doc.get("output_tokens"),
        cache_read_tokens=doc.get("cache_read_tokens"),
        cache_write_tokens=doc.get("cache_write_tokens"),
        reasoning_tokens=doc.get("reasoning_tokens"),
        cost_usd_micros=doc.get("cost_usd_micros"),
        status=UsageStatus(str(doc["status"])),
        source=str(doc["source"]),
        subagents=SubagentUsage(used=sub.get("used"), disclosed=bool(sub.get("disclosed", False))),
    )


def process_identity_to_json(pi: ProcessIdentity | None) -> JsonObject | None:
    if pi is None:
        return None
    return {
        "pid": pi.pid,
        "pgid": pi.pgid,
        "started_at": require_aware(pi.started_at).isoformat(),
        "ownership": cast("JsonObject", thaw_json(pi.ownership)),
        "boot_id": pi.boot_id,
        "session_ref": pi.session_ref,
        "start_ticks": pi.start_ticks,
    }


def process_identity_from_json(raw: object) -> ProcessIdentity | None:
    if raw is None:
        return None
    doc = cast("Mapping[str, Any]", raw)
    return ProcessIdentity(
        pid=doc.get("pid"),
        pgid=doc.get("pgid"),
        started_at=datetime.fromisoformat(str(doc["started_at"])),
        ownership=cast("JsonObject", thaw_json(doc["ownership"])),
        boot_id=doc.get("boot_id"),
        session_ref=doc.get("session_ref"),
        start_ticks=doc.get("start_ticks"),
    )
