"""Platform doctor registration, authorization and inventory queries."""

import json
from pathlib import Path
from typing import cast

import pytest

from skm.application_bus.platform import doctor as doctor_module
from skm.application_bus.platform.doctor import (
    CHECK_IDS,
    DOCTOR,
    RESTART_PENDING,
)
from skm.application_bus.platform.migrations import MIGRATION_STATUS
from skm.application_bus.platform.outbox import LIST_DEAD_OUTBOX
from skm.application_bus.platform.storage import VERIFY_STORAGE, StorageObjects, StorageRepair
from skm.application_bus.ports import (
    CurrentProcessObserver,
    DoctorRunner,
)
from skm.bootstrap.platform_module import PLATFORM_MANIFEST
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, InternalError, ValidationFailed
from skm.kernel.ids import ScopeId
from skm.kernel.ports_uow import Isolation
from skm.kernel.scopes import ScopeRecord, ScopeRegistry
from skm.platform.config import diagnostics
from skm.platform.config.store import ConfigStore
from skm.platform.generated.queries import Doctor
from unit.application_bus._platform_doctor_support import (
    HOST,
    INSTANCE,
    OWNER,
    PLAN,
    PROJECT,
    RESULT_URN,
    RUN,
    SECRET,
    STRANGER,
    WORKSPACE,
    _observation,
    ask,
    detail,
    make_app,
    meta,
    run_handler,
    seed,
    with_observer,
    write,
)

# ---------------------------------------------------------------------------------------------- registration


def test_platform_manifest_registers_doctor_with_its_gateway_port() -> None:
    assert PLATFORM_MANIFEST.queries == (DOCTOR, MIGRATION_STATUS, LIST_DEAD_OUTBOX, VERIFY_STORAGE)
    assert PLATFORM_MANIFEST.gateway_ports == (DoctorRunner, StorageObjects, StorageRepair)
    assert DOCTOR.name == "platform.doctor"
    assert DOCTOR.permission == "config.read"
    assert DOCTOR.scope_of is None  # instance scope
    assert DOCTOR.isolation is Isolation.REPEATABLE_READ
    assert DOCTOR.internal is False
    assert getattr(DoctorRunner, "__skm_port_kind__", None) == "control_plane_gateway"
    # the process observation is a seam beneath the runner, not a gateway of its own
    assert getattr(CurrentProcessObserver, "__skm_port_kind__", None) is None


def test_default_composition_routes_doctor_and_supplies_the_runner(tmp_path: Path) -> None:
    app, _ = make_app(tmp_path)
    assert app.bus._registry.query(Doctor) is DOCTOR
    assert app.gateways.has(DoctorRunner)
    assert app.gateways.get(DoctorRunner).check_ids() == frozenset()  # no manifest registers a check yet
    assert app.gateways.kind == "control_plane_gateway"
    assert app.doctor is not None
    assert app.doctor.ids() == frozenset()
    # the handler-facing port and its adapter serve recorded reports only: nothing there executes a check
    assert not hasattr(DoctorRunner, "run")
    assert not hasattr(app.gateways.get(DoctorRunner), "run")
    app.close()


def test_check_catalog_covers_every_engine_code() -> None:
    engine_codes = diagnostics._MESSAGES  # drift guard on the engine's private code table
    assert {f"config.{code}" for code in engine_codes} <= CHECK_IDS
    assert {"config.registry", "config.configured_state", RESTART_PENDING} <= CHECK_IDS


# ---------------------------------------------------------------------------------------------- authority


def test_denied_actor_reads_no_inventory_and_no_configuration(tmp_path: Path) -> None:
    app, log = make_app(tmp_path)
    seed(app)
    log.clear()
    with pytest.raises(Forbidden) as caught:
        ask(app, actor=STRANGER)
    assert caught.value.details["permission"] == "config.read"
    assert [entry[0] for entry in log] == ["authorize"]


