"""Exports housekeeping runs in bounded batches when the module is enabled."""

from typing import override

from fakes.clock import FrozenClock
from skm.background.janitor import JanitorCommandDispatcher, PurgeNotesTask, build_janitor_tasks
from skm.kernel.actor import SYSTEM_PRINCIPAL_ID, Actor
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.modules.exports.public import PurgeNotes, PurgeNotesResult
from skm.platform.system_ids import Uuid7Generator


class _RecordingBus(JanitorCommandDispatcher):
    def __init__(self) -> None:
        self.calls = 0

    @override
    def dispatch(self, cmd: object, *, actor: Actor, meta: RequestMeta) -> PurgeNotesResult:
        assert cmd == PurgeNotes(500)
        assert actor.principal_id == SYSTEM_PRINCIPAL_ID
        assert meta.surface == Surface.BACKGROUND
        self.calls += 1
        return PurgeNotesResult(500)


def test_exports_task_runs_one_bounded_batch_and_is_module_gated() -> None:
    clock = FrozenClock()
    bus = _RecordingBus()
    task = PurgeNotesTask(bus, PurgeNotes, Uuid7Generator(clock), clock, batch_size=500)

    assert build_janitor_tasks(enabled_modules=(), exports_purge=task) == ()
    (enabled,) = build_janitor_tasks(enabled_modules=("exports",), exports_purge=task)
    assert enabled.name == "exports_purge"
    assert enabled.run() == 500
    assert bus.calls == 1
