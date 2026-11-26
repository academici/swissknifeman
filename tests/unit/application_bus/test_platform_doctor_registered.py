"""Platform doctor collection and validation of registered checks."""

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, cast

import pytest

from skm.application_bus.platform.doctor import (
    REGISTERED_CHECKS,
    RESTART_PENDING,
)
from skm.application_bus.ports import (
    DoctorRunner,
    RegisteredCheckReport,
)
from skm.bootstrap import composition
from skm.bootstrap.composition import App
from skm.bootstrap.doctor import DoctorCheckSpec
from skm.bootstrap.platform_module import PLATFORM_MANIFEST
from skm.kernel.errors import Forbidden, ValidationFailed
from skm.kernel.generated.documents import CheckResult
from skm.modules.integrations.domain.reports import CheckResult as LocalFinding
from skm.modules.integrations.domain.target import TargetId
from skm.platform.generated.queries import Doctor
from skm.platform.generated.results import DoctorResult
from skm.platform.logging.redaction import MASK, Redactor
from unit.application_bus._platform_doctor_support import (
    INSTANCE,
    PROJECT,
    RESULT_URN,
    SECRET,
    STRANGER,
    FakeRunner,
    NoGateways,
    _observation,
    ask,
    detail,
    make_app,
    meta,
    restart,
    run_handler,
    seed,
    write,
)

# ------------------------------------------------------------------------------------------ registered checks


@dataclass
class SyntheticCheck:
    """A registered ``DoctorCheckSpec`` callback; it records its contexts and the units of work open then."""

    level: str = "warning"
    error: Exception | None = None
    finding_id: str = "review.synthetic"
    findings: list[LocalFinding] | None = None
    backend: Any = None
    contexts: list[object] = field(default_factory=list[object])
    open_units: list[int] = field(default_factory=list[int])

    def __call__(self, context: object) -> list[LocalFinding]:
        self.contexts.append(context)
        if self.backend is not None:
            self.open_units.append(self.backend.active)
        if self.error is not None:
            raise self.error
        if self.findings is not None:
            return self.findings
        return [LocalFinding(self.finding_id, TargetId.CODEX, self.level, "Synthetic", "d", None, "h")]


def registered_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *specs: DoctorCheckSpec
) -> tuple[App, list[tuple[Any, ...]]]:
    monkeypatch.setattr(composition, "PLATFORM_MANIFEST", replace(PLATFORM_MANIFEST, doctor_checks=specs))
    app, log = make_app(tmp_path)
    seed(app)
    log.clear()
    return app, log


def collect(app: App, redactor: Redactor | None = None, only: frozenset[str] | None = None) -> None:
    """The host-side collection bootstrap or the host doctor runs, outside every unit of work."""
    assert app.doctor is not None
    app.doctor.collect(redactor=redactor if redactor is not None else Redactor(), only=only)


def backend_of(app: App) -> Any:
    return cast("Any", app.uow_factory)._backend


