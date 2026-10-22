"""``orch.run.*`` events: data contracts, fixtures, best-effort emission, no emission from pure operations."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from aicore.ext import events as aicore_events
from aicore.ext import journal

from orch import events, schema, settings
from tests.test_cli_prepare import CliCase

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "events"
SCHEMAS = ROOT / "schemas" / "event-data" / "v1"
STARTED = {"run_id": "run-1", "submission_id": "sub-1", "attempt_id": "att-1",
           "source": {"plugin": "planner-orch", "ref": "P10.9"}, "scenario": "solo"}


def kind_of(event_type: str) -> str:
    return event_type.replace(".", "-")


def registry():
    return schema.load_registry(SCHEMAS, urn_prefix="urn:swissknifeman:orch:event-data:",
                                kinds=tuple(kind_of(t) for t in events.EVENT_TYPES))


class Contract(unittest.TestCase):
    def test_unit_declares_exactly_the_event_types_with_a_schema(self):
        unit = json.loads((ROOT / "unit.json").read_text(encoding="utf-8"))
        published = {p.name[:-len(".schema.json")] for p in SCHEMAS.glob("*.schema.json")}
        self.assertEqual(set(unit["provides"]["events"]), set(events.EVENT_TYPES))
        self.assertEqual(published, set(events.EVENT_TYPES))

    def test_every_schema_carries_the_id_of_its_type(self):
        for event_type in events.EVENT_TYPES:
            document = json.loads((SCHEMAS / f"{event_type}.schema.json").read_text(encoding="utf-8"))
            self.assertEqual(document["$id"], events.data_schema(event_type))
            self.assertFalse(document["additionalProperties"])

    def test_fixtures_are_valid_or_invalid_as_named(self):
        reg = registry()
        seen = {t: {"valid": 0, "invalid": 0} for t in events.EVENT_TYPES}
        for path in sorted(FIXTURES.glob("*/*.json")):
            event_type = path.parent.name
            with self.subTest(fixture=f"{event_type}/{path.name}"):
                document = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(aicore_events.validate_document(document), [])
                self.assertEqual(document["type"], event_type)
                self.assertEqual(document["dataschema"], events.data_schema(event_type))
                issues = schema.validate(document["data"], kind_of(event_type), reg)
                kind = "valid" if path.name.startswith("valid-") else "invalid"
                self.assertEqual(not issues, kind == "valid", [i.message for i in issues])
                seen[event_type][kind] += 1
        for event_type, counts in seen.items():
            self.assertGreaterEqual(counts["valid"], 1, event_type)
            self.assertGreaterEqual(counts["invalid"], 1, event_type)


class Emission(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / "home"
        (self.home / "skm").mkdir(parents=True)
        patcher = mock.patch.dict(os.environ, {"HOME": str(self.home), "SKM_HOME": str(self.home / "skm"),
                                               "SKM_AICORE_EVENTS__DELIVERY": "off"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def journal(self) -> Path:
        return journal.journal_path(journal.journal_dir())

    def settings(self, enabled: bool) -> settings.Settings:
        base = settings.defaults()
        return settings.Settings(**{**base.__dict__, "events_enabled": enabled})

    def test_an_enabled_emit_journals_a_valid_event_after_the_schema(self):
        events.emit("orch.run.started", STARTED, subject="run-1", settings=self.settings(True))
        stored, problems = aicore_events.read_events()
        self.assertEqual((len(stored), problems), (1, []))
        event = stored[0]
        self.assertEqual((event.type, event.subject, event.module), ("orch.run.started", "run-1", "orch"))
        self.assertEqual(event.dataschema, events.data_schema("orch.run.started"))
        self.assertEqual(schema.validate(event.data, "orch-run-started", registry()), [])

    def test_disabled_events_write_no_journal(self):
        events.emit("orch.run.started", STARTED, subject="run-1", settings=self.settings(False))
        self.assertFalse(self.journal().exists())

    def test_the_configuration_decides_without_explicit_settings(self):
        path = Path(self.tmp.name) / "off.toml"
        path.write_text('schema_version = 1\n[orch.events]\nenabled = false\n', encoding="utf-8")
        events.emit("orch.run.started", STARTED, subject="run-1", config_file=path)
        self.assertFalse(self.journal().exists())

    def test_a_failing_emit_warns_once_per_event_and_does_not_raise(self):
        import io
        from contextlib import redirect_stderr
        err = io.StringIO()
        with mock.patch.object(aicore_events, "emit", side_effect=OSError("disk full")), redirect_stderr(err):
            events.emit("orch.run.started", STARTED, subject="run-1", settings=self.settings(True))
        self.assertEqual(err.getvalue(), "ORCH_EVENT_NOT_EMITTED: orch.run.started: OSError: disk full\n")

    def test_an_unwritable_journal_reports_one_line_every_time(self):
        import io
        from contextlib import redirect_stderr
        events.emit("orch.run.started", STARTED, subject="run-1", settings=self.settings(True))
        self.journal().chmod(0o400)
        self.addCleanup(self.journal().chmod, 0o600)
        if os.access(self.journal(), os.W_OK):
            self.skipTest("the journal stays writable for this user")
        for _ in range(2):
            err = io.StringIO()
            with redirect_stderr(err):
                events.emit("orch.run.started", STARTED, subject="run-1", settings=self.settings(True))
            lines = err.getvalue().splitlines()
            self.assertEqual(len(lines), 1, lines)
            self.assertTrue(lines[0].startswith("ORCH_EVENT_NOT_EMITTED: orch.run.started: JOURNAL_IO"), lines)

    def test_a_closed_stderr_does_not_make_emit_raise(self):
        import io
        from contextlib import redirect_stderr
        closed = io.StringIO()
        closed.close()
        with mock.patch.object(aicore_events, "emit", side_effect=OSError("disk full")), redirect_stderr(closed):
            events.emit("orch.run.started", STARTED, subject="run-1", settings=self.settings(True))

    def test_data_that_breaks_its_schema_is_not_journaled_and_is_reported(self):
        import io
        from contextlib import redirect_stderr
        err = io.StringIO()
        with mock.patch.dict(os.environ, {"SKM_CONTRACTS_STRICT": ""}), redirect_stderr(err):
            result = events.emit("orch.run.started", {**STARTED, "not_a_field": 1}, subject="run-1",
                                 settings=self.settings(True))
        self.assertIsNone(result)
        self.assertFalse(self.journal().exists())
        self.assertTrue(err.getvalue().startswith("ORCH_EVENT_NOT_EMITTED: orch.run.started: EVENT_DATA_INVALID: "),
                        err.getvalue())

    def test_data_missing_a_required_field_is_not_journaled(self):
        import io
        from contextlib import redirect_stderr
        err = io.StringIO()
        with mock.patch.dict(os.environ, {"SKM_CONTRACTS_STRICT": ""}), redirect_stderr(err):
            events.emit("orch.run.started", {"run_id": "run-1"}, subject="run-1", settings=self.settings(True))
        self.assertFalse(self.journal().exists())
        self.assertIn("EVENT_DATA_INVALID", err.getvalue())

    def test_strict_mode_raises_for_data_that_breaks_its_schema(self):
        from aicore.ext.errors import ExtError
        with mock.patch.dict(os.environ, {"SKM_CONTRACTS_STRICT": "1"}):
            with self.assertRaises(ExtError) as caught:
                events.emit("orch.run.started", {**STARTED, "not_a_field": 1}, subject="run-1",
                            settings=self.settings(True))
        self.assertEqual(caught.exception.code, "EVENT_DATA_INVALID")
        self.assertFalse(self.journal().exists())

    def test_strict_mode_keeps_valid_events_and_other_failures_best_effort(self):
        import io
        from contextlib import redirect_stderr
        err = io.StringIO()
        with mock.patch.dict(os.environ, {"SKM_CONTRACTS_STRICT": "1"}), redirect_stderr(err), \
                mock.patch.object(aicore_events, "emit", side_effect=OSError("disk full")):
            events.emit("orch.run.started", STARTED, subject="run-1", settings=self.settings(True))
        self.assertIn("OSError: disk full", err.getvalue())

    def test_a_secret_in_the_data_is_refused_and_never_printed(self):
        import io
        from contextlib import redirect_stderr
        from aicore.config.secrets import Secret
        err = io.StringIO()
        with redirect_stderr(err):
            events.emit("orch.run.started", {**STARTED, "scenario": Secret("env://HUNTER2_SENTINEL", lambda: "hunter2-sentinel")}, subject="run-1",
                        settings=self.settings(True))
        self.assertIn("ORCH_EVENT_NOT_EMITTED: orch.run.started: EVENT_SECRET", err.getvalue())
        self.assertNotIn("hunter2-sentinel", err.getvalue())
        self.assertFalse(self.journal().exists())


class PureOperations(CliCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(os.environ, {"SKM_AICORE_EVENTS__DELIVERY": "off"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_dry_run_prepare_and_policy_test_emit_nothing(self):
        with mock.patch.object(events, "emit", side_effect=AssertionError("pure operation emitted")), \
                mock.patch.object(aicore_events, "emit", side_effect=AssertionError("pure operation emitted")):
            code, _, err = self.prepare()
            self.assertEqual((code, err), (0, ""))
            code, _, err = self.run_cli("policy", "test")
            self.assertEqual((code, err), (0, ""))
        self.assertFalse(journal.journal_path(journal.journal_dir()).exists())


if __name__ == "__main__":
    unittest.main()