def test_a_grant_below_the_instance_is_not_enough(tmp_path: Path) -> None:
    app, log = make_app(tmp_path, grants=frozenset({(OWNER.principal_id, "config.read", WORKSPACE)}))
    seed(app)
    log.clear()
    with pytest.raises(Forbidden):
        ask(app)
    assert [entry[0] for entry in log] == ["authorize"]


def test_denial_wins_over_an_invalid_selector(tmp_path: Path) -> None:
    app, log = make_app(tmp_path)
    seed(app)
    log.clear()
    with pytest.raises(Forbidden):
        ask(app, Doctor(only=("no.such.check",)), actor=STRANGER)
    assert [entry[0] for entry in log] == ["authorize"]


def test_authorization_precedes_disclosure_in_the_same_read_only_uow(tmp_path: Path) -> None:
    app, log = make_app(tmp_path)
    seed(app)
    log.clear()
    ask(app)
    assert log[0][0] == "authorize"
    _, state_id, readonly, isolation = log[0]
    assert readonly is True
    assert isolation is Isolation.REPEATABLE_READ
    assert sum(1 for entry in log if entry[0] == "authorize") == 1
    assert {entry[1] for entry in log} == {state_id}  # every read in the authorizing UoW, none nested
    assert any(entry[0] == "list_scopes" for entry in log)


def test_doctor_writes_nothing(tmp_path: Path) -> None:
    app, _ = make_app(tmp_path)
    seed(app)
    write(app, WORKSPACE, "x.unknown", 1)
    with app.uow_factory(meta(), readonly=True) as uow:
        before = uow.repo(ConfigStore).generation()
    ask(app)
    with app.uow_factory(meta(), readonly=True) as uow:
        assert uow.repo(ConfigStore).generation() == before


# ---------------------------------------------------------------------------------------------- inventory


@pytest.mark.parametrize(("limit", "pages"), [(2, [2, 2, 2, 0]), (4, [4, 2, 0]), (500, [6, 0])])
def test_inventory_reads_every_page_until_an_empty_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, limit: int, pages: list[int]
) -> None:
    monkeypatch.setattr(doctor_module, "_PAGE_LIMIT", limit)
    app, log = make_app(tmp_path)
    seed(app)
    log.clear()
    result = ask(app)
    assert [entry[3] for entry in log if entry[0] == "list_scopes"] == pages
    assert {entry[2] for entry in log if entry[0] == "list_scopes"} == {limit}
    configured = [check for check in result.checks if check.id == "config.configured_state"]
    targets = sorted((check.details.target, detail(check)["chain"]) for check in configured)
    assert targets == sorted(
        [
            (f"instance:{INSTANCE}", "work"),
            (f"instance:{INSTANCE}", "host"),
            (f"workspace:{WORKSPACE}", "work"),
            (f"project:{PROJECT}", "work"),
            (f"plan:{PLAN}", "work"),
            (f"run:{RUN}", "work"),
            (f"host:{HOST}", "host"),
        ]
    )
    assert all(check.status == "ok" for check in configured)


def test_instance_only_inventory_checks_both_instance_chains(tmp_path: Path) -> None:
    app, _ = make_app(tmp_path)
    seed(app, full=False)
    result = ask(app)
    assert result.checks[0].id == "config.registry"
    configured = [check for check in result.checks if check.id == "config.configured_state"]
    assert sorted(detail(check)["chain"] for check in configured) == ["host", "work"]


def test_result_is_deterministic(tmp_path: Path) -> None:
    app, _ = make_app(tmp_path)
    seed(app)
    write(app, PROJECT, "x.unknown", 1)
    assert ask(app) == ask(app)