def test_registered_checks_are_collected_host_side_and_served_by_the_query(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    check = SyntheticCheck()
    app, log = registered_app(tmp_path, monkeypatch, DoctorCheckSpec("review.synthetic", check))
    check.backend = backend_of(app)
    assert app.gateways.get(DoctorRunner).check_ids() == {"review.synthetic"}
    collect(app)
    assert check.open_units == [0]  # no unit of work was open while the check ran
    result = ask(app)
    assert len(check.contexts) == 1  # the query served the recorded report and executed nothing
    (found,) = [item for item in result.checks if item.id == "review.synthetic"]
    assert (found.status, found.message, found.hint, found.details.target) == (
        "warn",
        "Synthetic",
        "h",
        "codex",
    )
    assert {"config.registry", RESTART_PENDING} <= {item.id for item in result.checks}
    assert REGISTERED_CHECKS not in {item.id for item in result.checks}  # the catalog is known
    assert type(check.contexts[0]) is object  # bootstrap's opaque context, not the request UoW or ports
    assert log[0][0] == "authorize"
    app.schemas.require_valid(RESULT_URN, json.loads(json.dumps(result.to_json(), default=str)))


def test_the_query_never_executes_a_registered_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """R1: the callback once ran under the handler's read-only UoW; its host effects survived the request."""
    marker = tmp_path / "host-effect"

    def host_check(context: object) -> list[LocalFinding]:
        marker.write_text("written by a registered check")
        raise RuntimeError(SECRET)

    app, _ = registered_app(tmp_path, monkeypatch, DoctorCheckSpec("review.host", host_check))
    for query in (Doctor(), Doctor(only=("review.host",))):
        result = ask(app, query)
        assert [(item.status, detail(item)) for item in result.checks if item.id == "review.host"] == [
            ("warn", {"reason": "not_collected"})  # unknown until collected, never healthy
        ]
        assert not marker.exists()
    assert backend_of(app).peak_active == 1  # the request's UoW only
    collect(app)
    assert marker.exists()
    (found,) = ask(app, Doctor(only=("review.host",))).checks
    assert (found.status, detail(found)) == ("warn", {"reason": "check_failed"})


def test_collection_refuses_inside_a_unit_of_work(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    check = SyntheticCheck()
    app, _ = registered_app(tmp_path, monkeypatch, DoctorCheckSpec("review.synthetic", check))
    with app.uow_factory(meta(), readonly=True), pytest.raises(RuntimeError, match="outside every unit"):
        collect(app)
    assert check.contexts == []
    (found,) = ask(app, Doctor(only=("review.synthetic",))).checks
    assert detail(found) == {"reason": "not_collected"}


def test_a_registered_check_can_be_selected_alone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    check, other = SyntheticCheck(), SyntheticCheck(finding_id="review.other")
    app, log = registered_app(
        tmp_path,
        monkeypatch,
        DoctorCheckSpec("review.synthetic", check),
        DoctorCheckSpec("review.other", other),
    )
    collect(app, only=frozenset({"review.synthetic"}))
    assert (len(check.contexts), other.contexts) == (1, [])
    result = ask(app, Doctor(only=("review.synthetic",)))
    assert [item.id for item in result.checks] == ["review.synthetic"]
    assert not any(entry[0] == "list_scopes" for entry in log)
    assert ask(app, Doctor(only=())).checks == ()
    assert [(item.id, detail(item)) for item in ask(app, Doctor(only=("review.other",))).checks] == [
        ("review.other", {"reason": "not_collected"})
    ]
    assert (len(check.contexts), other.contexts) == (1, [])
    with pytest.raises(ValueError, match="not registered"):
        collect(app, only=frozenset({"review.missing"}))


def test_unknown_selector_lists_registered_ids(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app, _ = registered_app(tmp_path, monkeypatch, DoctorCheckSpec("review.synthetic", SyntheticCheck()))
    with pytest.raises(ValidationFailed) as caught:
        ask(app, Doctor(only=("review.missing",)))
    assert caught.value.details["reason"] == "unknown_check_id"
    assert "review.synthetic" in cast("list[str]", caught.value.details["known"])


def test_a_denied_actor_runs_and_sees_no_registered_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    check = SyntheticCheck()
    app, log = registered_app(tmp_path, monkeypatch, DoctorCheckSpec("review.synthetic", check))
    with pytest.raises(Forbidden):
        ask(app, Doctor(only=("review.synthetic",)), actor=STRANGER)
    assert check.contexts == []
    collect(app)
    with pytest.raises(Forbidden) as caught:
        ask(app, Doctor(only=("review.synthetic",)), actor=STRANGER)
    assert "Synthetic" not in json.dumps(dict(caught.value.details), default=str)
    assert len(check.contexts) == 1
    assert [entry[0] for entry in log] == ["authorize", "authorize"]


@pytest.mark.parametrize("check", [SyntheticCheck(error=RuntimeError(SECRET)), SyntheticCheck(level="bogus")])
def test_a_failing_registered_check_is_a_warning_without_error_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, check: SyntheticCheck
) -> None:
    healthy = SyntheticCheck(level="info")
    app, _ = registered_app(
        tmp_path,
        monkeypatch,
        DoctorCheckSpec("review.broken", check),
        DoctorCheckSpec("review.healthy", healthy),
    )
    collect(app)
    result = ask(app, Doctor(only=("review.broken", "review.healthy")))
    assert [(item.id, item.status) for item in result.checks] == [
        ("review.broken", "warn"),
        ("review.synthetic", "ok"),
    ]
    assert detail(result.checks[0]) == {"reason": "check_failed"}
    assert SECRET not in json.dumps(result.to_json(), default=str)


def test_a_registered_check_may_not_reuse_a_handler_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        composition,
        "PLATFORM_MANIFEST",
        replace(PLATFORM_MANIFEST, doctor_checks=(DoctorCheckSpec(RESTART_PENDING, SyntheticCheck()),)),
    )
    with pytest.raises(ValidationFailed) as caught:
        make_app(tmp_path)
    assert caught.value.details == {"reason": "reserved_check_id", "check_ids": [RESTART_PENDING]}


def _local(**changes: Any) -> LocalFinding:
    return replace(LocalFinding("review.bad", TargetId.CODEX, "info", "Bad", "d", None, None), **changes)


@pytest.mark.parametrize(
    "finding",
    [
        _local(check_id=cast("Any", 7)),
        _local(check_id=""),
        _local(title=cast("Any", 7)),
        _local(hint=cast("Any", {"h": 1})),
        _local(detail=cast("Any", {"d": 1})),
        _local(target=cast("Any", "codex")),
        _local(path=cast("Any", 7)),
        _local(level=cast("Any", ["info"])),
        cast("Any", {"check_id": "review.bad"}),
    ],
)
def test_a_malformed_finding_fails_only_its_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, finding: LocalFinding
) -> None:
    """R4: a wrong runtime field once passed normalization and failed the whole query in the encoder."""
    bad = SyntheticCheck(
        findings=[_local(), finding]
    )  # a valid finding first: the check's findings are atomic
    healthy = SyntheticCheck(level="info", finding_id="review.fine")
    app, _ = registered_app(
        tmp_path,
        monkeypatch,
        DoctorCheckSpec("review.bad", bad),
        DoctorCheckSpec("review.healthy", healthy),
    )
    collect(app)
    result = ask(app, Doctor(only=("review.bad", "review.healthy")))
    assert [
        (item.id, item.status, detail(item) if item.id == "review.bad" else None) for item in result.checks
    ] == [
        ("review.bad", "warn", {"reason": "check_failed"}),
        ("review.fine", "ok", None),
    ]
    app.schemas.require_valid(RESULT_URN, json.loads(json.dumps(result.to_json())))


