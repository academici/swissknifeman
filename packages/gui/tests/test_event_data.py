"""gui event data: every declared event type has a schema, and the journal gate refuses data that breaks it."""
import asyncio
import io
import json
import os
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from aicore.ext import events
from aicore.ext.errors import ExtError

from gui import backend, contracts
from gui.core import broker

MODULE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = contracts.SCHEMAS / "event-data" / "v1"
UNIT = json.loads((MODULE_ROOT / "unit.json").read_text(encoding="utf-8"))
RUN = {"run_id": "run-" + "0" * 32, "command": "orch.run-status", "owner": "orch", "state": "lost"}


def dataschema(event_type: str) -> str:
    return backend.EVENT_DATA_SCHEMA.format(name=event_type.replace(".", "-"))


class Gate:
    """``GuiBackend.emit`` without a backend: only the gate and the aicore emit it calls."""

    env = {}
    emit = backend.BackendState.emit


class TestDeclaredTypes(unittest.TestCase):
    def test_every_declared_type_has_a_schema_and_no_schema_is_stray(self):
        declared = set(UNIT["provides"]["events"])
        published = {path.name[:-len(".schema.json")] for path in DATA_DIR.glob("*.schema.json")}
        self.assertEqual(declared, published)

    def test_every_run_verb_of_the_broker_is_declared(self):
        for verb in set(broker._VERBS.values()):
            with self.subTest(verb=verb):
                self.assertIn(f"gui.run.{verb}", UNIT["provides"]["events"])

    def test_every_verb_is_a_valid_event_type(self):
        for verb in set(broker._VERBS.values()):
            with self.subTest(verb=verb):
                events.build_event(f"gui.run.{verb}", source="gui")

    def test_run_data_of_every_state_fits_the_schema_of_its_verb(self):
        for state, verb in broker._VERBS.items():
            with self.subTest(state=state):
                data = {**RUN, "state": state}
                self.assertEqual([], events.validate_data(data, dataschema(f"gui.run.{verb}"), DATA_DIR))


class TestGate(unittest.TestCase):
    def test_valid_data_is_journaled_with_its_dataschema(self):
        with mock.patch("aicore.ext.events.emit") as emit:
            Gate().emit("gui.run.lost", RUN, subject=RUN["run_id"], project="/p")
        self.assertEqual(dataschema("gui.run.lost"), emit.call_args.kwargs["dataschema"])

    def test_invalid_data_is_not_journaled_and_is_reported(self):
        err = io.StringIO()
        with mock.patch("aicore.ext.events.emit") as emit, redirect_stderr(err), \
                mock.patch.dict(os.environ, {"SKM_CONTRACTS_STRICT": ""}):
            Gate().emit("gui.run.lost", {**RUN, "extra": 1}, subject=RUN["run_id"], project="/p")
        emit.assert_not_called()
        self.assertIn("GUI_EVENT_NOT_EMITTED: gui.run.lost: EVENT_DATA_INVALID:", err.getvalue())

    def test_a_wrong_state_for_the_verb_is_refused(self):
        err = io.StringIO()
        with mock.patch("aicore.ext.events.emit") as emit, redirect_stderr(err), \
                mock.patch.dict(os.environ, {"SKM_CONTRACTS_STRICT": ""}):
            Gate().emit("gui.run.lost", {**RUN, "state": "running"}, subject=RUN["run_id"], project="/p")
        emit.assert_not_called()

    def test_strict_mode_raises(self):
        with mock.patch.dict(os.environ, {"SKM_CONTRACTS_STRICT": "1"}):
            with self.assertRaises(ExtError) as caught:
                Gate().emit("gui.run.lost", {**RUN, "extra": 1}, subject=RUN["run_id"], project="/p")
        self.assertEqual("EVENT_DATA_INVALID", caught.exception.code)


BAD_OWNER = {**RUN, "owner": "INVALID"}


def real_gate(strict: str):
    """A ``Broker.emit`` / ``BackendState.start`` emitter that is the real gate over a throwaway object."""
    gate = SimpleNamespace(env={"SKM_CONTRACTS_STRICT": strict})

    def emit(type_, data, **kwargs):
        return backend.BackendState.emit(gate, type_, data, **kwargs)

    return emit