@pytest.mark.parametrize("reason", ["not_ascending", "page_over_limit"])
def test_an_inconsistent_inventory_fails_closed(tmp_path: Path, reason: str) -> None:
    app, _ = make_app(tmp_path)
    seed(app)

    class Broken:
        def __init__(self, inner: ScopeRegistry) -> None:
            self.inner = inner
            self.calls = 0

        def list_scopes(self, *, after: ScopeId | None = None, limit: int = 100) -> tuple[ScopeRecord, ...]:
            self.calls += 1
            page = self.inner.list_scopes(limit=500)
            if self.calls > 1:
                return ()
            return page[::-1] if reason == "not_ascending" else page * 100

    with app.uow_factory(meta(), readonly=True) as uow:
        broken = Broken(uow.repo(ScopeRegistry))
        with pytest.raises(InternalError) as caught:
            doctor_module._inventory(cast("ScopeRegistry", broken))
    assert caught.value.details == {"reason": reason}


def test_handler_refuses_a_non_instance_chain(tmp_path: Path) -> None:
    app, _ = make_app(tmp_path)
    seed(app)
    _, gateways = with_observer()
    with pytest.raises(InternalError) as caught:
        run_handler(app, Doctor(), gateways, chain_of=WORKSPACE)
    assert caught.value.details == {"reason": "not_instance_scope"}


# ---------------------------------------------------------------------------------------------- selectors


def test_restart_only_selector_skips_the_inventory(tmp_path: Path) -> None:
    app, log = make_app(tmp_path)
    seed(app)
    log.clear()
    result = ask(app, Doctor(only=(RESTART_PENDING,)))
    assert [check.id for check in result.checks] == [RESTART_PENDING]
    assert not any(entry[0] == "list_scopes" for entry in log)


def test_configured_selector_skips_the_process_observer(tmp_path: Path) -> None:
    observer, _ = with_observer()
    app, _ = make_app(tmp_path, observer=observer)
    seed(app)
    result = ask(app, Doctor(only=("config.registry", "config.registry")))
    assert [check.id for check in result.checks] == ["config.registry"]
    assert observer.calls == []


def test_a_selected_check_without_findings_returns_no_checks(tmp_path: Path) -> None:
    app, _ = make_app(tmp_path)
    seed(app)
    assert ask(app, Doctor(only=("config.CONFIG_LOCKED",))).checks == ()


def test_empty_selection_is_schema_valid_and_selects_nothing(tmp_path: Path) -> None:
    observer, _ = with_observer(_observation())
    app, log = make_app(tmp_path, observer=observer)
    seed(app)
    app.schemas.require_valid(Doctor.SCHEMA_URN, {"only": []})
    query = Doctor.from_json({"only": []})
    assert query == Doctor(only=())
    log.clear()
    result = ask(app, query)
    assert result.checks == ()
    app.schemas.require_valid(RESULT_URN, json.loads(json.dumps(result.to_json())))
    assert log[0][0] == "authorize"
    assert not any(entry[0] == "list_scopes" for entry in log)  # no inventory, observation or check run
    assert observer.calls == []
    assert observer.asked == []


def test_omitted_and_empty_selectors_differ(tmp_path: Path) -> None:
    app, _ = make_app(tmp_path)
    seed(app)
    every = ask(app, Doctor.from_json({}))
    assert {check.id for check in every.checks} >= {"config.registry", RESTART_PENDING}
    assert ask(app, Doctor.from_json({"only": []})).checks == ()


def test_duplicate_selectors_select_once(tmp_path: Path) -> None:
    app, _ = make_app(tmp_path)
    seed(app)
    once = ask(app, Doctor(only=(RESTART_PENDING,)))
    assert ask(app, Doctor(only=(RESTART_PENDING, RESTART_PENDING))) == once


def test_unknown_selector_is_refused_without_echoing_it(tmp_path: Path) -> None:
    app, log = make_app(tmp_path)
    seed(app)
    log.clear()
    with pytest.raises(ValidationFailed) as caught:
        ask(app, Doctor(only=("config.registry", SECRET)))
    error = caught.value
    assert error.code is ErrorCode.SCHEMA_INVALID
    assert error.details["reason"] == "unknown_check_id"
    assert error.details["index"] == 1
    assert SECRET not in str(error)
    assert SECRET not in json.dumps(dict(error.details))
    assert not any(entry[0] == "list_scopes" for entry in log)
