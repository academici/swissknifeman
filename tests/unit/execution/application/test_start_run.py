"""Start admission freezes the precise preview and leaves blocked task identities in history."""

from typing import Any, cast

import pytest

from skm.kernel.errors import SkmError
from skm.kernel.json_types import JsonObject
from skm.modules.execution.generated.commands import StartRun, StartRunSelectionVariant1, ValidateForExecution
from skm.modules.execution.ports import BundleRepository, RunRepository, TaskRepository

from ._support import _shared_side as _shared_side
from ._support import side as side


def test_preview_persists_exact_request_and_start_freezes_bundle(side: Any) -> None:
    report = side.client.dispatch(ValidateForExecution(side.plan1, side.rev2))
    assert report.status in {"ready", "ready_with_advisories"}
    started = side.client.dispatch(StartRun(side.plan1, side.rev2, report.report_id, {}, "run"))
    with side.uow(readonly=True) as uow:
        run = uow.repo(RunRepository).get(started.run_id)
        bundle = uow.repo(BundleRepository).get(run.id)
        tasks = uow.repo(TaskRepository).list_for_run(run.id)
        assert run.revision_id == side.rev2
        assert bundle.resource_pins.packs
        assert bundle.work_policies is not None
        assert "@default" in bundle.work_policies
        assert {t.display_key for t in tasks} <= set(bundle.work_policies)
        assert started.task_count == len(tasks)
        assert any(t.status.value == "blocked" for t in tasks)
        import json

        from skm.modules.execution.application.commands.reconfigure_run import FIXED_KEYS
        from skm.modules.execution.domain.budget import BudgetDimension
        from skm.modules.execution.ports import BudgetRepository

        from ._support import ROOT

        schema = json.loads((ROOT / "src/skm/schemas/settings/budgets.v1.json").read_text())
        expected = {
            scope: {
                key.removeprefix("max_")
                for key in schema["properties"][scope]["properties"]
                if key.startswith("max_")
            }
            for scope in ("run", "task")
        }
        assert {
            "execution.parallel.max_units",
            *(f"budgets.{scope}.max_{dimension}" for scope, dims in expected.items() for dimension in dims),
        } == FIXED_KEYS
        accounts = [
            a
            for dimension in BudgetDimension
            for a in uow.repo(BudgetRepository).accounts_for(run.id, tasks[0].id, dimension)
        ]
        for scope in ("run", "task"):
            assert {a.dimension.value for a in accounts if a.scope == scope} == expected[scope]


def test_start_request_b_rejected_for_preview_a(side: Any) -> None:
    report = side.client.dispatch(ValidateForExecution(side.plan1, side.rev2))
    with pytest.raises(SkmError):
        side.client.dispatch(
            StartRun(
                side.plan1,
                side.rev2,
                report.report_id,
                {},
                "changed",
                selection=StartRunSelectionVariant1(task_keys=("P1.1/U1",)),
            )
        )


def test_start_needs_readiness_and_rejects_foreign_revision(side: Any) -> None:
    for cmd in (
        StartRun(side.plan1, side.rev2, None, {}, "missing"),
        StartRun(side.plan2, side.rev2, None, {}, "foreign"),
    ):
        with pytest.raises(SkmError):
            side.client.dispatch(cmd)


def test_readiness_expiry_and_changed_override_are_refused(side: Any) -> None:
    from datetime import timedelta

    report = side.client.dispatch(ValidateForExecution(side.plan1, side.rev2))
    with pytest.raises(SkmError) as caught:
        side.client.dispatch(
            StartRun(side.plan1, side.rev2, report.report_id, {"budgets.task.max_attempts": 1}, "changed")
        )
    assert caught.value.details.get("reason") == "start_request_changed"
    from ._support import context

    with side.uow(readonly=True) as uow:
        max_age = context(side, uow).config.get("execution.readiness.max_age_seconds")
    side.clock.advance(timedelta(seconds=max_age + 1))
    with pytest.raises(SkmError):
        side.client.dispatch(StartRun(side.plan1, side.rev2, report.report_id, {}, "expired"))


def test_changed_profile_stales_preview_but_keeps_existing_run_pins(side: Any) -> None:
    from contracts.extensions.harness import pack_payload
    from skm.modules.execution.application._state import load_state
    from skm.modules.execution.generated.queries import GetReadinessReport
    from skm.modules.extensions.generated.commands import SyncBuiltinPacks
    from skm.modules.extensions.ports import BuiltinPacks

    report = side.client.dispatch(ValidateForExecution(side.plan1, side.rev2))
    started = side.client.dispatch(StartRun(side.plan1, side.rev2, report.report_id, {}, "frozen"))
    with side.uow(readonly=True) as uow:
        original = uow.repo(BundleRepository).get(started.run_id)
        tasks = uow.repo(TaskRepository).list_for_run(started.run_id)
        _, workflow = load_state(uow, tasks[0].id)
    builtin = side.app.gateways.get(BuiltinPacks)
    files = {
        f.path: f.content.decode().replace('version = "1.1.0"', 'version = "1.2.0"')
        for f in builtin.current[0].files
    }
    builtin.current = (pack_payload("core", "1.2.0", files=files),)
    side.client.dispatch(SyncBuiltinPacks())
    current = side.client.ask(GetReadinessReport(report_id=report.report_id))
    assert current.effective_status == "stale"
    with pytest.raises(SkmError):
        side.client.dispatch(StartRun(side.plan1, side.rev2, report.report_id, {}, "stale"))
    with side.uow(readonly=True) as uow:
        assert uow.repo(BundleRepository).get(started.run_id) == original
        assert load_state(uow, tasks[0].id)[1] == workflow


def test_new_revision_keeps_the_existing_run_contract(side: Any) -> None:
    from contracts.execution.harness import _publish_revision

    report = side.client.dispatch(ValidateForExecution(side.plan1, side.rev2))
    started = side.client.dispatch(StartRun(side.plan1, side.rev2, report.report_id, {}, "old revision"))
    with side.uow(readonly=True) as uow:
        original = uow.repo(BundleRepository).get(started.run_id)
    from skm.modules.planning import public as planning
    from skm.modules.planning.domain.specification import to_document

    with side.uow(readonly=True) as uow:
        document = to_document(planning.get_revision_specification(uow, side.rev2))
        phases = cast("list[JsonObject]", document["phases"])
    phases[0]["title"] = "New phase title"
    newer = _publish_revision(
        side.app, side.client, side.owner, side.clock, side.plan1, {"phases": document["phases"]}, "current"
    )
    assert newer != side.rev2
    with side.uow(readonly=True) as uow:
        assert uow.repo(RunRepository).get(started.run_id).revision_id == side.rev2
        assert uow.repo(BundleRepository).get(started.run_id) == original