@pytest.mark.parametrize("claimed", [RESTART_PENDING, "config.registry", REGISTERED_CHECKS, "review.other"])
def test_findings_may_not_claim_a_platform_or_another_registered_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, claimed: str
) -> None:
    """R3: a selected check once answered for ``review.other`` and an ``ok`` restart it never observed."""
    selected = SyntheticCheck(
        findings=[_local(check_id="review.selected"), _local(check_id=claimed, title="Healthy")]
    )
    other = SyntheticCheck(finding_id="review.other")
    app, _ = registered_app(
        tmp_path,
        monkeypatch,
        DoctorCheckSpec("review.selected", selected),
        DoctorCheckSpec("review.other", other),
    )
    collect(app, only=frozenset({"review.selected"}))
    assert other.contexts == []
    result = ask(app, Doctor(only=("review.selected", "review.selected")))
    assert [(item.id, item.status, detail(item)) for item in result.checks] == [
        ("review.selected", "warn", {"reason": "reserved_check_id"})
    ]
    every = ask(app)  # omitted: nothing is appended under a platform id
    assert "Healthy" not in json.dumps(every.to_json())
    (restart_check,) = restart(every)
    assert detail(restart_check)["reason"] == "snapshot_missing"
    assert [(item.status, detail(item)) for item in every.checks if item.id == "review.other"] == [
        ("warn", {"reason": "not_collected"})
    ]