class TestCallersSeeTheStrictError(unittest.TestCase):
    """The best-effort callers of the gate must not hide ``EVENT_DATA_INVALID`` from a strict test."""

    def journal(self, strict: str, state: str = "lost"):
        run = {**BAD_OWNER, "state": state}
        instance = object.__new__(broker.Broker)
        instance.emit = real_gate(strict)
        loop = mock.Mock()
        loop.run_in_executor.side_effect = lambda executor, callback: callback()
        with mock.patch.dict(os.environ, {"SKM_CONTRACTS_STRICT": strict}), \
                mock.patch("gui.core.broker.asyncio.get_running_loop", return_value=loop), \
                mock.patch.object(broker.log, "warning") as warning, redirect_stderr(io.StringIO()):
            instance._journal(run, "/p")
        return warning

    def test_the_broker_raises_the_strict_error(self):
        with self.assertRaises(ExtError) as caught:
            self.journal("1")
        self.assertEqual("EVENT_DATA_INVALID", caught.exception.code)

    def test_the_broker_stays_best_effort_in_the_working_mode(self):
        self.assertFalse(self.journal("").called)  # the gate reports on stderr and returns; nothing is raised

    def test_the_broker_still_logs_other_journal_failures_in_strict_mode(self):
        instance = object.__new__(broker.Broker)
        instance.emit = mock.Mock(side_effect=OSError("disk full"))
        with mock.patch.dict(os.environ, {"SKM_CONTRACTS_STRICT": "1"}), \
                mock.patch.object(broker.log, "warning") as warning:
            instance._journal({**RUN, "state": "lost"}, "/p")
        self.assertTrue(warning.called)

    def test_the_config_service_raises_the_strict_error_and_hides_other_failures(self):
        from gui.core import config
        service = object.__new__(config.ConfigService)
        service._emit_machine = None
        gate = real_gate("1")
        service._emit_project = lambda type_, data, subject, root: gate(type_, data, subject=subject, project=root)
        with mock.patch.dict(os.environ, {"SKM_CONTRACTS_STRICT": "1"}):
            with self.assertRaises(ExtError):
                service._announce("INVALID", "project", "/p", ["a.b"], "rev")  # module id breaks the schema
        service._emit_project = mock.Mock(side_effect=OSError("disk full"))
        service._announce("orch", "project", "/p", ["a.b"], "rev")  # not raised

    def start(self, strict: str):
        gate = real_gate(strict)

        async def idle():
            return None

        store = mock.Mock()
        store.mark_lost.return_value = [RUN["run_id"]]
        store.get.return_value = {"context": {"project_id": "p"}, "command": RUN["command"], "owner": "INVALID"}
        stub = SimpleNamespace(
            env={"SKM_CONTRACTS_STRICT": strict}, loop=None, plugins=mock.Mock(), catalog=None, store=store,
            settings=SimpleNamespace(runs=SimpleNamespace(cancel_grace_s=1),
                                     retention=SimpleNamespace(log_days=1, log_total_mb=1)),
            registry=SimpleNamespace(resolve=lambda project_id: Path("/p")), runs_dir=Path("/nonexistent-runs"),
            emit=gate, _heartbeats=idle, _journals=idle, _terminal_timers=idle, tasks=[])

        async def run():
            with mock.patch.object(backend, "prune_logs"), redirect_stderr(io.StringIO()):
                await backend.BackendState.start(stub)
            await asyncio.gather(*stub.tasks)

        asyncio.run(run())

    def test_start_raises_the_strict_error(self):
        with mock.patch.dict(os.environ, {"SKM_CONTRACTS_STRICT": "1"}):
            with self.assertRaises(ExtError) as caught:
                self.start("1")
        self.assertEqual("EVENT_DATA_INVALID", caught.exception.code)

    def test_start_goes_on_in_the_working_mode(self):
        with mock.patch.dict(os.environ, {"SKM_CONTRACTS_STRICT": ""}):
            self.start("")


if __name__ == "__main__":
    unittest.main()
