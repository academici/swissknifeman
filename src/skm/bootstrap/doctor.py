"""Doctor registration, normalization and host-side collection (kernel-platform §5.2a).

DoctorContext is opaque until the host doctor's implementation. Local findings (integrations §5.6) are
normalized into ``urn:skm:kernel:check-result:v1``; the registry runs existing checks and is no engine.
``DoctorCheckCollector`` is the only caller of the registered checks: bootstrap or the host doctor runs it
outside every unit of work, and bus handlers read only its recorded reports (§5.2a: bus handlers do not
execute these checks). Serving-process restart observation is separate from configured-state validation and
host checks.
"""

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import PurePath
from threading import Lock
from typing import Any, Final, Literal, cast
from uuid import UUID

from skm.application_bus.ports import RegisteredCheckReport
from skm.kernel.errors import ValidationFailed
from skm.kernel.generated.documents import CheckResult as KernelCheckResult
from skm.kernel.generated.documents import CheckResultDetails
from skm.kernel.generated.error_codes import ErrorCode
from skm.kernel.json_types import JsonObject
from skm.kernel.outcomes import CHECK_STATUS, Severity
from skm.modules.integrations.domain.reports import CheckResult
from skm.modules.integrations.domain.target import TargetId
from skm.platform.config.effective import EffectiveConfig
from skm.platform.config.keys import Chain
from skm.platform.config.loader import ConfigLoader
from skm.platform.config.scopes import ScopeRef
from skm.platform.config.store import ConfigStore, ScopeTree
from skm.platform.logging.redaction import Redactor

__all__ = [
    "DoctorCheckCollector",
    "DoctorCheckRegistry",
    "DoctorCheckSpec",
    "DoctorContext",
    "RestartPendingKey",
    "ServingProcessObservation",
    "ServingProcessObserver",
]

type DoctorContext = object

_LEVELS: Final = frozenset(Severity)


@dataclass(frozen=True, slots=True)
class DoctorCheckSpec:
    """A registered check. Its owner builds findings from facts, identifiers and paths, never secret values
    (integrations §5.6); ``DoctorCheckCollector`` redacts known secrets as a second layer only."""

    id: str
    run: Callable[[DoctorContext], Iterable[CheckResult]]


def _result(finding: CheckResult) -> KernelCheckResult:
    """§5.2a mapping of one local finding; any field of the wrong runtime type is refused here, inside the
    check's isolation, rather than by the result encoder after its siblings ran."""
    if not isinstance(cast("object", finding), CheckResult):
        raise TypeError("a doctor check yields integrations CheckResult findings")
    level, target, path = (
        cast("object", finding.level),
        cast("object", finding.target),
        cast("object", finding.path),
    )
    status = CHECK_STATUS[Severity(level)] if isinstance(level, str) and level in _LEVELS else None
    if status is None:
        raise ValueError(f"unknown doctor level {level!r}")
    if not isinstance(target, TargetId):
        raise TypeError("doctor finding target must be a TargetId")
    if path is not None and not isinstance(path, str | PurePath):
        raise TypeError("doctor finding path must be a string, a path or null")
    texts = (finding.check_id, finding.title, finding.detail)
    if not all(isinstance(cast("object", text), str) for text in texts) or not finding.check_id:
        raise TypeError("doctor finding id, title and detail must be strings and the id non-empty")
    if finding.hint is not None and not isinstance(cast("object", finding.hint), str):
        raise TypeError("doctor finding hint must be a string or null")
    return KernelCheckResult(
        id=finding.check_id,
        status=status,
        message=finding.title,
        hint=finding.hint,
        details=CheckResultDetails(
            target=str(target.value),
            detail=finding.detail,
            path=None if path is None else str(path),
        ),
    )


def _normalize(finding: CheckResult) -> JsonObject:
    return _result(finding).to_json()


def _failed(check_id: str) -> KernelCheckResult:
    """A check that raised or returned an unnormalizable finding: unknown, never healthy; no error text."""
    return KernelCheckResult(
        id=check_id,
        status="warn",
        message="Doctor check could not run.",
        hint=None,
        details=CheckResultDetails(target="doctor", detail='{"reason":"check_failed"}', path=None),
    )


