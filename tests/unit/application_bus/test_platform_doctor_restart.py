"""Platform doctor diagnostics for the serving process and pending restarts."""

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest

from skm.application_bus.platform.doctor import (
    RESTART_PENDING,
)
from skm.application_bus.ports import (
    CurrentProcessObservation,
    PendingRestart,
)
from skm.bootstrap.doctor import ServingProcessObserver
from skm.kernel.outcomes import Severity
from skm.platform.config.keys import Chain, Level
from skm.platform.config.scopes import ScopeRef as ConfigScopeRef
from skm.platform.config.store import ConfigStore, ScopeTree
from skm.platform.generated.queries import Doctor
from unit.application_bus._platform_doctor_support import (
    HOST,
    INSTANCE,
    SECRET,
    WORKSPACE,
    NoGateways,
    SpyStore,
    _observation,
    ask,
    detail,
    make_app,
    meta,
    restart,
    run_handler,
    seed,
    start_process,
    with_observer,
    write,
)

# ------------------------------------------------------------------------------------------ current process


def test_missing_process_snapshot_is_unknown_not_healthy(tmp_path: Path) -> None:
    app, _ = make_app(tmp_path)
    seed(app)
    (check,) = restart(ask(app))
    assert check.status == "warn"
    assert check.details.target == "current_process"
    assert detail(check) == {
        "coverage": "current_process",
        "host": None,
        "instance_scope_id": None,
        "process_generation": None,
        "reason": "snapshot_missing",
        "state": "unknown",
    }


def test_engine_placeholder_is_replaced_by_the_process_observation(tmp_path: Path) -> None:
    app, _ = make_app(tmp_path)
    seed(app)
    start_process(app)
    (check,) = restart(ask(app))
    assert check.status == "ok"
    assert detail(check)["state"] == "observed"
    assert detail(check)["instance_scope_id"] == str(INSTANCE)
    assert detail(check)["host"] is None  # no host captured: no claim about any host


def test_pending_restart_of_the_work_and_captured_host_chain(tmp_path: Path) -> None:
    app, _ = make_app(tmp_path)
    seed(app)
    start_process(app, host=HOST)
    write(app, INSTANCE, "integrations.conflict_suffix", ".skm-alt")
    write(app, HOST, "policy.host.allow_unconfined", True)
    checks = restart(ask(app, Doctor(only=(RESTART_PENDING,))))
    # settings §B.7: CONFIG_RESTART_PENDING is informational; kernel-platform §5.2a: info -> ok
    assert [
        (check.status, check.details.target, detail(check)["chain"], detail(check)["key"]) for check in checks
    ] == [
        ("ok", f"host:{HOST}", "host", "policy.host.allow_unconfined"),
        ("ok", f"instance:{INSTANCE}", "work", "integrations.conflict_suffix"),
    ]
    for check in checks:
        assert detail(check)["host"] == f"host:{HOST}"
        assert detail(check)["severity"] == "info"
        assert detail(check)["code"] == "CONFIG_RESTART_PENDING"
        assert check.message == "A configured value is pending restart of the current process."
        assert check.hint is not None
        assert ".skm-alt" not in check.details.detail


def test_public_severity_matches_the_provider(tmp_path: Path) -> None:
    app, _ = make_app(tmp_path)
    seed(app)
    start_process(app, host=HOST)
    write(app, INSTANCE, "integrations.conflict_suffix", ".skm-alt")
    write(app, HOST, "policy.host.allow_unconfined", True)
    with app.uow_factory(meta(), readonly=True) as uow:
        provider = ServingProcessObserver(app.config).observe(uow.repo(ConfigStore), uow.repo(ScopeTree))
    assert sorted(check.status for check in provider.to_checks()) == ["ok", "ok"]
    assert sorted(check.status for check in restart(ask(app, Doctor(only=(RESTART_PENDING,))))) == [
        "ok",
        "ok",
    ]


def test_empty_instance_root_host_chain_is_observed(tmp_path: Path) -> None:
    app, _ = make_app(tmp_path)
    seed(app)
    start_process(app, host=INSTANCE, level=Level.INSTANCE)
    (check,) = restart(ask(app, Doctor(only=(RESTART_PENDING,))))
    assert check.status == "ok"
    assert detail(check)["state"] == "observed"
    assert detail(check)["host"] == f"instance:{INSTANCE}"


