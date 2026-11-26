"""``platform.doctor`` (kernel-platform §5.2a, §5.6; settings §A.14 ``skm config doctor``).

The bus authorizes ``config.read`` at the instance scope in the read-only repeatable-read UoW before this
handler runs; only then does the handler read the scope inventory, page by page, from that same UoW.
Configured state comes from ``platform.config.diagnostics.diagnose_config`` over the complete inventory with
the registry of ``ctx.config``. Registered checks of the platform, the enabled modules and plugins are
executed host-side by bootstrap's ``DoctorCheckCollector``, outside every unit of work (kernel-platform §5.2a:
bus handlers do not execute them); this handler only reads their recorded reports through ``DoctorRunner``,
so no registered callback runs under its UoW. Restart-pending is the observation of the current process only,
composed beneath that gateway; a missing gateway, snapshot or a failed or malformed observation is reported as
unknown, never as healthy, and other processes or hosts are never claimed. An unreadable registered catalog, a
check never collected or a malformed report is likewise unknown. No nested UoW and no host IO.

Every check is ``urn:skm:kernel:check-result:v1``. Handler-owned findings carry handler-owned messages and
details of deterministic JSON identifiers, without configured values or error texts. Findings of a
registered check are built by its owner under §5.2a and passed through the process ``Redactor`` at
collection; they may not use an id of this handler or of another registered check.
"""

import json
from collections.abc import Mapping
from typing import Final, cast, get_args
from uuid import UUID

from skm.application_bus.context import QueryContext
from skm.application_bus.platform.migrations import SchemaVersionReader
from skm.application_bus.ports import (
    CurrentProcessObservation,
    DoctorRunner,
    PendingRestart,
    ProcessObservationState,
    RegisteredCheckReport,
)
from skm.application_bus.registry import QuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError, ValidationFailed
from skm.kernel.generated.documents import CheckResult, CheckResultDetails
from skm.kernel.ids import ScopeId
from skm.kernel.json_types import JsonValue
from skm.kernel.outcomes import CHECK_STATUS, CheckStatus, Severity
from skm.kernel.pagination import MAX_PAGE_LIMIT
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRecord, ScopeRegistry
from skm.platform.config.diagnostics import diagnose_config
from skm.platform.config.keys import Chain, Level
from skm.platform.config.scopes import ScopeRef as ConfigScopeRef
from skm.platform.config.store import ConfigStore, PackConfigSource, ScopeTree
from skm.platform.generated.queries import Doctor
from skm.platform.generated.results import DoctorResult

__all__ = ["CHECK_IDS", "DOCTOR", "INSTANCE_CHECK", "REGISTERED_CHECKS", "RESTART_PENDING", "handle"]

INSTANCE_CHECK: Final = "platform.instance"
RESTART_PENDING: Final = "config.restart_pending"
# Coverage of the registered catalog: a ``warn`` only when that catalog is unknown, never an ``ok``.
REGISTERED_CHECKS: Final = "doctor.registered_checks"
# Every id this handler itself can return (settings §B.15, §A.14); ``only`` selects among these and the ids
# of the checks registered behind ``DoctorRunner``. Neither a registered check nor any of its findings may
# reuse them.
CHECK_IDS: Final = frozenset(
    {
        INSTANCE_CHECK,
        "config.registry",
        "config.configured_state",
        "config.CONFIG_DIAGNOSTIC_UNKNOWN",
        RESTART_PENDING,
        REGISTERED_CHECKS,
        *(
            f"config.{code}"
            for code in (
                "CONFIG_UNKNOWN_KEY",
                "CONFIG_DEPRECATED_KEY",
                "CONFIG_SCOPE_NOT_ALLOWED",
                "CONFIG_PACK_NOT_ALLOWED",
                "CONFIG_OVERRIDE_NOT_ALLOWED",
                "CONFIG_LOCKED",
                "CONFIG_OP_NOT_ALLOWED",
                "CONFIG_NARROWING_VIOLATION",
                "CONFIG_INVALID",
            )
        ),
    }
)
_CONFIGURED: Final = CHECK_IDS - {INSTANCE_CHECK, RESTART_PENDING, REGISTERED_CHECKS}

_PAGE_LIMIT = MAX_PAGE_LIMIT
_TARGET: Final = "current_process"
_STATES: Final = frozenset(get_args(ProcessObservationState.__value__))