def test_a_check_returns_every_finding_under_its_own_or_a_free_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    check = SyntheticCheck(
        findings=[_local(check_id="review.multi"), _local(check_id="claude.layer_json_valid", level="error")]
    )
    app, _ = registered_app(tmp_path, monkeypatch, DoctorCheckSpec("review.multi", check))
    collect(app)
    result = ask(app, Doctor(only=("review.multi",)))
    assert [(item.id, item.status) for item in result.checks] == [
        ("review.multi", "ok"),
        ("claude.layer_json_valid", "fail"),
    ]


def test_collection_redacts_secrets_in_every_projected_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R2: a callback's secret once reached message, hint, detail and path although the Redactor knew it."""
    token = "ghp_" + "Q" * 36  # caught by the default patterns without registration
    leaky = SyntheticCheck(
        findings=[
            LocalFinding(
                "review.leaky",
                TargetId.CODEX,
                "warning",
                f"title {SECRET}",
                f"detail {SECRET} {token}",
                f"/home/{SECRET}/settings.json",
                f"hint {SECRET}",
            )
        ]
    )
    app, _ = registered_app(tmp_path, monkeypatch, DoctorCheckSpec("review.leaky", leaky))
    redactor = Redactor()
    redactor.register_secret(SECRET)
    collect(app, redactor)
    result = ask(app, Doctor(only=("review.leaky",)))
    (found,) = result.checks
    payload = json.dumps(result.to_json())
    assert SECRET not in payload
    assert token not in payload
    assert (found.id, found.status, found.details.target) == ("review.leaky", "warn", "codex")
    assert (found.message, found.hint, found.details.detail, found.details.path) == (
        f"title {MASK}",
        f"hint {MASK}",
        f"detail {MASK} {MASK}",
        f"/home/{MASK}/settings.json",
    )
    app.schemas.require_valid(RESULT_URN, json.loads(payload))


SYNTHETIC = CheckResult.from_json(
    {
        "id": "review.synthetic",
        "status": "ok",
        "message": "m",
        "hint": None,
        "details": {"target": "t", "detail": "d", "path": None},
    }
)


REPORT = RegisteredCheckReport("review.synthetic", "collected", (SYNTHETIC,))
FINE = RegisteredCheckReport("review.fine", "collected", (replace(SYNTHETIC, id="review.fine"),))
TWO = frozenset({"review.synthetic", "review.fine"})


@pytest.mark.parametrize(
    "runner",
    [
        FakeRunner(ids=frozenset({"review.synthetic"}), reports_error=RuntimeError(SECRET)),
        FakeRunner(ids=frozenset({"review.synthetic"}), recorded=[REPORT]),
        FakeRunner(ids=frozenset({"review.synthetic"}), recorded=(SYNTHETIC,)),
        FakeRunner(ids=frozenset({"review.synthetic"}), recorded=None),
        FakeRunner(ids=frozenset({"review.synthetic"}), recorded=(REPORT, REPORT)),
        FakeRunner(
            ids=frozenset({"review.synthetic"}), recorded=(replace(REPORT, check_id="review.unasked"),)
        ),
        FakeRunner(ids=frozenset({"review.synthetic"}), recorded=(replace(REPORT, check_id=cast("Any", 7)),)),
    ],
)
def test_a_failing_runner_reports_each_selected_check(tmp_path: Path, runner: FakeRunner) -> None:
    app, _ = make_app(tmp_path, observer=runner)
    seed(app)
    result = ask(app, Doctor(only=("review.synthetic",)))
    assert [(item.id, item.status, detail(item)) for item in result.checks] == [
        ("review.synthetic", "warn", {"reason": "runner_failed"})
    ]
    assert runner.asked == [frozenset({"review.synthetic"})]
    assert SECRET not in json.dumps(result.to_json(), default=str)