def test_pending_instance_root_host_chain_is_projected(tmp_path: Path) -> None:
    app, _ = make_app(tmp_path)
    seed(app)
    start_process(app, host=INSTANCE, level=Level.INSTANCE)
    write(app, INSTANCE, "policy.host.allow_unconfined", True)
    checks = restart(ask(app, Doctor(only=(RESTART_PENDING,))))
    assert ("ok", f"instance:{INSTANCE}", "host", "policy.host.allow_unconfined") in [
        (check.status, check.details.target, detail(check)["chain"], detail(check)["key"]) for check in checks
    ]
    assert all(detail(check)["state"] == "observed" for check in checks)


@pytest.mark.parametrize(
    ("severity", "status"), [(Severity.INFO, "ok"), (Severity.WARNING, "warn"), (Severity.ERROR, "fail")]
)
def test_pending_status_follows_the_diagnostic_severity(
    tmp_path: Path, severity: Severity, status: str
) -> None:
    observer, _ = with_observer(
        _observation(
            host_target=ConfigScopeRef(Level.HOST, HOST),
            pending=(replace(WORK_PENDING, severity=severity), replace(HOST_PENDING, severity=severity)),
        )
    )
    app, _ = make_app(tmp_path, observer=observer)
    seed(app)
    checks = restart(ask(app, Doctor(only=(RESTART_PENDING,))))
    assert [(check.status, detail(check)["chain"]) for check in checks] == [
        (status, "host"),
        (status, "work"),
    ]
    assert all(detail(check)["severity"] == severity.value for check in checks)


WORK_PENDING = PendingRestart(
    "integrations.conflict_suffix", Chain.WORK, ConfigScopeRef(Level.INSTANCE, INSTANCE)
)
WORKSPACE_PENDING = PendingRestart(
    "integrations.conflict_suffix", Chain.WORK, ConfigScopeRef(Level.WORKSPACE, WORKSPACE)
)
HOST_PENDING = PendingRestart("policy.host.allow_unconfined", Chain.HOST, ConfigScopeRef(Level.HOST, HOST))


@pytest.mark.parametrize(
    ("observation", "reason"),
    [
        (
            _observation(state="snapshot_missing", instance_scope_id=None, process_generation=None),
            "snapshot_missing",
        ),
        (_observation(state="uncommitted"), "uncommitted"),
        (_observation(state="instance_mismatch", instance_scope_id=uuid4()), "instance_mismatch"),
        (_observation(instance_scope_id=uuid4()), "instance_mismatch"),
        (_observation(process_generation=None), "observation_invalid"),
        (_observation(process_generation=-1), "observation_invalid"),
        (_observation(state="healthy"), "observation_invalid"),
        (_observation(host_target=ConfigScopeRef(Level.WORKSPACE, WORKSPACE)), "observation_invalid"),
        # another host than the captured one is never this process: no fleet claim
        (_observation(pending=(HOST_PENDING,)), "observation_invalid"),
        (_observation(pending=(WORKSPACE_PENDING,)), "observation_invalid"),
        (
            _observation(host_target=ConfigScopeRef(Level.HOST, uuid4()), pending=(HOST_PENDING,)),
            "observation_invalid",
        ),
        (_observation(pending=("integrations.conflict_suffix",)), "observation_invalid"),
        ({"state": "observed"}, "observation_invalid"),
        (None, "observation_invalid"),
        # an instance-root host chain belongs to this process's own instance only
        (_observation(host_target=ConfigScopeRef(Level.INSTANCE, uuid4())), "observation_invalid"),
        (
            _observation(
                state="uncommitted",
                instance_scope_id=None,
                host_target=ConfigScopeRef(Level.INSTANCE, INSTANCE),
            ),
            "observation_invalid",
        ),
        (
            _observation(
                host_target=ConfigScopeRef(Level.HOST, HOST),
                pending=(
                    PendingRestart(
                        "policy.host.allow_unconfined", Chain.HOST, ConfigScopeRef(Level.INSTANCE, INSTANCE)
                    ),
                ),
            ),
            "observation_invalid",
        ),
        (
            _observation(
                host_target=ConfigScopeRef(Level.INSTANCE, INSTANCE),
                pending=(HOST_PENDING,),
            ),
            "observation_invalid",
        ),
    ],
)
def test_unusable_observations_are_unknown(tmp_path: Path, observation: object, reason: str) -> None:
    app, _ = make_app(tmp_path)
    seed(app)
    _, gateways = with_observer(observation)
    (check,) = restart(run_handler(app, Doctor(only=(RESTART_PENDING,)), gateways))
    assert check.status == "warn"
    assert detail(check)["state"] == "unknown"
    assert detail(check)["reason"] == reason