class DoctorCheckRegistry:
    def __init__(self, specs: Sequence[object]) -> None:
        seen: set[str] = set()
        for spec in specs:
            if not isinstance(spec, DoctorCheckSpec) or type(spec.id) is not str or not spec.id:
                raise ValidationFailed(
                    ErrorCode.CONFIG_INVALID,
                    "doctor checks must be DoctorCheckSpec with a non-empty id",
                    details={"reason": "invalid_check_spec"},
                )
            if spec.id in seen:
                raise ValidationFailed(
                    ErrorCode.CONFIG_INVALID,
                    f"duplicate doctor check id {spec.id!r}",
                    details={"check_id": spec.id},
                )
            seen.add(spec.id)
        self._specs = cast("tuple[DoctorCheckSpec, ...]", tuple(specs))

    def ids(self) -> frozenset[str]:
        return frozenset(spec.id for spec in self._specs)

    def ordered_ids(self) -> tuple[str, ...]:
        return tuple(spec.id for spec in self._specs)

    def run(self, context: DoctorContext) -> tuple[JsonObject, ...]:
        return tuple(_normalize(f) for spec in self._specs for f in spec.run(context))

    def reports(
        self, context: DoctorContext, only: frozenset[str] | None = None
    ) -> tuple[RegisteredCheckReport, ...]:
        """One report per check in registration order, every check or those whose id is in ``only``.

        A check's findings are buffered and normalized as a whole: if it raises, or any finding has a field of
        the wrong type, the check is ``failed`` with no findings and its siblings are unaffected.
        """
        reports: list[RegisteredCheckReport] = []
        for spec in self._specs:
            if only is not None and spec.id not in only:
                continue
            try:
                findings = tuple(_result(finding) for finding in spec.run(context))
            except Exception:  # noqa: BLE001 - a diagnostic reports, it does not fail
                reports.append(RegisteredCheckReport(spec.id, "failed"))
            else:
                reports.append(RegisteredCheckReport(spec.id, "collected", findings))
        return tuple(reports)

    def run_isolated(
        self, context: DoctorContext, only: frozenset[str] | None = None
    ) -> tuple[KernelCheckResult, ...]:
        """``reports`` flattened; a failed check is one ``warn`` under its id (``reason=check_failed``)."""
        results: list[KernelCheckResult] = []
        for report in self.reports(context, only):
            results.extend(report.findings if report.state == "collected" else (_failed(report.check_id),))
        return tuple(results)


def _redacted(report: RegisteredCheckReport, redactor: Redactor) -> RegisteredCheckReport:
    """Every string of every finding through the process ``Redactor``; the §5.2a field mapping is kept."""
    try:
        findings = tuple(
            KernelCheckResult.from_json(cast("Mapping[str, Any]", redactor.document(finding.to_json())))
            for finding in report.findings
        )
    except Exception:  # noqa: BLE001 - an unredactable report is not recorded
        return RegisteredCheckReport(report.check_id, "failed")
    return replace(report, findings=findings)


class DoctorCheckCollector:
    """Host-side execution of the registered checks; the only place they run.

    ``collect`` is called by bootstrap or the host doctor outside every unit of work of this process (it
    refuses inside one): it builds the opaque ``DoctorContext``, runs the selected checks with per-check
    isolation, passes each finding through the caller's ``Redactor`` (known revealed secrets and the default
    patterns) and records one report per check, replacing that check's previous report. ``reports`` returns
    recorded reports only and never executes a check, so the ``platform.doctor`` handler performs no host
    operation under its read-only unit of work. A check that was never collected has no report.
    """

    def __init__(self, registry: DoctorCheckRegistry, *, in_unit_of_work: Callable[[], bool]) -> None:
        self._registry = registry
        self._in_unit_of_work = in_unit_of_work
        self._lock = Lock()
        self._recorded: Mapping[str, RegisteredCheckReport] = {}

    def ids(self) -> frozenset[str]:
        return self._registry.ids()

    def collect(self, *, redactor: Redactor, only: frozenset[str] | None = None) -> None:
        if self._in_unit_of_work():
            raise RuntimeError("doctor checks are collected outside every unit of work")
        if only is not None and not only <= self.ids():
            raise ValueError("only names a doctor check that is not registered")
        context: DoctorContext = object()
        collected = {
            report.check_id: _redacted(report, redactor) for report in self._registry.reports(context, only)
        }
        with self._lock:
            self._recorded = {**self._recorded, **collected}

    def reports(self, only: frozenset[str] | None = None) -> tuple[RegisteredCheckReport, ...]:
        with self._lock:
            recorded = self._recorded
        return tuple(
            recorded[check_id]
            for check_id in self._registry.ordered_ids()
            if check_id in recorded and (only is None or check_id in only)
        )