def _details(**changes: Any) -> CheckResult:
    return replace(SYNTHETIC, details=replace(SYNTHETIC.details, **changes))


@pytest.mark.parametrize(
    ("report", "reason"),
    [
        (replace(REPORT, state="failed", findings=()), "check_failed"),
        (replace(REPORT, state=cast("Any", "ok")), "check_failed"),
        (replace(REPORT, findings=cast("Any", [SYNTHETIC])), "check_failed"),
        (replace(REPORT, findings=cast("Any", (SYNTHETIC.to_json(),))), "check_failed"),
        (replace(REPORT, findings=(replace(SYNTHETIC, id=cast("Any", 7)),)), "check_failed"),
        (replace(REPORT, findings=(replace(SYNTHETIC, id=""),)), "check_failed"),
        (replace(REPORT, findings=(replace(SYNTHETIC, status=cast("Any", "healthy")),)), "check_failed"),
        (replace(REPORT, findings=(replace(SYNTHETIC, message=cast("Any", 7)),)), "check_failed"),
        (replace(REPORT, findings=(replace(SYNTHETIC, hint=cast("Any", {})),)), "check_failed"),
        (replace(REPORT, findings=(replace(SYNTHETIC, details=cast("Any", None)),)), "check_failed"),
        (replace(REPORT, findings=(_details(target=cast("Any", 7)),)), "check_failed"),
        (replace(REPORT, findings=(_details(detail=cast("Any", {})),)), "check_failed"),
        (replace(REPORT, findings=(_details(path=cast("Any", 7)),)), "check_failed"),
        (replace(REPORT, findings=(SYNTHETIC, replace(SYNTHETIC, id=RESTART_PENDING))), "reserved_check_id"),
        (replace(REPORT, findings=(replace(SYNTHETIC, id="review.fine"),)), "reserved_check_id"),
    ],
)
def test_a_malformed_recorded_report_fails_only_its_check(
    tmp_path: Path, report: RegisteredCheckReport, reason: str
) -> None:
    runner = FakeRunner(result=_observation(), ids=TWO, recorded=(report, FINE))
    app, _ = make_app(tmp_path, observer=runner)
    seed(app)
    result = ask(app, Doctor(only=("review.synthetic", "review.fine")))
    assert [(item.id, item.status) for item in result.checks] == [
        ("review.synthetic", "warn"),
        ("review.fine", "ok"),
    ]
    assert detail(result.checks[0]) == {"reason": reason}
    app.schemas.require_valid(RESULT_URN, json.loads(json.dumps(result.to_json())))


def test_the_runner_gets_none_when_nothing_is_selected(tmp_path: Path) -> None:
    runner = FakeRunner(result=_observation(), ids=frozenset({"review.synthetic"}), recorded=(REPORT,))
    app, _ = make_app(tmp_path, observer=runner)
    seed(app)
    result = ask(app)
    assert result.checks[-1] == SYNTHETIC
    assert runner.asked == [None]


def test_a_registered_check_without_a_report_is_not_collected(tmp_path: Path) -> None:
    runner = FakeRunner(result=_observation(), ids=TWO, recorded=(FINE,))
    app, _ = make_app(tmp_path, observer=runner)
    seed(app)
    result = ask(app, Doctor(only=("review.synthetic", "review.fine")))
    assert [(item.id, item.status) for item in result.checks] == [
        ("review.fine", "ok"),
        ("review.synthetic", "warn"),
    ]
    assert detail(result.checks[1]) == {"reason": "not_collected"}
    assert result.checks[1].message == "Doctor check has not been collected by the host doctor."