def _selected(
    only: tuple[str, ...] | None, catalog: frozenset[str], *, complete: bool = True
) -> frozenset[str] | None:
    """Selectors are exact check ids; ``None`` selects every check, an empty selection none.

    While the registered catalog is unknown (``complete=False``) an id outside ``catalog`` is not provably
    unknown: it is kept, and the handler reports the unknown coverage instead of refusing it.
    """
    if only is None:
        return None
    for index, check_id in enumerate(only):
        if complete and check_id not in catalog:
            # The rejected text is not echoed; the caller is authorized to see the catalog.
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "only names an unknown check",
                details={
                    "field": "only",
                    "reason": "unknown_check_id",
                    "index": index,
                    "known": [*sorted(catalog)],
                },
            )
    return frozenset(only)


def _inventory(registry: ScopeRegistry) -> tuple[ScopeRecord, ...]:
    """All scopes of the UoW snapshot: pages in ascending id order until an empty page."""
    records: list[ScopeRecord] = []
    after: ScopeId | None = None
    while page := registry.list_scopes(after=after, limit=_PAGE_LIMIT):
        if len(page) > _PAGE_LIMIT:
            raise _inventory_error("page_over_limit")
        for record in page:
            if after is not None and record.id <= after:
                raise _inventory_error("not_ascending")
            after = record.id
        records.extend(page)
    return tuple(records)


def _inventory_error(reason: str) -> InternalError:
    return InternalError(
        ErrorCode.INTERNAL_ERROR, "scope inventory is inconsistent", details={"reason": reason}
    )