@dataclass(frozen=True, slots=True)
class RestartPendingKey:
    """Metadata of a loader restart diagnostic; no configured or captured values."""

    key: str
    chain: Chain
    target: ScopeRef
    severity: Severity = Severity.INFO  # settings §B.7: restart-pending is informational


@dataclass(frozen=True, slots=True)
class ServingProcessObservation:
    """Only the supplied serving loader's instance work chain and captured host chain.

    An empty ``pending`` proves no change only when ``state == 'observed'``. Invalid changed restart
    values also produce pending diagnostics: this observation makes no claim about configured validity.
    ``host_target is None`` means no host baseline was captured, not that other hosts were checked.
    """

    state: Literal["observed", "snapshot_missing", "instance_mismatch", "uncommitted"]
    instance_scope_id: UUID | None
    host_target: ScopeRef | None
    process_generation: int | None
    pending: tuple[RestartPendingKey, ...] = ()

    def to_checks(self) -> tuple[KernelCheckResult, ...]:
        """Fit the existing CheckResult schema; unknown coverage is explicitly a warning.

        Pending findings keep their diagnostic severity through the §5.2a mapping (``info`` → ``ok``) and
        stay visible by message and detail; they never replace an unknown state. Detail strings retain
        key, chain, scope and process generation without widening the wire schema.
        Diagnostic messages/details and effective values are deliberately not projected.
        """
        metadata = (
            f"coverage=serving_process; instance={self.instance_scope_id}; "
            f"host={_target(self.host_target)}; process_generation={self.process_generation}"
        )
        if self.state != "observed":
            return (
                KernelCheckResult(
                    id="config.restart_pending",
                    status="warn",
                    message="Serving-process restart status is unknown",
                    hint=None,
                    details=CheckResultDetails(
                        target="serving_process", detail=f"reason={self.state}; {metadata}", path=None
                    ),
                ),
            )
        if not self.pending:
            return (
                KernelCheckResult(
                    id="config.restart_pending",
                    status="ok",
                    message="No restart-pending changes in the observed serving-process chains",
                    hint=None,
                    details=CheckResultDetails(target="serving_process", detail=metadata, path=None),
                ),
            )
        return tuple(
            KernelCheckResult(
                id="config.restart_pending",
                status=CHECK_STATUS[item.severity],
                message="A configured value is pending serving-process restart",
                hint="Restart the serving process after validating the configured state.",
                details=CheckResultDetails(
                    target=_target(item.target),
                    detail=(f"CONFIG_RESTART_PENDING; key={item.key}; chain={item.chain.value}; {metadata}"),
                    path=None,
                ),
            )
            for item in self.pending
        )


class ServingProcessObserver:
    """Observe an existing serving loader through ports from the caller's read-only unit of work.

    Never starts or replaces the loader's process snapshot. There is no fleet registry, host IO, run
    bundle, secret resolution or configured-state checker here. Later handler assembly can inject this
    provider without changing bus context. A loader with no captured snapshot remains unknown.
    """

    def __init__(self, loader: ConfigLoader) -> None:
        self._loader = loader

    def observe(self, store: ConfigStore, scopes: ScopeTree) -> ServingProcessObservation:
        process = self._loader.process
        if process is None:
            return ServingProcessObservation("snapshot_missing", None, None, None)
        metadata = (process.instance_scope_id, process.host_target, process.generation)
        if process.instance_scope_id != scopes.instance_scope().scope_id:
            return ServingProcessObservation("instance_mismatch", *metadata)
        if store.pending_writes():
            return ServingProcessObservation("uncommitted", *metadata)
        work = self._loader.effective(store, scopes, None)
        pending = _pending_keys(work)
        if process.host_target is not None:
            host = self._loader.effective_host(store, scopes, process.host_target)
            pending += _pending_keys(host)
        return ServingProcessObservation("observed", *metadata, pending)


def _pending_keys(effective: EffectiveConfig) -> tuple[RestartPendingKey, ...]:
    return tuple(
        RestartPendingKey(
            diagnostic.target, effective.chain.kind, effective.chain.target, diagnostic.severity
        )
        for diagnostic in effective.diagnostics
        if diagnostic.code == "CONFIG_RESTART_PENDING" and diagnostic.target is not None
    )


def _target(scope: ScopeRef | None) -> str:
    return "not_captured" if scope is None else f"{scope.level.value}:{scope.scope_id}"
