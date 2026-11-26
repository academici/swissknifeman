"""Two slots share full filesystem reservations and retained recovery bytes survive admission refusal."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest

from skm.bootstrap.host_services import build_host_storage
from skm.kernel.errors import BackendUnavailable
from skm.modules.execution.host.stages.base import StageCapture
from skm.modules.execution.host.worker_loop import run
from skm.platform.fs.storage_budget import StorageBudget

from ._support import make_host


def test_racing_slots_reserve_before_spawn_or_write_without_oversubscription(tmp_path):
    budget = build_host_storage(tmp_path)
    # Share the same interprocess ledger through two independently constructed budget objects.
    other = build_host_storage(tmp_path)
    budget._free_bytes = other._free_bytes = lambda _: 70_000
    roots = [tmp_path / str(i) for i in range(2)]
    for root in roots:
        root.mkdir()
    ready, refused = Barrier(2), Event()
    spawned = []

    def stage(index):
        ready.wait(timeout=10)
        ledger = (budget, other)[index]
        try:
            capture = StageCapture(roots[index], ledger, owner=f"slot:{index}", max_bytes=20000, floor=10000)
        except BackendUnavailable as error:
            refused.set()
            assert error.details["reason"] == "disk_low"  # noqa: PT017 - concurrent admission result
            return "refused"
        spawned.append(index)
        assert refused.wait(10)
        capture.write("raw.json", "{}")
        capture.close()
        return "spawned"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(stage, (0, 1))) == ["refused", "spawned"]
    assert len(spawned) == 1
    assert not tuple(roots[1 - spawned[0]].iterdir())
    assert budget.snapshot(tmp_path, min_free_bytes=10000).reserved_bytes == 0


def test_claim_and_stage_admission_include_other_roots_active_full_reservations(tmp_path, monkeypatch):
    fixture = make_host(tmp_path, monkeypatch)
    budget = fixture.services.storage
    monkeypatch.setattr(budget, "_free_bytes", lambda _: 100000)
    reservation = budget.reserve(
        fixture.services.state_dir, owner_id="other-slot", max_bytes=90000, min_free_bytes=1000
    )
    monkeypatch.setattr(
        fixture.runtime, "start", lambda _: pytest.fail("runtime spawned under disk pressure")
    )
    try:
        summary = run(fixture.ctx, fixture.request)
        assert summary["reason"] == "host_failure"
        failure = next(c for c, _ in fixture.client.calls if c["operation"] == "report_attempt_failure")
        assert failure["error_class"] == "disk_low"
        assert not any(
            c["operation"] in {"begin_stage", "record_stage_result"} for c, _ in fixture.client.calls
        )
    finally:
        reservation.close()


def test_recovery_and_operator_evidence_are_never_removed_by_age_or_disk_pressure(tmp_path, monkeypatch):
    import os

    fixture = make_host(tmp_path, monkeypatch)
    for folder in ("recovery", "operator-evidence"):
        directory = fixture.services.state_dir / folder
        directory.mkdir()
        evidence = directory / "retained.bin"
        evidence.write_bytes(b"owned pending evidence")
        os.utime(evidence, (1, 1))
    monkeypatch.setattr(fixture.services.storage, "_free_bytes", lambda _: 0)
    assert run(fixture.ctx, fixture.request)["reason"] == "disk_low"
    assert not fixture.client.calls
    assert [p.read_bytes() for p in fixture.services.state_dir.rglob("retained.bin")] == [
        b"owned pending evidence",
        b"owned pending evidence",
    ]


def test_startup_reconciliation_preserves_unknown_owners_and_settles_dead_writers(tmp_path):
    from skm.platform.fs.storage_budget import StorageOwnerIdentity

    alive: dict[int, bool | None] = {1: None}
    budget = StorageBudget(
        tmp_path / "locks",
        free_bytes=lambda _: 200000,
        identity=lambda: StorageOwnerIdentity("boot", 1, "100"),
        owner_alive=lambda owner: alive[owner.pid],
    )
    reservation = budget.reserve(tmp_path, owner_id="interrupted-stage", max_bytes=10000, min_free_bytes=1000)
    target = reservation.open_file(tmp_path / "raw.json")
    target.write(b"{}")
    assert budget.reconcile(tmp_path).unknown_owners == ("interrupted-stage",)
    alive[1] = False
    target.close()
    assert budget.reconcile(tmp_path).reserved_bytes == 0
    assert (tmp_path / "raw.json").read_bytes() == b"{}"


def test_separate_checkout_filesystem_is_admitted_before_begin_and_spawn(tmp_path, monkeypatch):
    fixture = make_host(tmp_path, monkeypatch)
    root = next(iter(fixture.environment.mounts.values())).resolve()
    monkeypatch.setattr(fixture.services.storage, "_free_bytes", lambda path: 0 if path == root else 1000000)
    monkeypatch.setattr(
        fixture.runtime, "start", lambda _: pytest.fail("spawn on a full checkout filesystem")
    )
    assert run(fixture.ctx, fixture.request)["reason"] == "host_failure"
    failure = next(c for c, _ in fixture.client.calls if c["operation"] == "report_attempt_failure")
    assert failure["error_class"] == "disk_low"
    assert not any(c["operation"] == "begin_stage" for c, _ in fixture.client.calls)


def test_owned_environment_locator_survives_restart_and_rejects_another_attempt(tmp_path, monkeypatch):
    from uuid import uuid4

    from skm.modules.execution.host.context import EnvironmentBindings

    fixture = make_host(tmp_path, monkeypatch)
    bindings = EnvironmentBindings(fixture.services, floor=0)
    bindings.remember(
        fixture.ids["attempt"], str(fixture.environment.environment_id), fixture.environment.locator
    )
    restarted = EnvironmentBindings(fixture.services, floor=0)
    assert (
        restarted.locator(fixture.ids["attempt"], str(fixture.environment.environment_id))
        == fixture.environment.locator
    )
    with pytest.raises(ValueError, match="another attempt"):
        restarted.locator(str(uuid4()), str(fixture.environment.environment_id))