def _detail(metadata: Mapping[str, JsonValue]) -> str:
    return json.dumps(dict(metadata), sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def _check(
    status: CheckStatus, message: str, target: str, metadata: Mapping[str, JsonValue], hint: str | None = None
) -> CheckResult:
    return CheckResult(
        id=RESTART_PENDING,
        status=status,
        message=message,
        hint=hint,
        details=CheckResultDetails(target=target, detail=_detail(metadata), path=None),
    )


def _unknown(reason: str, metadata: Mapping[str, JsonValue] | None = None) -> tuple[CheckResult, ...]:
    detail: dict[str, JsonValue] = {"coverage": _TARGET, **(metadata or {})}
    detail.update(state="unknown", reason=reason)
    return (_check("warn", "Current-process restart-pending state is unknown.", _TARGET, detail),)


def _scope(scope: ConfigScopeRef) -> str:
    return f"{scope.level.value}:{scope.scope_id}"


def _valid_host(host: object, instance_scope_id: UUID | None) -> bool:
    """A captured host chain is rooted at a host, or at the process's own instance (``ProcessConfig``)."""
    if host is None:
        return True
    if not isinstance(host, ConfigScopeRef) or not isinstance(cast("object", host.scope_id), UUID):
        return False
    if host.level is Level.HOST:
        return True
    return (
        host.level is Level.INSTANCE and instance_scope_id is not None and host.scope_id == instance_scope_id
    )


def _valid_pending(item: object, instance: ConfigScopeRef, host: ConfigScopeRef | None) -> bool:
    """Only the instance work chain and the captured host chain belong to the current process."""
    if not isinstance(item, PendingRestart):
        return False
    key, severity = cast("object", item.key), cast("object", item.severity)
    if not isinstance(key, str) or not key or not isinstance(severity, Severity):
        return False
    if not isinstance(cast("object", item.target), ConfigScopeRef):
        return False
    if item.chain is Chain.WORK:
        return item.target == instance
    return item.chain is Chain.HOST and host is not None and item.target == host


def _metadata(observation: object) -> tuple[str, dict[str, JsonValue], ConfigScopeRef | None] | None:
    """State, identity metadata and captured host of a well-typed observation; ``None`` otherwise.

    The gateway is a process-local adapter: its output is checked, not trusted to match the annotations, and
    nothing of it is projected before its type is checked.
    """
    if not isinstance(observation, CurrentProcessObservation):
        return None
    state = cast("object", observation.state)
    scope_id = cast("object", observation.instance_scope_id)
    host = cast("object", observation.host_target)
    generation = cast("object", observation.process_generation)
    if (
        not isinstance(state, str)
        or state not in _STATES
        or (scope_id is not None and not isinstance(scope_id, UUID))
        or (generation is not None and (type(generation) is not int or generation < 0))
        or not _valid_host(host, scope_id)
    ):
        return None
    captured = cast("ConfigScopeRef | None", host)
    metadata: dict[str, JsonValue] = {
        "coverage": _TARGET,
        "instance_scope_id": None if scope_id is None else str(scope_id),
        "host": None if captured is None else _scope(captured),
        "process_generation": generation,
    }
    return state, metadata, captured


def _project(observation: object, instance: ScopeRecord) -> tuple[CheckResult, ...]:
    checked = _metadata(observation)
    if checked is None:
        return _unknown("observation_invalid")
    state, metadata, captured = checked
    observation = cast("CurrentProcessObservation", observation)
    if state != "observed":
        return _unknown(state, metadata)
    if metadata["process_generation"] is None:
        return _unknown("observation_invalid", metadata)
    if observation.instance_scope_id != instance.id:
        return _unknown("instance_mismatch", metadata)
    work = ConfigScopeRef(Level.INSTANCE, instance.id)
    items = cast("object", observation.pending)
    if not isinstance(items, tuple) or not all(
        _valid_pending(item, work, captured) for item in cast("tuple[object, ...]", items)
    ):
        return _unknown("observation_invalid", metadata)
    if not items:
        message = "No restart-pending configuration in the current process's captured chains."
        return (_check("ok", message, _TARGET, {**metadata, "state": "observed"}),)
    pending = sorted(
        {
            (item.chain.value, _scope(item.target), item.key[:200], item.severity.value)
            for item in cast("tuple[PendingRestart, ...]", items)
        }
    )
    return tuple(
        _check(
            CHECK_STATUS[Severity(severity)],
            "A configured value is pending restart of the current process.",
            target,
            {
                **metadata,
                "state": "observed",
                "code": "CONFIG_RESTART_PENDING",
                "chain": chain,
                "key": key,
                "severity": severity,
            },
            hint="Restart this process after validating the configured state.",
        )
        for chain, target, key, severity in pending
    )


def _restart_checks(
    ctx: QueryContext,
    runner: DoctorRunner | None,
    store: ConfigStore,
    scopes: ScopeTree,
    instance: ScopeRecord,
) -> tuple[CheckResult, ...]:
    if runner is None:
        return _unknown("observer_unavailable")
    try:
        observation = runner.observe(store, scopes)
    except Exception as exc:  # noqa: BLE001 - a diagnostic reports, it does not fail; no error text leaks
        ctx.log.warning("doctor.process_observation_failed", error_type=type(exc).__name__)
        return _unknown("observation_failed")
    return _project(observation, instance)


def _registered_ids(ctx: QueryContext, runner: DoctorRunner | None) -> tuple[frozenset[str], str | None]:
    """The registered catalog, or an empty one and why it is unknown; never an inferred empty catalog."""
    if runner is None:
        return frozenset(), "runner_unavailable"
    try:
        ids = cast("object", runner.check_ids())
    except Exception as exc:  # noqa: BLE001 - a diagnostic reports, it does not fail; no error text leaks
        ctx.log.warning("doctor.check_catalog_failed", error_type=type(exc).__name__)
        return frozenset(), "catalog_failed"
    if not isinstance(ids, frozenset | set) or not all(
        isinstance(check_id, str) and check_id and check_id not in CHECK_IDS
        for check_id in cast("frozenset[object]", ids)
    ):
        return frozenset(), "catalog_invalid"
    return frozenset(cast("frozenset[str]", ids)), None


def _coverage_unknown(reason: str) -> CheckResult:
    return CheckResult(
        id=REGISTERED_CHECKS,
        status="warn",
        message="Registered doctor checks are unknown: their catalog could not be read.",
        hint=None,
        details=CheckResultDetails(
            target="doctor", detail=_detail({"reason": reason, "state": "unknown"}), path=None
        ),
    )


def _registered_warn(check_id: str, reason: str, message: str = "Doctor check could not run.") -> CheckResult:
    return CheckResult(
        id=check_id,
        status="warn",
        message=message,
        hint=None,
        details=CheckResultDetails(target="doctor", detail=_detail({"reason": reason}), path=None),
    )


def _runner_failed(check_ids: frozenset[str]) -> tuple[CheckResult, ...]:
    return tuple(_registered_warn(check_id, "runner_failed") for check_id in sorted(check_ids))


def _optional_text(value: object) -> bool:
    return value is None or isinstance(value, str)


def _valid_finding(item: object) -> bool:
    """The runtime shape the result encoder needs; the generated dataclass does not check its fields."""
    if not isinstance(item, CheckResult):
        return False
    check_id, status, message = (
        cast("object", item.id),
        cast("object", item.status),
        cast("object", item.message),
    )
    details = cast("object", item.details)
    if not isinstance(details, CheckResultDetails):
        return False
    target, text = cast("object", details.target), cast("object", details.detail)
    return (
        isinstance(check_id, str)
        and bool(check_id)
        and isinstance(status, str)
        and status in CHECK_STATUS.values()
        and isinstance(message, str)
        and _optional_text(cast("object", item.hint))
        and isinstance(target, str)
        and isinstance(text, str)
        and _optional_text(cast("object", details.path))
    )


def _report_checks(report: RegisteredCheckReport, foreign: frozenset[str]) -> tuple[CheckResult, ...]:
    """All findings of one collected check, or one ``warn`` under its registered id.

    A finding may carry its own id, but never one of this handler's ids or of another registered check
    (``foreign``): such a report is impersonation, not a finding of its owner, and none of it is returned.
    """
    check_id, state, findings = report.check_id, cast("object", report.state), cast("object", report.findings)
    if state != "collected" or not isinstance(findings, tuple):
        return (_registered_warn(check_id, "check_failed"),)
    items = cast("tuple[object, ...]", findings)
    if not all(_valid_finding(item) for item in items):
        return (_registered_warn(check_id, "check_failed"),)
    checks = cast("tuple[CheckResult, ...]", items)
    if any(check.id in CHECK_IDS or check.id in foreign for check in checks):
        return (_registered_warn(check_id, "reserved_check_id"),)
    return checks


def _registered_checks(
    ctx: QueryContext, runner: DoctorRunner, registered: frozenset[str], selected: frozenset[str] | None
) -> tuple[CheckResult, ...]:
    """Recorded findings of the selected registered checks; never a silent omission, never an execution."""
    wanted = registered if selected is None else registered & selected
    try:
        reports = cast("object", runner.reports(None if selected is None else wanted))
    except Exception as exc:  # noqa: BLE001 - a diagnostic reports, it does not fail; no error text leaks
        ctx.log.warning("doctor.runner_failed", error_type=type(exc).__name__)
        return _runner_failed(wanted)
    if not isinstance(reports, tuple) or not all(
        isinstance(item, RegisteredCheckReport) for item in cast("tuple[object, ...]", reports)
    ):
        return _runner_failed(wanted)
    by_id: dict[str, RegisteredCheckReport] = {}
    for report in cast("tuple[RegisteredCheckReport, ...]", reports):
        check_id = cast("object", report.check_id)
        if not isinstance(check_id, str) or check_id not in wanted or check_id in by_id:
            return _runner_failed(wanted)
        by_id[check_id] = report
    checks: list[CheckResult] = []
    for check_id, report in by_id.items():
        checks.extend(_report_checks(report, registered - {check_id}))
    checks.extend(
        _registered_warn(check_id, "not_collected", "Doctor check has not been collected by the host doctor.")
        for check_id in sorted(wanted - by_id.keys())
    )
    return tuple(checks)


def _instance_check(uow: UnitOfWork, instance: ScopeRecord) -> CheckResult:
    version = None
    try:
        reader = uow.repo(SchemaVersionReader)
    except InternalError as error:
        if error.details.get("port") != SchemaVersionReader.__name__:
            raise
    else:
        version = max((entry.version for entry in reader.applied()), default=0)
    metadata = _detail({"instance_id": str(instance.id), "schema_version": version})
    return CheckResult(
        INSTANCE_CHECK, "ok", "Backend instance", None, CheckResultDetails("instance", metadata, None)
    )


def handle(query: Doctor, ctx: QueryContext, uow: UnitOfWork) -> DoctorResult:
    chain = ctx.scope_chain
    if len(chain) != 1 or chain[0].kind is not ScopeKind.INSTANCE:
        raise InternalError(
            ErrorCode.INTERNAL_ERROR,
            "platform.doctor is authorized at the instance scope only",
            details={"reason": "not_instance_scope"},
        )
    runner = ctx.gateways.get(DoctorRunner) if ctx.gateways.has(DoctorRunner) else None
    registered, unknown = _registered_ids(ctx, runner)
    selected = _selected(query.only, CHECK_IDS | registered, complete=unknown is None)
    store, scopes = uow.repo(ConfigStore), uow.repo(ScopeTree)
    checks: list[CheckResult] = []
    if selected is None or selected & _CONFIGURED:
        configured = diagnose_config(
            registry=ctx.config.registry,
            inventory=_inventory(uow.repo(ScopeRegistry)),
            store=store,
            scopes=scopes,
            packs=uow.repo(PackConfigSource),
        )
        # The engine's own restart finding is a placeholder; the observation of this process replaces it.
        checks.extend(
            check
            for check in configured
            if check.id != RESTART_PENDING and (selected is None or check.id in selected)
        )
    if selected is None or INSTANCE_CHECK in selected:
        checks.append(_instance_check(uow, chain[0]))
    if selected is None or RESTART_PENDING in selected:
        checks.extend(_restart_checks(ctx, runner, store, scopes, chain[0]))
    if unknown is not None and (selected is None or REGISTERED_CHECKS in selected or selected - CHECK_IDS):
        checks.append(_coverage_unknown(unknown))
    if runner is not None and registered and (selected is None or selected & registered):
        checks.extend(_registered_checks(ctx, runner, registered, selected))
    return DoctorResult(checks=tuple(checks))


DOCTOR: Final = QuerySpec(
    name="platform.doctor",
    dto=Doctor,
    result=DoctorResult,
    permission="config.read",
    scope_of=None,  # instance: inventory covers every scope
    handler=handle,
)