@pytest.mark.parametrize(
    ("ids", "reason"),
    [
        (RuntimeError(SECRET), "catalog_failed"),
        (["review.synthetic"], "catalog_invalid"),
        (frozenset({7}), "catalog_invalid"),
        (frozenset({"review.synthetic", 7}), "catalog_invalid"),
        (frozenset({""}), "catalog_invalid"),
        (frozenset({RESTART_PENDING}), "catalog_invalid"),
    ],
)
def test_an_unusable_catalog_is_unknown_coverage_not_health(tmp_path: Path, ids: object, reason: str) -> None:
    """R6: a failed catalog once yielded only healthy platform findings and refused a registered selector."""
    runner = FakeRunner(result=_observation(), ids=ids, recorded=(REPORT,))
    app, _ = make_app(tmp_path, observer=runner)
    seed(app)
    result = ask(app)
    assert runner.asked == []
    coverage = [(item.status, detail(item)) for item in result.checks if item.id == REGISTERED_CHECKS]
    assert coverage == [("warn", {"reason": reason, "state": "unknown"})]
    assert "review.synthetic" not in {item.id for item in result.checks}
    for only in (("review.synthetic",), (SECRET,), (REGISTERED_CHECKS,)):
        selected = ask(app, Doctor(only=only))  # not provably unknown: coverage, not SCHEMA_INVALID
        assert [(item.id, item.status, detail(item)) for item in selected.checks] == [
            (REGISTERED_CHECKS, "warn", {"reason": reason, "state": "unknown"})
        ]
        assert SECRET not in json.dumps(selected.to_json())
    assert [item.id for item in ask(app, Doctor(only=(RESTART_PENDING,))).checks] == [RESTART_PENDING]
    assert SECRET not in json.dumps(result.to_json())


def test_a_readable_catalog_has_no_coverage_finding(tmp_path: Path) -> None:
    app, _ = make_app(tmp_path)
    seed(app)
    assert REGISTERED_CHECKS not in {item.id for item in ask(app).checks}
    assert ask(app, Doctor(only=(REGISTERED_CHECKS,))).checks == ()
    with pytest.raises(ValidationFailed):
        ask(app, Doctor(only=("review.synthetic",)))


def test_an_absent_gateway_leaves_registered_coverage_unknown(tmp_path: Path) -> None:
    app, _ = make_app(tmp_path)
    seed(app)
    result = run_handler(app, Doctor(), NoGateways())
    assert [(item.status, detail(item)) for item in result.checks if item.id == REGISTERED_CHECKS] == [
        ("warn", {"reason": "runner_unavailable", "state": "unknown"})
    ]


# ---------------------------------------------------------------------------------------------- secrecy, DTO


def test_configured_findings_never_carry_values(tmp_path: Path) -> None:
    app, _ = make_app(tmp_path)
    seed(app)
    write(app, INSTANCE, "integrations.conflict_suffix", SECRET)  # breaks the key's pattern
    write(app, PROJECT, "x.secret_token", SECRET)
    result = ask(app)
    ids = {check.id: check.status for check in result.checks}
    assert ids["config.CONFIG_INVALID"] == "fail"
    assert ids["config.CONFIG_UNKNOWN_KEY"] == "warn"
    assert SECRET not in json.dumps(result.to_json(), default=str)


def test_result_roundtrips_and_matches_its_schema(tmp_path: Path) -> None:
    app, _ = make_app(tmp_path)
    seed(app)
    write(app, PROJECT, "x.unknown", 1)
    result = ask(app)
    payload = json.loads(json.dumps(result.to_json(), default=str))
    app.schemas.require_valid(RESULT_URN, payload)
    assert DoctorResult.from_json(payload) == result
    query = Doctor(only=(RESTART_PENDING,))
    assert Doctor.from_json(query.to_json()) == query
    assert Doctor.from_json({}) == Doctor()