def test_observer_failure_is_unknown_and_secret_free(tmp_path: Path) -> None:
    observer, _ = with_observer(error=RuntimeError(f"connection to postgresql://u:{SECRET}@db failed"))
    app, _ = make_app(tmp_path, observer=observer)
    seed(app)
    result = ask(app)
    (check,) = restart(result)
    assert detail(check)["reason"] == "observation_failed"
    assert SECRET not in json.dumps(result.to_json(), default=str)
    assert len(observer.calls) == 1


def test_absent_observer_is_unknown(tmp_path: Path) -> None:
    app, _ = make_app(tmp_path)
    seed(app)
    (check,) = restart(run_handler(app, Doctor(only=(RESTART_PENDING,)), NoGateways()))
    assert detail(check)["reason"] == "observer_unavailable"


def test_observer_reads_the_ports_of_the_request_uow(tmp_path: Path) -> None:
    observer, _ = with_observer(_observation(pending=(WORK_PENDING,)))
    app, _ = make_app(tmp_path, observer=observer)
    seed(app)
    (check,) = restart(ask(app, Doctor(only=(RESTART_PENDING,))))
    assert check.status == "ok"  # informational by default
    assert detail(check)["key"] == "integrations.conflict_suffix"
    ((store, scopes),) = observer.calls
    assert isinstance(store, SpyStore)
    assert type(scopes).__name__ == "MemoryScopeTree"


def _forged_scope(level: Level, scope_id: object) -> ConfigScopeRef:
    """A ``ScopeRef`` that bypasses its own validation, as a misbehaving gateway could return."""
    forged = object.__new__(ConfigScopeRef)
    object.__setattr__(forged, "level", level)
    object.__setattr__(forged, "scope_id", scope_id)
    object.__setattr__(forged, "label", "")
    return forged


MARKER = "SYNTHETIC-DOCTOR-MARKER"


@pytest.mark.parametrize(
    "observation",
    [
        CurrentProcessObservation(cast("Any", []), INSTANCE, None, 3),
        CurrentProcessObservation(cast("Any", {"observed"}), INSTANCE, None, 3),
        _observation(pending=None),
        _observation(pending=7),
        _observation(pending=[WORK_PENDING]),
        _observation(pending=(replace(WORK_PENDING, key=cast("Any", ["k"])),)),
        _observation(pending=(replace(WORK_PENDING, severity=cast("Any", "info")),)),
        _observation(pending=(replace(WORK_PENDING, severity=cast("Any", [])),)),
        _observation(pending=(replace(WORK_PENDING, target=cast("Any", MARKER)),)),
        _observation(pending=(replace(WORK_PENDING, chain=cast("Any", [])),)),
        _observation(process_generation=True),
        _observation(process_generation="3"),
        CurrentProcessObservation("uncommitted", cast("Any", MARKER), None, 3),
        CurrentProcessObservation("observed", cast("Any", MARKER), None, 3),
        _observation(host_target=cast("Any", MARKER)),
        _observation(host_target=_forged_scope(Level.HOST, MARKER)),
        _observation(state="uncommitted", host_target=_forged_scope(Level.HOST, MARKER)),
    ],
)
def test_malformed_observations_are_a_closed_unknown_through_the_bus(
    tmp_path: Path, observation: object
) -> None:
    observer, _ = with_observer(observation)
    app, _ = make_app(tmp_path, observer=observer)
    seed(app)
    result = ask(app, Doctor(only=(RESTART_PENDING,)))
    (check,) = result.checks
    assert check.status == "warn"
    assert (detail(check)["state"], detail(check)["reason"]) == ("unknown", "observation_invalid")
    assert MARKER not in json.dumps(result.to_json(), default=str)  # unvalidated metadata is omitted
